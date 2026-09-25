import { randomUUID } from "node:crypto";
/** Isolated per-runtime event cache. No model notifications or unbounded queues. */
export class LiveEventStore {
  constructor(capacity = 500, now = Date.now) {
    this.cacheId = randomUUID();
    this.capacity = capacity;
    this.now = now;
    this.events = [];
    this.latest = null;
    this.sequence = 0;
    this.dropped = 0;
    this.receivedAt = null;
  }
  accept(event) {
    if (!event || !["telemetry", "log", "command", "stage_changed", "patch_applied", "patch_undone", "patch_discarded", "patch_exported", "run_started", "guard_paused", "telemetry_error"].includes(event.kind)) return;
    if (!Number.isSafeInteger(event.sequence) || !Number.isFinite(event.atUnixMs) || !event.data || typeof event.data !== "object" || Array.isArray(event.data)) return;
    if (JSON.stringify(event).length > 32 * 1024) return;
    const receivedAtUnixMs = this.now();
    const entry = { ...event, bridgeSequence: event.sequence, sequence: ++this.sequence, receivedAtUnixMs };
    if (event.kind === "telemetry") {
      this.latest = entry.data;
      this.receivedAt = receivedAtUnixMs;
    }
    this.events.push(entry);
    if (this.events.length > this.capacity) { this.events.shift(); this.dropped++; }
  }
  read({ afterSequence = 0, limit = 50 } = {}, connected = false) {
    if (afterSequence > this.sequence) afterSequence = 0;
    const events = this.events.filter(e => e.sequence > afterSequence).slice(0, limit);
    const ageMs = this.receivedAt === null ? null : Math.max(0, this.now() - this.receivedAt);
    return {
      cacheId: this.cacheId, connected, latest: this.latest, ageMs, stale: !connected || ageMs === null || ageMs > 2500,
      events, nextSequence: events.at(-1)?.sequence ?? afterSequence,
      moreAvailable: Boolean(events.length && events.at(-1).sequence < this.sequence),
      cursorGap: Boolean(this.events.length && afterSequence < this.events[0].sequence - 1),
      cacheDropped: this.dropped, sampleHz: 4,
    };
  }
}
