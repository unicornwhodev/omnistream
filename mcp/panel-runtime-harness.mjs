import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import http from "node:http";
import { randomBytes } from "node:crypto";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const pluginRoot = path.resolve(__dirname, "..");
const webRoot = path.join(__dirname, "web-dist");
// Developer-only harness: no seeded workspace or generated stage.
// The native MCP controller uses the operator's real configuration.
const sessionToken = randomBytes(32).toString("hex");

const mcp = spawn(process.execPath, ["./mcp/server.mjs"], {
  cwd: pluginRoot,
  stdio: ["pipe", "pipe", "pipe"]
});

let lineBuffer = "";
let nextId = 0;
let cleanupPromise = null;
const pending = new Map();
const mimeTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".map", "application/json; charset=utf-8"],
  [".svg", "image/svg+xml"],
  [".woff2", "font/woff2"]
]);

mcp.stdout.setEncoding("utf8");
mcp.stdout.on("data", (chunk) => {
  lineBuffer += chunk;
  let separator;
  while ((separator = lineBuffer.indexOf("\n")) >= 0) {
    const line = lineBuffer.slice(0, separator);
    lineBuffer = lineBuffer.slice(separator + 1);
    if (!line.trim()) continue;
    let response;
    try {
      response = JSON.parse(line);
    } catch {
      continue;
    }
    const record = pending.get(response.id);
    if (!record) continue;
    clearTimeout(record.timeout);
    pending.delete(response.id);
    if (response.error) record.reject(new Error("Local MCP tool request failed."));
    else record.resolve(response.result);
  }
});

mcp.stderr.on("data", () => {
  // Keep local Kit/MCP diagnostics off the browser bridge so neither launch
  // arguments nor a session token can be reflected into the panel document.
});

function mcpRequest(method, params, timeoutMs = 60_000) {
  if (mcp.exitCode !== null || mcp.stdin.destroyed) return Promise.reject(new Error("The local MCP controller is unavailable."));
  const id = ++nextId;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      pending.delete(id);
      reject(new Error("The local MCP request exceeded its bounded harness wait."));
    }, timeoutMs);
    pending.set(id, { resolve, reject, timeout });
    mcp.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, ...(params ? { params } : {}) }) + "\n");
  });
}

function sendJson(response, statusCode, value) {
  const body = JSON.stringify(value);
  response.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store"
  });
  response.end(body);
}

function browserShim() {
  return `(() => {
  const request = async (name, args) => {
    const response = await fetch('/__codex_tool', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-OmniStream-Session': ${JSON.stringify(sessionToken)} },
      body: JSON.stringify({ name, args })
    });
    const payload = await response.json();
    if (!response.ok || payload.error) throw new Error(payload.error || 'Local Codex bridge request failed.');
    window.openai.toolResponseMetadata = payload._meta || null;
    return payload;
  };
  window.openai = { toolResponseMetadata: null, callTool: request };
})();`;
}

function safeStaticPath(urlPath) {
  const decoded = decodeURIComponent(urlPath);
  const requested = decoded === "/" ? "/index.html" : decoded;
  const candidate = path.resolve(webRoot, "." + requested);
  const relative = path.relative(webRoot, candidate);
  return relative && !relative.startsWith("..") && !path.isAbsolute(relative) ? candidate : null;
}

async function readRequestBody(request, maximumBytes = 64 * 1024) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > maximumBytes) throw new Error("request_too_large");
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8");
}

const httpServer = http.createServer(async (request, response) => {
  const address = httpServer.address();
  const authority = `127.0.0.1:${address?.port}`;
  const origin = `http://${authority}`;
  if (request.headers.host !== authority || (request.headers.origin && request.headers.origin !== origin)) {
    sendJson(response, 403, { error: "loopback_origin_required" }); return;
  }
  if (request.method === "POST" && (request.headers["x-omnistream-session"] !== sessionToken || !String(request.headers["content-type"] || "").startsWith("application/json"))) {
    sendJson(response, 403, { error: "session_authorization_required" }); return;
  }
  const url = new URL(request.url || "/", origin);
  if (url.pathname === "/__openai_shim.js" && request.method === "GET") {
    const body = browserShim();
    response.writeHead(200, { "Content-Type": "text/javascript; charset=utf-8", "Content-Length": Buffer.byteLength(body), "Cache-Control": "no-store" });
    response.end(body);
    return;
  }
  if (url.pathname === "/__shutdown" && request.method === "POST") {
    sendJson(response, 202, { accepted: true });
    void cleanup(0);
    return;
  }
  if (url.pathname === "/__codex_tool" && request.method === "POST") {
    try {
      const body = JSON.parse(await readRequestBody(request));
      if (!body || typeof body.name !== "string" || !body.name || !body.args || typeof body.args !== "object" || Array.isArray(body.args)) {
        sendJson(response, 400, { error: "invalid_tool_request" });
        return;
      }
      const result = await mcpRequest("tools/call", { name: body.name, arguments: body.args });
      sendJson(response, 200, result);
    } catch {
      sendJson(response, 502, { error: "local_tool_unavailable" });
    }
    return;
  }
  if (request.method !== "GET" && request.method !== "HEAD") {
    response.writeHead(405, { Allow: "GET, HEAD" });
    response.end();
    return;
  }
  const target = safeStaticPath(url.pathname);
  if (!target || !existsSync(target) || !statSync(target).isFile()) {
    response.writeHead(404);
    response.end();
    return;
  }
  const extension = path.extname(target).toLowerCase();
  response.setHeader("Content-Type", mimeTypes.get(extension) || "application/octet-stream");
  response.setHeader("Cache-Control", "no-store");
  if (path.basename(target) === "index.html") {
    const html = readFileSync(target, "utf8").replace("<script type=\"module\"", "<script src=\"/__openai_shim.js\"></script>\n    <script type=\"module\"");
    response.end(html);
    return;
  }
  if (request.method === "HEAD") {
    response.end();
    return;
  }
  createReadStream(target).pipe(response);
});

async function closeHttpServer() {
  if (!httpServer.listening) return;
  await new Promise((resolve) => httpServer.close(resolve));
}

async function endMcpController() {
  if (mcp.exitCode !== null) return;
  const exited = new Promise((resolve) => mcp.once("exit", resolve));
  if (!mcp.stdin.destroyed) mcp.stdin.end();
  await Promise.race([exited, new Promise((resolve) => setTimeout(resolve, 90_000))]);
}

async function cleanup(exitCode) {
  if (cleanupPromise) return cleanupPromise;
  cleanupPromise = (async () => {
    for (const entry of pending.values()) {
      clearTimeout(entry.timeout);
      entry.reject(new Error("Local panel harness is closing."));
    }
    pending.clear();
    await closeHttpServer();
    await endMcpController();
    process.exit(exitCode);
  })();
  return cleanupPromise;
}

process.once("SIGINT", () => { void cleanup(0); });
process.once("SIGTERM", () => { void cleanup(0); });
process.once("uncaughtException", () => { void cleanup(1); });

await mcpRequest("initialize", {
  protocolVersion: "2025-06-18",
  capabilities: {},
  clientInfo: { name: "panel-runtime-harness", version: "1" }
});
mcp.stdin.write(JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) + "\n");
await new Promise((resolve, reject) => {
  httpServer.once("error", reject);
  httpServer.listen(0, "127.0.0.1", () => {
    httpServer.off("error", reject);
    resolve();
  });
});
const address = httpServer.address();
if (!address || typeof address === "string") throw new Error("Local panel harness did not bind an IPv4 loopback port.");
process.stdout.write("PANEL_HARNESS_READY http://127.0.0.1:" + address.port + "/\n");
