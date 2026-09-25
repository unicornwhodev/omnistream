import { existsSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const pluginRoot = resolve(import.meta.dirname, "..");
const generatedDirectories = [
  resolve(pluginRoot, "mcp", "web-dist"),
  resolve(pluginRoot, "web", "dist")
];

function run(label, args, extraEnv = {}) {
  const child = spawnSync(process.execPath, args, {
    cwd: pluginRoot,
    env: { ...process.env, ...extraEnv },
    stdio: "inherit"
  });
  if (child.error) throw child.error;
  if (child.status !== 0) throw new Error(`${label} failed with exit code ${child.status ?? 1}.`);
}

let failure = null;
try {
  run("web build", ["./scripts/build-web.mjs"]);
  run("built panel MCP contract", ["./mcp/test-server.mjs"], { OMNISTREAM_EXPECT_PANEL_BUNDLE: "1" });
  run("built panel web contract", ["./web/tests/panel-contract.mjs"]);
} catch (error) {
  failure = error;
} finally {
  for (const directory of generatedDirectories) {
    if (existsSync(directory)) rmSync(directory, { recursive: true, force: true });
  }
}

if (failure) {
  process.stderr.write(`${failure instanceof Error ? failure.message : String(failure)}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write("WebRTC panel build and contracts passed; generated bundles were removed.\n");
}
