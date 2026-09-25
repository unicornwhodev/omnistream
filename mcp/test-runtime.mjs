import assert from "node:assert/strict";
import { copyFileSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { queryMainWindowHandle } from "./process-identity.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const pluginRoot = path.resolve(__dirname, "..");
const stagePath = "control-camera.usda";
const sourceFixturePath = path.join(pluginRoot, "mcp", "fixtures", stagePath);
const sourceFixtureBefore = readFileSync(sourceFixturePath, "utf8");
const workspaceRoot = mkdtempSync(path.join(os.tmpdir(), "codex-omniverse-runtime-"));
const fixturePath = path.join(workspaceRoot, stagePath);
copyFileSync(sourceFixturePath, fixturePath);
const fixtureBefore = readFileSync(fixturePath, "utf8");
const server = spawn(process.execPath, ["./mcp/server.mjs"], {
  cwd: pluginRoot,
  stdio: ["pipe", "pipe", "pipe"]
});

let buffer = "";
let stderr = "";
const replies = new Map();
server.stdout.setEncoding("utf8");
server.stderr.setEncoding("utf8");
server.stdout.on("data", (chunk) => {
  buffer += chunk;
  let index;
  while ((index = buffer.indexOf("\n")) >= 0) {
    const line = buffer.slice(0, index);
    buffer = buffer.slice(index + 1);
    if (!line.trim()) continue;
    const response = JSON.parse(line);
    replies.get(response.id)?.(response);
  }
});
server.stderr.on("data", (chunk) => { stderr += chunk; });

function request(id, method, params, timeoutMs = 20_000) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("MCP request timed out: " + method + ". " + stderr)), timeoutMs);
    replies.set(id, (response) => {
      clearTimeout(timeout);
      replies.delete(id);
      if (response.error) reject(new Error(response.error.message));
      else if (response.result?.isError) reject(new Error(response.result.structuredContent?.message || "Tool returned an error"));
      else resolve(response.result);
    });
    server.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, ...(params ? { params } : {}) }) + "\n");
  });
}

async function tool(id, name, args, { timeoutMs } = {}) {
  try {
    return await request(id, "tools/call", { name, arguments: args }, timeoutMs);
  } catch (error) {
    throw new Error(name + ": " + (error instanceof Error ? error.message : String(error)), { cause: error });
  }
}

/**
 * Never terminate the MCP test controller abruptly while it still owns a Kit
 * session.  EOF drives the production safe-stop path, which retains the
 * controller until `runtime.prepare_stop`, the exact process identity check,
 * and the WebRTC signaling-stop check have all completed.  An unconditional
 * child kill here used to orphan a hidden Kit process whenever a test request
 * timed out.
 */
async function closeServerGracefully(timeoutMs = 75_000) {
  if (server.exitCode !== null) return;
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error("MCP test controller did not complete its safe shutdown within " + timeoutMs + " ms."));
    }, timeoutMs);
    server.once("exit", () => {
      clearTimeout(timeout);
      resolve();
    });
    if (!server.stdin.destroyed) server.stdin.end();
  });
}

async function waitForConnectedRuntime() {
  const deadline = Date.now() + 120_000;
  let current;
  while (Date.now() < deadline) {
    const status = await tool(3, "get_omniverse_stream_status", {});
    current = status.structuredContent;
    assert.equal(Object.hasOwn(current, "streamAccessToken"), false, "Read-only runtime status must not disclose the WebRTC bearer token.");
    assert.equal(Object.hasOwn(current, "controlToken"), false, "Read-only runtime status must not disclose the control credential.");
    if (!current.processAlive) break;
    if (current.streamListening && current.controlBridgeConnected) return current;
    await new Promise((resolve) => setTimeout(resolve, 1_500));
  }
  throw new Error("Kit did not expose both WebRTC signaling and its authenticated local control bridge. Last state: " + JSON.stringify(current));
}

async function waitForSafeStop() {
  const deadline = Date.now() + 90_000;
  let pendingError = null;
  let attempt = 0;
  while (Date.now() < deadline) {
    try {
      return await tool(130 + attempt, "stop_omniverse_stream", {}, { timeoutMs: 45_000 });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (!/Safe stop is pending|stream_stop_timeout|runtime\.prepare_stop/i.test(message)) throw error;
      pendingError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 2_000));
    const status = await tool(230 + attempt, "get_omniverse_stream_status", {});
    const current = status.structuredContent;
    if (!current.processAlive && !current.streamListening && !current.controlBridgeConnected && current.streamStopState === "idle") {
      return { structuredContent: current };
    }
    attempt += 1;
  }
  throw new Error("Safe-stop recovery did not complete within the runtime-test deadline.", { cause: pendingError });
}

async function readOnlyBridgeTool(id, name, args) {
  const deadline = Date.now() + 60_000;
  let lastError = null;
  let attempt = 0;
  while (Date.now() < deadline) {
    try {
      return await tool(attempt === 0 ? id : 500 + id * 10 + attempt, name, args);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (!/did not complete the control request in time/i.test(message)) throw error;
      lastError = error;
    }
    const status = await tool(700 + id * 10 + attempt, "get_omniverse_stream_status", {});
    const current = status.structuredContent;
    if (!current.processAlive || !current.streamListening || !current.controlBridgeConnected) {
      throw new Error(`${name} timed out and the managed runtime was no longer fully ready.`, { cause: lastError });
    }
    await new Promise((resolve) => setTimeout(resolve, 2_000));
    attempt += 1;
  }
  throw new Error(`${name} did not complete within the read-only retry deadline.`, { cause: lastError });
}

function statusSummary(status) {
  return {
    runtimeReady: status.runtimeReady,
    processAlive: status.processAlive,
    streamListening: status.streamListening,
    controlBridgeConnected: status.controlBridgeConnected,
    stageLoadState: status.stageLoadState,
    streamStopState: status.streamStopState,
    stopState: status.stopState,
    windowMode: status.windowMode
  };
}

function assertBridgeResult(value, operation) {
  assert.equal(value.controlBridgeConnected, true, operation + " did not use the authenticated local Kit bridge.");
  assert.equal(Object.hasOwn(value, "token"), false, operation + " disclosed a token.");
  assert.equal(Object.hasOwn(value, "controlToken"), false, operation + " disclosed the control credential.");
}

let started = false;
try {
  await request(1, "initialize", { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "runtime-test", version: "1" } });
  server.stdin.write(JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) + "\n");

  const configured = await tool(2, "configure_omniverse_simulation", {
    name: "OmniStream runtime fixture",
    workspaceRoot,
    stagePath,
    initialTimeSeconds: 0,
    rateMultiplier: 1,
    loop: true,
    playEveryFrame: true,
    autoPlay: false
  });
  assert.equal(configured.structuredContent.configuration.name, "OmniStream runtime fixture");
  assert.equal(configured.structuredContent.configuration.loop, true);

  const preflight = await tool(21, "preflight_omniverse_simulation", {});
  assert.equal(preflight.structuredContent.ready, true, "Target runtime preflight must pass before a release-candidate smoke launch.");
  assert.ok(Array.isArray(preflight.structuredContent.checks), "Preflight must return its individual readiness checks.");
  assert.equal(preflight.structuredContent.failed.length, 0, "Preflight returned blocking checks: " + JSON.stringify(preflight.structuredContent.failed));

  const launched = await tool(3, "launch_omniverse_simulation", {}, { timeoutMs: 180_000 });
  const launchStatus = launched.structuredContent.runtime;
  const launchedSimulation = launched.structuredContent.simulation;
  assert.equal(launchStatus.runtimeReady, true);
  assert.ok(launchStatus.processId, "Kit process id was not returned.");
  assert.equal(Object.hasOwn(launched.structuredContent, "streamAccessToken"), false, "Structured content must not disclose the WebRTC bearer token.");
  assert.equal(Object.hasOwn(launchStatus, "controlToken"), false, "Structured content must not disclose the control credential.");
  assert.match(launched._meta["omnistream/streamAccessToken"], /^[A-Za-z0-9_-]{43}$/, "Simulation launch did not return a session-scoped WebRTC bearer token in widget metadata.");
  assert.equal(launchStatus.windowMode, "no-native-window", "Runtime status must expose the windowless Kit contract.");
  assertBridgeResult(launchedSimulation, "simulation launch");
  assert.equal(launchedSimulation.loop, true, "Configured loop mode was not applied by the Kit bridge.");
  assert.equal(launchedSimulation.playEveryFrame, true, "Configured every-frame mode was not applied by the Kit bridge.");
  started = true;

  const attached = await tool(20, "attach_omniverse_stream", {});
  const attachStatus = attached.structuredContent;
  assert.equal(attachStatus.processId, launchStatus.processId, "Reattachment did not target the managed hidden Kit session.");
  assert.equal(Object.hasOwn(attachStatus, "streamAccessToken"), false, "Reattachment structured content disclosed the WebRTC bearer token.");
  assert.equal(Object.hasOwn(attachStatus, "controlToken"), false, "Reattachment structured content disclosed the control credential.");
  assert.equal(attached._meta["omnistream/streamAccessToken"], launched._meta["omnistream/streamAccessToken"], "Reattachment did not return the existing session-scoped WebRTC capability.");

  const connected = await waitForConnectedRuntime();
  assert.equal(connected.processAlive, true);
  assert.equal(connected.streamListening, true);
  assert.equal(connected.controlBridgeConnected, true);
  assert.equal(connected.windowMode, "no-native-window", "Connected runtime no longer reported the windowless Kit contract.");

  const runtimeLogs = await tool(22, "read_omnistream_runtime_logs", { stream: "both", lines: 120 });
  assert.equal(runtimeLogs.structuredContent.runtimeActive, true, "Managed runtime logs must be associated with the active session.");
  assert.ok(runtimeLogs.structuredContent.logs.stdout.available || runtimeLogs.structuredContent.logs.stderr.available, "At least one managed log stream must exist.");
  const logText = JSON.stringify(runtimeLogs.structuredContent);
  assert.equal(logText.includes(launched._meta["omnistream/streamAccessToken"]), false, "Runtime log diagnostics disclosed the WebRTC bearer token.");
  assert.ok(Number.isInteger(connected.processId), "Connected Kit runtime did not retain a process id for hidden-window verification.");
  const mainWindowHandle = await queryMainWindowHandle(connected.processId, {
    powershellExe: path.join(process.env.SystemRoot || "C:\\Windows", "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
  });
  assert.equal(mainWindowHandle, "0", "The connected Kit runtime exposed a native top-level window instead of remaining hidden.");

  const supervised = await readOnlyBridgeTool(4, "supervise_omniverse_simulation", {});
  assert.equal(supervised.structuredContent.health.runtime, "ready");
  assert.equal(supervised.structuredContent.health.stream, "ready");
  assert.equal(supervised.structuredContent.health.bridge, "ready");
  assert.equal(supervised.structuredContent.run.name, "OmniStream runtime fixture");
  assert.ok(typeof supervised.structuredContent.simulation.state === "string", "Simulation supervision did not include the timeline state.");

  const listed = await readOnlyBridgeTool(6, "list_omniverse_cameras", {});
  assertBridgeResult(listed.structuredContent, "camera list");
  assert.ok(Array.isArray(listed.structuredContent.cameras), "Kit did not return the current stage cameras.");
  const fixtureCamera = listed.structuredContent.cameras.find((camera) => camera.path === "/World/Camera");
  assert.ok(fixtureCamera, "The fixture camera was not discoverable from the loaded stage.");

  const selected = await tool(7, "select_omniverse_camera", { cameraPath: fixtureCamera.path });
  assertBridgeResult(selected.structuredContent, "camera selection");
  assert.equal(selected.structuredContent.camera?.path, fixtureCamera.path);

  const navigated = await tool(8, "navigate_omniverse_camera", { mode: "orbit", horizontal: 0.05, vertical: -0.03 });
  assertBridgeResult(navigated.structuredContent, "camera navigation");
  assert.equal(navigated.structuredContent.camera?.path, fixtureCamera.path);
  assert.equal(navigated.structuredContent.camera?.dirty, true, "Temporary camera navigation was not tracked as unsaved.");
  assert.equal(
    navigated.structuredContent.camera?.saveAvailable,
    true,
    "Temporary camera navigation did not leave an explicit save available."
  );

  const saved = await tool(9, "save_omniverse_camera", {});
  assertBridgeResult(saved.structuredContent, "camera save");
  assert.equal(saved.structuredContent.saved, true, "Explicit camera save was not confirmed.");
  assert.equal(saved.structuredContent.camera?.dirty, false, "Camera remained marked dirty after its explicit save.");
  assert.notEqual(readFileSync(fixturePath, "utf8"), fixtureBefore, "Explicit camera save did not update the isolated USD copy.");

  const stepped = await tool(10, "control_omniverse_simulation", { action: "step_forward" });
  assertBridgeResult(stepped.structuredContent.simulation, "simulation step");
  assert.ok(typeof stepped.structuredContent.simulation.timeSeconds === "number");

  const rate = await tool(11, "control_omniverse_simulation", { action: "set_rate", rateMultiplier: 1.25 });
  assertBridgeResult(rate.structuredContent.simulation, "simulation rate");
  assert.equal(rate.structuredContent.simulation.rateMultiplier, 1.25);

  const loopOff = await tool(12, "control_omniverse_simulation", { action: "set_loop", loop: false });
  assert.equal(loopOff.structuredContent.simulation.loop, false);

  const paused = await tool(13, "control_omniverse_simulation", { action: "pause" });
  assertBridgeResult(paused.structuredContent.simulation, "simulation pause");
  assert.equal(paused.structuredContent.simulation.state, "paused");

  const reset = await tool(14, "control_omniverse_simulation", { action: "reset" });
  assert.equal(reset.structuredContent.simulation.timeSeconds, 0);

  await tool(800, "control_omniverse_simulation", { action: "stop" });
  const afterCameraSource = readFileSync(fixturePath, "utf8");
  let inspectedScene = (await tool(801, "inspect_omniverse_scene", { parentPath: "/World" })).structuredContent;
  assert.ok(inspectedScene.prims.some(p => p.path === "/World/ReferenceCube"));
  const scenePreview = (await tool(802, "preview_omniverse_scene_patch", {
    stageId: inspectedScene.stageId, expectedRevision: inspectedScene.revision,
    operations: [
      { op: "playback_range", startSeconds: 0, endSeconds: 3, framesPerSecond: 30 },
      { op: "animate_transform", primPath: "/World/ReferenceCube", keys: [
        { timeSeconds: 0, translation: [0, 0, 50], rotation: [0, 0, 0], scale: [1, 1, 1] },
        { timeSeconds: 3, translation: [0, 100, 50], rotation: [0, 90, 0], scale: [1, 1, 1] }
      ] }
    ]
  })).structuredContent;
  assert.equal(readFileSync(fixturePath, "utf8"), afterCameraSource, "Preview wrote source USD");
  const appliedScene = (await tool(803, "apply_omniverse_scene_patch", {
    stageId: scenePreview.stageId, expectedRevision: scenePreview.revision, previewId: scenePreview.previewId
  })).structuredContent;
  assert.equal(appliedScene.applied, true);
  const inspectedPrim = (await tool(804, "inspect_omniverse_prim", { stageId: scenePreview.stageId, primPath: "/World/ReferenceCube" })).structuredContent;
  assert.equal(inspectedPrim.attributes.find(a => a.name === "xformOp:translate:omnistream").timeSampleCount, 2);
  await tool(805, "configure_omniverse_scene_watch", { stageId: scenePreview.stageId, properties: [{ primPath: "/World/ReferenceCube", attribute: "xformOp:translate:omnistream" }] });
  await tool(806, "run_omniverse_scene", { stageId: scenePreview.stageId, mode: "animation", wallTimeLimitSeconds: 1 });
  await new Promise(resolve => setTimeout(resolve, 1800));
  const live = (await tool(807, "read_omniverse_live_telemetry", { limit: 100 })).structuredContent;
  assert.equal(live.stale, false, "Live Kit telemetry must arrive over the authenticated channel");
  assert.equal(live.latest.playing, false, "Kit-local wall-time guard must pause the run");
  assert.equal(live.latest.watches.length, 1);
  await tool(808, "control_omniverse_simulation", { action: "stop" });
  inspectedScene = (await tool(809, "inspect_omniverse_scene", {})).structuredContent;
  await tool(810, "undo_omniverse_scene_patch", { stageId: inspectedScene.stageId, expectedRevision: inspectedScene.revision });
  assert.equal(readFileSync(fixturePath, "utf8"), afterCameraSource, "Scene edits modified source USD");
  console.log("Current-stage animation, preview/apply/undo, watcher and local watchdog passed on real Kit.");

  if (process.argv.includes("--physics")) {
    const scene = (await tool(820, "inspect_omniverse_scene", {})).structuredContent;
    assert.equal(scene.capabilities.rigidBodySimulation, true, "Physical gate requires omni.physx; it must not silently skip.");
    const preview = (await tool(821, "preview_omniverse_scene_patch", {
      stageId: scene.stageId, expectedRevision: scene.revision,
      operations: [
        { op: "playback_range", startSeconds: 0, endSeconds: 10, framesPerSecond: 60 },
        { op: "physics_scene", primPath: "/World/PhysicsScene", gravityDirection: [0, -1, 0], gravityMagnitude: 9.81 / scene.metersPerUnit },
        { op: "rigid_body", primPath: "/World/ReferenceCube", mass: 1, kinematic: false, collider: true }
      ]
    })).structuredContent;
    await tool(822, "apply_omniverse_scene_patch", { stageId: scene.stageId, expectedRevision: preview.revision, previewId: preview.previewId });
    const before = (await tool(823, "inspect_omniverse_prim", { stageId: scene.stageId, primPath: "/World/ReferenceCube" })).structuredContent;
    await tool(824, "run_omniverse_scene", { stageId: scene.stageId, mode: "physics", wallTimeLimitSeconds: 5 });
    let moved = false;
    for (let attempt = 0; attempt < 6; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 400));
      const current = (await tool(825 + attempt, "inspect_omniverse_prim", { stageId: scene.stageId, primPath: "/World/ReferenceCube" })).structuredContent;
      if (current.localMatrix[3][1] < before.localMatrix[3][1] - 1e-6) { moved = true; break; }
    }
    await tool(840, "control_omniverse_simulation", { action: "stop" });
    assert.equal(moved, true, "No physical displacement observed in USD. Check PhysX execution and USD writeback; Fabric-only state is not covered by this gate.");
    const fresh = (await tool(841, "inspect_omniverse_scene", {})).structuredContent;
    await tool(842, "undo_omniverse_scene_patch", { stageId: fresh.stageId, expectedRevision: fresh.revision });
    assert.equal(readFileSync(fixturePath, "utf8"), afterCameraSource, "Physics validation saved a source layer");
    console.log("Physical gate: actual falling-body displacement observed through USD; source unchanged.");
  }


  console.log(JSON.stringify({ launch: statusSummary(launchStatus), connected: statusSummary(connected), state: paused.structuredContent.simulation.state }, null, 2));
  console.log("Hidden Kit signaling, authenticated local control bridge, zero native window handle, high-level configure/launch/supervise/control workflow, and temporary camera controls passed.");
} finally {
  try {
    if (started) {
      // A successful stop response is only valid once the server has observed
      // that the session's local WebRTC signaling endpoint is no longer live.
      const stopped = await waitForSafeStop();
      const stoppedStatus = stopped.structuredContent;
      console.log(JSON.stringify({ stopped: statusSummary(stoppedStatus) }, null, 2));
      assert.equal(stoppedStatus.processAlive, false, "Kit process remained alive after stop.");
      assert.equal(stoppedStatus.streamListening, false, "WebRTC signaling remained available after stop.");
      assert.equal(stoppedStatus.controlBridgeConnected, false, "Control bridge remained available after stop.");
      assert.equal(stoppedStatus.streamStopState, "idle", "Stop success returned before the retained signaling-stop session was released.");
    }
  } finally {
    await closeServerGracefully();
    assert.equal(readFileSync(sourceFixturePath, "utf8"), sourceFixtureBefore, "Runtime validation modified the packaged USD fixture.");
    rmSync(workspaceRoot, { recursive: true, force: true, maxRetries: 3 });
  }
}
