import { existsSync, mkdirSync, readFileSync, readdirSync } from "node:fs";
import { openSync, readSync, closeSync, fstatSync } from "node:fs";
import { sceneTools, sceneRoutes, liveTool, validateSchema } from "./scene-tools.mjs";
import { LiveEventStore } from "./live-events.mjs";
import { randomBytes } from "node:crypto";
import net from "node:net";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { ControlRpcError, LoopbackControlServer } from "./control-rpc.mjs";
import { OperationClientTimeoutError, OperationInProgressError, SerialOperationQueue } from "./operation-queue.mjs";
import {
  parseLaunchedProcessIdentity,
  processIdentityMatches,
  queryProcessIdentity,
  stopProcessIfIdentityMatches
} from "./process-identity.mjs";
import {
  PrepareStopPendingError,
  StopRecoveryScheduler,
  isTransientStopError,
  prepareKitForStop
} from "./prepare-stop-retry.mjs";
import { waitForTcpStop } from "./stream-stop-wait.mjs";
import { ensureOmniStreamRuntimeDirs, envPathList, loadOmniStreamConfig } from "./paths.mjs";
import {
  listWorkspaceAssets,
  listWorkspaceUsdStages,
  validateStagePath as validateStagePathPolicy,
  validateWorkspaceRoot as validateWorkspaceRootPolicy
} from "./stage-path-policy.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const pluginRoot = path.resolve(__dirname, "..");
const manifest = JSON.parse(readFileSync(path.join(pluginRoot, ".codex-plugin", "plugin.json"), "utf8"));
const widgetUri = "ui://omnistream-for-codex/panel.html";
const widgetAccessTokenMetaKey = "omnistream/streamAccessToken";
const localConfig = loadOmniStreamConfig();
const runtimePaths = ensureOmniStreamRuntimeDirs();
const configuredKitRoot = [process.env.OMNISTREAM_KIT_ROOT, process.env.OMNIVERSE_KIT_APP_ROOT, localConfig.kitRoot]
  .find((value) => typeof value === "string" && value.trim())?.trim() || "";
const configuredWorkspaceRoot = [process.env.OMNISTREAM_WORKSPACE_ROOT, localConfig.workspaceRoot]
  .find((value) => typeof value === "string" && value.trim())?.trim() || "";
const configuredAssetRoots = [...new Set([
  ...envPathList(process.env.OMNISTREAM_ASSET_ROOTS),
  ...(localConfig.assetRoots || [])
])];
const streamKitRelativePath = process.env.OMNISTREAM_STREAM_KIT_RELATIVE_PATH?.trim() || localConfig.streamKitRelativePath || "apps/omnistream.runtime_streaming.kit";
const streamSettingsPrefix = "--/exts/omnistream_codex_bridge/";
const signalingPort = Number(process.env.OMNISTREAM_SIGNALING_PORT || localConfig.signalingPort || 49100);
const mediaPort = Number(process.env.OMNISTREAM_MEDIA_PORT || localConfig.mediaPort || 47998);
const hiddenKitLauncher = path.join(__dirname, "launch-hidden-kit.ps1");
const windowsPowerShellExe = path.join(process.env.SystemRoot || "C:\\Windows", "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
const controlMethod = Object.freeze({
  stageOpen: "stage.open",
  simulationState: "simulation.state",
  simulationConfigure: "simulation.configure",
  simulationControl: "simulation.control",
  timelineControl: "timeline.control",
  cameraList: "camera.list",
  cameraSelect: "camera.select",
  cameraNavigate: "camera.navigate",
  cameraSave: "camera.save",
  runtimePrepareStop: "runtime.prepare_stop"
});
const stageOpenRequestTimeoutMs = 65_000;
const stageOpenCompletionTimeoutMs = 120_000;
const standardMutationClientTimeoutMs = 20_000;
const standardMutationCompletionTimeoutMs = 45_000;
const cameraSaveClientTimeoutMs = 90_000;
const cameraSaveCompletionTimeoutMs = 150_000;
// A stop request must always give the MCP caller a result before its own
// request deadline.  If Kit cannot acknowledge the admission barrier quickly,
// the lifecycle code returns `stop_pending` and the retained session retries
// in the background; it never waits several minutes while holding the MCP
// response open.
const runtimePrepareStopTimeoutMs = 6_000;
const stopBridgeReconnectWaitMs = 6_000;
const stopBridgePrepareAttempts = 1;
const stopRecoveryDelayMs = 2_000;
const trackedProcessExitTimeoutMs = 10_000;
const streamStopTimeoutMs = 10_000;
// A slow, explicit camera save is allowed to finish before the lifecycle
// barrier runs.  Keep that correctness property, but do not make a Codex
// tool request wait for the save's longer completion deadline.
const stopRequestClientTimeoutMs = 30_000;
const streamStopPollMs = 250;
const timelineActions = new Set(["play", "pause", "stop", "step_forward", "step_back", "seek", "set_rate"]);
const simulationControlActions = new Set(["play", "pause", "stop", "reset", "step_forward", "step_back", "seek", "set_rate", "set_loop"]);
const cameraNavigationModes = new Set(["orbit", "pan", "dolly"]);
const streamStopPendingStates = new Set(["safe_stop_pending", "awaiting_runtime_exit", "waiting_for_signaling", "stream_stop_timeout"]);
const sensitiveKeyPattern = /(?:token|secret|credential|authorization|password)/i;
const widgetResourceMeta = {
  ui: {
    prefersBorder: true,
    csp: {
      connectDomains: [
        `http://127.0.0.1:${signalingPort}`,
        `ws://127.0.0.1:${signalingPort}`,
        `http://localhost:${signalingPort}`,
        `ws://localhost:${signalingPort}`
      ],
      resourceDomains: []
    }
  },
  "openai/widgetDescription": "Interactive Omniverse Kit viewport. The displayed pixels and input come from a hidden Kit runtime over WebRTC; the panel targets 127.0.0.1, while strict LAN isolation remains a host firewall policy.",
  "openai/widgetPrefersBorder": true
};

let runtimeSession = null;
let simulationDraft = null;
let lifecyclePhase = "stopped";
let shutdownRequested = false;
let shutdownPromise = null;
let shutdownRecoveryReported = false;
let stopRecovery = null;
let stopOperation = null;
const sideEffectQueue = new SerialOperationQueue({
  onActiveChange(operation) {
    lifecyclePhase = operation ? operation.name : (runtimeSession ? "running" : "stopped");
  }
});

class ToolError extends Error {
  constructor(message, code = "invalid_request") {
    super(message);
    this.name = "ToolError";
    this.code = code;
  }
}

function toolError(message, code) {
  return new ToolError(message, code);
}

function schema(properties, required = [], extra = {}) {
  return { type: "object", properties, required, additionalProperties: false, ...extra };
}

function tool(name, title, description, inputSchema, readOnlyHint, meta = {}, destructiveHint = false) {
  return {
    name,
    title,
    description,
    inputSchema,
    annotations: {
      readOnlyHint,
      destructiveHint,
      // A requested root layer is bounded locally, but Kit can resolve its USD
      // dependencies through the configured resolver (including external or
      // network assets). Keep the MCP declaration conservative.
      openWorldHint: true
    },
    _meta: { "openai/widgetAccessible": true, ui: { visibility: ["model", "app"] }, ...meta }
  };
}

const timelineInputSchema = schema({
  action: { type: "string", enum: [...timelineActions], description: "Session-only transport action. seek requires timeSeconds; set_rate requires rateMultiplier." },
  timeSeconds: { type: "number", minimum: 0, maximum: 1_000_000, description: "Session timeline time in seconds, used only with seek." },
  rateMultiplier: { type: "number", minimum: 0.05, maximum: 8, description: "Target frame-cadence multiplier, used only with set_rate; NOT physical time dilation." }
}, ["action"], {
  allOf: [
    { if: { properties: { action: { const: "seek" } }, required: ["action"] }, then: { required: ["timeSeconds"] } },
    { if: { properties: { action: { const: "set_rate" } }, required: ["action"] }, then: { required: ["rateMultiplier"] } }
  ]
});

const cameraNavigateInputSchema = {
  oneOf: [
    schema({
      mode: { type: "string", enum: ["orbit", "pan"], description: "Temporary orbit or pan mode." },
      horizontal: { type: "number", minimum: -1, maximum: 1, description: "Normalized horizontal delta." },
      vertical: { type: "number", minimum: -1, maximum: 1, description: "Normalized vertical delta." }
    }, ["mode", "horizontal", "vertical"]),
    schema({
      mode: { const: "dolly", description: "Temporary dolly mode." },
      amount: { type: "number", minimum: -1, maximum: 1, description: "Normalized dolly amount." }
    }, ["mode", "amount"])
  ]
};

const simulationConfigurationInputSchema = schema({
  name: { type: "string", minLength: 1, maxLength: 80, description: "Human-readable simulation name for this Codex session." },
  workspaceRoot: { type: "string", minLength: 1, description: "Existing local workspace root that bounds the simulation stage." },
  stagePath: { type: "string", minLength: 1, description: "Existing USD stage below workspaceRoot." },
  kitRoot: { type: "string", minLength: 1, description: "Optional compatible local Kit App Template root." },
  initialTimeSeconds: { type: "number", minimum: 0, maximum: 1000000, description: "Initial session time applied after the stage loads." },
  rateMultiplier: { type: "number", minimum: 0.05, maximum: 8, description: "Target frame-cadence multiplier; NOT physical time dilation." },
  loop: { type: "boolean", description: "Loop playback for the current Kit session only." },
  playEveryFrame: { type: "boolean", description: "Ask Kit to avoid frame skipping while the timeline is playing." },
  autoPlay: { type: "boolean", description: "Start timeline playback automatically after launch." },
  cameraPath: { type: "string", minLength: 2, maxLength: 1024, description: "Optional existing absolute USD camera prim path selected after stage load." }
}, ["workspaceRoot", "stagePath"]);

const simulationControlInputSchema = schema({
  action: { type: "string", enum: [...simulationControlActions], description: "Simulation session action. stop stops playback but keeps Kit running." },
  timeSeconds: { type: "number", minimum: 0, maximum: 1000000, description: "Required only for seek." },
  rateMultiplier: { type: "number", minimum: 0.05, maximum: 8, description: "Required only for set_rate." },
  loop: { type: "boolean", description: "Required only for set_loop." }
}, ["action"], {
  allOf: [
    { if: { properties: { action: { const: "seek" } }, required: ["action"] }, then: { required: ["timeSeconds"] } },
    { if: { properties: { action: { const: "set_rate" } }, required: ["action"] }, then: { required: ["rateMultiplier"] } },
    { if: { properties: { action: { const: "set_loop" } }, required: ["action"] }, then: { required: ["loop"] } }
  ]
});

const tools = [
  ...sceneTools, liveTool,
  tool(
    "open_omniverse_simulation_studio",
    "Open OmniStream for Codex",
    "Open the live Omniverse WebRTC control panel in Codex. The panel shows actual Kit frames once the local runtime is live.",
    schema({}),
    true,
    {
      ui: { resourceUri: widgetUri },
      "openai/outputTemplate": widgetUri,
      "openai/widgetAccessible": true
    }
  ),
  tool(
    "configure_omniverse_simulation",
    "Configure Omniverse Simulation",
    "Validate and store a runnable simulation configuration for this Codex session without starting Kit or changing USD.",
    simulationConfigurationInputSchema,
    false
  ),
  tool(
    "preflight_omniverse_simulation",
    "Preflight Omniverse Simulation",
    "Check the configured simulation, local Kit build, ports, workspace, stage, bridge source, and panel bundle before launch without starting or changing anything.",
    schema({}),
    true
  ),
  tool(
    "launch_omniverse_simulation",
    "Launch Configured Omniverse Simulation",
    "Launch the configured local Kit runtime, load the configured USD stage, apply session-only simulation settings, and optionally begin playback.",
    schema({}),
    false
  ),
  tool(
    "supervise_omniverse_simulation",
    "Supervise Omniverse Simulation",
    "Return one consolidated health snapshot for the configured simulation, managed Kit process, WebRTC stream, control bridge, loaded stage, timeline, and selected camera.",
    schema({}),
    true
  ),
  tool(
    "read_omnistream_runtime_logs",
    "Read OmniStream Runtime Logs",
    "Read a bounded tail of the managed Kit stdout/stderr logs for diagnostics. Credentials and secret-like values are redacted.",
    schema({
      stream: { type: "string", enum: ["stdout", "stderr", "both"], description: "Log stream to read. Defaults to both." },
      lines: { type: "integer", minimum: 10, maximum: 500, description: "Maximum lines returned per log stream. Defaults to 120." }
    }),
    true
  ),
  tool(
    "control_omniverse_simulation",
    "Control Omniverse Simulation",
    "Control the active simulation playback: play, pause, stop, reset, step, seek, change target cadence, or toggle looping. Stopping playback does not terminate Kit.",
    simulationControlInputSchema,
    false
  ),
  tool(
    "attach_omniverse_stream",
    "Attach Managed Omniverse Stream",
    "Reattach the panel to the already managed, live hidden Kit session. This returns only that session's WebRTC credential to the panel and never starts Kit or changes USD.",
    schema({}),
    true
  ),
  tool(
    "inspect_omniverse_stream_runtime",
    "Inspect Omniverse Stream Runtime",
    "Verify the configured local Kit executable and streaming layer without starting Omniverse.",
    schema({ kitRoot: { type: "string", minLength: 1, description: "Optional compatible Kit app-template root. Defaults to OMNISTREAM_KIT_ROOT when configured." } }),
    true
  ),
  tool(
    "list_workspace_usd_stages",
    "List Workspace USD Stages",
    "List local USD stages below one selected workspace root. Symlinks are skipped and results are capped.",
    schema({ workspaceRoot: { type: "string", minLength: 1, description: "Existing directory that bounds stage discovery and loading." } }, ["workspaceRoot"]),
    true
  ),
  tool(
    "discover_omniverse_local_assets",
    "Discover Local Omniverse Assets",
    "Inspect configured local OmniStream asset roots and, when present, a legacy sibling content folder beside the selected Kit root. This never contacts Nucleus or a remote content service.",
    schema({ kitRoot: { type: "string", minLength: 1, description: "Optional Kit app-template root used to locate its sibling local content directory." } }),
    true
  ),
  tool(
    "start_omniverse_stream",
    "Start Hidden Omniverse Stream",
    "Start a compatible local Kit app without a native window. Kit keeps the application framebuffer required for WebRTC, while the scene is viewed through the Codex panel.",
    schema({
      workspaceRoot: { type: "string", minLength: 1, description: "Existing directory allowed for USD stage loading." },
      stagePath: { type: "string", description: "Optional USD stage path under workspaceRoot. Load it through the panel after the hidden runtime connects." },
      kitRoot: { type: "string", minLength: 1, description: "Optional local Kit app-template root." }
    }, ["workspaceRoot"]),
    false
  ),
  tool(
    "get_omniverse_stream_status",
    "Get Omniverse Stream Status",
    "Return the known hidden Kit process state, local WebRTC endpoint state, and authenticated local control-bridge state.",
    schema({}),
    true
  ),
  tool(
    "stop_omniverse_stream",
    "Stop Hidden Omniverse Stream",
    "Stop only the hidden Kit process started by this MCP server during the current Codex session.",
    schema({}),
    false,
    {},
    true
  ),
  tool(
    "load_omniverse_stage",
    "Load Omniverse USD Stage",
    "Load one validated USD stage into the running hidden Kit session. The path must remain below the session workspace root.",
    schema({ stagePath: { type: "string", minLength: 1, description: "USD stage path below the workspace root selected when this session started." } }, ["stagePath"]),
    false
  ),
  tool(
    "get_omniverse_simulation_state",
    "Get Omniverse Simulation State",
    "Read the current session-only timeline, stage, and camera state from the connected hidden Kit runtime.",
    schema({}),
    true
  ),
  tool(
    "control_omniverse_timeline",
    "Control Omniverse Session Timeline",
    "Play, pause, stop, step, seek, or set the session playback rate. This never writes USD timeline metadata or saves a stage.",
    timelineInputSchema,
    false
  ),
  tool(
    "list_omniverse_cameras",
    "List Omniverse Cameras",
    "List selectable existing USD cameras from the currently loaded stage. This does not create a camera.",
    schema({}),
    true
  ),
  tool(
    "select_omniverse_camera",
    "Select Omniverse Camera",
    "Select an existing camera for temporary free navigation. The camera remains unchanged until explicit save.",
    schema({ cameraPath: { type: "string", minLength: 2, maxLength: 1024, description: "Existing absolute USD camera prim path." } }, ["cameraPath"]),
    false
  ),
  tool(
    "navigate_omniverse_camera",
    "Navigate Omniverse Camera",
    "Temporarily orbit, pan, or dolly the selected existing camera. Changes are not saved automatically.",
    cameraNavigateInputSchema,
    false
  ),
  tool(
    "save_omniverse_camera",
    "Save Selected Omniverse Camera",
    "Explicitly persist the selected camera pose to its existing writable USD source. This is the only camera-persistence operation.",
    schema({}),
    false,
    {},
    true
  )
];

function runtimeLayout(kitRootValue) {
  const requestedKitRoot = typeof kitRootValue === "string" ? kitRootValue.trim() : "";
  const kitRootCandidate = requestedKitRoot || configuredKitRoot;
  if (!kitRootCandidate) {
    return { kitRoot: "", releaseRoot: "", kitExe: "", streamKit: "" };
  }
  const kitRoot = path.resolve(kitRootCandidate);
  const releaseRoot = path.join(kitRoot, "_build", "windows-x86_64", "release");
  const streamKit = path.resolve(releaseRoot, streamKitRelativePath);
  const streamKitRelative = path.relative(releaseRoot, streamKit);
  return {
    kitRoot,
    releaseRoot,
    kitExe: path.join(releaseRoot, "kit", "kit.exe"),
    streamKit: streamKitRelative.startsWith("..") || path.isAbsolute(streamKitRelative) ? "" : streamKit
  };
}

function assertToolObject(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw toolError("Tool arguments must be an object.");
  return value;
}

function assertOnlyKeys(value, allowed) {
  const args = assertToolObject(value);
  for (const key of Object.keys(args)) {
    if (!allowed.has(key)) throw toolError("Unexpected tool argument: " + key + ".");
  }
  return args;
}

function assertEmptyArgs(value) {
  return assertOnlyKeys(value, new Set());
}

function assertNonEmptyString(value, label, maxLength = 4096) {
  if (typeof value !== "string" || !value.trim() || value.length > maxLength) throw toolError(label + " must be a non-empty string.");
  return value.trim();
}

function assertFiniteNumber(value, label, min, max) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) {
    throw toolError(label + " must be a finite number between " + min + " and " + max + ".");
  }
  return value;
}

function assertOptionalBoolean(value, label, fallback) {
  if (value === undefined) return fallback;
  if (typeof value !== "boolean") throw toolError(label + " must be a boolean.");
  return value;
}

function assertOptionalString(value, label, maxLength = 4096) {
  if (value === undefined || value === null || value === "") return "";
  return assertNonEmptyString(value, label, maxLength);
}

function parseSimulationConfiguration(rawArgs) {
  const args = assertOnlyKeys(rawArgs, new Set([
    "name", "workspaceRoot", "stagePath", "kitRoot", "initialTimeSeconds", "rateMultiplier",
    "loop", "playEveryFrame", "autoPlay", "cameraPath"
  ]));
  const workspaceRoot = validateWorkspaceRoot(args.workspaceRoot);
  const stagePath = validateStagePath(workspaceRoot, args.stagePath);
  const name = assertOptionalString(args.name, "name", 80) || path.basename(stagePath, path.extname(stagePath)) || "Simulation";
  const cameraPath = assertOptionalString(args.cameraPath, "cameraPath", 1024);
  if (cameraPath && !cameraPath.startsWith("/")) throw toolError("cameraPath must be an absolute USD prim path beginning with /.");
  return {
    name,
    workspaceRoot,
    stagePath,
    kitRoot: assertOptionalString(args.kitRoot, "kitRoot"),
    initialTimeSeconds: Object.hasOwn(args, "initialTimeSeconds") ? assertFiniteNumber(args.initialTimeSeconds, "initialTimeSeconds", 0, 1_000_000) : 0,
    rateMultiplier: Object.hasOwn(args, "rateMultiplier") ? assertFiniteNumber(args.rateMultiplier, "rateMultiplier", 0.05, 8) : 1,
    loop: assertOptionalBoolean(args.loop, "loop", false),
    playEveryFrame: assertOptionalBoolean(args.playEveryFrame, "playEveryFrame", false),
    autoPlay: assertOptionalBoolean(args.autoPlay, "autoPlay", false),
    cameraPath
  };
}

function parseSimulationControl(rawArgs) {
  const args = assertOnlyKeys(rawArgs, new Set(["action", "timeSeconds", "rateMultiplier", "loop"]));
  const action = assertNonEmptyString(args.action, "action", 64);
  if (!simulationControlActions.has(action)) throw toolError("action must be one of: " + [...simulationControlActions].join(", ") + ".");
  const params = { action };
  if (action === "seek") params.timeSeconds = assertFiniteNumber(args.timeSeconds, "timeSeconds", 0, 1_000_000);
  else if (Object.hasOwn(args, "timeSeconds")) throw toolError("timeSeconds is permitted only with seek.");
  if (action === "set_rate") params.rateMultiplier = assertFiniteNumber(args.rateMultiplier, "rateMultiplier", 0.05, 8);
  else if (Object.hasOwn(args, "rateMultiplier")) throw toolError("rateMultiplier is permitted only with set_rate.");
  if (action === "set_loop") {
    if (typeof args.loop !== "boolean") throw toolError("loop must be a boolean with set_loop.");
    params.loop = args.loop;
  } else if (Object.hasOwn(args, "loop")) throw toolError("loop is permitted only with set_loop.");
  return params;
}

function validateWorkspaceRoot(value) {
  try {
    return validateWorkspaceRootPolicy(value).realPath;
  } catch (error) {
    throw toolError(error instanceof Error ? error.message : "workspaceRoot could not be validated.");
  }
}

function validateStagePath(workspaceRoot, stagePath) {
  try {
    return validateStagePathPolicy(workspaceRoot, stagePath);
  } catch (error) {
    throw toolError(error instanceof Error ? error.message : "stagePath could not be validated.");
  }
}

function alive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error && error.code === "EPERM";
  }
}

function probeTcp(port, host = "127.0.0.1", timeoutMs = 400) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let settled = false;
    const finish = (connected) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(connected);
    };
    socket.setTimeout(timeoutMs);
    socket.once("connect", () => finish(true));
    socket.once("timeout", () => finish(false));
    socket.once("error", () => finish(false));
    socket.connect(port, host);
  });
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitForManagedRuntimeReady(timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  let last = {};
  while (Date.now() < deadline) {
    last = await runtimeStatus();
    if (last.processAlive && last.processOwnership === "owned" && last.streamListening && last.controlBridgeConnected) return last;
    if (runtimeSession && !last.processAlive) throw toolError("The managed Kit runtime exited before the simulation control bridge became ready.", "runtime_exited");
    await delay(1_000);
  }
  throw toolError(last.message || "The managed Kit runtime did not become ready before the simulation launch timeout.", "runtime_start_timeout");
}

async function waitForRuntimeStop(identity, timeoutMs = 6000) {
  const expected = parseLaunchedProcessIdentity(identity);
  if (!expected) return false;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!alive(expected.pid)) return true;
    const observed = await queryProcessIdentity(expected.pid, { powershellExe: windowsPowerShellExe });
    if (observed && !processIdentityMatches(expected, observed)) return true;
    await delay(250);
  }
  if (!alive(expected.pid)) return true;
  const observed = await queryProcessIdentity(expected.pid, { powershellExe: windowsPowerShellExe });
  return Boolean(observed && !processIdentityMatches(expected, observed));
}

function asOperationToolError(error) {
  if (error instanceof ToolError) return error;
  if (error instanceof OperationInProgressError) return toolError(error.message, error.code);
  if (error instanceof OperationClientTimeoutError) {
    return toolError(error.operationName + " is still completing. Wait for runtime status before retrying or stopping the hidden Kit session.", "operation_in_progress");
  }
  return error;
}

async function runExternalSideEffect(name, work, { clientTimeoutMs = standardMutationClientTimeoutMs } = {}) {
  if (shutdownRequested) throw toolError("The Omniverse MCP server is shutting down.", "server_shutting_down");
  if (sideEffectQueue.busy) {
    throw toolError("An Omniverse operation is already in progress: " + (sideEffectQueue.activeName || "queued operation") + ".", "operation_in_progress");
  }
  let operation;
  try {
    operation = sideEffectQueue.enqueue(name, work, { clientTimeoutMs });
  } catch (error) {
    throw asOperationToolError(error);
  }
  try {
    return await operation.client;
  } catch (error) {
    throw asOperationToolError(error);
  }
}

function enqueueLifecycleSideEffect(name, work) {
  try {
    return sideEffectQueue.enqueue(name, work, { allowWhenClosed: true }).completion;
  } catch (error) {
    throw asOperationToolError(error);
  }
}

function disposeSessionNow(session) {
  if (!session) return;
  void session.controlServer?.close().catch(() => {});
}

async function processOwnership(session) {
  if (!session?.processIdentity) return "identity_unverified";
  if (!alive(session.processIdentity.pid)) return "exited";
  const observed = await queryProcessIdentity(session.processIdentity.pid, { powershellExe: windowsPowerShellExe });
  if (!observed) return "identity_unverified";
  return processIdentityMatches(session.processIdentity, observed) ? "owned" : "identity_mismatch";
}

async function reconcileRuntimeSession() {
  const session = runtimeSession;
  if (!session) return null;
  const ownership = await processOwnership(session);
  session.processOwnership = ownership;
  if (ownership !== "exited") return session;
  // A verified stop can outlive Kit's PID briefly: the WebRTC signaling
  // service may still own the configured signaling port while its parent has exited. Retain the
  // session until that endpoint is observed down, so another launch cannot
  // be confused with the old panel session.
  if (streamStopPendingStates.has(session.streamStopState)) return session;
  disposeSessionNow(session);
  if (runtimeSession === session) runtimeSession = null;
  if (!shutdownRequested && !sideEffectQueue.busy) sideEffectQueue.openAdmission();
  return null;
}

function terminateSessionChildNow() {
  const session = runtimeSession;
  runtimeSession = null;
  disposeSessionNow(session);
}

function updateStopState(session, state) {
  session.stopState = state.state;
  session.stopAttempts = state.attempt || 0;
  session.stopLastCode = state.lastCode || null;
}

function reportShutdownRecovery(session, code) {
  if (shutdownRecoveryReported) return;
  shutdownRecoveryReported = true;
  process.stderr.write("Omniverse MCP shutdown is retaining its tracked session for bounded safe-stop recovery after " + code + ". It will not terminate an untracked process.\n");
}

async function prepareKitStop(session) {
  try {
    return await prepareKitForStop(session.controlServer, {
      method: controlMethod.runtimePrepareStop,
      reconnectWaitMs: stopBridgeReconnectWaitMs,
      completionTimeoutMs: runtimePrepareStopTimeoutMs,
      maxAttempts: stopBridgePrepareAttempts,
      onState: (state) => updateStopState(session, state)
    });
  } catch (error) {
    if (error instanceof PrepareStopPendingError) {
      throw toolError("The hidden Kit control bridge has not yet confirmed runtime.prepare_stop. The session remains owned and its safe stop will keep retrying.", "stop_pending");
    }
    if (error instanceof ControlRpcError) {
      throw toolError("The hidden Kit runtime did not confirm runtime.prepare_stop. The session remains owned and was not terminated.", error.code);
    }
    throw toolError("The hidden Kit runtime could not establish the safe stop barrier. The session remains owned and was not terminated.", "bridge_unavailable");
  }
}

/**
 * A successful native termination only proves that the tracked Kit process
 * exited. The user-visible scene is served through the configured signaling port, which
 * can shut down shortly afterwards. Do not release the session (or admit a
 * new launch) until the endpoint has actually stopped responding.
 */
async function confirmStreamStoppedAndReleaseSession(session) {
  session.streamStopState = "waiting_for_signaling";
  const streamStopped = await waitForTcpStop(
    () => probeTcp(signalingPort),
    { timeoutMs: streamStopTimeoutMs, pollMs: streamStopPollMs }
  );
  if (!streamStopped) {
    session.streamStopState = "stream_stop_timeout";
    updateStopState(session, {
      state: "stream_stop_timeout",
      attempt: session.stopAttempts,
      lastCode: "stream_stop_timeout"
    });
    throw toolError(
      "stream_stop_timeout: the tracked Kit process exited, but local WebRTC signaling on 127.0.0.1:" + signalingPort + " still responds after the bounded stop window. This session remains reserved, new launches stay blocked, and no untracked process was terminated.",
      "stream_stop_timeout"
    );
  }
  session.streamStopState = "stopped";
  await session.controlServer.close();
  if (runtimeSession === session) runtimeSession = null;
  if (!shutdownRequested) sideEffectQueue.openAdmission();
  return true;
}

async function stopTrackedSession(session, { timeoutMs = trackedProcessExitTimeoutMs } = {}) {
  if (!session) return true;
  // Retain the session from the moment a safe stop is requested. This also
  // covers startup rollback and EOF while the bridge has not connected yet:
  // should Kit exit in that window, the signaling endpoint is still checked
  // rather than being mistaken for an unrelated new session.
  session.streamStopState = "safe_stop_pending";
  const ownership = await processOwnership(session);
  session.processOwnership = ownership;
  if (ownership === "exited") {
    return confirmStreamStoppedAndReleaseSession(session);
  }
  if (ownership === "identity_mismatch") {
    await session.controlServer.close();
    throw toolError("The tracked Kit PID no longer proves ownership of this session. It was not terminated.", "session_not_owned");
  }
  if (ownership === "identity_unverified") {
    throw toolError("The tracked Kit PID is alive, but its creation identity could not be verified yet. It was not terminated and safe stop will retry.", "identity_unverified");
  }
  if (ownership !== "owned") throw toolError("The tracked Kit PID no longer proves ownership of this session. It was not terminated.", "session_not_owned");
  // This is intentionally before closing the bridge and before the process
  // helper. Kit atomically closes control admission and confirms every
  // WebRTC/JSONL mutation is idle through runtime.prepare_stop.
  await prepareKitStop(session);
  // Mark this before native termination so a concurrent status read cannot
  // discard the session in the short interval between PID exit and the
  // signaling-port probe below.
  session.streamStopState = "awaiting_runtime_exit";
  const stopped = await stopProcessIfIdentityMatches(session.processIdentity, { powershellExe: windowsPowerShellExe });
  if (stopped === "identity_mismatch") {
    session.processOwnership = "identity_mismatch";
    await session.controlServer.close();
    throw toolError("The tracked Kit PID was reused or changed identity before termination. It was not terminated.", "session_not_owned");
  }
  if (stopped !== "stopped") {
    if (!alive(session.pid)) {
      return confirmStreamStoppedAndReleaseSession(session);
    }
    throw toolError("The tracked hidden Kit process could not be stopped after runtime.prepare_stop confirmation.", "stop_failed");
  }
  if (!(await waitForRuntimeStop(session.processIdentity, timeoutMs))) {
    throw toolError("The tracked hidden Kit process did not exit after its verified termination request and remains tracked for recovery.", shutdownRequested ? "shutdown_timeout" : "stop_timeout");
  }
  return confirmStreamStoppedAndReleaseSession(session);
}

function ensureStopRecovery(session) {
  if (!session || runtimeSession !== session) return Promise.resolve();
  if (stopRecovery?.session === session) return stopRecovery.promise;
  const record = { session, scheduler: null, promise: null };
  const scheduler = new StopRecoveryScheduler({
    retryDelayMs: stopRecoveryDelayMs,
    isRecoverable: isTransientStopError,
    onState: (state) => {
      updateStopState(session, state);
      if (shutdownRequested && state.state === "recovery_wait") reportShutdownRecovery(session, state.lastCode || "stop_pending");
    },
    runPass: async () => {
      if (runtimeSession !== session) return { alreadyStopped: true };
      return enqueueLifecycleSideEffect("stop_recovery", () => stopTrackedSession(session, { timeoutMs: trackedProcessExitTimeoutMs }));
    }
  });
  record.scheduler = scheduler;
  record.promise = scheduler.start();
  stopRecovery = record;
  void record.promise.then(
    () => {
      if (stopRecovery === record) stopRecovery = null;
    },
    (error) => {
      if (runtimeSession === session) {
        updateStopState(session, {
          state: error?.code === "session_not_owned" ? "identity_mismatch" : "recovery_failed",
          attempt: session.stopAttempts,
          lastCode: error?.code || "stop_failed"
        });
      }
      if (stopRecovery === record) stopRecovery = null;
    }
  );
  return record.promise;
}

function statusText(status) {
  if (status.processOwnership === "identity_mismatch") return "The tracked PID no longer matches the Kit process this MCP session launched; it will not be controlled or terminated.";
  if (status.processOwnership === "identity_unverified") return "The tracked Kit PID is alive but its creation identity could not be verified; it will not be terminated.";
  if (status.streamStopState === "stream_stop_timeout") return "The tracked Kit process exited, but its local WebRTC signaling endpoint still responds. The session is retained and new launches remain blocked while bounded recovery rechecks the endpoint.";
  if (status.streamStopState === "waiting_for_signaling") return "The tracked Kit process exited and the session is waiting for its local WebRTC signaling endpoint to stop before release.";
  if (status.streamStopState === "awaiting_runtime_exit") return "A verified hidden Kit stop is in progress. The session remains reserved until both the tracked process and local WebRTC signaling have stopped.";
  if (status.streamStopState === "safe_stop_pending") return "Safe stop is in progress. The session remains reserved until its tracked process and local WebRTC signaling endpoint are both confirmed stopped.";
  if (["awaiting_bridge_recovery", "stop_pending", "recovery_attempt", "recovery_wait", "shutdown_recovery_pending"].includes(status.stopState)) return "Safe stop is pending in bounded background recovery. Mutations remain blocked; the tracked process will not be terminated before runtime.prepare_stop is acknowledged.";
  if (status.stopState === "waiting_for_bridge" || status.stopState === "bridge_retry") return "Safe stop is waiting for the authenticated Kit control bridge before any process termination.";
  if (status.uncertainOperation) return "A prior Kit mutation has an uncertain outcome. No further mutation will be admitted; safe stop waits for runtime.prepare_stop confirmation.";
  if (status.streamListening && status.processAlive && status.controlBridgeConnected) return "Windowless Kit runtime, local WebRTC signaling, and the authenticated local control bridge are running.";
  if (status.streamListening && status.processAlive) return "Windowless Kit runtime and local WebRTC signaling are running; the local control bridge is still connecting.";
  if (status.streamListening) return "A WebRTC signaling process responds locally but is not managed by this Codex panel.";
  if (status.processAlive) return "Windowless Kit runtime has started but WebRTC signaling is not listening yet.";
  if (status.runtimeReady) return "Streaming runtime is built but not running.";
  return "Streaming runtime is not built or the selected Kit root is unavailable.";
}

async function runtimeStatus(kitRootValue) {
  const session = await reconcileRuntimeSession();
  // An active session is bound to the Kit layout that launched it. Status
  // must keep describing that managed runtime rather than silently switching
  // to a caller's default/optional root while it is still alive.
  const layout = session?.kitLayout || runtimeLayout(kitRootValue);
  const processAlive = Boolean(session && alive(session.pid));
  const streamListening = await probeTcp(signalingPort);
  const hiddenLauncherExists = existsSync(hiddenKitLauncher);
  const powerShellExists = existsSync(windowsPowerShellExe);
  const runtimeReady = existsSync(layout.kitExe) && existsSync(layout.streamKit) && hiddenLauncherExists && powerShellExists;
  const status = {
    kitRoot: layout.kitRoot,
    releaseRoot: layout.releaseRoot,
    kitExe: layout.kitExe,
    streamKit: layout.streamKit,
    kitExeExists: existsSync(layout.kitExe),
    streamKitExists: existsSync(layout.streamKit),
    hiddenLauncherExists,
    powerShellExists,
    runtimeReady,
    processAlive,
    processId: session ? session.pid : null,
    processOwnership: session ? session.processOwnership : "stopped",
    stagePath: session ? session.stagePath : "",
    stageLoadState: session ? session.stageLoadState : "idle",
    workspaceRoot: session ? session.workspaceRoot : "",
    defaultWorkspaceRoot: configuredWorkspaceRoot,
    assetRoots: configuredAssetRoots,
    omnistreamHome: runtimePaths.home,
    logsRoot: runtimePaths.logs,
    streamListening,
    signalingHost: "127.0.0.1",
    signalingPort,
    mediaPort,
    requiresBearerAuthentication: true,
    controlBridge: session ? (session.controlServer.isConnected ? "connected" : "waiting") : "stopped",
    controlBridgeConnected: Boolean(session?.controlServer.isConnected),
    controlTransport: "authenticated-loopback-jsonl",
    lifecyclePhase,
    operationInProgress: sideEffectQueue.activeName,
    mutationAdmission: sideEffectQueue.isAdmissionClosed ? "closed" : "open",
    cameraSaveState: session ? session.cameraSaveState : "idle",
    uncertainOperation: session?.uncertainOperation || null,
    streamStopState: session?.streamStopState || "idle",
    stopState: session ? session.stopState : "idle",
    stopAttempts: session ? session.stopAttempts : 0,
    stopLastCode: session?.stopLastCode || null,
    simulationRunId: session?.simulationRun?.runId || null,
    simulationRunStartedAt: session?.simulationRun?.startedAt || null,
    simulationRunName: session?.simulationRun?.name || simulationDraft?.name || null,
    simulationConfigured: Boolean(simulationDraft),
    pluginVersion: manifest.version,
    runtimeChannel: localConfig.runtimeChannel || null,
    windowMode: "no-native-window",
    networkBoundary: "The panel targets 127.0.0.1. Enforce strict LAN isolation with a host firewall policy."
  };
  return { ...status, message: statusText(status) };
}

function listStages(workspaceRoot) {
  try {
    const stages = listWorkspaceUsdStages(workspaceRoot);
    const assets = listWorkspaceAssets(workspaceRoot);
    return { ...stages, assets: assets.assets, assetsCapped: assets.capped };
  } catch (error) {
    throw toolError(error instanceof Error ? error.message : "workspaceRoot could not be inspected.");
  }
}

async function discoverLocalAssets(rawArgs) {
  const args = assertOnlyKeys(rawArgs, new Set(["kitRoot"]));
  const layout = runtimeLayout(args.kitRoot);
  const sources = [];
  let legacyContentRoot = "";

  const addSource = (sourceRoot, label) => {
    try {
      const stages = listWorkspaceUsdStages(sourceRoot, { maxResults: 250, maxDepth: 8 });
      const assets = listWorkspaceAssets(sourceRoot, { maxResults: 250, maxDepth: 8 });
      if (!stages.stages.length && !assets.assets.length) return;
      if (sources.some((source) => source.path === stages.workspaceRoot)) return;
      sources.push({
        label: label || path.basename(stages.workspaceRoot) || "OmniStream Assets",
        path: stages.workspaceRoot,
        stageCount: stages.stages.length,
        stageCapped: stages.capped,
        assetCount: assets.assets.length,
        assetCapped: assets.capped
      });
    } catch {
      // Missing, inaccessible, or reparse-point roots remain invisible. Asset
      // discovery never widens the configured local boundary automatically.
    }
  };

  for (const configuredRoot of configuredAssetRoots) addSource(configuredRoot);

  // Preserve read-only compatibility with installations that kept an old
  // sibling `content` directory, but never treat it as the canonical path.
  const candidateContentRoot = layout.kitRoot ? path.resolve(layout.kitRoot, "..", "content") : "";
  if (candidateContentRoot) {
    try {
      legacyContentRoot = validateWorkspaceRoot(candidateContentRoot);
      for (const entry of readdirSync(legacyContentRoot, { withFileTypes: true })) {
        if (entry.isDirectory()) addSource(path.join(legacyContentRoot, entry.name), entry.name);
      }
    } catch {
      legacyContentRoot = "";
    }
  }

  return {
    contentRoot: legacyContentRoot,
    sources,
    discovery: {
      kind: "configured-local",
      configuredRootCount: configuredAssetRoots.length,
      legacyContentDetected: Boolean(legacyContentRoot),
      message: sources.length
        ? `${sources.length} source${sources.length > 1 ? "s" : ""} locale${sources.length > 1 ? "s" : ""} disponible${sources.length > 1 ? "s" : ""}.`
        : configuredAssetRoots.length
          ? "Les racines d'assets configurées ne contiennent aucun asset pris en charge ou ne sont pas accessibles."
          : "Aucune racine d'assets locale n'est configurée. Utilisez l'installateur ou omnistream.json pour en ajouter une."
    }
  };
}

function streamLogs() {
  const dir = runtimePaths.logs;
  mkdirSync(dir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  return {
    stdout: path.join(dir, "kit-" + stamp + ".out.log"),
    stderr: path.join(dir, "kit-" + stamp + ".err.log"),
    pid: path.join(dir, "kit-" + stamp + ".pid")
  };
}

function quoteWindowsArgument(value) {
  const text = String(value);
  let quoted = "\"";
  let backslashes = 0;
  for (const character of text) {
    if (character === "\\") {
      backslashes += 1;
      continue;
    }
    if (character === "\"") {
      quoted += "\\".repeat(backslashes * 2 + 1) + "\"";
      backslashes = 0;
      continue;
    }
    quoted += "\\".repeat(backslashes) + character;
    backslashes = 0;
  }
  return quoted + "\\".repeat(backslashes * 2) + "\"";
}

function readTrackedProcessIdentity(pidPath) {
  try {
    return parseLaunchedProcessIdentity(readFileSync(pidPath, "utf8"));
  } catch {
    return null;
  }
}

function startHiddenKit(layout, launchArgs, logs, controlToken) {
  return new Promise((resolve, reject) => {
    const argumentLine = launchArgs.map(quoteWindowsArgument).join(" ");
    const launcher = spawn(windowsPowerShellExe, [
      "-NoLogo",
      "-NoProfile",
      "-NonInteractive",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      hiddenKitLauncher,
      "-KitExe",
      layout.kitExe,
      "-KitArgumentLine",
      argumentLine,
      "-WorkingDirectory",
      layout.releaseRoot,
      "-StdOutPath",
      logs.stdout,
      "-StdErrPath",
      logs.stderr,
      "-PidPath",
      logs.pid
    ], {
      cwd: layout.releaseRoot,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      // Start-Process inherits this PowerShell child's environment. The
      // authenticated control credential must never be placed in argv, Kit
      // settings, public status, or local launch logs.
      env: {
        ...process.env,
        CODEX_OMNIVERSE_CONTROL_TOKEN: controlToken
      }
    });
    let stdout = "";
    let settled = false;
    const rejectLaunch = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      reject(toolError("The hidden Kit launcher did not return a tracked runtime process.", "launcher_failed"));
    };
    const timeout = setTimeout(() => {
      launcher.kill();
    }, 15_000);
    launcher.stdout.setEncoding("utf8");
    launcher.stdout.on("data", (chunk) => { stdout += chunk; });
    launcher.once("error", rejectLaunch);
    // `close` waits for inherited stdio handles. Kit can retain one after the
    // PowerShell wrapper exits, so `exit` is the wrapper lifecycle signal.
    launcher.once("exit", () => {
      if (settled) return;
      clearTimeout(timeout);
      // If PowerShell was interrupted after Start-Process succeeded, the
      // atomic PID file still lets the caller verify and roll back the exact
      // Kit process instead of abandoning it.
      const identity = parseLaunchedProcessIdentity(stdout) || readTrackedProcessIdentity(logs.pid);
      if (!identity) return rejectLaunch();
      settled = true;
      resolve(identity);
    });
  });
}

async function verifyTrackedProcess(identity) {
  const expected = parseLaunchedProcessIdentity(identity);
  if (!expected) throw toolError("The hidden Kit launcher returned an invalid process identity.", "launcher_failed");
  const deadline = Date.now() + 1_500;
  while (Date.now() < deadline) {
    if (!alive(expected.pid)) break;
    const observed = await queryProcessIdentity(expected.pid, { powershellExe: windowsPowerShellExe });
    if (observed && processIdentityMatches(expected, observed)) return;
    if (observed) throw toolError("The hidden Kit PID did not retain the creation identity returned by the launcher.", "session_not_owned");
    await delay(100);
  }
  throw toolError("The hidden Kit process exited before this session could track it.", "runtime_exited");
}

async function startRuntime(rawArgs) {
  const args = assertOnlyKeys(rawArgs, new Set(["workspaceRoot", "stagePath", "kitRoot"]));
  return runExternalSideEffect("starting", () => startRuntimeLocked(args), { clientTimeoutMs: 30_000 });
}

async function startRuntimeLocked(args) {
  if (shutdownRequested) throw toolError("The Omniverse MCP server is shutting down.", "server_shutting_down");
  const current = await runtimeStatus(args.kitRoot);
  if (runtimeSession && streamStopPendingStates.has(runtimeSession.streamStopState)) {
    throw toolError(
      "stream_stop_timeout: the previous tracked Kit session is still completing its local WebRTC signaling shutdown. Wait for its status to report the endpoint stopped before starting another session.",
      "stream_stop_timeout"
    );
  }
  if (current.processAlive) {
    if (!runtimeSession?.streamAccessToken) throw toolError("The existing Kit session has no bearer credential. Stop it, then start a new session.", "session_invalid");
    return result(current, "The hidden Kit runtime is already running.", { [widgetAccessTokenMetaKey]: runtimeSession.streamAccessToken });
  }
  if (current.streamListening) throw toolError("A WebRTC signaling process already responds on local port " + signalingPort + " and is not managed by this panel. Stop that process before starting a new Kit session.", "stream_port_in_use");
  if (!current.runtimeReady) throw toolError("Compatible streaming Kit runtime or hidden-window launcher is unavailable. Configure OMNISTREAM_KIT_ROOT or pass kitRoot, then provide a compatible streaming .kit layer below " + (current.releaseRoot || "that Kit root") + ".", "runtime_unavailable");
  const workspaceRoot = validateWorkspaceRoot(args.workspaceRoot);
  const stagePath = validateStagePath(workspaceRoot, args.stagePath);
  const logs = streamLogs();
  const liveEvents = new LiveEventStore();
  const controlServer = await new LoopbackControlServer({
    onEvent: event => liveEvents.accept(event),
    requestTimeouts: { [controlMethod.stageOpen]: stageOpenCompletionTimeoutMs }
  }).start();
  if (shutdownRequested) {
    await controlServer.close();
    throw toolError("The Omniverse MCP server is shutting down.", "server_shutting_down");
  }
  const control = controlServer.launchSettings;
  const launchArgs = [
    current.streamKit,
    `--/exts/omni.kit.livestream.app/primaryStream/signalPort=${signalingPort}`,
    `--/exts/omni.kit.livestream.app/primaryStream/streamPort=${mediaPort}`,
    "--/exts/omni.kit.livestream.app/primaryStream/streamType=webrtc",
    streamSettingsPrefix + "allowedRoot=" + workspaceRoot,
    streamSettingsPrefix + "controlHost=" + control.host,
    streamSettingsPrefix + "controlPort=" + control.port
  ];
  let processIdentity;
  let provisionalSession = null;
  const streamAccessToken = randomBytes(32).toString("base64url");
  try {
    processIdentity = await startHiddenKit(current, launchArgs, logs, control.token);
    provisionalSession = {
      pid: processIdentity.pid,
      processIdentity,
      processOwnership: "launching",
      workspaceRoot,
      stagePath,
      stageLoadState: "idle",
      cameraSaveState: "idle",
      uncertainOperation: null,
      streamStopState: "idle",
      stopState: "idle",
      stopAttempts: 0,
      stopLastCode: null,
      kitLayout: {
        kitRoot: current.kitRoot,
        releaseRoot: current.releaseRoot,
        kitExe: current.kitExe,
        streamKit: current.streamKit
      },
      streamAccessToken,
      controlServer,
      liveEvents,
      logs,
      startedAt: new Date().toISOString()
    };
    runtimeSession = provisionalSession;
    await verifyTrackedProcess(processIdentity);
    provisionalSession.processOwnership = "owned";
    if (shutdownRequested) throw toolError("The Omniverse MCP server is shutting down.", "server_shutting_down");
    const status = await runtimeStatus(args.kitRoot);
    // The returned launch description intentionally excludes the loopback port,
    // control credential, raw launch arguments, and runtime log locations.
    status.launch = {
      stageRequested: Boolean(stagePath),
      controlTransport: "authenticated-loopback-jsonl",
      nativeWindow: "none"
    };
    return result(status, "Windowless Kit runtime launch requested. The Codex panel will reconnect while WebRTC and the local control bridge start.", { [widgetAccessTokenMetaKey]: streamAccessToken });
  } catch (error) {
    if (provisionalSession && runtimeSession === provisionalSession) {
      let rollbackError = null;
      try {
        // A just-launched Kit without an authenticated bridge cannot prove
        // that its stage/camera transaction gate is closed and idle. Preserve
        // ownership instead of forcing a PID kill; a later stop retries
        // runtime.prepare_stop after the bridge connects.
        if (provisionalSession.controlServer.isConnected) {
          const rolledBack = await stopTrackedSession(provisionalSession);
          if (!rolledBack) {
            throw toolError("The hidden Kit runtime did not complete startup and remains tracked. Stop it before retrying.", "startup_rollback_failed");
          }
        } else {
          rollbackError = toolError("The hidden Kit runtime did not complete startup and remains tracked until its control bridge can confirm a safe stop.", "startup_rollback_pending");
        }
      } catch (caughtRollbackError) {
        rollbackError = caughtRollbackError;
      }
      if (rollbackError) {
        if (rollbackError instanceof ToolError && rollbackError.code === "startup_rollback_failed") throw rollbackError;
        if (rollbackError instanceof ToolError && (rollbackError.code === "startup_rollback_pending" || isTransientStopError(rollbackError))) {
          // The failed launch owns a verified PID/session. Keep lifecycle
          // admission closed and recover in the background exactly as EOF
          // does, including a later signaling-port confirmation.
          provisionalSession.streamStopState = "safe_stop_pending";
          sideEffectQueue.closeAdmission();
          const recovery = ensureStopRecovery(provisionalSession);
          void recovery.catch(() => {});
          throw toolError("The hidden Kit runtime did not complete startup. Its tracked session remains reserved while bounded safe-stop recovery waits for the control bridge and local WebRTC signaling shutdown.", "startup_rollback_pending");
        }
        throw toolError("The hidden Kit runtime did not complete startup and remains tracked. Stop it before retrying.", "startup_rollback_failed");
      }
    } else {
      await controlServer.close();
    }
    if (error instanceof ToolError) throw error;
    throw toolError("The hidden Kit runtime could not be started.", "launcher_failed");
  }
}

async function attachRuntime(rawArgs) {
  assertEmptyArgs(rawArgs);
  const session = await reconcileRuntimeSession();
  if (!session || !alive(session.pid)) {
    throw toolError("No live hidden Kit runtime managed by this MCP session is available to attach. Start the hidden Omniverse stream first.", "runtime_not_running");
  }
  if (session.processOwnership !== "owned") {
    throw toolError("The tracked Kit PID no longer proves ownership of this session. Its WebRTC credential will not be reissued.", "session_not_owned");
  }
  if (
    shutdownRequested ||
    sideEffectQueue.isAdmissionClosed ||
    session.streamStopState !== "idle" ||
    session.stopState !== "idle"
  ) {
    throw toolError("The managed hidden Kit session is stopping and cannot accept a new panel attachment.", "session_stopping");
  }
  if (!session.streamAccessToken) {
    throw toolError("The managed hidden Kit session has no WebRTC credential. Stop it, then start a new session.", "session_invalid");
  }
  const status = await runtimeStatus();
  if (runtimeSession !== session || !status.processAlive || status.processOwnership !== "owned") {
    throw toolError("No live hidden Kit runtime managed by this MCP session is available to attach. Start the hidden Omniverse stream first.", "runtime_not_running");
  }
  // `runtimeStatus()` awaits the loopback probe. A concurrent safe-stop can
  // therefore close admission after the first check above; do not reissue the
  // credential once that transition has begun.
  if (
    shutdownRequested ||
    sideEffectQueue.isAdmissionClosed ||
    session.streamStopState !== "idle" ||
    session.stopState !== "idle"
  ) {
    throw toolError("The managed hidden Kit session is stopping and cannot accept a new panel attachment.", "session_stopping");
  }
  // Keep the bearer credential panel-private. Public structured content and
  // text carry only redacted runtime status, never either local credential.
  return result(status, "Reattached to the managed hidden Kit runtime.", {
    [widgetAccessTokenMetaKey]: session.streamAccessToken
  });
}

async function stopRuntime(rawArgs) {
  assertEmptyArgs(rawArgs);
  // Refuse new mutations first. The lifecycle operation itself is admitted so
  // it can wait behind a timed-out client view without ever killing mid-save.
  sideEffectQueue.closeAdmission();
  if (!stopOperation) {
    let operation;
    try {
      operation = sideEffectQueue.enqueue("stopping", stopRuntimeLocked, {
        allowWhenClosed: true,
        clientTimeoutMs: stopRequestClientTimeoutMs
      });
    } catch (error) {
      throw asOperationToolError(error);
    }
    const record = { operation, client: operation.client, completion: operation.completion };
    stopOperation = record;
    void record.completion.then(
      () => { if (stopOperation === record) stopOperation = null; },
      () => { if (stopOperation === record) stopOperation = null; }
    );
  }
  try {
    return await stopOperation.client;
  } catch (error) {
    if (error instanceof OperationClientTimeoutError) {
      const session = runtimeSession;
      if (session) {
        session.streamStopState = "safe_stop_pending";
        updateStopState(session, {
          state: "stop_pending",
          attempt: session.stopAttempts,
          lastCode: "client_timeout"
        });
      }
      throw toolError(
        "Safe stop is queued behind an in-flight Kit mutation. The session remains owned, new mutations are blocked, and runtime.prepare_stop will run before any process termination.",
        "stop_pending"
      );
    }
    throw asOperationToolError(error);
  }
}

async function stopRuntimeLocked() {
  await reconcileRuntimeSession();
  if (!runtimeSession) {
    if (!shutdownRequested) sideEffectQueue.openAdmission();
    return result(await runtimeStatus(), "No hidden Kit runtime from this Codex session is running.");
  }
  const stopped = runtimeSession;
  try {
    await stopTrackedSession(stopped);
  } catch (error) {
    if (!isTransientStopError(error)) throw error;
    updateStopState(stopped, {
      state: error.code === "stream_stop_timeout" ? "stream_stop_timeout" : "stop_pending",
      attempt: stopped.stopAttempts,
      lastCode: error.code || "stop_pending"
    });
    const recovery = ensureStopRecovery(stopped);
    void recovery.catch(() => {});
    if (error.code === "stream_stop_timeout") {
      throw toolError("stream_stop_timeout: safe stop is rechecking the local WebRTC signaling endpoint in the background. The exited session remains reserved and mutations stay blocked; no untracked process will be terminated.", "stream_stop_timeout");
    }
    throw toolError("Safe stop is pending in the background. The hidden Kit session remains owned, mutations stay blocked, and runtime.prepare_stop will be retried before any process termination.", "stop_pending");
  }
  const status = await runtimeStatus();
  return result({ ...status, stoppedProcessId: stopped.pid }, "Stop requested for the hidden Kit runtime started by this MCP server.");
}

async function activeControlSession({ allowUncertainMutation = false } = {}) {
  const session = await reconcileRuntimeSession();
  if (!session) throw toolError("Start the hidden Omniverse stream before using simulation controls.", "runtime_not_running");
  if (session.processOwnership !== "owned") {
    throw toolError("The tracked Kit PID no longer proves ownership of this session. It will not receive control commands.", "session_not_owned");
  }
  if (!session.controlServer.isConnected) throw toolError("The hidden Kit runtime is starting, but its authenticated local control bridge is not connected yet.", "bridge_not_connected");
  if (!allowUncertainMutation && session.uncertainOperation) {
    throw toolError("The outcome of " + session.uncertainOperation + " is uncertain. Further mutations are blocked; use safe stop to end the session after Kit confirms runtime.prepare_stop.", "mutation_uncertain");
  }
  return session;
}

function normalizedBridgeResult(bridgeResult) {
  return { ...redactStructured(bridgeResult), controlBridgeConnected: true };
}

function bridgeToolError(error) {
  if (error instanceof ToolError) return error;
  if (error instanceof ControlRpcError) return toolError(error.message, error.code);
  return toolError("The local Kit control bridge could not complete the request.", "bridge_unavailable");
}

function isUncertainControlFailure(error) {
  return error instanceof ToolError && new Set([
    "request_timeout",
    "bridge_disconnected",
    "bridge_unavailable",
    "bridge_closed"
  ]).has(error.code);
}

async function callKitRead(method, params) {
  const session = await activeControlSession({ allowUncertainMutation: true });
  try {
    return normalizedBridgeResult(await session.controlServer.request(method, params));
  } catch (error) {
    throw bridgeToolError(error);
  }
}

async function callKitMutation(session, method, params, completionTimeoutMs) {
  try {
    const request = session.controlServer.startRequest(method, params, {
      clientTimeoutMs: completionTimeoutMs,
      completionTimeoutMs
    });
    // Do not await the client view here. The serial operation must remain in
    // flight after an MCP client timeout so a late Kit completion can update
    // tracked state before any next mutation or lifecycle action is admitted.
    return normalizedBridgeResult(await request.completion);
  } catch (error) {
    throw bridgeToolError(error);
  }
}

async function runKitMutation(name, session, method, params, {
  clientTimeoutMs = standardMutationClientTimeoutMs,
  completionTimeoutMs = standardMutationCompletionTimeoutMs,
  onStart = () => {},
  onSuccess = () => {},
  onFailure = () => {}
} = {}) {
  return runExternalSideEffect(name, async () => {
    const active = await activeControlSession();
    if (active !== session) throw toolError("The hidden Kit session changed before the operation could start.", "runtime_changed");
    onStart(active);
    try {
      const response = await callKitMutation(active, method, params, completionTimeoutMs);
      onSuccess(active, response);
      return response;
    } catch (error) {
      if (isUncertainControlFailure(error)) active.uncertainOperation = name;
      onFailure(active, error);
      throw error;
    }
  }, { clientTimeoutMs });
}

function simulationPreflightChecks(configuration, runtime) {
  const checks = [];
  const add = (id, ok, label, detail, severity = "required") => checks.push({ id, ok: Boolean(ok), label, detail, severity });
  add("configuration", Boolean(configuration), "Configuration", configuration ? `Simulation « ${configuration.name} » configurée.` : "Aucune simulation configurée.");
  if (configuration) {
    add("workspace", existsSync(configuration.workspaceRoot), "Workspace", configuration.workspaceRoot);
    add("stage", existsSync(configuration.stagePath), "Stage USD", configuration.stagePath);
  } else {
    add("workspace", false, "Workspace", "Configurez d'abord un workspace.");
    add("stage", false, "Stage USD", "Configurez d'abord un stage USD.");
  }
  add("kitExecutable", runtime.kitExeExists, "Kit executable", runtime.kitExe || "Kit non configuré.");
  add("streamLayer", runtime.streamKitExists, "Streaming layer", runtime.streamKit || "Couche .kit de streaming absente.");
  add("powershell", runtime.powerShellExists, "Windows PowerShell", runtime.powerShellExists ? "Disponible." : "Windows PowerShell requis pour le launcher caché.");
  add("launcher", runtime.hiddenLauncherExists, "OmniStream launcher", runtime.hiddenLauncherExists ? "Disponible." : "Launcher OmniStream manquant.");
  const bridgeSource = path.join(pluginRoot, "runtime", "bridge", "omnistream.codex.bridge");
  add("bridgeSource", existsSync(bridgeSource), "Control bridge", bridgeSource);
  const panelHtml = path.join(pluginRoot, "mcp", "web-dist", "index.html");
  add("panelBundle", existsSync(panelHtml), "Panel bundle", existsSync(panelHtml) ? "Bundle UI construit." : "Bundle UI absent : exécutez npm run build:web.");
  const portSafe = runtime.processAlive ? runtime.processOwnership === "owned" : !runtime.streamListening;
  add("signalingPort", portSafe, "WebRTC signaling port", runtime.processAlive
    ? (runtime.processOwnership === "owned" ? `Port ${signalingPort} détenu par la session gérée.` : `Port ${signalingPort} occupé par une session non détenue.`)
    : (runtime.streamListening ? `Port ${signalingPort} déjà occupé par un autre processus.` : `Port ${signalingPort} disponible.`));
  return checks;
}

async function preflightSimulation(rawArgs) {
  assertEmptyArgs(rawArgs);
  const runtime = await runtimeStatus(simulationDraft?.kitRoot);
  const checks = simulationPreflightChecks(simulationDraft, runtime);
  const required = checks.filter((item) => item.severity === "required");
  const ready = required.every((item) => item.ok);
  return result({
    ready,
    configuration: simulationDraft,
    runtime,
    checks,
    failed: checks.filter((item) => !item.ok).map((item) => item.id)
  }, ready ? "Simulation preflight passed." : "Simulation preflight found blocking requirements.");
}

function redactLogLine(line) {
  let redacted = String(line);
  const secrets = [runtimeSession?.streamAccessToken, runtimeSession?.controlServer?.token].filter(Boolean);
  for (const secret of secrets) redacted = redacted.split(secret).join("[REDACTED]");
  redacted = redacted.replace(/bearer\s+[^\s,;]+/gi, "Bearer [REDACTED]");
  redacted = redacted.replace(/((?:token|secret|password|authorization|credential)\s*[:=]\s*)(?:"[^"]*"|[^\s,;]+)/gi, "$1[REDACTED]");
  return redacted;
}

function tailLogFile(filePath, lineLimit) {
  if (!filePath || !existsSync(filePath)) return { available: false, file: filePath ? path.basename(filePath) : "", lines: [] };
  const maxBytes = 512 * 1024;
  let text;
  const fd = openSync(filePath, "r");
  try {
    const size = fstatSync(fd).size;
    const length = Math.min(size, maxBytes);
    const buffer = Buffer.alloc(length);
    const count = readSync(fd, buffer, 0, length, Math.max(0, size - length));
    text = buffer.subarray(0, count).toString("utf8");
    if (size > maxBytes) text = text.slice(text.indexOf("\n") + 1);
  } finally { closeSync(fd); }
  const lines = text.split(/\r?\n/).filter(Boolean).slice(-lineLimit).map(redactLogLine);
  return { available: true, file: path.basename(filePath), lines };
}

async function readRuntimeLogs(rawArgs) {
  const args = assertOnlyKeys(rawArgs, new Set(["stream", "lines"]));
  const stream = args.stream === undefined ? "both" : assertNonEmptyString(args.stream, "stream", 16);
  if (!new Set(["stdout", "stderr", "both"]).has(stream)) throw toolError("stream must be stdout, stderr, or both.");
  const lines = args.lines === undefined ? 120 : assertFiniteNumber(args.lines, "lines", 10, 500);
  if (!Number.isInteger(lines)) throw toolError("lines must be an integer between 10 and 500.");
  const logs = runtimeSession?.logs || null;
  const payload = { stream, lineLimit: lines, runtimeActive: Boolean(runtimeSession), logs: {} };
  if (stream === "stdout" || stream === "both") payload.logs.stdout = tailLogFile(logs?.stdout, lines);
  if (stream === "stderr" || stream === "both") payload.logs.stderr = tailLogFile(logs?.stderr, lines);
  return result(payload, logs ? "Managed Kit log tail read." : "No managed Kit runtime logs are available in this MCP session.");
}

async function configureSimulation(rawArgs) {
  const configuration = parseSimulationConfiguration(rawArgs);
  const active = await reconcileRuntimeSession();
  if (active && active.workspaceRoot !== configuration.workspaceRoot) {
    throw toolError("The active Kit session is bound to a different workspaceRoot. Stop that runtime before configuring a simulation in another workspace.", "workspace_mismatch");
  }
  simulationDraft = { ...configuration, configuredAt: new Date().toISOString() };
  return result({ configuration: simulationDraft }, "Simulation configuration validated and stored for this Codex session.");
}

async function launchConfiguredSimulation(rawArgs) {
  assertEmptyArgs(rawArgs);
  if (!simulationDraft) throw toolError("Configure a simulation before launching it.", "simulation_not_configured");
  // Snapshot the validated draft before entering the serial side-effect queue.
  // Configure/launch therefore cannot observe a half-updated simulation plan.
  const configuration = { ...simulationDraft };
  return runExternalSideEffect("simulation.launch", async () => {
    let session = await reconcileRuntimeSession();
    if (session && session.workspaceRoot !== configuration.workspaceRoot) {
      throw toolError("The managed Kit runtime is bound to another workspace. Stop it before launching this configured simulation.", "workspace_mismatch");
    }

    if (!session) {
      // We are already inside the serial queue: call the locked lifecycle
      // primitive directly instead of nesting another queued MCP mutation.
      await startRuntimeLocked({
        workspaceRoot: configuration.workspaceRoot,
        stagePath: configuration.stagePath,
        ...(configuration.kitRoot ? { kitRoot: configuration.kitRoot } : {})
      });
    }

    await waitForManagedRuntimeReady();
    session = await activeControlSession();
    if (session.workspaceRoot !== configuration.workspaceRoot) {
      throw toolError("The managed Kit session changed while the simulation was launching.", "runtime_changed");
    }

    const stagePath = validateStagePath(session.workspaceRoot, configuration.stagePath);
    session.simulationRun = null;
    session.stageLoadState = "loading";
    let stage;
    try {
      stage = await callKitMutation(session, controlMethod.stageOpen, { path: stagePath }, stageOpenCompletionTimeoutMs);
      session.stagePath = stagePath;
      session.stageLoadState = "idle";
    } catch (error) {
      session.stageLoadState = isUncertainControlFailure(error) ? "uncertain" : "idle";
      if (isUncertainControlFailure(error)) session.uncertainOperation = "simulation.launch:stage.open";
      throw error;
    }

    const params = {
      initialTimeSeconds: configuration.initialTimeSeconds,
      rateMultiplier: configuration.rateMultiplier,
      loop: configuration.loop,
      playEveryFrame: configuration.playEveryFrame,
      autoPlay: configuration.autoPlay,
      ...(configuration.cameraPath ? { cameraPath: configuration.cameraPath } : {})
    };
    let simulation;
    try {
      simulation = await callKitMutation(session, controlMethod.simulationConfigure, params, standardMutationCompletionTimeoutMs);
      session.simulationConfiguration = { ...configuration };
    } catch (error) {
      if (isUncertainControlFailure(error)) session.uncertainOperation = "simulation.launch:simulation.configure";
      throw error;
    }

    session.simulationRun = {
      runId: randomBytes(10).toString("hex"),
      name: configuration.name,
      startedAt: new Date().toISOString()
    };
    const runtime = await runtimeStatus();
    return result({
      configuration,
      run: session.simulationRun,
      runtime,
      stage,
      simulation
    }, "Configured Omniverse simulation launched.", { [widgetAccessTokenMetaKey]: session.streamAccessToken });
  }, { clientTimeoutMs: 180_000 });
}

async function superviseSimulation(rawArgs) {
  assertEmptyArgs(rawArgs);
  const runtime = await runtimeStatus();
  const session = runtimeSession;
  let simulation = null;
  let simulationError = null;
  if (runtime.processAlive && runtime.controlBridgeConnected) {
    try {
      simulation = await callKitRead(controlMethod.simulationState, {});
    } catch (error) {
      simulationError = publicErrorMessage(error);
    }
  }
  const run = session?.simulationRun ? {
    ...session.simulationRun,
    uptimeSeconds: Math.max(0, Math.floor((Date.now() - Date.parse(session.simulationRun.startedAt)) / 1000))
  } : null;
  const stageReady = Boolean(simulation && typeof simulation.stagePath === "string" && simulation.stagePath);
  const health = {
    runtime: runtime.processAlive && runtime.processOwnership === "owned" ? "ready" : runtime.runtimeReady ? "idle" : "unavailable",
    stream: runtime.streamListening ? "ready" : runtime.processAlive ? "starting" : "offline",
    bridge: runtime.controlBridgeConnected ? "ready" : runtime.processAlive ? "starting" : "offline",
    stage: stageReady ? "ready" : runtime.processAlive ? "empty" : "offline",
    simulation: simulation?.state || (runtime.processAlive ? "waiting" : "offline")
  };
  return result({
    configuration: simulationDraft,
    run,
    runtime,
    simulation,
    health,
    ...(simulationError ? { simulationError } : {})
  }, "Omniverse simulation supervision snapshot read.");
}

async function controlSimulation(rawArgs) {
  const params = parseSimulationControl(rawArgs);
  const session = await activeControlSession();
  const response = await runKitMutation("simulation.control", session, controlMethod.simulationControl, params);
  if (simulationDraft && params.action === "set_rate") simulationDraft = { ...simulationDraft, rateMultiplier: params.rateMultiplier };
  if (simulationDraft && params.action === "set_loop") simulationDraft = { ...simulationDraft, loop: params.loop };
  return result({
    run: session.simulationRun || null,
    configuration: simulationDraft,
    simulation: response
  }, "Omniverse simulation control command sent.");
}

async function loadStage(rawArgs) {
  const args = assertOnlyKeys(rawArgs, new Set(["stagePath"]));
  const session = await activeControlSession();
  const stagePath = validateStagePath(session.workspaceRoot, args.stagePath);
  const response = await runKitMutation("stage.open", session, controlMethod.stageOpen, { path: stagePath }, {
    clientTimeoutMs: stageOpenRequestTimeoutMs,
    completionTimeoutMs: stageOpenCompletionTimeoutMs,
    onStart(active) { active.stageLoadState = "loading"; },
    onSuccess(active) {
      active.stagePath = stagePath;
      active.stageLoadState = "idle";
    },
    onFailure(active, error) {
      active.stageLoadState = isUncertainControlFailure(error) ? "uncertain" : "idle";
    }
  });
  return result(response, "USD stage load requested from the hidden Kit runtime.");
}

async function getSimulationState(rawArgs) {
  assertEmptyArgs(rawArgs);
  return result(await callKitRead(controlMethod.simulationState, {}), "Omniverse session state read.");
}

function parseTimelineArgs(rawArgs) {
  const args = assertOnlyKeys(rawArgs, new Set(["action", "timeSeconds", "rateMultiplier"]));
  const action = assertNonEmptyString(args.action, "action", 64);
  if (!timelineActions.has(action)) throw toolError("action must be one of: " + [...timelineActions].join(", ") + ".");
  const params = { action };
  if (action === "seek") {
    params.timeSeconds = assertFiniteNumber(args.timeSeconds, "timeSeconds", 0, 1_000_000);
  } else if (Object.hasOwn(args, "timeSeconds")) {
    throw toolError("timeSeconds is permitted only with the seek action.");
  }
  if (action === "set_rate") {
    params.rateMultiplier = assertFiniteNumber(args.rateMultiplier, "rateMultiplier", 0.05, 8);
  } else if (Object.hasOwn(args, "rateMultiplier")) {
    throw toolError("rateMultiplier is permitted only with the set_rate action.");
  }
  return params;
}

async function controlTimeline(rawArgs) {
  const params = parseTimelineArgs(rawArgs);
  const session = await activeControlSession();
  return result(await runKitMutation("timeline.control", session, controlMethod.timelineControl, params), "Omniverse session timeline command sent.");
}

async function listCameras(rawArgs) {
  assertEmptyArgs(rawArgs);
  return result(await callKitRead(controlMethod.cameraList, {}), "Omniverse cameras listed.");
}

async function selectCamera(rawArgs) {
  const args = assertOnlyKeys(rawArgs, new Set(["cameraPath"]));
  const cameraPath = assertNonEmptyString(args.cameraPath, "cameraPath", 1024);
  if (!cameraPath.startsWith("/")) throw toolError("cameraPath must be an absolute USD prim path.");
  const session = await activeControlSession();
  return result(await runKitMutation("camera.select", session, controlMethod.cameraSelect, { cameraPath }), "Omniverse camera selected for temporary navigation.");
}

function parseNavigationArgs(rawArgs) {
  const args = assertOnlyKeys(rawArgs, new Set(["mode", "horizontal", "vertical", "amount"]));
  const mode = assertNonEmptyString(args.mode, "mode", 32);
  if (!cameraNavigationModes.has(mode)) throw toolError("mode must be one of: orbit, pan, dolly.");
  if (mode === "dolly") {
    if (Object.hasOwn(args, "horizontal") || Object.hasOwn(args, "vertical")) {
      throw toolError("horizontal and vertical are permitted only with orbit or pan.");
    }
    return { mode, amount: assertFiniteNumber(args.amount, "amount", -1, 1) };
  }
  if (Object.hasOwn(args, "amount")) throw toolError("amount is permitted only with dolly.");
  return {
    mode,
    horizontal: assertFiniteNumber(args.horizontal, "horizontal", -1, 1),
    vertical: assertFiniteNumber(args.vertical, "vertical", -1, 1)
  };
}

async function navigateCamera(rawArgs) {
  const params = parseNavigationArgs(rawArgs);
  const session = await activeControlSession();
  return result(await runKitMutation("camera.navigate", session, controlMethod.cameraNavigate, params), "Temporary Omniverse camera navigation command sent. Use explicit save to persist it.");
}

async function saveCamera(rawArgs) {
  assertEmptyArgs(rawArgs);
  const session = await activeControlSession();
  const response = await runKitMutation("camera.save", session, controlMethod.cameraSave, {}, {
    clientTimeoutMs: cameraSaveClientTimeoutMs,
    completionTimeoutMs: cameraSaveCompletionTimeoutMs,
    onStart(active) { active.cameraSaveState = "saving"; },
    onSuccess(active) { active.cameraSaveState = "idle"; },
    onFailure(active, error) {
      active.cameraSaveState = isUncertainControlFailure(error) ? "uncertain" : "idle";
    }
  });
  return result(response, "Selected Omniverse camera save requested.");
}

function safeAssetPath(webDist, assetRef) {
  const relative = assetRef.replace(/^\//, "");
  const resolved = path.resolve(webDist, relative);
  const check = path.relative(webDist, resolved);
  if (check.startsWith("..") || path.isAbsolute(check)) throw toolError("Invalid bundled asset path.");
  if (!existsSync(resolved)) throw toolError("Missing bundled panel asset: " + assetRef + ".");
  return resolved;
}

function widgetHtml() {
  const webDist = path.join(__dirname, "web-dist");
  const indexPath = path.join(webDist, "index.html");
  if (!existsSync(indexPath)) throw toolError("The panel bundle is missing. Run npm run build:web before loading this plugin.");
  let html = readFileSync(indexPath, "utf8");
  html = html.replace(/<link([^>]*?)href="([^"]+\.css)"([^>]*)>/g, (whole, before, href, after) => {
    const css = readFileSync(safeAssetPath(webDist, href), "utf8");
    return "<style data-omniverse-panel-css>" + css + "</style>";
  });
  html = html.replace(/<script([^>]*?)src="([^"]+\.js)"([^>]*)><\/script>/g, (whole, before, src, after) => {
    const script = readFileSync(safeAssetPath(webDist, src), "utf8").replace(/<\/script/gi, "<\\/script");
    return '<script type="module" data-omniverse-panel-js>' + script + "</script>";
  });
  if (!html.includes("data-omniverse-panel-js")) throw toolError("The panel bundle did not contain a JavaScript entrypoint.");
  return html;
}

function redactText(value) {
  let text = String(value ?? "");
  const secrets = [runtimeSession?.streamAccessToken, runtimeSession?.controlServer?.token].filter(Boolean);
  for (const secret of secrets) text = text.split(secret).join("[redacted]");
  return text;
}

function redactStructured(value, depth = 0) {
  if (depth > 16) return "[truncated]";
  if (typeof value === "string") return redactText(value);
  if (Array.isArray(value)) return value.slice(0, 500).map((item) => redactStructured(item, depth + 1));
  if (!value || typeof value !== "object") return value;
  const output = {};
  for (const [key, item] of Object.entries(value)) {
    if (sensitiveKeyPattern.test(key)) continue;
    output[key] = redactStructured(item, depth + 1);
  }
  return output;
}

function result(structuredContent, text, meta = {}) {
  return {
    structuredContent: redactStructured(structuredContent),
    content: [{ type: "text", text: redactText(text) }],
    ...(Object.keys(meta).length ? { _meta: meta } : {})
  };
}

function publicErrorMessage(error) {
  if (error instanceof ToolError || error instanceof ControlRpcError) return redactText(error.message);
  return "The Omniverse operation could not be completed. Check the non-secret local runtime status and try again.";
}

function respond(id, value) {
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, result: value }) + "\n");
}

function fail(id, code, message) {
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, error: { code, message: redactText(message) } }) + "\n");
}

async function handle(message) {
  const id = message.id;
  try {
    if (message.method === "initialize") {
      return respond(id, {
        protocolVersion: "2025-06-18",
        capabilities: { tools: {}, resources: {} },
        serverInfo: { name: manifest.name || "omnistream-for-codex", version: manifest.version || "0.1.0" },
        instructions: "This server starts a compatible local Kit app without a native window. The Codex panel displays actual Kit WebRTC frames and sends session controls through an authenticated local loopback bridge. Camera changes are temporary unless explicit save is requested. For an already open stage, inspect_omniverse_scene then preview/apply corrections and run_omniverse_scene; do NOT relaunch/reload it. read_omniverse_live_telemetry is a cached 4 Hz sample stream, not autonomous model execution."
      });
    }
    if (message.method === "notifications/initialized") return;
    if (message.method === "tools/list") return respond(id, { tools });
    if (message.method === "resources/list") {
      return respond(id, {
        resources: [{
          uri: widgetUri,
          name: "omnistream-for-codex",
          title: "OmniStream for Codex",
          mimeType: "text/html;profile=mcp-app",
          _meta: widgetResourceMeta
        }]
      });
    }
    if (message.method === "resources/read") {
      if (message.params?.uri !== widgetUri) throw toolError("Unknown resource: " + message.params?.uri + ".", "unknown_resource");
      return respond(id, {
        contents: [{
          uri: widgetUri,
          mimeType: "text/html;profile=mcp-app",
          text: widgetHtml(),
          _meta: widgetResourceMeta
        }]
      });
    }
    if (message.method !== "tools/call") return fail(id, -32601, "Unknown method: " + message.method);
    const name = message.params?.name;
    const args = message.params?.arguments ?? {};
    if (name === liveTool.name) {
      validateSchema(args, liveTool.inputSchema);
      const data = runtimeSession?.liveEvents?.read(args, runtimeSession.controlServer.isConnected)
        || { connected: false, stale: true, latest: null, ageMs: null, events: [], nextSequence: args.afterSequence || 0 };
      return respond(id, result(data, "Cached live telemetry read; check stale and ageMs before interpreting values."));
    }
    const sceneRoute = sceneRoutes.get(name);
    if (sceneRoute) {
      validateSchema(args, sceneRoute.inputSchema);
      try {
        const data = sceneRoute.readOnlyHint
          ? await callKitRead(sceneRoute.method, args)
          : await runKitMutation(sceneRoute.method, await activeControlSession(), sceneRoute.method, args);
        return respond(id, result(data, `${name} completed.`));
      } catch (error) {
        return respond(id, { isError: true, content: [{ type: "text", text: publicErrorMessage(error) }],
          structuredContent: { ok: false, code: error.code || "scene_command_failed", message: publicErrorMessage(error) } });
      }
    }
    if (name === "open_omniverse_simulation_studio") {
      assertEmptyArgs(args);
      return respond(id, result(await runtimeStatus(), "OmniStream control studio opened.", { "openai/outputTemplate": widgetUri }));
    }
    if (name === "inspect_omniverse_stream_runtime") {
      const inspected = assertOnlyKeys(args, new Set(["kitRoot"]));
      return respond(id, result(await runtimeStatus(inspected.kitRoot), "Omniverse streaming runtime preflight complete."));
    }
    if (name === "list_workspace_usd_stages") {
      const listedArgs = assertOnlyKeys(args, new Set(["workspaceRoot"]));
      const listed = listStages(listedArgs.workspaceRoot);
      return respond(id, result(listed, listed.stages.length + " local USD stage(s) found."));
    }
    if (name === "discover_omniverse_local_assets") {
      const discovered = await discoverLocalAssets(args);
      return respond(id, result(discovered, discovered.sources.length + " local Omniverse library/libraries found."));
    }
    if (name === "configure_omniverse_simulation") return respond(id, await configureSimulation(args));
    if (name === "preflight_omniverse_simulation") return respond(id, await preflightSimulation(args));
    if (name === "launch_omniverse_simulation") return respond(id, await launchConfiguredSimulation(args));
    if (name === "supervise_omniverse_simulation") return respond(id, await superviseSimulation(args));
    if (name === "read_omnistream_runtime_logs") return respond(id, await readRuntimeLogs(args));
    if (name === "control_omniverse_simulation") return respond(id, await controlSimulation(args));
    if (name === "start_omniverse_stream") return respond(id, await startRuntime(args));
    if (name === "attach_omniverse_stream") return respond(id, await attachRuntime(args));
    if (name === "get_omniverse_stream_status") {
      assertEmptyArgs(args);
      return respond(id, result(await runtimeStatus(), "Omniverse stream status read."));
    }
    if (name === "stop_omniverse_stream") return respond(id, await stopRuntime(args));
    if (name === "load_omniverse_stage") return respond(id, await loadStage(args));
    if (name === "get_omniverse_simulation_state") return respond(id, await getSimulationState(args));
    if (name === "control_omniverse_timeline") return respond(id, await controlTimeline(args));
    if (name === "list_omniverse_cameras") return respond(id, await listCameras(args));
    if (name === "select_omniverse_camera") return respond(id, await selectCamera(args));
    if (name === "navigate_omniverse_camera") return respond(id, await navigateCamera(args));
    if (name === "save_omniverse_camera") return respond(id, await saveCamera(args));
    return fail(id, -32602, "Unknown tool: " + name);
  } catch (error) {
    return fail(id, -32000, publicErrorMessage(error));
  }
}

function shutdownServer() {
  if (shutdownPromise) return shutdownPromise;
  shutdownRequested = true;
  // The shutdown operation is allowed into the serial queue after closing
  // admission. It can therefore wait for a client-timed-out save/load to
  // reach a definite result, then asks Kit itself to atomically prepare stop
  // before any verified process termination.
  sideEffectQueue.closeAdmission();
  shutdownPromise = (async () => {
    const firstPass = await enqueueLifecycleSideEffect("shutting_down", async () => {
      await reconcileRuntimeSession();
      const session = runtimeSession;
      if (!session) return { state: "stopped" };
      if (stopRecovery?.session === session) return { state: "recovering", recovery: stopRecovery.promise };
      try {
        await stopTrackedSession(session, { timeoutMs: trackedProcessExitTimeoutMs });
        return { state: "stopped" };
      } catch (error) {
        return { state: "error", session, error };
      }
    });
    if (firstPass.state === "stopped") return;
    if (firstPass.state === "recovering") return firstPass.recovery;
    if (!isTransientStopError(firstPass.error)) throw firstPass.error;
    updateStopState(firstPass.session, {
      state: "shutdown_recovery_pending",
      attempt: firstPass.session.stopAttempts,
      lastCode: firstPass.error.code || "shutdown_timeout"
    });
    reportShutdownRecovery(firstPass.session, firstPass.error.code || "shutdown_timeout");
    const recovery = ensureStopRecovery(firstPass.session);
    return recovery;
  })();
  // EOF has no request caller to observe a delayed recovery. Keep the process
  // alive through the promise, but never emit an unhandled rejection while the
  // permanent failure remains available through the retained session state.
  void shutdownPromise.catch(() => {});
  return shutdownPromise;
}

function shutdownAndExit(exitCode) {
  void shutdownServer().then(
    () => process.exit(exitCode),
    (error) => {
      // Do not force process exit: the session ownership is intentionally
      // retained when Kit has not confirmed runtime.prepare_stop, its
      // signaling endpoint remains up, or the PID identity changed.
      fail(null, -32000, "MCP shutdown retained the tracked session safely: " + publicErrorMessage(error));
    }
  );
}

let buffer = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  if (shutdownRequested) return;
  buffer += chunk;
  let index;
  while ((index = buffer.indexOf("\n")) >= 0) {
    const line = buffer.slice(0, index).trim();
    buffer = buffer.slice(index + 1);
    if (!line) continue;
    try {
      const message = JSON.parse(line);
      Promise.resolve(handle(message)).catch(() => fail(message?.id ?? null, -32000, "The Omniverse operation could not be completed."));
    } catch {
      fail(null, -32700, "Invalid JSON-RPC message.");
    }
  }
});

process.stdin.once("end", () => shutdownAndExit(0));
process.stdin.once("close", () => shutdownAndExit(0));
process.stdin.once("error", () => shutdownAndExit(1));
process.on("uncaughtException", () => {
  fail(null, -32000, "The Omniverse MCP server encountered an unexpected local error.");
  shutdownAndExit(1);
});
process.on("exit", terminateSessionChildNow);
process.once("SIGINT", () => {
  shutdownAndExit(0);
});
process.once("SIGTERM", () => {
  shutdownAndExit(0);
});
