import { cpSync, existsSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const pluginRoot = resolve(import.meta.dirname, "..");
const webRoot = resolve(pluginRoot, "web");
const webDist = resolve(webRoot, "dist");
const panelDist = resolve(pluginRoot, "mcp", "web-dist");
const isWindows = process.platform === "win32";
const npmCommand = isWindows ? "cmd.exe" : "npm";
const npmArguments = isWindows ? ["/d", "/s", "/c", "npm run build"] : ["run", "build"];

const build = spawnSync(npmCommand, npmArguments, {
  cwd: webRoot,
  env: process.env,
  stdio: "inherit"
});

if (build.error) throw build.error;
if (build.status !== 0) process.exit(build.status ?? 1);
if (!existsSync(webDist)) throw new Error(`Le build Vite n'a pas produit ${webDist}.`);

rmSync(panelDist, { recursive: true, force: true });
cpSync(webDist, panelDist, { recursive: true });
process.stdout.write(`Panneau WebRTC généré dans ${panelDist}\n`);
