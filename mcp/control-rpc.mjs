import { randomBytes, timingSafeEqual } from "node:crypto";
import net from "node:net";

export const CONTROL_PROTOCOL_VERSION = 1;
export const DEFAULT_MAX_MESSAGE_BYTES = 64 * 1024;
export const DEFAULT_REQUEST_TIMEOUT_MS = 8_000;

export class ControlRpcError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "ControlRpcError";
    this.code = code;
  }
}

function safeErrorMessage(value, fallback) {
  if (typeof value !== "string" || !value.trim()) return fallback;
  return value.trim().slice(0, 320);
}

function isJsonObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function encodeLine(value, maxMessageBytes) {
  const text = JSON.stringify(value);
  if (Buffer.byteLength(text, "utf8") > maxMessageBytes) {
    throw new ControlRpcError("message_too_large", "The local Kit control message exceeded the permitted size.");
  }
  return text + "\n";
}

function clientView(completion, method, timeoutMs) {
  if (!timeoutMs) return completion;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new ControlRpcError("client_timeout", "The hidden Kit runtime is still completing " + method + "."));
    }, timeoutMs);
    completion.then(
      (value) => {
        clearTimeout(timeout);
        resolve(value);
      },
      (error) => {
        clearTimeout(timeout);
        reject(error);
      }
    );
  });
}

function tokenMatches(expected, supplied) {
  const expectedBuffer = Buffer.from(expected, "utf8");
  const suppliedRaw = Buffer.from(typeof supplied === "string" ? supplied : "", "utf8");
  // Compare exactly the expected number of bytes even when the supplied token
  // has another length. The protocol limits an input line to 64 KiB, so this
  // fixed-size copy avoids an attacker-controlled allocation while preserving
  // a constant-time credential comparison.
  const suppliedBuffer = Buffer.alloc(expectedBuffer.length);
  suppliedRaw.copy(suppliedBuffer, 0, 0, expectedBuffer.length);
  return typeof supplied === "string" && suppliedRaw.length === expectedBuffer.length && timingSafeEqual(expectedBuffer, suppliedBuffer);
}

/**
 * A one-bridge, authenticated JSONL channel. The MCP process owns the listener
 * on the IPv4 loopback interface; Kit connects outward after it has started.
 * Keeping the token in this object prevents it from becoming tool output.
 */
export class LoopbackControlServer {
  constructor({
    host = "127.0.0.1",
    token = randomBytes(32).toString("base64url"),
    maxMessageBytes = DEFAULT_MAX_MESSAGE_BYTES,
    requestTimeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
    requestTimeouts = {},
    onEvent = () => {},
    handshakeTimeoutMs = 8_000
  } = {}) {
    if (host !== "127.0.0.1") throw new ControlRpcError("invalid_host", "The Kit control listener must use IPv4 loopback.");
    if (typeof token !== "string" || token.length < 32) throw new ControlRpcError("invalid_token", "A session control credential is required.");
    this.onEvent = onEvent;
    this.host = host;
    this.token = token;
    this.maxMessageBytes = maxMessageBytes;
    this.requestTimeoutMs = requestTimeoutMs;
    this.requestTimeouts = new Map(Object.entries(requestTimeouts));
    this.handshakeTimeoutMs = handshakeTimeoutMs;
    this.server = null;
    this.socket = null;
    this.pendingSockets = new Set();
    this.pending = new Map();
    this.connectionWaiters = new Set();
    this.sequence = 0;
    this.closed = false;
    this.port = null;
  }

  get isListening() {
    return Boolean(this.server?.listening);
  }

  get isConnected() {
    return Boolean(this.socket && !this.socket.destroyed);
  }

  /** Settings are for the local Kit process only. Never return this object from a tool. */
  get launchSettings() {
    if (!this.isListening || !this.port) throw new ControlRpcError("not_listening", "The local Kit control listener is not ready.");
    return { host: this.host, port: this.port, token: this.token };
  }

  async start() {
    if (this.closed) throw new ControlRpcError("closed", "The local Kit control listener is closed.");
    if (this.isListening) return this;
    this.server = net.createServer((socket) => this.#accept(socket));
    // A bad local client must not block the authenticated Kit bridge during
    // its handshake timeout. Only one authenticated socket can ever win.
    this.server.maxConnections = 16;
    this.server.on("error", () => {
      // Requests and lifecycle callers receive a bounded generic error. Do not
      // forward node network diagnostics, which can include process arguments.
      this.#rejectPending(new ControlRpcError("bridge_unavailable", "The local Kit control bridge is unavailable."));
    });
    await new Promise((resolve, reject) => {
      const onError = () => {
        this.server?.off("listening", onListening);
        reject(new ControlRpcError("listener_failed", "The local Kit control listener could not start."));
      };
      const onListening = () => {
        this.server?.off("error", onError);
        const address = this.server?.address();
        if (!address || typeof address === "string" || address.address !== this.host || !Number.isInteger(address.port)) {
          reject(new ControlRpcError("listener_failed", "The local Kit control listener did not bind IPv4 loopback."));
          return;
        }
        this.port = address.port;
        resolve();
      };
      this.server?.once("error", onError);
      this.server?.once("listening", onListening);
      this.server?.listen({ host: this.host, port: 0, exclusive: true });
    });
    return this;
  }

  startRequest(method, params = {}, { clientTimeoutMs, completionTimeoutMs } = {}) {
    if (this.closed || !this.isConnected) {
      throw new ControlRpcError("bridge_unavailable", "The hidden Kit runtime is not connected to its local control bridge yet.");
    }
    if (typeof method !== "string" || !method) throw new ControlRpcError("invalid_method", "A Kit control method is required.");
    if (!isJsonObject(params)) throw new ControlRpcError("invalid_params", "Kit control parameters must be an object.");
    const hardTimeoutMs = completionTimeoutMs ?? this.requestTimeouts.get(method) ?? this.requestTimeoutMs;
    const visibleTimeoutMs = clientTimeoutMs ?? hardTimeoutMs;
    if (!Number.isInteger(hardTimeoutMs) || hardTimeoutMs < 100 || hardTimeoutMs > 180_000) {
      throw new ControlRpcError("invalid_timeout", "The local Kit control request timeout is invalid.");
    }
    if (!Number.isInteger(visibleTimeoutMs) || visibleTimeoutMs < 0 || visibleTimeoutMs > hardTimeoutMs) {
      throw new ControlRpcError("invalid_timeout", "The local Kit client timeout is invalid.");
    }
    const id = `${++this.sequence}-${randomBytes(8).toString("hex")}`;
    const line = encodeLine({ type: "request", id, method, params }, this.maxMessageBytes);
    const completion = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new ControlRpcError("request_timeout", "The hidden Kit runtime did not complete the control request in time."));
      }, hardTimeoutMs);
      this.pending.set(id, { resolve, reject, timeout });
      this.socket.write(line, (error) => {
        if (!error) return;
        const pending = this.pending.get(id);
        if (!pending) return;
        clearTimeout(pending.timeout);
        this.pending.delete(id);
        reject(new ControlRpcError("bridge_unavailable", "The local Kit control bridge disconnected while sending a request."));
      });
    });
    // Completion is deliberately observed internally even if a caller chooses
    // a shorter client timeout. A late bridge response can then settle the
    // serialized mutation instead of being abandoned.
    void completion.catch(() => {});
    const client = clientView(completion, method, visibleTimeoutMs);
    // A JSON-RPC caller can attach its handler after a short event-loop turn.
    // Observe the client view internally so its timeout never becomes an
    // unhandled rejection while the real completion remains tracked above.
    void client.catch(() => {});
    return {
      id,
      completion,
      client
    };
  }

  async request(method, params = {}, options = {}) {
    return this.startRequest(method, params, options).client;
  }

  /**
   * Wait for the next authenticated Kit bridge without polling the listener.
   * A disconnect does not resolve existing waiters: Kit may reconnect with the
   * same session credential while a safe lifecycle operation is pending.
   */
  waitForConnection(timeoutMs = 0) {
    if (this.closed) return Promise.resolve(false);
    if (this.isConnected) return Promise.resolve(true);
    if (!Number.isInteger(timeoutMs) || timeoutMs < 0 || timeoutMs > 180_000) {
      throw new ControlRpcError("invalid_timeout", "The local Kit connection wait timeout is invalid.");
    }
    return new Promise((resolve) => {
      const waiter = {
        timer: null,
        resolve: (connected) => {
          if (!this.connectionWaiters.delete(waiter)) return;
          if (waiter.timer) clearTimeout(waiter.timer);
          resolve(connected);
        }
      };
      if (timeoutMs) waiter.timer = setTimeout(() => waiter.resolve(false), timeoutMs);
      this.connectionWaiters.add(waiter);
    });
  }

  async close() {
    if (this.closed) return;
    this.closed = true;
    this.#rejectPending(new ControlRpcError("bridge_closed", "The local Kit control bridge was stopped."));
    this.#resolveConnectionWaiters(false);
    for (const socket of [this.socket, ...this.pendingSockets]) {
      if (socket && !socket.destroyed) socket.destroy();
    }
    this.socket = null;
    this.pendingSockets.clear();
    if (!this.server) return;
    const server = this.server;
    this.server = null;
    this.port = null;
    if (!server.listening) return;
    await new Promise((resolve) => server.close(() => resolve()));
  }

  #accept(socket) {
    if (this.closed || this.isConnected) {
      socket.destroy();
      return;
    }
    // Keep a bounded pre-authentication set without letting its oldest silent
    // members reserve every connection slot. A legitimate Kit hello arriving
    // after six mute peers therefore still gets a chance to authenticate.
    while (this.pendingSockets.size >= 6) {
      const oldest = this.pendingSockets.values().next().value;
      this.pendingSockets.delete(oldest);
      if (oldest && !oldest.destroyed) oldest.destroy();
    }
    this.pendingSockets.add(socket);
    socket.setNoDelay(true);
    socket.setTimeout(this.handshakeTimeoutMs, () => this.#closeHandshake(socket));
    let authenticated = false;
    this.#consume(socket, (message) => {
      if (!authenticated) {
        authenticated = this.#handleHandshake(socket, message);
        return;
      }
      this.#handleResponse(socket, message);
    });
    socket.once("close", () => {
      this.pendingSockets.delete(socket);
      if (this.socket === socket) {
        this.socket = null;
        this.#rejectPending(new ControlRpcError("bridge_disconnected", "The local Kit control bridge disconnected."));
      }
    });
    socket.once("error", () => {
      // close handler provides the bounded failure to pending callers.
    });
  }

  #consume(socket, onMessage) {
    let buffered = "";
    socket.setEncoding("utf8");
    socket.on("data", (chunk) => {
      buffered += chunk;
      if (Buffer.byteLength(buffered, "utf8") > this.maxMessageBytes) {
        socket.destroy();
        return;
      }
      let separator;
      while ((separator = buffered.indexOf("\n")) >= 0) {
        const line = buffered.slice(0, separator);
        buffered = buffered.slice(separator + 1);
        if (!line.trim()) continue;
        if (Buffer.byteLength(line, "utf8") > this.maxMessageBytes) {
          socket.destroy();
          return;
        }
        let message;
        try {
          message = JSON.parse(line);
        } catch {
          socket.destroy();
          return;
        }
        if (!isJsonObject(message)) {
          socket.destroy();
          return;
        }
        onMessage(message);
        if (socket.destroyed) return;
      }
    });
  }

  #handleHandshake(socket, message) {
    if (this.closed || (this.socket && this.socket !== socket)) {
      socket.destroy();
      return false;
    }
    const authorized = message.type === "hello" && message.protocol === CONTROL_PROTOCOL_VERSION && tokenMatches(this.token, message.token);
    if (!authorized) {
      try {
        socket.end(encodeLine({ type: "hello", ok: false, error: { code: "unauthorized", message: "Control bridge authentication failed." } }, this.maxMessageBytes), () => socket.destroy());
      } catch {
        socket.destroy();
      }
      return false;
    }
    socket.setTimeout(0);
    for (const pendingSocket of this.pendingSockets) {
      if (pendingSocket !== socket && !pendingSocket.destroyed) pendingSocket.destroy();
    }
    this.pendingSockets.delete(socket);
    this.socket = socket;
    this.#resolveConnectionWaiters(true);
    try {
      socket.write(encodeLine({ type: "hello", ok: true, protocol: CONTROL_PROTOCOL_VERSION }, this.maxMessageBytes));
    } catch {
      socket.destroy();
      return false;
    }
    return true;
  }

  #handleResponse(socket, message) {
    if (isJsonObject(message) && message.type === "event" && isJsonObject(message.event)) {
      try { this.onEvent(message.event); } catch { /* Observability must not kill control. */ }
      return;
    }
    if (!isJsonObject(message) || message.type !== "response" || typeof message.id !== "string") {
      socket.destroy();
      return;
    }
    const pending = this.pending.get(message.id);
    if (!pending) return;
    clearTimeout(pending.timeout);
    this.pending.delete(message.id);
    if (message.ok === true && isJsonObject(message.result)) {
      pending.resolve(message.result);
      return;
    }
    const code = isJsonObject(message.error) && typeof message.error.code === "string" ? message.error.code : "command_failed";
    const detail = isJsonObject(message.error) ? safeErrorMessage(message.error.message, "The hidden Kit runtime rejected the control request.") : "The hidden Kit runtime rejected the control request.";
    pending.reject(new ControlRpcError(code, detail));
  }

  #closeHandshake(socket) {
    if (this.pendingSockets.has(socket) && !this.socket) socket.destroy();
  }

  #rejectPending(error) {
    for (const [id, pending] of this.pending) {
      clearTimeout(pending.timeout);
      this.pending.delete(id);
      pending.reject(error);
    }
  }

  #resolveConnectionWaiters(connected) {
    for (const waiter of [...this.connectionWaiters]) waiter.resolve(connected);
  }
}
