import { spawn } from 'node:child_process';
import path from 'node:path';

export function loopbackTlsConfiguration(raw, kitPort) {
  if (raw === undefined || raw === null) return null;
  if (typeof raw !== 'object' || Array.isArray(raw) || Object.keys(raw).some(key => !['port', 'certificateThumbprint'].includes(key)) ||
      !Number.isInteger(raw.port) || raw.port < 1024 || raw.port > 65535 || raw.port === kitPort ||
      typeof raw.certificateThumbprint !== 'string' || !/^[0-9a-fA-F]{40}$/.test(raw.certificateThumbprint)) {
    throw new Error('Invalid loopback signaling TLS configuration.');
  }
  return { port: raw.port, certificateThumbprint: raw.certificateThumbprint.toUpperCase() };
}

export function browserSignalingEndpoint(tls, kitPort) {
  return tls ? { host: 'localhost', port: tls.port, secure: true }
    : { host: '127.0.0.1', port: kitPort, secure: false };
}

function command(powershellExe, config, kitPort, validateOnly) {
  return [powershellExe, ['-NoLogo', '-NoProfile', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File',
    path.join(import.meta.dirname, 'start-loopback-tls.ps1'), '-CertificateThumbprint', config.certificateThumbprint,
    '-ListenPort', String(config.port), '-KitPort', String(kitPort), ...(validateOnly ? ['-ValidateOnly'] : [])]];
}

function start(config, kitPort, powershellExe, validateOnly, spawnChild = spawn) {
  const [exe, args] = command(powershellExe, config, kitPort, validateOnly);
  const child = spawnChild(exe, args, { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
  let live = true;
  const exited = new Promise(resolve => child.once('close', () => { live = false; resolve(); }));
  child.stdin.on('error', () => {});
  // Never return or retain request bytes or child error text. TLS terminates
  // inside the helper; it forwards the bearer bytes without inspecting them.
  child.stderr.resume();
  const stop = async () => {
    if (!live) return;
    child.stdin.end();
    let timer;
    try {
      await Promise.race([exited, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('TLS relay stop timed out.')), 5_000); })]);
    } finally { clearTimeout(timer); }
  };
  return new Promise((resolve, reject) => {
    let settled = false;
    let text = '';
    const timer = setTimeout(() => fail(), 12_000);
    const fail = () => {
      if (settled) return;
      settled = true; clearTimeout(timer); child.stdin.end();
      reject(new Error('The trusted localhost TLS relay could not be prepared.'));
    };
    child.once('error', fail);
    child.once('close', () => { if (!settled) fail(); });
    child.stdout.on('data', chunk => {
      text += chunk.toString();
      if (text.length > 8192) { fail(); return; }
      const lines = text.split(/\r?\n/); text = lines.pop();
      for (const line of lines) {
        let data; try { data = JSON.parse(line); } catch { continue; }
        if (!((validateOnly && data.valid === true) || (!validateOnly && data.ready === true && data.port === config.port && data.host === 'localhost'))) continue;
        if (settled) return;
        settled = true; clearTimeout(timer);
        resolve({ isAlive: () => live, stop });
      }
    });
  });
}

export async function validateLoopbackTls(config, kitPort, powershellExe, spawnChild) {
  if (!config) return;
  const helper = await start(config, kitPort, powershellExe, true, spawnChild);
  await helper.stop();
}

export function startLoopbackTls(config, kitPort, powershellExe, spawnChild) {
  return start(config, kitPort, powershellExe, false, spawnChild);
}
