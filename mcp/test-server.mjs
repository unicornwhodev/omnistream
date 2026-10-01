import assert from "node:assert/strict";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { LoopbackControlServer } from "./control-rpc.mjs";
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
import { listWorkspaceAssets, listWorkspaceUsdStages, validateStagePath } from "./stage-path-policy.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const pluginRoot = path.resolve(__dirname, "..");
const expectPanelBundle = process.env.OMNISTREAM_EXPECT_PANEL_BUNDLE === "1"
  || existsSync(path.resolve(import.meta.dirname, "web-dist", "index.html"));

function jsonLineReader(socket) {
  let buffer = "";
  const queued = [];
  const waiters = [];
  const emit = (value) => {
    const waiter = waiters.shift();
    if (waiter) waiter.resolve(value);
    else queued.push(value);
  };
  socket.setEncoding("utf8");
  socket.on("data", (chunk) => {
    buffer += chunk;
    let index;
    while ((index = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, index).trim();
      buffer = buffer.slice(index + 1);
      if (line) emit(JSON.parse(line));
    }
  });
  socket.on("error", (error) => {
    for (const waiter of waiters.splice(0)) waiter.reject(error);
  });
  return {
    next(timeoutMs = 2_000) {
      if (queued.length) return Promise.resolve(queued.shift());
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          const index = waiters.indexOf(entry);
          if (index >= 0) waiters.splice(index, 1);
          reject(new Error("Timed out waiting for control JSONL message."));
        }, timeoutMs);
        const entry = {
          resolve(value) {
            clearTimeout(timeout);
            resolve(value);
          },
          reject(error) {
            clearTimeout(timeout);
            reject(error);
          }
        };
        waiters.push(entry);
      });
    }
  };
}

async function connect(host, port) {
  const socket = net.createConnection({ host, port });
  // A rejected unauthenticated peer may be closed while its buffered response
  // is still delivered. Keep an error listener so the test can prove that a
  // bad client cannot block the genuine bridge without producing a process-
  // level unhandled socket error.
  socket.on("error", () => {});
  await new Promise((resolve, reject) => {
    socket.once("connect", resolve);
    socket.once("error", reject);
  });
  return socket;
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function integerConstant(source, name) {
  const match = source.match(new RegExp("const\\s+" + name + "\\s*=\\s*([0-9_]+);"));
  if (!match) throw new Error("Missing integer constant: " + name);
  return Number(match[1].replaceAll("_", ""));
}

async function testControlRpc() {
  const control = await new LoopbackControlServer({
    token: "A".repeat(43),
    requestTimeoutMs: 100,
    requestTimeouts: { "stage.open": 250 }
  }).start();
  const settings = control.launchSettings;
  assert.equal(settings.host, "127.0.0.1");
  assert.ok(Number.isInteger(settings.port) && settings.port > 0);

  // Six silent peers must not consume all pre-authentication capacity. The
  // server evicts the oldest pre-auth socket before admitting this real hello.
  const mutedIntruders = [];
  for (let index = 0; index < 6; index += 1) {
    mutedIntruders.push(await connect(settings.host, settings.port));
  }
  const bridge = await connect(settings.host, settings.port);
  const bridgeReader = jsonLineReader(bridge);
  bridge.write(JSON.stringify({ type: "hello", protocol: 1, token: settings.token }) + "\n");
  assert.deepEqual(await bridgeReader.next(), { type: "hello", ok: true, protocol: 1 });
  assert.equal(control.isConnected, true);

  const response = control.request("simulation.state", {});
  const request = await bridgeReader.next();
  assert.equal(request.type, "request");
  assert.equal(request.method, "simulation.state");
  assert.deepEqual(request.params, {});
  bridge.write(JSON.stringify({ type: "response", id: request.id, ok: true, result: { state: "paused" } }) + "\n");
  assert.deepEqual(await response, { state: "paused" });

  let stageSettled = false;
  const stageRequest = control.request("stage.open", { path: "C:\\safe\\stage.usda" }).then((value) => {
    stageSettled = true;
    return value;
  });
  const stageMessage = await bridgeReader.next();
  assert.equal(stageMessage.method, "stage.open");
  await new Promise((resolve) => setTimeout(resolve, 150));
  assert.equal(stageSettled, false, "The stage-open override must outlive the generic RPC timeout.");
  bridge.write(JSON.stringify({ type: "response", id: stageMessage.id, ok: true, result: { stagePath: "C:\\safe\\stage.usda" } }) + "\n");
  assert.deepEqual(await stageRequest, { stagePath: "C:\\safe\\stage.usda" });

  const slowSave = control.startRequest("camera.save", {}, { clientTimeoutMs: 50, completionTimeoutMs: 500 });
  const slowSaveMessage = await bridgeReader.next();
  assert.equal(slowSaveMessage.method, "camera.save");
  await assert.rejects(slowSave.client, (error) => error.code === "client_timeout");
  bridge.write(JSON.stringify({ type: "response", id: slowSaveMessage.id, ok: true, result: { saved: true } }) + "\n");
  assert.deepEqual(await slowSave.completion, { saved: true }, "The internal completion must survive the short client timeout.");

  const timeout = control.request("timeline.control", { action: "play" });
  await bridgeReader.next();
  await assert.rejects(timeout, /did not complete/);
  bridge.destroy();
  for (const intruder of mutedIntruders) intruder.destroy();
  await control.close();
}

async function testSlowSaveQueueAndLifecycleBarrier() {
  const control = await new LoopbackControlServer({ token: "Q".repeat(43), requestTimeoutMs: 500 }).start();
  const settings = control.launchSettings;
  const bridge = await connect(settings.host, settings.port);
  const bridgeReader = jsonLineReader(bridge);
  bridge.write(JSON.stringify({ type: "hello", protocol: 1, token: settings.token }) + "\n");
  assert.equal((await bridgeReader.next()).ok, true);

  const queue = new SerialOperationQueue();
  const saving = queue.enqueue("camera.save", async () => {
    const request = control.startRequest("camera.save", {}, { clientTimeoutMs: 50, completionTimeoutMs: 500 });
    return request.completion;
  }, { clientTimeoutMs: 50 });
  const saveRequest = await bridgeReader.next();
  assert.equal(saveRequest.method, "camera.save");
  await assert.rejects(saving.client, (error) => error instanceof OperationClientTimeoutError && error.code === "client_timeout");
  assert.equal(queue.busy, true, "A client timeout must not release the serialized camera-save operation.");
  assert.throws(() => queue.assertIdle(), (error) => error instanceof OperationInProgressError);

  // This mirrors stop/EOF: close normal mutation admission, but allow the
  // lifecycle barriers to wait behind a slow save. Neither starts early.
  queue.closeAdmission();
  assert.throws(() => queue.enqueue("camera.navigate", async () => {}), (error) => error instanceof OperationInProgressError);
  let stopStarted = false;
  let shutdownStarted = false;
  const stop = queue.enqueue("stopping", async () => {
    stopStarted = true;
    const prepared = control.startRequest("runtime.prepare_stop", {}, { completionTimeoutMs: 500 });
    return prepared.completion;
  }, { allowWhenClosed: true, clientTimeoutMs: 50 });
  const shutdown = queue.enqueue("shutting_down", async () => {
    shutdownStarted = true;
  }, { allowWhenClosed: true });
  await delay(80);
  assert.equal(stopStarted, false, "Stop must wait for the save completion rather than terminate during it.");
  assert.equal(shutdownStarted, false, "EOF shutdown must wait behind the same save completion.");
  await assert.rejects(
    stop.client,
    (error) => error instanceof OperationClientTimeoutError && error.code === "client_timeout",
    "A user-facing stop request must become bounded-pending while its real lifecycle completion remains queued behind a save."
  );

  bridge.write(JSON.stringify({ type: "response", id: saveRequest.id, ok: true, result: { saved: true } }) + "\n");
  assert.deepEqual(await saving.completion, { saved: true });
  const prepareRequest = await bridgeReader.next();
  assert.equal(prepareRequest.method, "runtime.prepare_stop");
  bridge.write(JSON.stringify({ type: "response", id: prepareRequest.id, ok: true, result: { prepared: true } }) + "\n");
  assert.deepEqual(await stop.completion, { prepared: true });
  await shutdown.completion;
  assert.equal(shutdownStarted, true);
  bridge.destroy();
  await control.close();
}

async function testBoundedStopPendingDoesNotHang() {
  const control = await new LoopbackControlServer({ token: "P".repeat(43), requestTimeoutMs: 100 }).start();
  try {
    const pendingPass = prepareKitForStop(control, {
      reconnectWaitMs: 25,
      completionTimeoutMs: 100,
      maxAttempts: 1
    });
    await assert.rejects(pendingPass, (error) => error instanceof PrepareStopPendingError && error.code === "stop_pending");

    let passes = 0;
    let verifiedExactStopCalls = 0;
    const recovery = new StopRecoveryScheduler({
      retryDelayMs: 10,
      isRecoverable: isTransientStopError,
      runPass: async () => {
        passes += 1;
        const prepared = await prepareKitForStop(control, {
          reconnectWaitMs: 20,
          completionTimeoutMs: 100,
          maxAttempts: 1
        });
        verifiedExactStopCalls += 1;
        return prepared;
      }
    });
    const recovered = recovery.start();
    void recovered.catch(() => {});
    await delay(90);
    assert.ok(passes >= 2, "Background recovery must repeat bounded stop_pending passes instead of holding an MCP response indefinitely.");
    assert.equal(verifiedExactStopCalls, 0, "No exact process stop may be reached while runtime.prepare_stop remains unacknowledged.");
    recovery.cancel(new Error("test complete"));
    await assert.rejects(recovered, /test complete/);
  } finally {
    await control.close();
  }
}

async function testBoundedStreamStopWait() {
  let probes = 0;
  const stopped = await waitForTcpStop(() => {
    probes += 1;
    return probes < 3;
  }, { timeoutMs: 100, pollMs: 2 });
  assert.equal(stopped, true, "The stop waiter must not complete until the local endpoint stops responding.");
  assert.equal(probes, 3, "The stop waiter must keep probing until it observes the endpoint down.");

  let persistentProbes = 0;
  const timedOut = await waitForTcpStop(() => {
    persistentProbes += 1;
    return true;
  }, { timeoutMs: 25, pollMs: 5 });
  assert.equal(timedOut, false, "A persistent local endpoint must produce a bounded timeout result rather than a false stop success.");
  assert.ok(persistentProbes >= 2, "A persistent local endpoint must be rechecked before timeout.");
  assert.equal(isTransientStopError({ code: "stream_stop_timeout" }), true, "EOF/background recovery must retry a bounded signaling-stop timeout.");
}

async function testPrepareStopReconnectAfterEof() {
  const control = await new LoopbackControlServer({ token: "R".repeat(43), requestTimeoutMs: 500 }).start();
  const settings = control.launchSettings;
  const state = [];
  let verifiedExactStopCalls = 0;
  let transientIdentityFailure = true;
  // This represents EOF after a session was started but before Kit connected.
  // The first bounded pass has a transient identity-verification failure;
  // recovery must retain the listener/session, retry, and never run exact
  // process stop before a later prepare_stop acknowledgement.
  const eofRecovery = new StopRecoveryScheduler({
    retryDelayMs: 15,
    isRecoverable: isTransientStopError,
    onState: (entry) => state.push(entry.state + (entry.lastCode ? ":" + entry.lastCode : "")),
    runPass: async () => {
      if (transientIdentityFailure) {
        transientIdentityFailure = false;
        const error = new Error("Temporary process identity query failure.");
        error.code = "identity_unverified";
        throw error;
      }
      const prepared = await prepareKitForStop(control, {
        reconnectWaitMs: 150,
        completionTimeoutMs: 500,
        maxAttempts: 5,
        onState: (entry) => state.push(entry.state)
      });
      assert.equal(prepared.response.prepared, true);
      verifiedExactStopCalls += 1;
    }
  });
  const eofShutdown = eofRecovery.start();
  await delay(45);
  assert.equal(verifiedExactStopCalls, 0, "EOF safe stop must wait for an authenticated bridge instead of abandoning or killing.");

  const firstBridge = await connect(settings.host, settings.port);
  const firstReader = jsonLineReader(firstBridge);
  firstBridge.write(JSON.stringify({ type: "hello", protocol: 1, token: settings.token }) + "\n");
  assert.equal((await firstReader.next()).ok, true);
  const firstPrepare = await firstReader.next();
  assert.equal(firstPrepare.method, "runtime.prepare_stop");
  const firstClosed = new Promise((resolve) => firstBridge.once("close", resolve));
  firstBridge.destroy();
  await firstClosed;
  for (let attempt = 0; attempt < 20 && control.isConnected; attempt += 1) await delay(10);
  assert.equal(control.isConnected, false, "The local control server must observe the transient bridge disconnect before reconnection.");

  // The control listener remains owned by the session and accepts Kit's
  // transient reconnection. Only its acknowledged prepare_stop releases the
  // fake verified exact-stop step.
  const secondBridge = await connect(settings.host, settings.port);
  const secondReader = jsonLineReader(secondBridge);
  secondBridge.write(JSON.stringify({ type: "hello", protocol: 1, token: settings.token }) + "\n");
  assert.equal((await secondReader.next()).ok, true);
  const secondPrepare = await secondReader.next();
  assert.equal(secondPrepare.method, "runtime.prepare_stop");
  assert.equal(verifiedExactStopCalls, 0, "Exact process stop must not run before the reconnecting bridge confirms prepare_stop.");
  secondBridge.write(JSON.stringify({ type: "response", id: secondPrepare.id, ok: true, result: { prepared: true } }) + "\n");
  await eofShutdown;
  assert.equal(verifiedExactStopCalls, 1);
  assert.ok(state.includes("recovery_wait:identity_unverified"));
  assert.ok(state.includes("waiting_for_bridge"));
  assert.ok(state.includes("bridge_retry"));
  assert.ok(state.includes("prepared"));
  secondBridge.destroy();
  await control.close();
}

async function testProcessIdentitySafety() {
  if (process.platform !== "win32") {
    assert.equal(parseLaunchedProcessIdentity('{"pid":0,"startedAtUtc":"2026-01-01T00:00:00.000Z","startedAtFileTimeUtc":"133801632000000000"}'), null);
    assert.equal(processIdentityMatches(
      { pid: 10, startedAtUtc: "2026-01-01T00:00:00.000Z", startedAtFileTimeUtc: "133801632000000001" },
      { pid: 10, startedAtUtc: "2026-01-01T00:00:00.000Z", startedAtFileTimeUtc: "133801632000000002" }
    ), false);
    return;
  }
  const powershellExe = path.join(process.env.SystemRoot || "C:\\Windows", "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
  const observed = await queryProcessIdentity(process.pid, { powershellExe });
  assert.ok(observed, "The Windows process-identity helper must read the current Node process.");
  const parsed = parseLaunchedProcessIdentity(JSON.stringify(observed));
  assert.deepEqual(parsed, observed);
  assert.equal(parseLaunchedProcessIdentity('{"pid":0,"startedAtUtc":"2026-01-01T00:00:00.000Z","startedAtFileTimeUtc":"133801632000000000"}'), null);
  const mismatch = { ...observed, startedAtFileTimeUtc: (BigInt(observed.startedAtFileTimeUtc) + 1n).toString() };
  assert.equal(processIdentityMatches(observed, mismatch), false);
  // The helper compares FILETIME and terminates only through the same native
  // handle. This intentional mismatch proves it refuses a live PID without
  // killing this test process.
  assert.equal(await stopProcessIfIdentityMatches(mismatch, { powershellExe }), "identity_mismatch");
  assert.doesNotThrow(() => process.kill(process.pid, 0));

  // A disposable child proves that the same helper accepts the exact identity
  // format emitted by the launcher and performs the verified termination.
  const child = spawn(process.execPath, ["-e", "setInterval(() => {}, 1000)"], { windowsHide: true, stdio: "ignore" });
  try {
    let childIdentity = null;
    for (let attempt = 0; attempt < 20 && !childIdentity; attempt += 1) {
      childIdentity = await queryProcessIdentity(child.pid, { powershellExe });
      if (!childIdentity) await delay(50);
    }
    assert.ok(childIdentity, "The disposable child must have a readable creation identity.");
    const exited = new Promise((resolve) => child.once("exit", resolve));
    assert.equal(await stopProcessIfIdentityMatches(childIdentity, { powershellExe }), "stopped");
    await Promise.race([
      exited,
      delay(5_000).then(() => { throw new Error("Verified child termination timed out."); })
    ]);
  } finally {
    if (child.exitCode === null) child.kill();
  }
}

function testStagePathPolicy() {
  const temporaryRoot = mkdtempSync(path.join(os.tmpdir(), "omniverse-stage-policy-"));
  try {
    const workspace = path.join(temporaryRoot, "workspace");
    const outside = path.join(temporaryRoot, "outside");
    mkdirSync(workspace);
    mkdirSync(outside);
    writeFileSync(path.join(workspace, "inside.usda"), "#usda 1.0\n");
    writeFileSync(path.join(workspace, "texture.png"), "not-an-image");
    writeFileSync(path.join(outside, "outside.usda"), "#usda 1.0\n");

    const accepted = validateStagePath(workspace, "inside.usda");
    assert.match(accepted, /inside\.usda$/i);
    assert.throws(() => validateStagePath(workspace, path.join("..", "outside", "outside.usda")), /stay below workspaceRoot/);

    const junction = path.join(workspace, "escape");
    symlinkSync(outside, junction, "junction");
    assert.throws(() => validateStagePath(workspace, path.join("escape", "outside.usda")), /symbolic link, junction, or reparse point/);
    const listed = listWorkspaceUsdStages(workspace);
    assert.deepEqual(listed.stages, ["inside.usda"]);
    const assets = listWorkspaceAssets(workspace);
    assert.deepEqual(assets.assets, ["inside.usda", "texture.png"]);
  } finally {
    rmSync(temporaryRoot, { recursive: true, force: true });
  }
}

async function testMcpProtocol() {
  const child = spawn(process.execPath, ["./mcp/server.mjs"], {
    cwd: pluginRoot,
    stdio: ["pipe", "pipe", "pipe"]
  });

  let buffer = "";
  const replies = new Map();
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
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
  child.stderr.on("data", (chunk) => { stderr += chunk; });

  function request(id, method, params) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error("Timed out waiting for " + method + ". " + stderr)), 5_000);
      replies.set(id, (response) => {
        clearTimeout(timeout);
        replies.delete(id);
        resolve(response);
      });
      child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, ...(params ? { params } : {}) }) + "\n");
    });
  }

  try {
    const serverSource = readFileSync(path.join(pluginRoot, "mcp", "server.mjs"), "utf8");
    const launcherSource = readFileSync(path.join(pluginRoot, "mcp", "launch-hidden-kit.ps1"), "utf8");
    const identitySource = readFileSync(path.join(pluginRoot, "mcp", "process-identity.mjs"), "utf8");
    assert.match(serverSource, /CODEX_OMNIVERSE_CONTROL_TOKEN/);
    assert.doesNotMatch(serverSource, /controlToken=/);
    assert.match(serverSource, /stageOpenRequestTimeoutMs = 65_000/);
    assert.match(serverSource, /runtimePrepareStop/);
    assert.ok(integerConstant(serverSource, "runtimePrepareStopTimeoutMs") <= 10_000, "A single runtime.prepare_stop pass must return before an MCP client can time out.");
    assert.ok(integerConstant(serverSource, "stopBridgeReconnectWaitMs") <= 10_000, "The initial stop bridge reconnect wait must remain bounded for an interactive MCP response.");
    assert.equal(integerConstant(serverSource, "stopBridgePrepareAttempts"), 1, "Later prepare_stop retries belong to the background recovery scheduler, not the initial MCP response.");
    assert.ok(integerConstant(serverSource, "trackedProcessExitTimeoutMs") <= 15_000, "A verified process-exit wait must remain within the stop response budget.");
    assert.ok(integerConstant(serverSource, "streamStopTimeoutMs") <= 15_000, "The signaling-stop observation must remain within the stop response budget.");
    assert.ok(integerConstant(serverSource, "stopRequestClientTimeoutMs") < 45_000, "Stop must return a bounded pending response before the runtime test client deadline, even behind a slow save.");
    assert.match(serverSource, /prepareKitForStop/);
    assert.match(serverSource, /StopRecoveryScheduler/);
    assert.match(serverSource, /ensureStopRecovery/);
    assert.match(serverSource, /waitForTcpStop/);
    assert.match(serverSource, /identity_unverified/);
    assert.match(serverSource, /"stop_pending"/);
    assert.match(serverSource, /"stream_stop_timeout"/);
    assert.match(serverSource, /stopProcessIfIdentityMatches/);
    assert.doesNotMatch(serverSource, /process\.kill\(session\.pid\)/);
    assert.match(serverSource, /controlMethod\.stageOpen, \{ path: stagePath \}/);
    assert.match(launcherSource, /\$PidPath/);
    assert.match(launcherSource, /startedAtUtc/);
    assert.match(launcherSource, /startedAtFileTimeUtc/);
    assert.match(launcherSource, /ConvertTo-Json -Compress/);
    assert.match(launcherSource, /\$KitArgumentLine\.Trim\(\) \+ " --no-window"/);
    assert.doesNotMatch(launcherSource, /controlToken/i);
    assert.doesNotMatch(launcherSource, /Stop-Process/);
    assert.match(identitySource, /OpenProcess/);
    assert.match(identitySource, /GetProcessTimes/);
    assert.match(identitySource, /TerminateProcess/);
    assert.doesNotMatch(identitySource, /Stop-Process -Id/);
    const attachFunctionStart = serverSource.indexOf("async function attachRuntime(rawArgs)");
    const attachFunctionEnd = serverSource.indexOf("\nasync function stopRuntime(rawArgs)", attachFunctionStart);
    assert.ok(attachFunctionStart >= 0 && attachFunctionEnd > attachFunctionStart, "The managed-stream attach handler must remain a focused server operation.");
    const attachFunction = serverSource.slice(attachFunctionStart, attachFunctionEnd);
    assert.match(attachFunction, /assertEmptyArgs\(rawArgs\)/);
    assert.match(attachFunction, /reconcileRuntimeSession\(\)/);
    assert.match(attachFunction, /processOwnership !== "owned"/);
    assert.match(attachFunction, /\[widgetAccessTokenMetaKey\]: session\.streamAccessToken/);
    assert.doesNotMatch(attachFunction, /startHiddenKit|startRuntime\(|launchArgs|stage\.open|callKit|runKitMutation|controlServer|controlToken/);
    assert.equal((attachFunction.match(/sideEffectQueue\.isAdmissionClosed/g) || []).length, 2, "Attach must recheck stopped-session admission after its awaited status probe.");
    assert.equal((attachFunction.match(/session\.streamStopState !== "idle"/g) || []).length, 2, "Attach must not reissue a credential once safe stop begins during its status probe.");
    assert.match(serverSource, /const layout = session\?\.kitLayout \|\| runtimeLayout\(kitRootValue\);/);
    assert.match(serverSource, /kitLayout: \{\s*kitRoot: current\.kitRoot,\s*releaseRoot: current\.releaseRoot,\s*kitExe: current\.kitExe,\s*streamKit: current\.streamKit\s*\}/s);
    assert.match(serverSource, /OMNISTREAM_KIT_ROOT/, "The public plugin must use a portable Kit-root configuration.");
    const prohibitedKitPath = ["D:", "Programs"].join("/");
    assert.doesNotMatch(serverSource, new RegExp(prohibitedKitPath.replace("/", "\\\\/")), "The public plugin must not embed a machine-specific Kit root.");
    assert.match(serverSource, /streamKitRelative\.startsWith\("\.\."\) \|\| path\.isAbsolute\(streamKitRelative\)/, "The configured streaming .kit path must remain below the selected Kit release root.");
    const launchFunctionStart = serverSource.indexOf("async function launchConfiguredSimulation");
    const launchFunctionEnd = serverSource.indexOf("\nasync function superviseSimulation", launchFunctionStart);
    assert.ok(launchFunctionStart >= 0 && launchFunctionEnd > launchFunctionStart, "The simulation launch handler must remain a focused orchestration operation.");
    const launchFunction = serverSource.slice(launchFunctionStart, launchFunctionEnd);
    assert.match(launchFunction, /runExternalSideEffect\("simulation\.launch"/, "Configured launch must occupy one serialized side-effect slot.");
    assert.match(launchFunction, /startRuntimeLocked\(/, "Launch must use the locked runtime primitive while already inside the serial queue.");
    assert.match(launchFunction, /callKitMutation\(session, controlMethod\.stageOpen/, "Launch must open the configured stage inside the same serialized operation.");
    assert.match(launchFunction, /callKitMutation\(session, controlMethod\.simulationConfigure/, "Launch must apply simulation settings inside the same serialized operation.");
    assert.doesNotMatch(launchFunction, /await startRuntime\(|await loadStage\(|runKitMutation\(/, "Launch must not nest public queued mutations and create interleaving gaps.");

    const initialized = await request(1, "initialize", { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "test", version: "1" } });
    assert.equal(initialized.result.serverInfo.name, "omnistream-for-codex");
    child.stdin.write(JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) + "\n");

    const listedTools = await request(2, "tools/list");
    const names = new Set(listedTools.result.tools.map((item) => item.name));
    for (const name of [
      "open_omniverse_simulation_studio",
      "configure_omniverse_simulation",
      "preflight_omniverse_simulation",
      "launch_omniverse_simulation",
      "supervise_omniverse_simulation",
      "read_omnistream_runtime_logs",
      "control_omniverse_simulation",
      "attach_omniverse_stream",
      "discover_omniverse_local_assets",
      "start_omniverse_stream",
      "load_omniverse_stage",
      "get_omniverse_simulation_state",
      "control_omniverse_timeline",
      "list_omniverse_cameras",
      "select_omniverse_camera",
      "navigate_omniverse_camera",
      "save_omniverse_camera"
    ]) assert.ok(names.has(name), "Missing MCP tool " + name + ".");
    for (const item of listedTools.result.tools) {
      assert.equal(typeof item.name, "string", "Every MCP tool must expose a string name.");
      assert.equal(typeof item.title, "string", `${item.name} must expose a string title.`);
      assert.equal(typeof item.description, "string", `${item.name} must expose a string description.`);
      assert.equal(typeof item.inputSchema, "object", `${item.name} inputSchema must be a JSON Schema object.`);
      assert.notEqual(item.inputSchema, null, `${item.name} inputSchema must not be null.`);
      assert.ok(item.inputSchema.type === "object" || Array.isArray(item.inputSchema.oneOf), `${item.name} inputSchema must describe object arguments.`);
      assert.equal(typeof item.annotations?.readOnlyHint, "boolean", `${item.name} must declare readOnlyHint.`);
      assert.equal(typeof item.annotations?.destructiveHint, "boolean", `${item.name} must declare destructiveHint.`);
    }
    const openTool = listedTools.result.tools.find((item) => item.name === "open_omniverse_simulation_studio");
    assert.equal(openTool._meta.ui.resourceUri, "ui://omnistream-for-codex/panel.html");
    assert.equal(openTool._meta["openai/outputTemplate"], "ui://omnistream-for-codex/panel.html");
    assert.equal(openTool._meta["openai/widgetAccessible"], true);
    assert.ok(listedTools.result.tools.filter((item) => item.name !== "read_omniverse_live_telemetry").every((item) => item.annotations.openWorldHint === true), "Kit can resolve USD dependencies beyond the requested root, so its MCP tools must not claim a closed-world boundary.");
    assert.equal(listedTools.result.tools.find((item) => item.name === "save_omniverse_camera").annotations.destructiveHint, true);
    assert.equal(listedTools.result.tools.find((item) => item.name === "control_omniverse_timeline").inputSchema.additionalProperties, false);
    const superviseTool = listedTools.result.tools.find((item) => item.name === "supervise_omniverse_simulation");
    assert.equal(superviseTool.annotations.readOnlyHint, true, "Simulation supervision must be read-only.");
    assert.equal(listedTools.result.tools.find((item) => item.name === "preflight_omniverse_simulation").annotations.readOnlyHint, true, "Simulation preflight must be read-only.");
    assert.equal(listedTools.result.tools.find((item) => item.name === "read_omnistream_runtime_logs").annotations.readOnlyHint, true, "Runtime log access must be read-only.");
    const configureTool = listedTools.result.tools.find((item) => item.name === "configure_omniverse_simulation");
    assert.equal(configureTool.annotations.readOnlyHint, false, "Simulation configuration changes the MCP session draft.");
    assert.equal(configureTool.inputSchema.additionalProperties, false);
    const controlTool = listedTools.result.tools.find((item) => item.name === "control_omniverse_simulation");
    assert.equal(controlTool.inputSchema.additionalProperties, false);
    assert.ok(controlTool.inputSchema.properties.action.enum.includes("reset"));
    assert.ok(controlTool.inputSchema.properties.action.enum.includes("set_loop"));

    const attachTool = listedTools.result.tools.find((item) => item.name === "attach_omniverse_stream");
    assert.equal(attachTool.annotations.readOnlyHint, true, "Reattachment must not be advertised as a mutation.");
    assert.equal(attachTool.inputSchema.additionalProperties, false);
    assert.match(attachTool.description, /never starts Kit or changes USD/i);

    const resources = await request(3, "resources/list");
    assert.equal(resources.result.resources[0].uri, "ui://omnistream-for-codex/panel.html");

    const resource = await request(4, "resources/read", { uri: "ui://omnistream-for-codex/panel.html" });
    if (expectPanelBundle) {
      const html = resource.result.contents[0].text;
      assert.match(html, /remote-video/);
      assert.match(html, /<div id="root"><\/div>/);
      assert.match(html, /data-omniverse-panel-js/);
    } else {
      assert.equal(resource.error.code, -32000);
      assert.match(resource.error.message, /panel bundle is missing.*npm run build:web/i);
    }

    const open = await request(5, "tools/call", { name: "open_omniverse_simulation_studio", arguments: {} });
    assert.equal(open.result._meta["openai/outputTemplate"], "ui://omnistream-for-codex/panel.html");

    const simulationRoot = mkdtempSync(path.join(os.tmpdir(), "omnistream-simulation-config-"));
    const configuredStage = path.join(simulationRoot, "configured.usda");
    writeFileSync(configuredStage, "#usda 1.0\n");
    const configured = await request(20, "tools/call", {
      name: "configure_omniverse_simulation",
      arguments: {
        name: "Contract simulation",
        workspaceRoot: simulationRoot,
        stagePath: configuredStage,
        initialTimeSeconds: 1.25,
        rateMultiplier: 1.5,
        loop: true,
        playEveryFrame: true,
        autoPlay: false
      }
    });
    assert.equal(configured.result.structuredContent.configuration.name, "Contract simulation");
    assert.equal(configured.result.structuredContent.configuration.loop, true);
    assert.equal(configured.result.structuredContent.configuration.playEveryFrame, true);
    const simulationPreflight = await request(22, "tools/call", { name: "preflight_omniverse_simulation", arguments: {} });
    assert.equal(simulationPreflight.result.structuredContent.configuration.name, "Contract simulation");
    assert.ok(Array.isArray(simulationPreflight.result.structuredContent.checks));
    assert.ok(simulationPreflight.result.structuredContent.checks.some((item) => item.id === "stage" && item.ok === true));
    assert.ok(simulationPreflight.result.structuredContent.checks.some((item) => item.id === "workspace" && item.ok === true));
    assert.equal(typeof simulationPreflight.result.structuredContent.ready, "boolean");
    const noLogs = await request(23, "tools/call", { name: "read_omnistream_runtime_logs", arguments: { stream: "both", lines: 20 } });
    assert.equal(noLogs.result.structuredContent.runtimeActive, false);
    assert.equal(noLogs.result.structuredContent.lineLimit, 20);
    const supervised = await request(21, "tools/call", { name: "supervise_omniverse_simulation", arguments: {} });
    assert.equal(supervised.result.structuredContent.configuration.name, "Contract simulation");
    assert.equal(supervised.result.structuredContent.runtime.processAlive, false);
    assert.equal(supervised.result.structuredContent.health.simulation, "offline");
    rmSync(simulationRoot, { recursive: true, force: true });

    const noManagedSession = await request(50, "tools/call", { name: "attach_omniverse_stream", arguments: {} });
    assert.equal(noManagedSession.error.code, -32000);
    assert.match(noManagedSession.error.message, /Start the hidden Omniverse stream first/);
    assert.equal(Object.hasOwn(noManagedSession.error, "_meta"), false);
    assert.doesNotMatch(JSON.stringify(noManagedSession), /streamAccessToken|controlToken|credential|token|controlPort/i);

    const attachWithArguments = await request(51, "tools/call", {
      name: "attach_omniverse_stream",
      arguments: { workspaceRoot: "C:\\must-not-start-kit" }
    });
    assert.equal(attachWithArguments.error.code, -32000);
    assert.match(attachWithArguments.error.message, /Unexpected tool argument: workspaceRoot/);

    const statusAfterRejectedAttach = await request(52, "tools/call", { name: "get_omniverse_stream_status", arguments: {} });
    assert.equal(statusAfterRejectedAttach.result.structuredContent.processAlive, false, "A rejected attach must not launch Kit.");
    assert.equal(statusAfterRejectedAttach.result.structuredContent.processId, null, "A rejected attach must not create a managed runtime session.");
    assert.equal(Object.hasOwn(statusAfterRejectedAttach.result.structuredContent, "streamAccessToken"), false);
    assert.equal(Object.hasOwn(statusAfterRejectedAttach.result.structuredContent, "controlToken"), false);

    const unavailable = await request(6, "tools/call", { name: "get_omniverse_simulation_state", arguments: {} });
    assert.equal(unavailable.error.code, -32000);
    assert.match(unavailable.error.message, /Start the hidden Omniverse stream/);
    assert.doesNotMatch(unavailable.error.message, /token|stack|controlPort/i);

    const invalidTimeline = await request(7, "tools/call", {
      name: "control_omniverse_timeline",
      arguments: { action: "seek" }
    });
    assert.equal(invalidTimeline.error.code, -32000);
    assert.match(invalidTimeline.error.message, /timeSeconds/);

    const invalidNavigation = await request(8, "tools/call", {
      name: "navigate_omniverse_camera",
      arguments: { mode: "orbit", horizontal: 5 }
    });
    assert.equal(invalidNavigation.error.code, -32000);
    assert.match(invalidNavigation.error.message, /between -1 and 1/);

    const incompatibleNavigation = await request(9, "tools/call", {
      name: "navigate_omniverse_camera",
      arguments: { mode: "dolly", amount: 0.25, horizontal: 0 }
    });
    assert.equal(incompatibleNavigation.error.code, -32000);
    assert.match(incompatibleNavigation.error.message, /orbit or pan/);

    const preflight = await request(10, "tools/call", { name: "inspect_omniverse_stream_runtime", arguments: {} });
    assert.ok(Object.hasOwn(preflight.result.structuredContent, "runtimeReady"));
    assert.equal(Object.hasOwn(preflight.result.structuredContent, "controlToken"), false);
  } finally {
    child.kill();
  }
}

async function testStdinShutdown() {
  const child = spawn(process.execPath, ["./mcp/server.mjs"], {
    cwd: pluginRoot,
    stdio: ["pipe", "pipe", "pipe"]
  });
  let stderr = "";
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const exited = new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      child.kill();
      reject(new Error("MCP server did not close after stdin ended. " + stderr));
    }, 5_000);
    child.once("exit", (code, signal) => {
      clearTimeout(timeout);
      resolve({ code, signal });
    });
  });
  child.stdin.end();
  const result = await exited;
  assert.equal(result.signal, null);
  assert.equal(result.code, 0);
}

await testControlRpc();
await testSlowSaveQueueAndLifecycleBarrier();
await testBoundedStopPendingDoesNotHang();
await testBoundedStreamStopWait();
await testPrepareStopReconnectAfterEof();
await testProcessIdentitySafety();
testStagePathPolicy();
await testMcpProtocol();
await testStdinShutdown();
console.log("MCP protocol, local control bridge, and embedded WebRTC panel contract passed.");
