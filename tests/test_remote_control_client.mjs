import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { remoteControlCredential, requestRemoteControl } from '../mcp/remote-control-client.mjs';

const token='synthetic-private-control-credential-00001';
const profile={signalingUrl:'ws://100.78.12.34:49100/sign_in',mediaConnectivity:'tailscale'};
function transport(change=()=>{}) {
  const seen={};
  return {seen,request(url,options,callback){
    seen.url=url.href;seen.headers=options.headers;
    const request=new EventEmitter();
    request.destroy=()=>request.emit('close');
    request.end=body=>queueMicrotask(()=>{
      const input=JSON.parse(body);seen.input=input;
      const response=new PassThrough();response.statusCode=200;change(input,response);
      callback(response);response.end(JSON.stringify({ok:true,id:input.id,result:{native:true}}));request.emit('close');
    });
    return request;
  }};
}
test('remote credential references fail closed without reflecting private values or paths',t=>{
  const root=mkdtempSync(path.join(tmpdir(),'omnistream-control-'));t.after(()=>rmSync(root,{recursive:true,force:true}));
  const file=path.join(root,'private-credential');writeFileSync(file,token);
  assert.equal(remoteControlCredential({controlTokenFile:file}),token);
  assert.equal(remoteControlCredential({controlTokenEnv:'OMNISTREAM_REMOTE_CONTROL'},{OMNISTREAM_REMOTE_CONTROL:token}),token);
  writeFileSync(file,'x'.repeat(513));
  assert.throws(()=>remoteControlCredential({controlTokenFile:file}),e=>!e.message.includes(root)&&!e.message.includes(token));
  assert.throws(()=>remoteControlCredential({controlTokenFile:file+'-missing'}),/private credential/);
});
test('private control destination is fixed and credentials occur only in the header',async()=>{
  const t=transport();assert.deepEqual(await requestRemoteControl(profile,token,'simulation.state',{}, {requestImpl:t.request}),{native:true});
  assert.equal(t.seen.url,'http://100.78.12.34:49100/omnistream/control');
  assert.equal(t.seen.headers.Authorization,`Bearer ${token}`);
  assert.doesNotMatch(JSON.stringify(t.seen.input),new RegExp(token));
  assert.throws(()=>requestRemoteControl({...profile,mediaConnectivity:'direct'},token,'scene.inspect',{}),/private overlay/);
});
test('WSS control preserves TLS and mismatched response identities are rejected',async()=>{
  const t=transport();await requestRemoteControl({...profile,signalingUrl:'wss://100.78.12.34:49100/sign_in'},token,'control.status',{}, {requestImpl:t.request});
  assert.equal(t.seen.url,'https://100.78.12.34:49100/omnistream/control');
  const wrong=transport(input=>input.id='wrong-request');
  await assert.rejects(requestRemoteControl(profile,token,'camera.list',{}, {requestImpl:wrong.request}),/unavailable/);
});
