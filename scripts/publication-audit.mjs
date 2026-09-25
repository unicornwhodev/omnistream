import { readdirSync, readFileSync, statSync, lstatSync } from "node:fs";
import { relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const pluginRoot = resolve(import.meta.dirname, "..");
const gitSafeDirectory = pluginRoot.replaceAll("\\", "/");
const forbiddenNames = new Set(["node_modules", "_build", "extscache", "__pycache__", "packman", "deps", ".pytest_cache"]);
const forbiddenDirectories = new Set([".playwright-cli", "mcp/web-dist", "web/dist", "web/node_modules", "release"]);
const personalPublicationIdentity = ["charli", "dev420"].join("-");
const copiedNvidiaSourceHeader = new RegExp([
  "SPDX-FileCopyrightText:",
  "NVIDIA CORPORATION"
].join(".*"), "i");
const forbiddenPatterns = [
  ["Windows user-profile path", /[A-Za-z]:[\\/]+Users[\\/]+/i],
  ["OneDrive workspace marker", /OneDrive[\\/]/i],
  ["machine-specific Kit installation path", /D:[\\/]+Programs/i],
  ["personal publication identity", new RegExp(personalPublicationIdentity, "i")],
  ["GitHub personal access token", /\bghp_[A-Za-z0-9]{30,}\b/],
  ["GitHub fine-grained token", /\bgithub_pat_[A-Za-z0-9_]{20,}\b/],
  ["AWS access key", /\bAKIA[0-9A-Z]{16}\b/],
  ["private key material", /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/],
  ["Slack token", /\bxox[baprs]-[A-Za-z0-9-]{10,}\b/],
  ["OpenAI-style API key", /\bsk-[A-Za-z0-9_-]{16,}\b/],
  ["copied NVIDIA source header", copiedNvidiaSourceHeader]
];
const imageExtensions = new Set([".png", ".jpg", ".jpeg", ".webp", ".gif"]);
const forbiddenExtensions = new Set([".zip", ".7z", ".tar", ".gz", ".exe", ".dll", ".pdb", ".so", ".dylib", ".lib", ".pyc", ".msi", ".whl", ".woff", ".woff2", ".ttf", ".otf"]);
const failures = [];

function gitFiles() {
  const listed = spawnSync("git", ["-c", `safe.directory=${gitSafeDirectory}`, "ls-files", "--cached", "-z"], { cwd: pluginRoot, encoding: "buffer" });
  if (listed.error || listed.status !== 0) return null;
  return listed.stdout.toString("utf8").split("\0").filter(Boolean);
}

function stagedText(localPath) {
  const shown = spawnSync("git", ["-c", `safe.directory=${gitSafeDirectory}`, "show", `:${localPath}`], { cwd: pluginRoot, encoding: "buffer" });
  if (shown.error || shown.status !== 0) throw new Error(`Could not read staged file ${localPath}.`);
  return shown.stdout.toString("utf8");
}

function filesystemFiles() {
  const files = [];
  const walk = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      if (entry.name === ".git") continue;
      const full = resolve(directory, entry.name);
      const local = relative(pluginRoot, full).replaceAll("\\", "/");
      if (entry.isSymbolicLink()) { failures.push(`${local}: symbolic link is not allowed in a release`); continue; }
      if (entry.isDirectory()) {
        if (forbiddenDirectories.has(local) || forbiddenNames.has(entry.name)) {
          failures.push(`${local}: generated, local, or third-party directory must not be published`);
          continue;
        }
        walk(full);
      } else if (entry.isFile()) files.push(local);
    }
  };
  walk(pluginRoot);
  return files;
}

function extension(localPath) {
  const index = localPath.lastIndexOf(".");
  return index >= 0 ? localPath.slice(index).toLowerCase() : "";
}

// A release audit inspects actual files, not a possibly stale Git index.
const indexed = process.argv.includes("--index") ? gitFiles() : null;
const files = indexed ?? filesystemFiles();
if (!files.length) failures.push("No source files were available to audit.");
if (indexed) {
  for (const directory of forbiddenDirectories) {
    if (files.some((file) => file === directory || file.startsWith(`${directory}/`))) failures.push(`${directory}: generated, local, or third-party directory must not be published`);
  }
}

for (const localPath of files) {
  if (localPath.split("/").some((part) => forbiddenNames.has(part)) || forbiddenExtensions.has(extension(localPath))) {
    failures.push(`${localPath}: generated, binary, archive or third-party payload is not permitted`); continue;
  }
  if (imageExtensions.has(extension(localPath))) continue;
  let content = "";
  if (indexed) {
    content = stagedText(localPath);
  } else {
    const full = resolve(pluginRoot, localPath);
    if (lstatSync(full).isSymbolicLink()) { failures.push(`${localPath}: symbolic link is not allowed`); continue; }
    if (statSync(full).size > 2 * 1024 * 1024) { failures.push(`${localPath}: oversized source requires manual review`); continue; }
    content = readFileSync(full, "utf8");
  }
  if (content.includes("\0")) { failures.push(`${localPath}: binary data hidden in a source file`); continue; }
  for (const [label, pattern] of forbiddenPatterns) {
    pattern.lastIndex = 0;
    if (pattern.test(content)) failures.push(`${localPath}: ${label}`);
  }
}

if (failures.length) {
  process.stderr.write(`Public publication audit failed:\n${[...new Set(failures)].map((failure) => `- ${failure}`).join("\n")}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write(`Public publication audit passed (${indexed ? "Git index" : "source tree"}): no forbidden generated/binary payload, symlink, machine-local path or common credential pattern found. This is not a security certification.\n`);
}
