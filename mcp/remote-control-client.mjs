import http from 'node:http';
import https from 'node:https';
import { randomUUID } from 'node:crypto';
import { readFileSync, lstatSync } from 'node:fs';
import { ControlRpcError } from './control-rpc.mjs';

export function remoteControlCredential(profile, env = process.env) {
  let token;
  try {
    if (profile.controlTokenEnv) token = env[profile.controlTokenEnv];
    else if (profile.controlTokenFile) {
      const stat = lstatSync(profile.controlTokenFile);
      if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 512) throw new Error();
      token = readFileSync(profile.controlTokenFile, 'utf8').trim();
    }
  } catch { /* No private path or credential enters an error. */ }
  if (typeof token !== 'string' || !/^[A-Za-z0-9_-]{32,128}$/.test(token)) throw new ControlRpcError('remote_control_unconfigured', 'Remote Kit control requires its own private credential.');
  return token;
}

/** The control destination is derived exclusively from the validated private
 * stream profile. No caller URL, redirect, browser Origin or raw code is used. */
export function requestRemoteControl(profile, token, method, params, { timeoutMs = 180_000, requestImpl } = {}) {
  if (profile.mediaConnectivity !== 'tailscale') throw new ControlRpcError('remote_control_unavailable', 'This control transport requires the configured private overlay.');
  const url = new URL(profile.signalingUrl);
  url.pathname = '/omnistream/control'; url.search = ''; url.hash = ''; url.protocol = url.protocol === 'wss:' ? 'https:' : 'http:';
  requestImpl ??= url.protocol === 'https:' ? https.request : http.request;
  const id = randomUUID(); const body = JSON.stringify({ id, method, params });
  if (Buffer.byteLength(body) > 64 * 1024) throw new ControlRpcError('message_too_large', 'Remote control request exceeds its bound.');
  return new Promise((resolve, reject) => {
    const fail = () => reject(new ControlRpcError('bridge_unavailable', 'The authenticated remote Kit control bridge is unavailable.'));
    const request = requestImpl(url, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } }, response => {
      let size = 0; const chunks = [];
      response.on('data', chunk => { size += chunk.length; if (size > 128 * 1024) { response.destroy(); request.destroy(); fail(); } else chunks.push(chunk); });
      response.on('error', fail);
      response.on('end', () => {
        try {
          const result = JSON.parse(Buffer.concat(chunks).toString('utf8'));
          if (response.statusCode !== 200 || result.id !== id || typeof result.ok !== 'boolean') return fail();
          if (!result.ok) return reject(new ControlRpcError(['request_timeout','bridge_unavailable','mutation_blocked','operation_changed','command_failed'].includes(result.error?.code) ? result.error.code : 'command_failed', 'The native remote Kit command was refused or did not complete.'));
          resolve(result.result);
        } catch { fail(); }
      });
    });
    const timer = setTimeout(() => { request.destroy(); reject(new ControlRpcError('request_timeout', 'Remote Kit control completion is uncertain. Inspect the session before another mutation.')); }, timeoutMs);
    request.on('error', fail); request.once('close', () => clearTimeout(timer)); request.end(body);
  });
}
