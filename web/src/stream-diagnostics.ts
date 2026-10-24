type PolicyEvent = { effectiveDirective: string; disposition: string; blockedURI: string };
// Same fidelity policy for both transports. 60 Mb/s is an upper bound, not a
// promised or constant rate. Native captures remain independent of WebRTC.
export const STUDIO_STREAM_PROFILE = {
  width:1920, height:1080, fps:30, fitStreamResolution:false,
  maxBitrateKbps:60_000, dynamicStreamingMode:0,
} as const;

export type StreamResolution = '1080p' | '4k';
export function studioStreamProfile(resolution: StreamResolution) {
  return resolution === '4k'
    ? { ...STUDIO_STREAM_PROFILE, width:3840, height:2160 }
    : STUDIO_STREAM_PROFILE;
}

/** SDK units: Mb/s and milliseconds. Never label a cumulative loss count as a percentage. */
export function formatStreamStats(stats: { codec?: string; streamingResolutionWidth?: number; streamingResolutionHeight?: number; fps?: number; currentBitrate?: number; rtd?: number; packetLoss?: number }): string {
  const number = (value: number | undefined, decimals=0) => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value.toFixed(decimals) : '—';
  const codec = ['H264','H265','AV1','VP8','VP9'].includes(stats.codec || '') ? ` · ${stats.codec}` : '';
  return `${number(stats.streamingResolutionWidth)} × ${number(stats.streamingResolutionHeight)} · ${number(stats.fps)} fps · ${number(stats.currentBitrate,1)} Mb/s · RTT ${number(stats.rtd)} ms · ${number(stats.packetLoss)} paquets perdus${codec}`;
}

/** Public browser capability names only, never SDP or device identifiers. */
export function supportedVideoCodecs(receiver?: Pick<typeof RTCRtpReceiver, 'getCapabilities'>): string[] {
  try {
    const codecs = receiver?.getCapabilities?.('video')?.codecs || [];
    return ['H264', 'H265', 'AV1', 'VP8', 'VP9'].filter(name =>
      codecs.some(codec => codec.mimeType.toUpperCase() === `VIDEO/${name}`));
  } catch { return []; }
}

/** Classify a CSP failure without retaining a URL, path, query or credential. */
export function policyDiagnostic(event: PolicyEvent): string | null {
  if (!["connect-src", "worker-src"].includes(event.effectiveDirective)) return null;
  const value = event.blockedURI;
  let resource = "ressource non identifiée";
  if (value === "data" || value.startsWith("data:")) resource = "donnée embarquée (data:)";
  else if (value === "blob" || value.startsWith("blob:")) resource = "objet local (blob:)";
  else {
    try {
      const url = new URL(value);
      if (["http:", "https:", "ws:", "wss:"].includes(url.protocol)) {
        resource = ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)
          ? `connexion loopback ${url.protocol}//${url.hostname}${url.port ? `:${url.port}` : ""}`
          : "connexion réseau externe (destination masquée)";
      }
    } catch { /* The classification deliberately omits unrecognized values. */ }
  }
  const disposition = ["enforce", "report"].includes(event.disposition) ? event.disposition : "unknown";
  return `Politique de l’hôte : ${resource} [${event.effectiveDirective}, ${disposition}].`;
}

/** SDK error information can include signaling credentials. Keep enum values
 * and recognized numeric error codes only, never the raw info string. */
export function streamEventDiagnostic(event: { action?: unknown; status?: unknown; info?: unknown }): string {
  const action = ["start", "stop", "terminate", "connect", "stream"].includes(String(event.action)) ? String(event.action) : "event";
  const status = ["success", "error", "warning", "inProgress", "canceled"].includes(String(event.status)) ? String(event.status) : "unknown";
  const info = typeof event.info === "string" ? event.info : event.info instanceof Error ? event.info.message : "";
  const code = info.match(/\b(?:0x[0-9a-fA-F]{8}|800[bB][0-9a-fA-F]{4}|NVST_[A-Z_]{1,48})\b/g)?.slice(0, 3).join(" ");
  const reason = info.match(/^Session stopped: (CLIENT_DISCONNECTED|SERVER_DISCONNECTED|NETWORK_ERROR|ERROR)$/)?.[1];
  return `SDK vidéo : ${action}/${status}${code ? ` (${code})` : ""}${reason ? ` [${reason}]` : ""}.`;
}

/** Observe this panel's native peers. No SDP, ICE credentials, candidate
 * addresses, device information or arbitrary SDK text enters the journal. */
export function installRtcDiagnostics(target: { RTCPeerConnection: typeof RTCPeerConnection }, report: (message: string) => void) {
  const native = target.RTCPeerConnection;
  const cleanups = new Set<() => void>();
  let nextPeer = 0, disposed = false;
  const routed = new Proxy(native, {
    construct(constructor, args) {
      const peer = Reflect.construct(constructor, args) as RTCPeerConnection;
      // Capability probes also create peers; bound diagnostics independently.
      if (disposed || nextPeer >= 8) return peer;
      const id = ++nextPeer;
      let timer: ReturnType<typeof setInterval> | undefined;
      let samples = 0, reading = false, received = false, decoded = false;
      let pairSummary = '';
      const listeners: Array<[string, EventListener]> = [];
      const emit = (text: string) => { if (!disposed) report(`WebRTC ${id} : ${text}`); };
      const listen = (type: string, handler: EventListener) => { peer.addEventListener(type, handler); listeners.push([type, handler]); };
      const clearTimer = () => { if (timer !== undefined) clearInterval(timer); timer = undefined; };
      const sample = async () => {
        if (disposed || reading || peer.connectionState === "closed") return;
        reading = true;
        try {
          const stats = await peer.getStats();
          if (disposed) return;
          let bytes = 0, frames = 0;
          const pairs: string[] = [];
          stats.forEach(stat => {
            if (stat.type === 'candidate-pair' && ['in-progress', 'succeeded', 'failed'].includes(stat.state)) {
              const count = (value: unknown) => Number.isSafeInteger(value) && Number(value) >= 0 ? Number(value) : 0;
              pairs.push(`${stat.state}, requêtes ${count(stat.requestsSent)}, réponses ${count(stat.responsesReceived)}`);
            }
            if (stat.type !== "inbound-rtp" || (stat.kind !== "video" && stat.mediaType !== "video")) return;
            if (Number.isSafeInteger(stat.bytesReceived) && stat.bytesReceived >= 0) bytes += stat.bytesReceived;
            if (Number.isSafeInteger(stat.framesDecoded) && stat.framesDecoded >= 0) frames += stat.framesDecoded;
          });
          const summary = pairs.slice(0, 4).join(' ; ');
          if (summary && summary !== pairSummary) { emit(`trajets ICE : ${summary}.`); pairSummary = summary; }
          if (samples === 0 || (!received && bytes > 0) || (!decoded && frames > 0))
            emit(`vidéo reçue ${bytes} octets, ${frames} images décodées.`);
          received ||= bytes > 0; decoded ||= frames > 0;
        } catch { emit("statistiques indisponibles."); }
        finally { reading = false; if (++samples >= 15) clearTimer(); }
      };
      listen("connectionstatechange", () => {
        emit(`connexion ${peer.connectionState}.`);
        if (peer.connectionState === "connected" && timer === undefined && samples < 15) {
          void sample(); timer = setInterval(() => { void sample(); }, 2_000);
        }
        if (["closed", "failed"].includes(peer.connectionState)) clearTimer();
      });
      listen("iceconnectionstatechange", () => {
        emit(`ICE ${peer.iceConnectionState}.`);
        if (peer.iceConnectionState === 'checking' && timer === undefined && samples < 15) {
          void sample(); timer = setInterval(() => { void sample(); }, 2_000);
        }
      });
      listen("signalingstatechange", () => emit(`signalisation ${peer.signalingState}.`));
      listen("track", event => {
        const kind = (event as RTCTrackEvent).track.kind;
        if (["audio", "video"].includes(kind)) emit(`piste ${kind} reçue.`);
      });
      listen("icecandidateerror", event => {
        const code = (event as RTCPeerConnectionIceErrorEvent).errorCode;
        emit(`erreur ICE${Number.isInteger(code) && code >= 0 && code <= 65535 ? ` ${code}` : ""}.`);
      });
      cleanups.add(() => { clearTimer(); for (const [type, handler] of listeners) peer.removeEventListener(type, handler); });
      return peer;
    },
  });
  target.RTCPeerConnection = routed;
  return { dispose() {
    disposed = true; for (const cleanup of cleanups) cleanup(); cleanups.clear();
    if (target.RTCPeerConnection === routed) target.RTCPeerConnection = native;
  } };
}
