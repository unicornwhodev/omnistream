import http from 'node:http';
import { randomBytes, createHash, timingSafeEqual } from 'node:crypto';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { LoopbackControlServer } from './control-rpc.mjs';
import { LiveEventStore } from './live-events.mjs';

const reads = new Set(['simulation.state', 'simulation.preflight', 'camera.list', 'scene.inspect', 'scene.prim', 'scene.diagnose', 'telemetry.read', 'control.status']);
const methods = new Set([...reads, 'scene.preview', 'scene.apply', 'scene.undo', 'scene.export', 'scene.discard', 'scene.watch', 'scene.run', 'stage.open', 'simulation.configure', 'simulation.control', 'timeline.control', 'camera.select', 'camera.navigate', 'camera.save']);
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const failure = (code, message) => Object.assign(new Error(message), { code });

/** Runs beside Kit. The existing authenticated Kit worker connects to this
 * loopback server unchanged. Only the separately authenticated HTTP facade is
 * forwarded by the one-PC private relay; it never owns or terminates Kit. */
export async function createRemoteControlHost({ token, port = 9048, controlServer, now = Date.now } = {}) {
  if (typeof token !== 'string' || !/^[A-Za-z0-9_-]{32,128}$/.test(token)) throw failure('configuration_invalid', 'A private remote control credential is required.');
  const events = new LiveEventStore(500, now);
  const bridge = controlServer || new LoopbackControlServer({
    requestTimeoutMs: 180_000, onEvent: event => events.accept(event),
  });
  await bridge.start();
  const operations = new Map();
  let activeMutation = null, uncertain = false;
  const authorized = value => {
    const supplied = Buffer.from(typeof value === 'string' ? value : '');
    const expected = Buffer.from(`Bearer ${token}`); const fixed = Buffer.alloc(expected.length);
    supplied.copy(fixed); return supplied.length === expected.length && timingSafeEqual(expected, fixed);
  };
  const answer = (response, status, payload) => {
    const body = JSON.stringify(payload);
    response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'Content-Length': Buffer.byteLength(body) });
    response.end(body);
  };
  async function execute(message) {
    const { id, method, params } = message;
    if (Object.keys(message).some(key => !['id', 'method', 'params'].includes(key)) ||
        typeof id !== 'string' || !/^[A-Za-z0-9_-]{1,80}$/.test(id) || !methods.has(method) || !object(params))
      throw failure('request_invalid', 'Unsupported remote control request.');
    const fingerprint = createHash('sha256').update(JSON.stringify({ method, params })).digest('hex');
    const prior = operations.get(id);
    if (prior) {
      if (prior.fingerprint !== fingerprint) throw failure('operation_changed', 'A remote operation identity cannot change its parameters.');
      return prior.promise;
    }
    for (const [key, value] of operations) if (operations.size >= 256 && value.finished) operations.delete(key);
    if (operations.size >= 256) throw failure('busy', 'Remote operation storage is full.');
    const mutation = !reads.has(method);
    if (mutation && (activeMutation || uncertain)) throw failure('mutation_blocked', 'The previous remote mutation must settle before another one starts.');
    if (!bridge.isConnected) throw failure('bridge_unavailable', 'The authenticated Kit bridge is not connected.');
    const entry = { fingerprint, finished: false, promise: null };
    // Start on a microtask after reservation, so retries share exactly one
    // native request. A disconnected HTTP caller cannot abandon its mutation.
    if (mutation) activeMutation = id;
    entry.promise = Promise.resolve().then(async () => {
      if (method === 'telemetry.read') return events.read(params, bridge.isConnected);
      if (method === 'control.status') return { protocol: 1, connected: bridge.isConnected, ownership: 'external', mutationUncertain: uncertain };
      return bridge.request(method, params, { completionTimeoutMs: 180_000, clientTimeoutMs: 180_000 });
    }).then(result => ({ ok: true, id, result }), error => {
      if (mutation && ['request_timeout', 'bridge_disconnected', 'bridge_unavailable', 'bridge_closed'].includes(error.code)) uncertain = true;
      return { ok: false, id, error: { code: error.code || 'command_failed', message: 'The native Kit command did not complete successfully.' } };
    }).finally(() => { entry.finished = true; if (activeMutation === id) activeMutation = null; });
    operations.set(id, entry); return entry.promise;
  }
  const server = http.createServer(async (request, response) => {
    if (request.url !== '/omnistream/control' || request.method !== 'POST') return answer(response, 404, { ok: false });
    if (request.headers.origin || !authorized(request.headers.authorization)) return answer(response, 401, { ok: false, error: { code: 'unauthorized' } });
    try {
      let size = 0; const chunks = [];
      for await (const chunk of request) { size += chunk.length; if (size > 64 * 1024) throw failure('message_too_large', 'Remote request exceeds its bound.'); chunks.push(chunk); }
      const message = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if (!object(message)) throw failure('request_invalid', 'Remote request must be an object.');
      answer(response, 200, await execute(message));
    } catch (error) {
      answer(response, 400, { ok: false, error: { code: ['request_invalid', 'message_too_large', 'operation_changed', 'busy', 'mutation_blocked', 'bridge_unavailable'].includes(error.code) ? error.code : 'request_invalid', message: 'Remote request refused.' } });
    }
  });
  server.requestTimeout = 180_000; server.headersTimeout = 10_000; server.maxConnections = 16;
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', resolve); });
  return { bridge, server, events, address: server.address(), async close() { await new Promise(resolve => server.close(resolve)); await bridge.close(); } };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const configPath = process.argv[2];
  if (!configPath || !process.argv.includes('--control-authorized')) throw new Error('An operator configuration and explicit control authorization are required.');
  const config = JSON.parse(readFileSync(configPath, 'utf8'));
  if (!config.tokenFile || !config.bridgeSettingsFile) throw new Error('Private credential paths are required.');
  if (!existsSync(config.tokenFile)) writeFileSync(config.tokenFile, randomBytes(32).toString('base64url'), { mode: 0o600, flag: 'wx' });
  const host = await createRemoteControlHost({ token: readFileSync(config.tokenFile, 'utf8').trim(), port: 9048 });
  writeFileSync(config.bridgeSettingsFile, JSON.stringify(host.bridge.launchSettings), { mode: 0o600 });
  console.log('REMOTE_CONTROL_HOST_READY: authenticated HTTP loopback and original authenticated Kit worker; no external process ownership.');
  for (const signal of ['SIGTERM', 'SIGINT']) process.once(signal, () => { void host.close().finally(() => process.exit()); });
}
