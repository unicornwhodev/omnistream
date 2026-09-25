import { ControlRpcError } from "./control-rpc.mjs";

export class PrepareStopPendingError extends Error {
  constructor(message, attempts, lastCode = "bridge_not_connected") {
    super(message);
    this.name = "PrepareStopPendingError";
    this.code = "stop_pending";
    this.attempts = attempts;
    this.lastCode = lastCode;
  }
}

const transientStopCodes = new Set([
  "stop_pending",
  "identity_unverified",
  "stop_failed",
  "shutdown_timeout",
  "stop_timeout",
  "stream_stop_timeout",
  "bridge_not_connected",
  "bridge_unavailable",
  "bridge_disconnected",
  "bridge_closed",
  "request_timeout"
]);

export function isTransientStopError(error) {
  return Boolean(error && typeof error === "object" && transientStopCodes.has(error.code));
}

function assertInteger(value, label, minimum, maximum) {
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error(label + " must be an integer between " + minimum + " and " + maximum + ".");
  }
  return value;
}

export function isRetryablePrepareStopError(error) {
  return error instanceof ControlRpcError && new Set([
    "bridge_unavailable",
    "bridge_disconnected",
    "bridge_closed",
    "request_timeout"
  ]).has(error.code);
}

/**
 * Establish the Kit-side stop barrier across transient local-control bridge
 * disconnects. Each wait and request is bounded. Callers may schedule a fresh
 * bounded pass later (EOF recovery does this automatically) without ever
 * killing the process before the bridge has acknowledged prepare_stop.
 */
export async function prepareKitForStop(controlServer, {
  method = "runtime.prepare_stop",
  reconnectWaitMs = 15_000,
  completionTimeoutMs = 180_000,
  maxAttempts = 3,
  onState = () => {}
} = {}) {
  if (!controlServer || typeof controlServer.waitForConnection !== "function" || typeof controlServer.startRequest !== "function") {
    throw new Error("An authenticated loopback control server is required.");
  }
  if (method !== "runtime.prepare_stop") throw new Error("Only runtime.prepare_stop may establish the lifecycle stop barrier.");
  assertInteger(reconnectWaitMs, "reconnectWaitMs", 1, 180_000);
  assertInteger(completionTimeoutMs, "completionTimeoutMs", 100, 180_000);
  assertInteger(maxAttempts, "maxAttempts", 1, 32);

  let lastCode = "bridge_not_connected";
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    if (!controlServer.isConnected) {
      onState({ state: "waiting_for_bridge", attempt, lastCode });
      const connected = await controlServer.waitForConnection(reconnectWaitMs);
      if (!connected) {
        lastCode = "bridge_not_connected";
        continue;
      }
    }
    onState({ state: "preparing_stop", attempt, lastCode });
    try {
      const request = controlServer.startRequest(method, {}, {
        clientTimeoutMs: completionTimeoutMs,
        completionTimeoutMs
      });
      const response = await request.completion;
      onState({ state: "prepared", attempt, lastCode: null });
      return { response, attempts: attempt };
    } catch (error) {
      if (!isRetryablePrepareStopError(error)) throw error;
      lastCode = error.code;
      onState({ state: "bridge_retry", attempt, lastCode });
    }
  }
  onState({ state: "stop_pending", attempt: maxAttempts, lastCode });
  throw new PrepareStopPendingError(
    "The hidden Kit control bridge did not reconnect and confirm runtime.prepare_stop in the bounded retry window.",
    maxAttempts,
    lastCode
  );
}

/**
 * Schedules bounded stop passes without holding an MCP response or a serial
 * queue entry open between attempts. The caller owns the actual stop pass;
 * this scheduler merely retries errors that are safe to retry and keeps an
 * explicit state callback for status reporting.
 */
export class StopRecoveryScheduler {
  constructor({
    runPass,
    retryDelayMs = 2_000,
    isRecoverable = isTransientStopError,
    onState = () => {}
  } = {}) {
    if (typeof runPass !== "function") throw new Error("A bounded stop pass callback is required.");
    if (typeof isRecoverable !== "function") throw new Error("A stop recoverability predicate is required.");
    assertInteger(retryDelayMs, "retryDelayMs", 1, 180_000);
    this.runPass = runPass;
    this.retryDelayMs = retryDelayMs;
    this.isRecoverable = isRecoverable;
    this.onState = onState;
    this.attempt = 0;
    this.timer = null;
    this.finished = false;
    this.promise = null;
    this.resolve = null;
    this.reject = null;
  }

  start() {
    if (this.promise) return this.promise;
    this.promise = new Promise((resolve, reject) => {
      this.resolve = resolve;
      this.reject = reject;
    });
    queueMicrotask(() => { void this.#run(); });
    return this.promise;
  }

  cancel(reason = new Error("Safe stop recovery was cancelled.")) {
    if (this.finished) return;
    this.finished = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.reject(reason);
  }

  async #run() {
    if (this.finished) return;
    this.attempt += 1;
    this.onState({ state: "recovery_attempt", attempt: this.attempt, lastCode: null });
    try {
      const value = await this.runPass(this.attempt);
      if (this.finished) return;
      this.finished = true;
      this.resolve(value);
    } catch (error) {
      if (this.finished) return;
      if (!this.isRecoverable(error)) {
        this.finished = true;
        this.reject(error);
        return;
      }
      const code = typeof error?.code === "string" ? error.code : "stop_pending";
      this.onState({ state: "recovery_wait", attempt: this.attempt, lastCode: code });
      this.timer = setTimeout(() => {
        this.timer = null;
        void this.#run();
      }, this.retryDelayMs);
    }
  }
}
