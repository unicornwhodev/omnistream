import test from 'node:test';
import assert from 'node:assert/strict';
import { createRemoteControlHost } from '../mcp/remote-control-host.mjs';

const token = 'synthetic-control-test-credential-never-output';
async function setup(t, request) {
  const calls = [];
  const bridge = { isConnected: true, async start() {}, async close() {}, async request(method, params) { calls.push({method,params}); return request ? request(method,params) : { nativeResult: true }; } };
  const host = await createRemoteControlHost({ token, port: 0, controlServer: bridge });
  t.after(() => host.close());
  const call = (body, headers = {}) => fetch(`http://127.0.0.1:${host.address.port}/omnistream/control`, {
    method: 'POST', headers: {Authorization:`Bearer ${token}`, 'Content-Type':'application/json', ...headers}, body: JSON.stringify(body),
  });
  return { host, calls, call };
}

test('remote facade requires authentication and rejects browser-origin requests and lifecycle shutdown', async t => {
  const {call,calls} = await setup(t);
  const body={id:'one',method:'scene.inspect',params:{}};
  assert.equal((await call(body,{Authorization:'Bearer wrong'})).status,401);
  assert.equal((await call(body,{Origin:'https://untrusted.example.test'})).status,401);
  assert.equal((await call({...body,method:'runtime.prepare_stop'})).status,400);
  assert.equal((await call({...body,method:'python.execute'})).status,400);
  assert.deepEqual(calls,[]);
});

test('a retried mutation executes once, survives its HTTP client and cannot change parameters', async t => {
  let release;const completion=new Promise(resolve=>release=resolve);
  const {call,calls}=await setup(t,()=>completion);
  const body={id:'apply-one',method:'scene.apply',params:{previewId:'bounded-preview'}};
  const first=call(body);const retry=call(body);
  await new Promise(resolve=>setTimeout(resolve,30));
  assert.equal(calls.length,1);
  const blocked=await call({id:'apply-two',method:'scene.undo',params:{}});
  assert.equal((await blocked.json()).error.code,'mutation_blocked');
  assert.equal((await call({...body,params:{previewId:'changed'}})).status,400);
  release({revision:2});
  assert.deepEqual(await (await first).json(),await (await retry).json());
  assert.equal(calls.length,1);
});

test('uncertain native completion blocks mutations while preserving read access', async t => {
  const {call,calls}=await setup(t,method=>{
    if(method==='scene.apply')throw Object.assign(new Error('private-native-detail'),{code:'request_timeout'});
    return {revision:2};
  });
  const uncertain=await (await call({id:'uncertain',method:'scene.apply',params:{}})).json();
  assert.equal(uncertain.error.code,'request_timeout');assert.doesNotMatch(JSON.stringify(uncertain),/private-native-detail/);
  assert.equal((await (await call({id:'next',method:'scene.undo',params:{}})).json()).error.code,'mutation_blocked');
  assert.equal((await (await call({id:'read',method:'scene.inspect',params:{}})).json()).result.revision,2);
  assert.equal(calls.length,2);
});
