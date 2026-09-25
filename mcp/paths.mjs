import { existsSync, mkdirSync, readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

function nonEmpty(value) {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function normalizeAbsolute(value) {
  const text = nonEmpty(value);
  return text ? path.resolve(text) : "";
}

export function defaultOmniStreamHome(env = process.env) {
  const explicit = nonEmpty(env.OMNISTREAM_HOME);
  if (explicit) return path.resolve(explicit);
  if (process.platform === "win32") {
    const localAppData = nonEmpty(env.LOCALAPPDATA);
    if (localAppData) return path.join(path.resolve(localAppData), "OmniStream");
  }
  const xdgState = nonEmpty(env.XDG_STATE_HOME);
  if (xdgState) return path.join(path.resolve(xdgState), "omnistream");
  return path.join(os.homedir(), ".local", "state", "omnistream");
}

export function omniStreamPaths(env = process.env) {
  const home = defaultOmniStreamHome(env);
  return Object.freeze({
    home,
    config: path.join(home, "config"),
    configFile: path.join(home, "config", "omnistream.json"),
    logs: path.join(home, "logs"),
    state: path.join(home, "state"),
    cache: path.join(home, "cache"),
    external: path.join(home, "external")
  });
}

export function ensureOmniStreamRuntimeDirs(env = process.env) {
  const paths = omniStreamPaths(env);
  for (const directory of [paths.home, paths.config, paths.logs, paths.state, paths.cache, paths.external]) {
    mkdirSync(directory, { recursive: true });
  }
  return paths;
}

function safeInteger(value, min, max) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= min && parsed <= max ? parsed : undefined;
}

function stringArray(value) {
  return Array.isArray(value) ? value.map(nonEmpty).filter(Boolean).map(normalizeAbsolute) : [];
}

export function loadOmniStreamConfig(env = process.env) {
  const paths = omniStreamPaths(env);
  if (!existsSync(paths.configFile)) return { paths };
  try {
    const raw = JSON.parse(readFileSync(paths.configFile, "utf8"));
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return { paths };
    return {
      paths,
      kitRoot: normalizeAbsolute(raw.kitRoot),
      workspaceRoot: normalizeAbsolute(raw.workspaceRoot),
      assetRoots: stringArray(raw.assetRoots),
      streamKitRelativePath: nonEmpty(raw.streamKitRelativePath),
      signalingPort: safeInteger(raw.signalingPort, 1024, 65535),
      mediaPort: safeInteger(raw.mediaPort, 1024, 65535),
      runtimeChannel: ["Production", "Feature", "Existing"].includes(raw.runtimeChannel) ? raw.runtimeChannel : undefined
    };
  } catch {
    return { paths };
  }
}

export function envPathList(value) {
  const text = nonEmpty(value);
  if (!text) return [];
  return text.split(path.delimiter).map(nonEmpty).filter(Boolean).map(normalizeAbsolute);
}
