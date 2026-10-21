import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { loopbackTlsConfiguration, browserSignalingEndpoint, startLoopbackTls, validateLoopbackTls } from '../mcp/loopback-tls.mjs';

const config = { port: 49101, certificateThumbprint: 'A'.repeat(40) };
test('TLS configuration is explicit and cannot redirect away from loopback', () => {
  assert.equal(loopbackTlsConfiguration(undefined, 49100), null);
  assert.deepEqual(browserSignalingEndpoint(null, 49100), { host:'127.0.0.1', port:49100, secure:false });
  assert.deepEqual(browserSignalingEndpoint(config, 49100), { host:'localhost', port:49101, secure:true });
  for (const value of [{...config,host:'remote.example'},{...config,port:49100},{...config,port:80},{...config,certificateThumbprint:'invalid'},[]])
    assert.throws(() => loopbackTlsConfiguration(value, 49100));
});

function fakeChild(announce, seen) {
  return (exe, args, options) => {
    seen.push({exe,args,options});
    const child = new EventEmitter();
    child.stdin = new PassThrough(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
    child.stdin.once('finish', () => queueMicrotask(() => child.emit('close', 0)));
    queueMicrotask(() => announce(child));
    return child;
  };
}
test('managed TLS relay closes on stdin EOF without killing a PID', async () => {
  const calls=[];
  const relay = await startLoopbackTls(config,49100,'powershell.exe',fakeChild(c => c.stdout.write(JSON.stringify({ready:true,host:'localhost',port:49101})+'\n'),calls));
  assert.equal(relay.isAlive(), true);
  assert.equal(calls[0].options.windowsHide,true);
  assert.ok(calls[0].args.includes('Hidden'));
  assert.ok(!calls[0].args.some(a=>/private-test/.test(a)));
  await relay.stop();assert.equal(relay.isAlive(),false);await relay.stop();
});
test('certificate validation starts no listening relay and waits for helper exit', async () => {
  const calls=[];
  await validateLoopbackTls(config,49100,'powershell.exe',fakeChild(c => c.stdout.write('{"valid":true}\n'),calls));
  assert.ok(calls[0].args.includes('-ValidateOnly'));
});
test('TLS helper failure is explicit and never forwards stderr', async () => {
  const calls=[];
  await assert.rejects(startLoopbackTls(config,49100,'powershell.exe',fakeChild(c => { c.stderr.write('private-test');c.emit('close',1); },calls)),error=>!error.message.includes('private-test')&&/TLS/.test(error.message));
});
