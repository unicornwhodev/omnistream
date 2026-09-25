import { existsSync, lstatSync, readdirSync, realpathSync, statSync } from "node:fs";
import path from "node:path";

export const usdExtensions = new Set([".usd", ".usda", ".usdc", ".usdz"]);
// These are only inventory labels.  A stage load remains restricted to the
// USD subset above and the configured workspace boundary.
export const assetExtensions = new Set([
  ...usdExtensions,
  ".abc", ".exr", ".fbx", ".glb", ".gltf", ".hdr", ".jpeg", ".jpg",
  ".mdl", ".obj", ".png", ".stl", ".tga", ".tif", ".tiff", ".usdz"
]);

function fail(message) {
  throw new Error(message);
}

function isInside(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative === "" || (!relative.startsWith(".." + path.sep) && relative !== ".." && !path.isAbsolute(relative));
}

function samePath(left, right) {
  // Windows paths are case-insensitive for the local Kit workflow. Strip the
  // extended-length prefix if realpath introduced one before comparing.
  const normalize = (value) => path.resolve(value).replace(/^\\\\\?\\/, "").toLocaleLowerCase("en-US");
  return normalize(left) === normalize(right);
}

function lstatExisting(target, label) {
  if (!existsSync(target)) fail(label + " does not exist: " + target + ".");
  try {
    return lstatSync(target);
  } catch {
    fail(label + " could not be inspected: " + target + ".");
  }
}

function realpathExisting(target, label) {
  try {
    return realpathSync.native(target);
  } catch {
    fail(label + " could not be resolved safely: " + target + ".");
  }
}

function assertNotReparsePoint(target, expectedRealPath, label) {
  const entry = lstatExisting(target, label);
  if (entry.isSymbolicLink()) fail(label + " must not traverse a symbolic link, junction, or reparse point.");
  const actualRealPath = realpathExisting(target, label);
  // lstat reports symlinks directly. The realpath comparison additionally
  // catches Windows junctions/reparse points represented as directories.
  if (expectedRealPath && !samePath(actualRealPath, expectedRealPath)) {
    fail(label + " must not traverse a symbolic link, junction, or reparse point.");
  }
  return { entry, realPath: actualRealPath };
}

export function validateWorkspaceRoot(value, label = "workspaceRoot") {
  if (typeof value !== "string" || !value.trim()) fail(label + " must be a non-empty path.");
  const resolved = path.resolve(value.trim());
  const checked = assertNotReparsePoint(resolved, undefined, label);
  if (!checked.entry.isDirectory()) fail(label + " does not exist or is not a directory: " + resolved + ".");
  return { resolved, realPath: checked.realPath };
}

function assertDescendantWithoutReparse(root, candidate, label) {
  const relative = path.relative(root.resolved, candidate);
  if (!isInside(root.resolved, candidate) || !relative) fail(label + " must stay below workspaceRoot.");
  let lexical = root.resolved;
  let expectedReal = root.realPath;
  for (const segment of relative.split(path.sep)) {
    lexical = path.join(lexical, segment);
    expectedReal = path.join(expectedReal, segment);
    assertNotReparsePoint(lexical, expectedReal, label);
  }
}

export function validateStagePath(workspaceRoot, stagePath) {
  if (stagePath === undefined || stagePath === null || stagePath === "") return "";
  if (typeof stagePath !== "string" || !stagePath.trim()) fail("stagePath must be a non-empty path.");
  const root = validateWorkspaceRoot(workspaceRoot);
  const candidate = path.resolve(root.resolved, stagePath.trim());
  if (!isInside(root.resolved, candidate)) fail("stagePath must stay below workspaceRoot.");
  if (!existsSync(candidate)) fail("stagePath does not exist or is not a file: " + candidate + ".");
  assertDescendantWithoutReparse(root, candidate, "stagePath");
  const finalEntry = statSync(candidate);
  if (!finalEntry.isFile()) fail("stagePath does not exist or is not a file: " + candidate + ".");
  if (!usdExtensions.has(path.extname(candidate).toLowerCase())) fail("stagePath must use .usd, .usda, .usdc, or .usdz.");
  const realCandidate = realpathExisting(candidate, "stagePath");
  if (!isInside(root.realPath, realCandidate)) fail("stagePath must stay below workspaceRoot after resolution.");
  return realCandidate;
}

function listWorkspaceFiles(workspaceRoot, extensions, { maxResults = 250, maxDepth = 8 } = {}) {
  const root = validateWorkspaceRoot(workspaceRoot);
  const entries = [];
  const walk = (current, expectedReal, depth) => {
    if (entries.length >= maxResults || depth > maxDepth) return;
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      if (entries.length >= maxResults) return;
      const fullPath = path.join(current, entry.name);
      const expectedChild = path.join(expectedReal, entry.name);
      try {
        assertNotReparsePoint(fullPath, expectedChild, "workspace entry");
      } catch {
        // Discovery is intentionally conservative: a reparse point is not a
        // stage candidate and is never traversed.
        continue;
      }
      if (entry.isDirectory()) {
        walk(fullPath, expectedChild, depth + 1);
      } else if (entry.isFile() && extensions.has(path.extname(entry.name).toLowerCase())) {
        entries.push(path.relative(root.realPath, realpathExisting(fullPath, "workspace entry")));
      }
    }
  };
  walk(root.resolved, root.realPath, 0);
  return { workspaceRoot: root.realPath, entries, capped: entries.length >= maxResults };
}

export function listWorkspaceUsdStages(workspaceRoot, options = {}) {
  const listed = listWorkspaceFiles(workspaceRoot, usdExtensions, options);
  return { workspaceRoot: listed.workspaceRoot, stages: listed.entries, capped: listed.capped };
}

export function listWorkspaceAssets(workspaceRoot, options = {}) {
  const listed = listWorkspaceFiles(workspaceRoot, assetExtensions, options);
  return { workspaceRoot: listed.workspaceRoot, assets: listed.entries, capped: listed.capped };
}
