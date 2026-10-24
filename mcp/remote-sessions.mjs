import { randomUUID } from 'node:crypto';
import { isIP } from 'node:net';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { LocalSignalingRelay } from './local-signaling.mjs';
import { remoteControlCredential, requestRemoteControl } from './remote-control-client.mjs';

const envName = /^OMNISTREAM_REMOTE_[A-Z0-9_]{1,80}$/;
const identifier = /^[a-zA-Z0-9_-]{1,64}$/;
const tailscaleAddress = value => isIP(value) === 4 && value.split('.')[0] === '100' &&
  Number(value.split('.')[1]) >= 64 && Number(value.split('.')[1]) <= 127;
const execute = promisify(execFile);

/** Verify the exact peer in the local encrypted overlay before any plaintext socket. */
export async function verifyTailscalePeer(address) {
  const executable = process.platform === 'win32' ? 'C:\\Program Files\\Tailscale\\tailscale.exe' : '/usr/bin/tailscale';
  let status;
  try {
    const { stdout } = await execute(executable, ['status', '--json'], { timeout: 5000, maxBuffer: 2 * 1024 * 1024, windowsHide: true });
    status = JSON.parse(stdout);
  } catch { invalid('The private Tailscale network is unavailable.'); }
  if (status.BackendState !== 'Running' || !Object.values(status.Peer || {}).some(peer =>
    peer.Online === true && peer.TailscaleIPs?.includes(address))) invalid('The configured Tailscale peer is not online in this network.');
}
const hostName = value => typeof value === 'string' && value.length <= 253 &&
  !/[\s/@?#:%\\]/.test(value) && (isIP(value) === 4 || /^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/.test(value));
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
export class RemoteSessionError extends Error {
  constructor(message) { super(message); this.name = 'RemoteSessionError'; this.code = 'remote_session_unavailable'; }
}
function invalid(message) { throw new RemoteSessionError(message); }

/** Explicit, operator-owned allowlist. Notebook URLs and inline secrets are not stream profiles. */
export function parseRemoteProfiles(value = []) {
  if (!Array.isArray(value) || value.length > 16) invalid('remoteSessions must contain at most 16 profiles.');
  const ids = new Set();
  return value.map(raw => {
    if (!object(raw) || !identifier.test(raw.id) || ids.has(raw.id)) invalid('Invalid or duplicate remote session identity.');
    ids.add(raw.id);
    const allowed = ['id', 'label', 'provider', 'signalingUrl', 'mediaServer', 'mediaPort', 'streamTokenEnv', 'iceServersEnv', 'mediaConnectivity', 'serverIceConfigured', 'controlTokenEnv', 'controlTokenFile'];
    if (Object.keys(raw).some(key => !allowed.includes(key))) invalid('Unknown remote session field; credentials must use environment references.');
    if (typeof raw.label !== 'string' || !raw.label.trim() || raw.label.length > 80 || /[\r\n\x00-\x1f]/.test(raw.label)) invalid('Invalid remote session label.');
    if (!['generic', 'runpod', 'colab'].includes(raw.provider)) invalid('Invalid remote session provider.');
    let url;
    try { url = new URL(raw.signalingUrl); } catch { invalid('A WSS Kit signaling URL is required, not a notebook link.'); }
    const privateNetwork = raw.mediaConnectivity === 'tailscale';
    if (raw.controlTokenEnv !== undefined && !envName.test(raw.controlTokenEnv)) invalid('Invalid remote control credential reference.');
    if (raw.controlTokenFile !== undefined && (typeof raw.controlTokenFile !== 'string' || raw.controlTokenFile.length > 1024 || /[\x00-\x1f]/.test(raw.controlTokenFile) || !/^(?:[A-Za-z]:[\\/]|\/)/.test(raw.controlTokenFile))) invalid('An absolute private control credential file is required.');
    if ((raw.controlTokenEnv || raw.controlTokenFile) && (!privateNetwork || (raw.controlTokenEnv && raw.controlTokenFile))) invalid('Remote control requires one separate credential reference and the private overlay.');
    if ((!privateNetwork && url.protocol !== 'wss:') || (privateNetwork && !['ws:', 'wss:'].includes(url.protocol)) || url.username || url.password || url.search || url.hash ||
      !hostName(url.hostname) || !/^(?:\/[A-Za-z0-9_-]+)*\/sign_in$/.test(url.pathname) ||
      /(?:^|\.)colab\.research\.google\.com$/i.test(url.hostname)) invalid('Use a credential-free WSS Kit signaling endpoint ending in /sign_in.');
    if (!hostName(raw.mediaServer) || !Number.isInteger(raw.mediaPort) || raw.mediaPort < 1 || raw.mediaPort > 65535) invalid('Invalid remote media address or port.');
    if (privateNetwork && (!tailscaleAddress(url.hostname) || raw.mediaServer !== url.hostname || raw.iceServersEnv)) invalid('Tailscale mode requires the same private IPv4 peer for signaling and media, without external ICE servers.');
    if ((!privateNetwork && !envName.test(raw.streamTokenEnv)) || (raw.streamTokenEnv !== undefined && !envName.test(raw.streamTokenEnv)) || (raw.iceServersEnv !== undefined && !envName.test(raw.iceServersEnv))) invalid('Remote credential references must use OMNISTREAM_REMOTE_ environment variables.');
    if (!['direct', 'relay', 'tailscale'].includes(raw.mediaConnectivity)) invalid('Declare direct, relay or tailscale WebRTC media connectivity.');
    if (raw.mediaConnectivity === 'relay' && (!raw.iceServersEnv || raw.serverIceConfigured !== true)) invalid('Relay mode requires ICE credentials and an explicitly configured server-side ICE route.');
    if (['runpod', 'colab'].includes(raw.provider) && !['relay', 'tailscale'].includes(raw.mediaConnectivity)) invalid('This provider requires an explicit relay path or private Tailscale network; an HTTP/TCP proxy alone does not qualify WebRTC media.');
    return Object.freeze({ ...raw, label: raw.label.trim(), signalingUrl: url.href });
  });
}

function privateIce(profile, env) {
  if (!profile.iceServersEnv) return undefined;
  let servers;
  try { servers = JSON.parse(env[profile.iceServersEnv] || ''); } catch { invalid('Remote ICE configuration is missing or invalid.'); }
  if (!Array.isArray(servers) || !servers.length || servers.length > 4) invalid('Remote ICE configuration is missing or invalid.');
  const result = servers.map(server => {
    if (!object(server) || Object.keys(server).some(key => !['urls', 'username', 'credential'].includes(key))) invalid('Invalid remote ICE server.');
    const urls = Array.isArray(server.urls) ? server.urls : [server.urls];
    if (!urls.length || urls.length > 4 || urls.some(url => typeof url !== 'string' || url.length > 512 ||
      !/^(?:stun|turn|turns):[A-Za-z0-9.-]+(?::[0-9]{1,5})?(?:\?transport=(?:udp|tcp))?$/.test(url))) invalid('Invalid remote ICE server URL.');
    const hasTurn = urls.some(url => /^turns?:/.test(url));
    if (hasTurn && (typeof server.username !== 'string' || !server.username || server.username.length > 512 ||
      typeof server.credential !== 'string' || !server.credential || server.credential.length > 2048)) invalid('TURN credentials are missing or invalid.');
    return { urls, ...(hasTurn ? { username: server.username, credential: server.credential } : {}) };
  });
  if (profile.mediaConnectivity === 'relay' && !result.some(server => server.urls.some(url => /^turns?:.*\?transport=tcp$/.test(url)))) invalid('A TCP TURN route is required for this relay profile.');
  return { iceServers: result, iceTransportPolicy: profile.mediaConnectivity === 'relay' ? 'relay' : 'all' };
}

export class RemoteSessions {
  constructor({ profiles = [], getProfiles, env = process.env, WebSocketClass = WebSocket, verifyPrivatePeer = verifyTailscalePeer } = {}) {
    this.getProfiles = getProfiles;
    this.profiles = parseRemoteProfiles(getProfiles ? getProfiles() : profiles);
    this.env = env;
    this.verifyPrivatePeer = verifyPrivatePeer;
    this.current = null;
    this.relay = new LocalSignalingRelay({ port: 49100, WebSocketClass,
      getSession: () => this.current && { identity: this.current, token: this.current.token || this.current.id,
        authenticate: this.current.profile.mediaConnectivity !== 'tailscale' || Boolean(this.current.token) },
      // Validated immutable configuration only, never a URL supplied to a tool.
      getEndpoint: () => this.current?.profile.signalingUrl });
  }
  refreshProfiles() {
    if (!this.getProfiles) return;
    let next;
    try { next = parseRemoteProfiles(this.getProfiles()); }
    catch {
      this.relay.closeAll(); this.current = null;
      invalid('Remote profile configuration is unavailable or invalid.');
    }
    if (this.current && JSON.stringify(next.find(profile => profile.id === this.current.profile.id)) !== JSON.stringify(this.current.profile)) {
      this.relay.closeAll(); this.current = null;
    }
    this.profiles = next;
  }
  list() {
    this.refreshProfiles();
    return { profiles: this.profiles.map(profile => {
      let accessConfigured = true;
      try { this.credentials(profile); } catch { accessConfigured = false; }
      return { id: profile.id, label: profile.label, provider: profile.provider,
        signalingOrigin: new URL(profile.signalingUrl).origin, mediaConnectivity: profile.mediaConnectivity,
        accessConfigured, controlConfigured: Boolean(profile.controlTokenEnv || profile.controlTokenFile), controlBridgeAvailable: this.current?.profile.id === profile.id && this.current.controlReady === true };
    }), attachment: this.describe(), mode: 'existing-stream-only' };
  }
  credentials(profile) {
    if (profile.mediaConnectivity === 'tailscale' && !profile.streamTokenEnv) return { token: null, ice: undefined };
    const token = this.env[profile.streamTokenEnv];
    if (typeof token !== 'string' || token.length < 16 || token.length > 4096 || !/^[A-Za-z0-9._~-]+$/.test(token)) invalid('Remote stream credentials are missing or invalid.');
    return { token, ice: privateIce(profile, this.env) };
  }
  describe() {
    if (!this.current) return null;
    return { attachmentId: this.current.id, profileId: this.current.profile.id,
      label: this.current.profile.label, provider: this.current.profile.provider,
      ownership: 'external', video: 'unverified', controlConfigured: Boolean(this.current.profile.controlTokenEnv || this.current.profile.controlTokenFile), controlBridgeAvailable: this.current.controlReady === true };
  }
  attach(profileId) {
    this.refreshProfiles();
    const profile = this.profiles.find(item => item.id === profileId);
    if (!profile) invalid('Unknown remote session profile.');
    const credentials = this.credentials(profile);
    if (this.current && this.current.profile.id !== profileId) invalid('Disconnect the current remote attachment before choosing another profile.');
    if (this.current && this.current.token !== credentials.token) { this.relay.closeAll(); this.current = null; }
    if (!this.current) this.current = { id: randomUUID(), profile, token: credentials.token };
    return { attachment: this.describe(), privateConfiguration: {
      attachmentId: this.current.id, profileId, mediaServer: profile.mediaServer, mediaPort: profile.mediaPort,
      ...(credentials.ice ? { iceServerConfiguration: credentials.ice } : {}) } };
  }
  require(id) {
    this.refreshProfiles();
    if (!this.current || this.current.id !== id) invalid('The remote attachment changed. Reconnect explicitly.');
  }
  detach(id) {
    this.require(id); this.relay.closeAll(); this.current = null;
    return { detached: true, remoteRuntimeStopped: false };
  }
  async open(args) {
    this.require(args.attachmentId);
    const selected = this.current;
    if (selected.profile.mediaConnectivity === 'tailscale') await this.verifyPrivatePeer(selected.profile.mediaServer);
    this.require(args.attachmentId);
    return this.relay.open(args.peerId, args);
  }
  async exchange(args) { this.require(args.attachmentId); return this.relay.exchange(args); }
  close(args) { this.require(args.attachmentId); return this.relay.close(args.channelId, args.code); }
  async control(method, params = {}) {
    if (!this.current) invalid('Select an existing remote Kit session before controlling it.');
    const selected = this.current;
    const token = remoteControlCredential(selected.profile, this.env);
    await this.verifyPrivatePeer(selected.profile.mediaServer);
    this.require(selected.id);
    try {
      const value = await requestRemoteControl(selected.profile, token, method, params);
      this.require(selected.id); selected.controlReady = true; return value;
    } catch (error) { selected.controlReady = false; throw error; }
  }
  dispose() { this.relay.dispose(); this.current = null; }
}
