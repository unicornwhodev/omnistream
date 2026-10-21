import { mkdirSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
const root = path.resolve(import.meta.dirname, "..");
const output = path.join(root, "test-results", "panel-state");
mkdirSync(output, { recursive: true });
const compiled = spawnSync(process.execPath, [
  path.join(root, "web/node_modules/typescript/bin/tsc"),
  "--target", "ES2023", "--module", "ESNext", "--moduleResolution", "bundler",
  "--skipLibCheck", "--strict", "--erasableSyntaxOnly", "--noEmitOnError",
  "--outDir", output, "src/session-preparation.ts", "src/signaling-probe.ts", "src/mcp-signaling.ts",
], { cwd: path.join(root, "web"), stdio: "inherit" });
if (compiled.status !== 0) process.exit(compiled.status ?? 1);
const tests = spawnSync(process.execPath, ["--test", "./web/tests/session-preparation.test.mjs", "./web/tests/signaling-probe.test.mjs", "./web/tests/mcp-signaling.test.mjs"],
  { cwd: root, stdio: "inherit" });
process.exit(tests.status ?? 1);
