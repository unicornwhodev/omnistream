import assert from 'node:assert/strict';
import test from 'node:test';
import {probeSignaling} from '../../test-results/panel-state/signaling-probe.js';

test('authenticated signaling diagnostic is bounded, cleans up and never returns credentials', async t=>{
 const previous=globalThis.WebSocket;
 let socket;
 class Socket {
  constructor(url,protocols){this.url=url;this.protocols=protocols;this.closed=false;socket=this;}
  close(){this.closed=true;}
 }
 globalThis.WebSocket=Socket;
 try {
  await t.test('successful upgrade closes its diagnostic connection',async()=>{
   const check=probeSignaling('127.0.0.1',49100,'private-test');
   assert.match(socket.url,/^ws:\/\/127\.0\.0\.1:49100\/sign_in\?peer_id=omnistream-check-/);
   assert.ok(!socket.url.includes('private-test'));
   assert.deepEqual(socket.protocols,['authorization.bearer.private-test']);
   socket.onopen(); assert.equal(await check,undefined);assert.equal(socket.closed,true);
  });
  await t.test('network rejection closes and does not expose the credential',async()=>{
   const check=probeSignaling('127.0.0.1',49100,'private-test');socket.onerror();
   await assert.rejects(check,e=>!e.message.includes('private-test')&&/WebSocket/.test(e.message));
   assert.equal(socket.closed,true);
  });
  await t.test('secure localhost uses WSS and keeps bearer out of the URL',async()=>{
   const check=probeSignaling('localhost',49101,'private-test',5000,true);
   assert.match(socket.url,/^wss:\/\/localhost:49101\/sign_in\?/);
   assert.ok(!socket.url.includes('private-test'));socket.onopen();await check;
  });
  await t.test('IPv6 loopback is bracketed and secure IP mismatch is refused',async()=>{
   const check=probeSignaling('::1',49100,'private-test');
   assert.match(socket.url,/^ws:\/\/\[::1\]:49100\//);socket.onopen();await check;
   socket=undefined;await assert.rejects(probeSignaling('127.0.0.1',49101,'private-test',5000,true));
   assert.equal(socket,undefined);
  });
  await t.test('timeout closes a stuck socket',async()=>{
   await assert.rejects(probeSignaling('127.0.0.1',49100,'private-test',1),/délai/);
   assert.equal(socket.closed,true);
  });
  await t.test('non-loopback and missing credentials create no socket',async()=>{
   socket=undefined;
   await assert.rejects(probeSignaling('remote.example',49100,'private-test'));
   await assert.rejects(probeSignaling('127.0.0.1',49100,''));
   assert.equal(socket,undefined);
  });
 } finally {globalThis.WebSocket=previous;}
});
