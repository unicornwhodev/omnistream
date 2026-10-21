type Invoke = (name: string, args: Record<string, unknown>) => Promise<Record<string, unknown>>;
type PendingMessage = { sequence: number; data: string };

/** WebSocket interface for the unchanged NVIDIA client's signaling only.
 * MCP carries SDP/ICE; RTCPeerConnection still carries real Kit video/input.
 */
export class McpSignalingSocket extends EventTarget {
  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSING = 2;
  readonly CLOSED = 3;
  readonly url: string;
  readonly protocol = "";
  readonly extensions = "";
  binaryType: BinaryType = "blob";
  readyState = 0;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  private invoke: Invoke;
  private channelId: string | null = null;
  private pending: PendingMessage[] = [];
  private sentSequence = 0;
  private receivedSequence = 0;
  private finished = false;
  private onFinished: () => void;
  private onDiagnostic: (code: string) => void;
  private sessionId: string | undefined;
  private diagnosticPackets: boolean;

  constructor(url: string, invoke: Invoke, onFinished: () => void = () => {}, onDiagnostic: (code: string) => void = () => {}, sessionId?: string, diagnosticPackets = false) {
    super(); this.url = url; this.invoke = invoke; this.onFinished = onFinished; this.onDiagnostic = onDiagnostic;
    this.sessionId = sessionId; this.diagnosticPackets = diagnosticPackets;
    void this.run();
  }

  get bufferedAmount() { return this.pending.reduce((sum, message) => sum + new TextEncoder().encode(message.data).length, 0); }

  send(data: string | ArrayBufferLike | Blob | ArrayBufferView) {
    if (this.readyState === this.CONNECTING) throw new DOMException("Signaling is connecting.", "InvalidStateError");
    if (this.readyState !== this.OPEN) return;
    if (typeof data !== "string" || new TextEncoder().encode(data).length > 128 * 1024 || this.bufferedAmount + new TextEncoder().encode(data).length > 512 * 1024 || this.pending.length >= 256) {
      this.fail(); return;
    }
    this.pending.push({ sequence: ++this.sentSequence, data });
    this.packetDiagnostic("out", data);
  }

  close(code = 1000, reason = "") {
    if (code !== 1000 && (code < 3000 || code > 4999)) throw new DOMException("Invalid close code.", "InvalidAccessError");
    if (new TextEncoder().encode(reason).length > 123) throw new DOMException("Close reason is too long.", "SyntaxError");
    if (this.finished || this.readyState === this.CLOSING) return;
    this.readyState = this.CLOSING;
    // Native WebSocket.close() never dispatches onclose inside its caller's
    // stack. The NVIDIA client clears its old socket after calling close.
    queueMicrotask(() => this.finish(code, true));
  }

  private emit(type: "open" | "error", event: Event): void;
  private emit(type: "message", event: MessageEvent): void;
  private emit(type: "close", event: CloseEvent): void;
  private emit(type: string, event: Event) {
    this.dispatchEvent(event);
    if (type === "open") this.onopen?.(event);
    else if (type === "error") this.onerror?.(event);
    else if (type === "message") this.onmessage?.(event as MessageEvent);
    else if (type === "close") this.onclose?.(event as CloseEvent);
  }

  private finish(code: number, wasClean: boolean) {
    if (this.finished) return;
    this.finished = true; this.readyState = this.CLOSED; this.pending = [];
    const event = new Event("close") as CloseEvent;
    Object.defineProperties(event, { code: { value: code }, reason: { value: "" }, wasClean: { value: wasClean } });
    this.emit("close", event); this.onFinished();
    if (this.channelId) void this.invoke("close_omniverse_signaling", { channelId: this.channelId }).catch(() => {});
  }

  private fail() {
    if (this.finished) return;
    this.emit("error", new Event("error"));
    this.finish(1006, false);
  }

  private packetDiagnostic(direction: string, data: string) {
    if (!this.diagnosticPackets) return;
    try {
      const value = JSON.parse(data);
      // Protocol field names only. No SDP, ICE password, bearer, session ID,
      // peer ID or other field value is included in a diagnostic message.
      const fields = Object.keys(value).filter(key => /^[A-Za-z_][A-Za-z0-9_]{0,39}$/.test(key)).slice(0, 20);
      const inner = typeof value.peer_msg?.msg === "string" ? JSON.parse(value.peer_msg.msg) : value;
      const innerFields = inner === value ? [] : Object.keys(inner).filter(key => /^[A-Za-z_][A-Za-z0-9_]{0,39}$/.test(key)).slice(0, 20);
      const kind = inner.type ?? inner.messageType;
      const known = ["offer", "answer", "iceCandidate", "candidate", "close", "start", "stop", "error", "success", "connect", "connected", "disconnect", "request", "response", "status", "ping", "pong"];
      const type = Number.isInteger(kind) && kind >= 0 && kind <= 255 ? String(kind) : known.includes(kind) ? kind : "other";
      const code = typeof inner.code === "number" && Number.isSafeInteger(inner.code) && inner.code >= 0 && inner.code <= 4294967295 ? `_code_${inner.code}` : "";
      this.onDiagnostic(`packet_${direction}_${type}_${fields.join("_")}${innerFields.length ? `_body_${innerFields.join("_")}` : ""}${code}`);
    } catch { this.onDiagnostic(`packet_${direction}_non_json`); }
  }

  private async run() {
    try {
      const url = new URL(this.url);
      const peerId = url.searchParams.get("peer_id");
      const pairingId = url.searchParams.get("pairing_id");
      if (this.diagnosticPackets) this.onDiagnostic(`options_pairing_${Boolean(pairingId)}_session_${Boolean(this.sessionId)}`);
      const opened = await this.invoke("open_omniverse_signaling", { peerId,
        ...(pairingId ? { pairingId } : {}), ...(this.sessionId ? { sessionId: this.sessionId } : {}),
        ...(url.searchParams.get("reconnect") === "1" ? { reconnect: true } : {}) });
      if (typeof opened.channelId !== "string" || opened.state !== "open") throw new Error("Invalid private signaling response.");
      this.channelId = opened.channelId;
      if (this.finished || this.readyState === this.CLOSING) { await this.invoke("close_omniverse_signaling", { channelId: this.channelId }); return; }
      this.readyState = this.OPEN; this.emit("open", new Event("open"));
      while (!this.finished && this.readyState !== this.CLOSING) {
        const payload = await this.invoke("exchange_omniverse_signaling", {
          channelId: this.channelId, afterSequence: this.receivedSequence,
          messages: this.pending.slice(0, 16), waitMs: 750,
        });
        if (this.finished) return;
        if (payload.channelId !== this.channelId || !Array.isArray(payload.events) ||
          !Number.isSafeInteger(payload.ackClientSequence) || (payload.ackClientSequence as number) > this.sentSequence || (payload.ackClientSequence as number) < 0)
          throw new Error("Invalid private signaling exchange.");
        this.pending = this.pending.filter(message => message.sequence > (payload.ackClientSequence as number));
        for (const event of payload.events) {
          if (!event || !Number.isSafeInteger(event.sequence)) throw new Error("Invalid signaling event.");
          if (event.sequence <= this.receivedSequence) continue;
          if (event.sequence !== this.receivedSequence + 1) throw new Error("Signaling event gap.");
          this.receivedSequence = event.sequence;
          if (event.type === "message" && typeof event.data === "string") { this.packetDiagnostic("in", event.data); this.emit("message", new MessageEvent("message", { data: event.data })); }
          else if (event.type === "close") { if (event.code !== 1000) this.onDiagnostic(`remote_close_${event.code || 1006}`); this.finish(event.code || 1006, event.code === 1000); break; }
          else throw new Error("Invalid signaling event type.");
        }
        if (payload.state === "closed" && !this.finished) this.finish(1006, false);
      }
    } catch (error) {
      const known: Record<string, string> = {
        "Invalid private signaling response.": "private_response_invalid",
        "Invalid private signaling exchange.": "private_exchange_invalid",
        "Invalid signaling event.": "event_invalid",
        "Signaling event gap.": "event_sequence_gap",
        "Invalid signaling event type.": "event_type_invalid",
      };
      if (!this.finished) this.onDiagnostic(known[error instanceof Error ? error.message : ""] || "mcp_exchange_failed");
      this.fail();
    }
  }
}

export function isOwnedSignalingUrl(value: unknown, port: number) {
  try {
    const url = new URL(String(value));
    const peer = url.searchParams.get("peer_id");
    const keys = new Set<string>();
    let validKeys = true;
    url.searchParams.forEach((_value, key) => {
      if (keys.has(key) || !["peer_id", "version", "peer_role", "reconnect", "pairing_id"].includes(key)) validKeys = false;
      keys.add(key);
    });
    return url.protocol === "ws:" && url.hostname === "127.0.0.1" && url.port === String(port) &&
      url.pathname === "/sign_in" && !url.username && !url.password && !url.hash &&
      url.searchParams.get("version") === "2" && url.searchParams.get("peer_role") === "1" &&
      peer !== null && /^[A-Za-z0-9_-]{1,128}$/.test(peer) &&
      validKeys;
  } catch { return false; }
}

/** Isolated panel realm only. Other URLs retain the native browser constructor.
 * Bearer subprotocols are deliberately not copied into MCP tool arguments.
 */
export function installMcpSignaling(target: { WebSocket: typeof WebSocket }, port: number, invoke: Invoke, onDiagnostic: (code: string) => void = () => {}, diagnosticPackets = false) {
  const native = target.WebSocket;
  const sockets = new Set<McpSignalingSocket>();
  const routed = new Proxy(native, {
    construct(constructor, args) {
      if (!isOwnedSignalingUrl(args[0], port)) return Reflect.construct(constructor, args);
      const protocols = typeof args[1] === "string" ? [args[1]] : Array.isArray(args[1]) ? args[1] : [];
      const session = protocols.find((value: unknown) => typeof value === "string" && value.startsWith("x-nv-sessionid."));
      const sessionId = typeof session === "string" ? session.slice("x-nv-sessionid.".length) : undefined;
      let socket: McpSignalingSocket;
      socket = new McpSignalingSocket(String(args[0]), invoke, () => sockets.delete(socket), onDiagnostic, sessionId, diagnosticPackets);
      sockets.add(socket); return socket;
    },
  });
  target.WebSocket = routed;
  const closeAll = () => { for (const socket of sockets) socket.close(); sockets.clear(); };
  return { closeAll, dispose: () => { closeAll(); if (target.WebSocket === routed) target.WebSocket = native; } };
}
