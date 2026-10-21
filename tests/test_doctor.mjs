import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const root = path.resolve(import.meta.dirname, '..');
function diagnose(overrides) {
  const home = mkdtempSync(path.join(tmpdir(), 'omnistream-doctor-'));
  try {
    mkdirSync(path.join(home, 'config'));
    writeFileSync(path.join(home, 'config/omnistream.json'), JSON.stringify({
      schemaVersion: 2, runtimeChannel: 'Existing', signalingPort: 49100,
      panelSignalingTransport: 'mcp', signalingTls: {port:49101, certificateThumbprint:'A'.repeat(40)},
      remoteSessions: [], ...overrides,
    }));
    const result = spawnSync(process.execPath, [path.join(root, 'scripts/doctor.mjs')], {
      env: {...process.env, OMNISTREAM_HOME: home}, encoding:'utf8', windowsHide:true, timeout:30000,
    });
    assert.equal(result.status, 0, result.stderr || result.error?.message);
    return result.stdout;
  } finally { rmSync(home, {recursive:true, force:true}); }
}
test('doctor accepts the configured MCP transport, inactive TLS and remote allowlist', () => {
  const output = diagnose({});
  for (const label of ['Clés configuration connues', 'Transport signaling panneau', 'Configuration TLS locale', 'Profils distants']) {
    assert.match(output, new RegExp('OK  +'+label));
  }
});
test('doctor reports invalid transport and TLS without echoing values', () => {
  const output = diagnose({panelSignalingTransport:'unexpected', signalingTls:{port:49100, certificateThumbprint:'private-test-value'}});
  assert.match(output, /INFO +Transport signaling panneau/);
  assert.match(output, /INFO +Configuration TLS locale/);
  assert.doesNotMatch(output, /private-test-value/);
});
test('doctor rejects unknown config keys and invalid remote credentials without exposing them', () => {
  const output = diagnose({unexpectedOption:true, remoteSessions:[{id:'qa', token:'private-test-value'}]});
  assert.match(output, /INFO +Clés configuration connues/);
  assert.match(output, /INFO +Profils distants/);
  assert.doesNotMatch(output, /private-test-value/);
});
