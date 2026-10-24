import { randomUUID } from 'node:crypto';

const MAX_MESSAGE_BYTES = 128 * 1024;
const MAX_QUEUE_BYTES = 512 * 1024;
const MAX_EVENTS = 256;

/** Kit signaling only. The caller never supplies a host, port or bearer. */
export class LocalSignalingRelay {
  constructor({ getSession, port, WebSocketClass = WebSocket, now = Date.now, idleMs = 30_000, getEndpoint }) {
    if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('Invalid Kit signaling port.');
    this.getSession = getSession;
    this.port = port;
    this.getEndpoint = getEndpoint;
    this.Socket = WebSocketClass;
    this.now = now;
    this.idleMs = idleMs;
    this.channels = new Map();
    this.timer = setInterval(() => this.expire(), 5_000);
    this.timer.unref?.();
  }

  session() {
    const session = this.getSession();
    if (!session?.identity || typeof session.token !== 'string' || !session.token) throw new Error('No owned Kit signaling session is available.');
    return session;
  }

  isCurrent(channel) {
    const session = this.getSession();
    return session?.identity === channel.identity && session?.token === channel.token;
  }

  enqueue(channel, event) {
    const size = typeof event.data === 'string' ? Buffer.byteLength(event.data) : 0;
    if (size > MAX_MESSAGE_BYTES || channel.bytes + size > MAX_QUEUE_BYTES || channel.events.length >= MAX_EVENTS) {
      channel.events = []; channel.bytes = 0;
      this.end(channel, 1009);
      return;
    }
    channel.events.push({ sequence: ++channel.sequence, ...event });
    channel.bytes += size;
    channel.wake?.();
  }

  end(channel, code = 1000) {
    if (channel.state === 'closed') return;
    channel.state = 'closed';
    // NVIDIA uses application close codes during signaling handoff/reconnect.
    // Replacing them with 1000 tells Kit to tear down the live media session.
    const wireCode = code === 1000 || (code >= 3000 && code <= 4999) ? code : 1000;
    try { channel.socket.close(wireCode); } catch { /* Already closed. */ }
    this.enqueue(channel, { type: 'close', code });
  }

  async open(peerId, { pairingId, reconnect = false, sessionId } = {}) {
    if (typeof peerId !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(peerId)) throw new Error('Invalid signaling peer identity.');
    for (const value of [pairingId, sessionId]) if (value !== undefined && (typeof value !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(value))) throw new Error('Invalid signaling pairing identity.');
    if (typeof reconnect !== 'boolean') throw new Error('Invalid reconnect flag.');
    this.expire();
    if (this.channels.size >= 2) throw new Error('Close the previous local signaling channel before reconnecting.');
    const session = this.session();
    const endpoint = this.getEndpoint ? this.getEndpoint() : `ws://127.0.0.1:${this.port}/sign_in`;
    const url = `${endpoint}?peer_id=${encodeURIComponent(peerId)}&version=2&peer_role=1${pairingId ? `&pairing_id=${encodeURIComponent(pairingId)}` : ''}${reconnect ? '&reconnect=1' : ''}`;
    const socket = new this.Socket(url, [...(sessionId ? [`x-nv-sessionid.${sessionId}`] : []),
      ...(session.authenticate === false ? [] : [`authorization.bearer.${session.token}`])]);
    const channel = { id: randomUUID(), identity: session.identity, token: session.token, socket,
      state: 'connecting', events: [], sequence: 0, lastClientSequence: 0, bytes: 0, touched: this.now(), polling: false, wake: null };
    this.channels.set(channel.id, channel);
    socket.addEventListener('message', event => {
      if (channel.state === 'closed') return;
      if (!this.isCurrent(channel)) { this.end(channel); return; }
      if (typeof event.data !== 'string') { this.end(channel, 1003); return; }
      this.enqueue(channel, { type: 'message', data: event.data });
    });
    socket.addEventListener('close', event => this.end(channel, event.code || 1006));
    socket.addEventListener('error', () => this.end(channel, 1006));
    try {
      await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => { this.end(channel); reject(new Error('Local Kit signaling timed out.')); }, 5_000);
        const finish = (error) => { clearTimeout(timeout); error ? reject(error) : resolve(); };
        socket.addEventListener('open', () => {
          if (!this.isCurrent(channel) || channel.state === 'closed') { this.end(channel); finish(new Error('The Kit session changed.')); return; }
          channel.state = 'open'; finish();
        }, { once: true });
        socket.addEventListener('error', () => finish(new Error('Local Kit signaling could not connect.')), { once: true });
        socket.addEventListener('close', () => finish(new Error('Local Kit signaling closed before opening.')), { once: true });
      });
      return { channelId: channel.id, state: channel.state };
    } catch (error) {
      this.end(channel); this.channels.delete(channel.id); throw error;
    }
  }

  async exchange({ channelId, afterSequence = 0, messages = [], waitMs = 750 }) {
    const channel = this.channels.get(channelId);
    if (!channel || !this.isCurrent(channel) || this.now() - channel.touched > this.idleMs) {
      if (channel) { this.end(channel); this.channels.delete(channel.id); }
      throw new Error('The local signaling channel expired or its Kit session changed.');
    }
    if (!Number.isInteger(afterSequence) || afterSequence < 0 || afterSequence > channel.sequence ||
      !Number.isInteger(waitMs) || waitMs < 0 || waitMs > 1_000 || !Array.isArray(messages) || messages.length > 16) throw new Error('Invalid signaling exchange.');
    if (channel.polling) throw new Error('A signaling exchange is already in progress.');
    // Validate the entire batch before sending any of it. Sequence numbers
    // make a retried MCP request safe after a response is lost.
    let expected = channel.lastClientSequence + 1;
    let batchBytes = 0;
    for (const message of messages) {
      if (!message || !Number.isSafeInteger(message.sequence) || message.sequence < 1 || typeof message.data !== 'string' || Buffer.byteLength(message.data) > MAX_MESSAGE_BYTES) throw new Error('Invalid signaling message.');
      batchBytes += Buffer.byteLength(message.data);
      if (batchBytes > MAX_QUEUE_BYTES) throw new Error('Signaling batch exceeds its bound.');
      if (message.sequence <= channel.lastClientSequence) continue;
      if (message.sequence !== expected++) throw new Error('Signaling message sequence changed.');
    }
    channel.touched = this.now();
    channel.events = channel.events.filter(event => event.sequence > afterSequence);
    channel.bytes = channel.events.reduce((sum, event) => sum + (event.data ? Buffer.byteLength(event.data) : 0), 0);
    for (const message of messages) {
      if (message.sequence <= channel.lastClientSequence) continue;
      if (channel.state !== 'open') throw new Error('Local Kit signaling is closed.');
      channel.socket.send(message.data); channel.lastClientSequence = message.sequence;
    }
    channel.polling = true;
    try {
      if (!channel.events.length && channel.state === 'open' && waitMs) await new Promise(resolve => {
        const timer = setTimeout(resolve, waitMs);
        channel.wake = () => { clearTimeout(timer); resolve(); };
      });
      if (!this.isCurrent(channel)) { this.end(channel); throw new Error('The Kit session changed.'); }
      return { channelId, state: channel.state, ackClientSequence: channel.lastClientSequence, events: [...channel.events] };
    } finally { channel.polling = false; channel.wake = null; }
  }

  close(channelId, code = 1000) {
    if (!Number.isInteger(code) || (code !== 1000 && (code < 3000 || code > 4999)))
      throw new Error('Invalid signaling close code.');
    const channel = this.channels.get(channelId);
    if (channel) { this.end(channel, code); this.channels.delete(channelId); }
    return { state: 'closed' };
  }

  expire() {
    for (const channel of this.channels.values()) if (!this.isCurrent(channel) || this.now() - channel.touched > this.idleMs) this.close(channel.id);
  }

  closeAll() { for (const id of this.channels.keys()) this.close(id); }
  dispose() { this.closeAll(); clearInterval(this.timer); }
}
