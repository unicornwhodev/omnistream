import { existsSync, readFileSync, statSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { loadOmniStreamConfig } from "../mcp/paths.mjs";

const pluginRoot = path.resolve(import.meta.dirname, "..");
const strict = process.argv.includes("--strict");
const rows = [];

function add(name, ok, detail, required = true) {
  rows.push({ name, ok: Boolean(ok), detail: String(detail || ""), required });
}

function fileExists(value) {
  try { return Boolean(value && statSync(value).isFile()); } catch { return false; }
}

function dirExists(value) {
  try { return Boolean(value && statSync(value).isDirectory()); } catch { return false; }
}

function parseVersion(text) {
  const match = String(text || "").match(/(\d+)\.(\d+)\.(\d+)/);
  return match ? match.slice(1).map(Number) : null;
}

function atLeast(actual, expected) {
  const left = parseVersion(actual);
  const right = parseVersion(expected);
  if (!left || !right) return false;
  for (let i = 0; i < 3; i += 1) {
    if (left[i] > right[i]) return true;
    if (left[i] < right[i]) return false;
  }
  return true;
}

function commandVersion(command, args = ["--version"]) {
  // Windows batch entry points must run through cmd; direct spawning is EINVAL.
  const batch = process.platform === "win32" && command === "npm.cmd";
  const result = spawnSync(batch ? "cmd.exe" : command, batch ? ["/d", "/s", "/c", "npm --version"] : args, {
    encoding: "utf8", windowsHide: true
  });
  if (result.error || result.status !== 0) return "";
  return `${result.stdout || ""}${result.stderr || ""}`.trim();
}

function safeJson(localPath) {
  try { return JSON.parse(readFileSync(localPath, "utf8")); } catch { return null; }
}

const config = loadOmniStreamConfig();
const rawConfig = safeJson(config.paths.configFile);
const nodeVersion = process.version.replace(/^v/, "");
const npmVersion = commandVersion(process.platform === "win32" ? "npm.cmd" : "npm");
const webPackage = safeJson(path.join(pluginRoot, "web", "package.json"));
const sdkPackagePath = path.join(pluginRoot, "web", "node_modules", "@nvidia", "ov-web-rtc", "package.json");
const sdkPackage = safeJson(sdkPackagePath);
const kitRoot = config.kitRoot || "";
const releaseRoot = kitRoot ? path.join(kitRoot, "_build", "windows-x86_64", "release") : "";
const streamKit = releaseRoot && config.streamKitRelativePath ? path.resolve(releaseRoot, config.streamKitRelativePath) : "";
const streamRelative = streamKit && releaseRoot ? path.relative(releaseRoot, streamKit) : "";
const streamInsideRelease = Boolean(streamRelative && !streamRelative.startsWith("..") && !path.isAbsolute(streamRelative));

add("Plateforme Windows", process.platform === "win32", process.platform, strict);
add("Node.js >= 20.18.1", atLeast(nodeVersion, "20.18.1"), nodeVersion, true);
add("npm >= 10.2.3", atLeast(npmVersion, "10.2.3"), npmVersion || "introuvable", true);
add("Manifest Codex", fileExists(path.join(pluginRoot, ".codex-plugin", "plugin.json")), path.join(pluginRoot, ".codex-plugin", "plugin.json"), true);
add("Serveur MCP", fileExists(path.join(pluginRoot, "mcp", "server.mjs")), path.join(pluginRoot, "mcp", "server.mjs"), true);
add("Bridge OmniStream", fileExists(path.join(pluginRoot, "runtime", "bridge", "omnistream.codex.bridge", "config", "extension.toml")), "runtime/bridge/omnistream.codex.bridge", true);
add("Configuration locale", fileExists(config.paths.configFile), config.paths.configFile, strict);
if (rawConfig) {
  add("Schéma configuration v2", rawConfig.schemaVersion === 2, `schemaVersion=${String(rawConfig.schemaVersion ?? "absent")}`, strict);
  const knownKeys = new Set(["schemaVersion", "kitRoot", "workspaceRoot", "assetRoots", "streamKitRelativePath", "signalingPort", "mediaPort", "runtimeChannel"]);
  const unknownKeys = Object.keys(rawConfig).filter((key) => !knownKeys.has(key));
  add("Clés configuration connues", unknownKeys.length === 0, unknownKeys.length ? `inconnues: ${unknownKeys.join(", ")}` : "OK", strict);
  add("Canal runtime", ["Production", "Feature", "Existing"].includes(rawConfig.runtimeChannel), String(rawConfig.runtimeChannel || "absent"), strict);
}
add("OMNISTREAM_HOME", dirExists(config.paths.home), config.paths.home, strict);
add("Workspace", dirExists(config.workspaceRoot), config.workspaceRoot || "non configuré", strict);

const assetRoots = Array.isArray(config.assetRoots) ? config.assetRoots : [];
if (assetRoots.length) {
  for (const root of assetRoots) add(`Assets: ${path.basename(root) || root}`, dirExists(root), root, strict);
} else {
  add("Racine d'assets", false, "aucune racine configurée", strict);
}

add("Kit root", dirExists(kitRoot), kitRoot || "non configuré", strict);
add("kit.exe", fileExists(releaseRoot && path.join(releaseRoot, "kit", "kit.exe")), releaseRoot ? path.join(releaseRoot, "kit", "kit.exe") : "non configuré", strict);
add("Streaming .kit borné", streamInsideRelease && fileExists(streamKit), streamKit || "non configuré", strict);
add("SDK WebRTC NVIDIA local", fileExists(sdkPackagePath), sdkPackage?.version ? `@nvidia/ov-web-rtc ${sdkPackage.version}` : "non installé", strict);
if (sdkPackage && webPackage?.dependencies?.["@nvidia/ov-web-rtc"]) {
  add("Version SDK attendue", sdkPackage.version === webPackage.dependencies["@nvidia/ov-web-rtc"], `attendue ${webPackage.dependencies["@nvidia/ov-web-rtc"]}, locale ${sdkPackage.version}`, strict);
}
add("Panneau Codex construit", fileExists(path.join(pluginRoot, "mcp", "web-dist", "index.html")), "mcp/web-dist/index.html", strict);
add("Port signaling", Number.isInteger(config.signalingPort ?? 49100), String(config.signalingPort ?? 49100), strict);
add("Port media", Number.isInteger(config.mediaPort ?? 47998), String(config.mediaPort ?? 47998), strict);

const requiredFailures = rows.filter((row) => row.required && !row.ok);
const width = Math.max(...rows.map((row) => row.name.length));
for (const row of rows) {
  const status = row.ok ? "OK  " : row.required ? "FAIL" : "INFO";
  process.stdout.write(`${status}  ${row.name.padEnd(width)}  ${row.detail}\n`);
}

if (requiredFailures.length) {
  process.stderr.write(`\nDiagnostic OmniStream: ${requiredFailures.length} contrôle(s) requis en échec.\n`);
  process.exitCode = 1;
} else {
  process.stdout.write("\nDiagnostic OmniStream: contrôles requis validés.\n");
}
