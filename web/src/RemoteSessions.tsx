import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { AppStreamer, EventStatus, StreamStatus, StreamType, VideoCodec, type DirectConfig } from '@nvidia/ov-web-rtc';
import { parseToolResult, privateToolMetadata } from './tool-result.mjs';
import { installMcpSignaling } from './mcp-signaling';
import { callHostTool, startHostBridge } from './host-bridge';
import { installRtcDiagnostics, streamEventDiagnostic, formatStreamStats, studioStreamProfile, supportedVideoCodecs, type StreamResolution } from './stream-diagnostics';

type Profile = { id: string; label: string; provider: string; signalingOrigin: string; mediaConnectivity: string; accessConfigured: boolean; controlConfigured?: boolean };
type Attachment = { attachmentId: string; profileId: string; label: string; provider: string };
type Configuration = { attachmentId: string; profileId: string; mediaServer: string; mediaPort: number; iceServerConfiguration?: DirectConfig['iceServerConfiguration'] };
const wait = (ms: number) => new Promise<void>(resolve => window.setTimeout(resolve, ms));
const LocalConnectionLock = createContext<(value: boolean) => void>(() => {});
const RemoteControlTarget = createContext(false);
type SessionConnection = { isRemote: boolean; controlReady: boolean; live: boolean; videoCodec: VideoCodec; streamResolution: StreamResolution; label: string; message: string; stats: string; selector: ReactNode; viewport: ReactNode; diagnostics: ReactNode };
const SessionConnectionContext = createContext<SessionConnection>({ isRemote:false, controlReady:false, live:false, videoCodec:VideoCodec.H264,streamResolution:'1080p',label:'',message:'',stats:'',selector:null,viewport:null,diagnostics:null });
export const useLocalConnectionLock = () => useContext(LocalConnectionLock);
export const useRemoteControlTarget = () => useContext(RemoteControlTarget);
export const useSessionConnection = () => useContext(SessionConnectionContext);
const noLocalLock = () => {};

async function invoke(name: string, args: Record<string, unknown>) {
  const response = await callHostTool(name, args);
  return { data: parseToolResult(response), meta: privateToolMetadata(response) };
}

/** One studio and viewport; only its session transport changes. */
export function ConnectionStudio({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<'local' | 'remote'>('local');
  const [videoCodec, setVideoCodec] = useState(VideoCodec.H264);
  const [streamResolution, setStreamResolution] = useState<StreamResolution>('1080p');
  const [browserCodecs] = useState(() => supportedVideoCodecs(window.RTCRtpReceiver));
  const [locked, setLocked] = useState(false);
  const [localLocked, setLocalLocked] = useState(false);
  const [remoteControlReady, setRemoteControlReady] = useState(false);
  const onLock = setLocked;
  const onControls = setRemoteControlReady;
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState('');
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(false);
  const [message, setMessage] = useState('Lire les profils de sessions existantes.');
  const [stats, setStats] = useState('');
  const [diagnostics, setDiagnostics] = useState<string[]>([]);
  const [controlMessage, setControlMessage] = useState('');
  const rtcDiagnostics = useRef<ReturnType<typeof installRtcDiagnostics> | null>(null);
  const report = (message: string) => { if (mounted.current) setDiagnostics(previous => [...previous.slice(-31), message]); };
  const video = useRef<HTMLVideoElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const streamer = useRef<AppStreamer | null>(null);
  const route = useRef<ReturnType<typeof installMcpSignaling> | null>(null);
  const attachmentRef = useRef<Attachment | null>(null);
  const operation = useRef(false);
  const generation = useRef(0);
  const pending = useRef<Promise<unknown> | null>(null);
  const retirement = useRef<Promise<void> | null>(null);
  const firstFrameTimer = useRef<number | null>(null);
  const focusCleanup = useRef<(() => void) | null>(null);
  const mounted = useRef(true);
  const acceptFrames = useRef(false);
  const frameSeen = useRef(false);
  const setAttachmentValue = (value: Attachment | null) => { attachmentRef.current = value; setAttachment(value); };
  const clearFrameTimer = () => { if (firstFrameTimer.current !== null) window.clearTimeout(firstFrameTimer.current); firstFrameTimer.current = null; };

  const retire = () => {
    if (retirement.current) return retirement.current;
    generation.current++; clearFrameTimer();
    acceptFrames.current = false; frameSeen.current = false;
    route.current?.dispose(); route.current = null;
    rtcDiagnostics.current?.dispose(); rtcDiagnostics.current = null;
    focusCleanup.current?.(); focusCleanup.current = null;
    const candidate = streamer.current; streamer.current = null;
    const negotiation = pending.current;
    if (video.current) video.current.srcObject = null;
    if (mounted.current) { setLive(false); setStats(''); }
    if (!candidate) return Promise.resolve();
    // terminate(false) disconnects the client; never terminate the external app.
    void candidate.terminate(false).catch(() => undefined);
    const completing = (negotiation ? negotiation.catch(() => undefined) : Promise.resolve()).then(async () => {
      while (candidate.streamStatus === StreamStatus.STARTING) await wait(250);
      if (candidate.streamStatus !== StreamStatus.NONE) void candidate.terminate(false).catch(() => undefined);
      while (candidate.streamStatus !== StreamStatus.NONE) await wait(250);
    }).finally(() => { if (retirement.current === completing) retirement.current = null; if (pending.current === negotiation) pending.current = null; });
    retirement.current = completing;
    return completing;
  };

  const refresh = async () => {
    if (operation.current) return;
    operation.current = true; setBusy(true);
    try {
      const { data } = await invoke('list_omniverse_remote_sessions', {});
      if (!mounted.current) return;
      const values = Array.isArray(data.profiles) ? data.profiles as Profile[] : [];
      setProfiles(values);
      const active = data.attachment as Attachment | null;
      setAttachmentValue(active || null); onLock(Boolean(active));
      if (active) setMode('remote');
      if (!active) onControls(false);
      setProfileId(previous => active?.profileId || (values.some(item => item.id === previous) ? previous : values[0]?.id || ''));
      if (!streamer.current) setMessage(active ? 'Session distante sélectionnée. Rattachez sa vidéo pour reprendre.' : values.length ? 'Sélectionnez une session existante, puis rattachez sa vidéo.' : 'Aucun profil distant déclaré. Ajoutez remoteSessions dans la configuration du contrôleur.');
    } catch { if (mounted.current) { onControls(false); setMessage('Les profils distants ne sont pas disponibles. Vérifiez la configuration et la version du contrôleur.'); } }
    finally { operation.current = false; if (mounted.current) setBusy(false); }
  };

  const checkControls = async () => {
    try {
      const {data} = await invoke('get_omniverse_simulation_state', {});
      if (!attachmentRef.current || typeof data.stagePath !== 'string' || data.controlBridgeConnected !== true) throw new Error();
      onControls(true); setControlMessage('Bridge Kit authentifié : les commandes de scène, caméra et simulation sont disponibles ci-dessous.');
    } catch { onControls(false); setControlMessage('Bridge de commandes non confirmé. Vérifiez le service de contrôle du Kit distant.'); }
  };

  const markFrame = () => {
    const element = video.current;
    if (!acceptFrames.current || !streamer.current || !element || element.videoWidth <= 0 || element.videoHeight <= 0 || element.readyState < 2 || !element.srcObject) return;
    frameSeen.current = true; clearFrameTimer(); setLive(true);
    setMessage('Image Kit reçue. Placez le focus dans la vidéo pour les interactions natives.');
  };

  const installFocus = () => {
    focusCleanup.current?.();
    const element = video.current; const root = viewport.current;
    if (!element || !root) return;
    const restore = () => { if (element.tabIndex !== 0) element.tabIndex = 0; if (element.style.outline === 'none') element.style.removeProperty('outline'); };
    const tab = (event: KeyboardEvent) => { if (event.key === 'Tab') event.stopPropagation(); };
    restore(); const observer = new MutationObserver(restore);
    observer.observe(element, { attributes: true, attributeFilter: ['tabindex', 'style'] });
    root.addEventListener('keydown', tab, { capture: true });
    focusCleanup.current = () => { observer.disconnect(); root.removeEventListener('keydown', tab, { capture: true }); };
  };

  const connect = async () => {
    if (operation.current || pending.current || retirement.current || !profileId || streamer.current) return;
    operation.current = true; setBusy(true); onLock(true); setLive(false); setStats(''); setDiagnostics([]);
    const epoch = ++generation.current;
    let selected: Attachment | null = null;
    try {
      setMessage('Rattachement de la session distante existante…');
      const { data, meta } = await invoke('attach_omniverse_remote_stream', { profileId });
      selected = data as unknown as Attachment;
      if (!mounted.current || epoch !== generation.current) return;
      if (typeof selected.attachmentId !== 'string' || selected.profileId !== profileId) throw new Error('Réponse de rattachement incompatible.');
      setAttachmentValue(selected);
      if (profiles.find(profile => profile.id === profileId)?.controlConfigured) void checkControls();
      const config = meta['omnistream/remoteStreamConfiguration'] as Configuration | undefined;
      if (!config || config.attachmentId !== selected.attachmentId || config.profileId !== profileId || !config.mediaServer || !Number.isInteger(config.mediaPort)) throw new Error('Configuration vidéo privée absente ou incompatible.');
      const attachedId = selected.attachmentId;
      rtcDiagnostics.current = installRtcDiagnostics(window, report);
      const codecs = supportedVideoCodecs(window.RTCRtpReceiver);
      document.documentElement.dataset.omnistreamVideoCodecs = codecs.join(',');
      report(`Codecs annoncés par ce navigateur : ${codecs.join(', ') || 'non renseignés'}.`);
      const candidate = new AppStreamer(); streamer.current = candidate;
      acceptFrames.current = true; frameSeen.current = false;
      const current = () => mounted.current && epoch === generation.current && streamer.current === candidate;
      route.current = installMcpSignaling(window, 49100, async (name, args) => {
        const remoteName = name.replace('_omniverse_signaling', '_omniverse_remote_signaling');
        const response = await invoke(remoteName, { ...args, attachmentId: attachedId });
        const payload = response.meta['omnistream/signalingPayload'];
        if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new Error('Remote signaling response unavailable.');
        return payload as Record<string, unknown>;
      }, code => report(`Signalisation MCP distante : ${code}.`), true);
      const stopped = () => {
        if (!current()) return;
        acceptFrames.current = false;
        clearFrameTimer(); setLive(false); setStats('');
        setMessage('Flux distant interrompu. Déconnectez le viewer puis rattachez-le ; le runtime reste actif.');
      };
      // This loopback URL is a virtual SDK signaling interface routed through MCP.
      // The controller fixes the actual WSS destination from the selected profile.
      const sdkConfig: DirectConfig = {
        codec: videoCodec, codecList: [videoCodec],
        videoElementId: 'remote-session-video', signalingServer: '127.0.0.1', signalingPort: 49100,
        mediaServer: config.mediaServer, mediaPort: config.mediaPort, authenticate: false, forceWSS: false,
        iceServerConfiguration: config.iceServerConfiguration, ...studioStreamProfile(streamResolution),
        mic: false, nativeTouchEvents: false, maxReconnects: 2, reconnectDelay: 1500, connectivityTimeout: 10000,
        onStart: event => { if (current()) { report(streamEventDiagnostic(event)); if (event.status === EventStatus.ERROR) stopped(); } },
        onStop: event => { if (current()) report(streamEventDiagnostic(event)); stopped(); },
        onTerminate: event => { if (current()) report(streamEventDiagnostic(event)); stopped(); },
        onStreamStats: event => { if (current() && event.data?.stats) setStats(formatStreamStats(event.data.stats)); },
      };
      setMessage('Négociation WebRTC distante ; aucune image reçue pour le moment.');
      const negotiation = candidate.connect({ streamSource: StreamType.DIRECT, streamConfig: sdkConfig });
      pending.current = negotiation;
      void negotiation.finally(() => { if (pending.current === negotiation) pending.current = null; }).catch(() => undefined);
      let timeout: number | undefined;
      try {
        const result = await Promise.race([negotiation, new Promise<never>((_resolve, reject) => { timeout = window.setTimeout(() => reject(new Error('La négociation vidéo distante a dépassé 75 secondes.')), 75000); })]);
        if (!current()) return;
        if (result.status === EventStatus.ERROR) throw new Error('La négociation WebRTC distante a échoué. Vérifiez WSS et le trajet média.');
      } finally { window.clearTimeout(timeout); }
      installFocus(); markFrame();
      if (!frameSeen.current) firstFrameTimer.current = window.setTimeout(() => {
        if (!current()) return;
        setLive(false); setMessage('Signalisation négociée, mais aucune image reçue en 30 secondes. Vérifiez NVENC et ICE/TURN sur les deux hôtes.');
      }, 30000);
    } catch (error) {
      if (mounted.current) { setLive(false); setMessage(error instanceof Error ? error.message : 'Le rattachement distant a échoué.'); }
      void retire();
      if (selected?.attachmentId) {
        try { await invoke('detach_omniverse_remote_stream', { attachmentId: selected.attachmentId }); if (mounted.current) setAttachmentValue(null); } catch { /* Preserve the exact attachment for explicit recovery. */ }
      }
    } finally {
      operation.current = false;
      if (mounted.current) { setBusy(false); onLock(Boolean(attachmentRef.current || retirement.current)); }
    }
  };

  const disconnect = async () => {
    if (operation.current) return;
    operation.current = true; setBusy(true); onLock(true);
    const selected = attachmentRef.current;
    void retire();
    try {
      if (selected) await invoke('detach_omniverse_remote_stream', { attachmentId: selected.attachmentId });
      setAttachmentValue(null);
      onControls(false); setControlMessage('');
      setMessage(retirement.current ? 'Viewer déconnecté. Nettoyage du SDK en cours ; aucun arrêt du runtime distant.' : 'Viewer déconnecté ; le runtime distant reste actif.');
    } catch { setMessage('Déconnexion non confirmée. Relisez les profils avant de réessayer.'); }
    finally { operation.current = false; setBusy(false); onLock(Boolean(attachmentRef.current || retirement.current)); }
  };

  useEffect(() => {
    mounted.current = true; void startHostBridge().then(() => { if (mounted.current) void refresh(); }).catch(() => {});
    const timer = window.setInterval(() => {
      if (!operation.current && !attachmentRef.current && !retirement.current && !pending.current) onLock(false);
    }, 500);
    return () => { mounted.current = false; window.clearInterval(timer); void retire(); };
  }, []);

  const selectedProfile = profiles.find(profile => profile.id === profileId);
  const selector = <section className="session-connection" aria-label="Connexion du studio" aria-busy={busy}>
      <label htmlFor="session-target">Session</label>
      <select id="session-target" value={mode === 'local' ? 'local' : profileId} disabled={busy || locked || localLocked} onChange={event => {
        onControls(false);setMode(event.target.value === 'local' ? 'local' : 'remote');
        if (event.target.value !== 'local') setProfileId(event.target.value);
      }}>
        <option value="local">Kit sur ce poste</option>
        {profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.label}</option>)}
      </select>
      {mode === 'remote' && <>
        <button className="primary" disabled={busy || live || !selectedProfile?.accessConfigured || Boolean(retirement.current) || Boolean(streamer.current)} onClick={() => void connect()}>Connecter</button>
        <button disabled={busy || (!attachment && !streamer.current)} onClick={() => void disconnect()}>Déconnecter</button>
      </>}
      <details className="session-details"><summary>Connexion</summary>
        <label htmlFor="session-video-resolution">Définition vidéo</label>
        <select id="session-video-resolution" value={streamResolution} disabled={busy || locked || localLocked} onChange={event => {
          if (event.target.value === '1080p' || event.target.value === '4k') setStreamResolution(event.target.value);
        }}>
          <option value="1080p">1920 × 1080</option>
          <option value="4k">4K · 3840 × 2160</option>
        </select>
        <label htmlFor="session-video-codec">Compression vidéo</label>
        <select id="session-video-codec" value={videoCodec} disabled={busy || locked || localLocked} onChange={event => {
          if ([VideoCodec.H264, VideoCodec.H265, VideoCodec.AV1].includes(event.target.value as VideoCodec)) setVideoCodec(event.target.value as VideoCodec);
        }}>
          <option value={VideoCodec.H264}>H.264 · compatibilité</option>
          {browserCodecs.includes('H265') && <option value={VideoCodec.H265}>H.265 · compression efficace</option>}
          {browserCodecs.includes('AV1') && <option value={VideoCodec.AV1}>AV1 · compression efficace</option>}
        </select>
        <p>Le Kit doit prendre en charge le format choisi. Déconnectez la vidéo pour changer de format.</p>
        <button disabled={busy || Boolean(streamer.current)} onClick={() => void refresh()}>Actualiser les sessions</button>
        {mode === 'remote' && <>
          {selectedProfile?.controlConfigured && <button disabled={busy || !attachment} onClick={() => void checkControls()}>Vérifier les commandes</button>}
          <p>{controlMessage || 'Connectez la session pour vérifier ses commandes et son rendu.'}</p>
          <p>Déconnecter libère le viewer et conserve le Kit distant.</p>
        </>}
      </details>
    </section>;
  const remoteViewport = <div className="remote-viewport-content" ref={viewport}>
        <video id="remote-session-video" data-configured-codec={videoCodec} ref={video} className="remote-video" autoPlay playsInline muted tabIndex={0} aria-label="Flux vidéo interactif du Kit distant" onLoadedData={markFrame} onPlaying={markFrame} />
        {!live && <div className="viewport-overlay"><h2>En attente du rendu distant</h2><p>Une connexion de signalisation ne prouve pas la réception de la vidéo.</p></div>}
        {live && <span className="live-badge">RTX LIVE</span>}
    </div>;
  const diagnosticView = diagnostics.length > 0 ? <details><summary>Diagnostic de la connexion</summary><ol aria-label="Journal de la connexion distante">{diagnostics.map((entry,index)=><li key={index}>{entry}</li>)}</ol></details> : null;
  return <SessionConnectionContext.Provider value={{isRemote:mode === 'remote',controlReady:remoteControlReady,live,videoCodec,streamResolution,label:attachment?.label || selectedProfile?.label || '',message,stats,selector,viewport:remoteViewport,diagnostics:diagnosticView}}>
    <RemoteControlTarget.Provider value={mode === 'remote'}>
      <LocalConnectionLock.Provider value={mode === 'local' ? setLocalLocked : noLocalLock}>{children}</LocalConnectionLock.Provider>
    </RemoteControlTarget.Provider>
  </SessionConnectionContext.Provider>;
}
