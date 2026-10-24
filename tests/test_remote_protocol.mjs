import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import path from 'node:path';
import os from 'node:os';

test('real MCP boundary separates remote attachment, private ICE, and local runtime ownership', async t => {
  const home=mkdtempSync(path.join(os.tmpdir(),'omnistream-remote-'));
  mkdirSync(path.join(home,'config'));
  writeFileSync(path.join(home,'config','omnistream.json'),JSON.stringify({remoteSessions:[{
    id:'external-test',label:'External stream protocol fixture',provider:'runpod',
    signalingUrl:'wss://gpu.example.test/sign_in',mediaServer:'gpu.example.test',mediaPort:47998,
    mediaConnectivity:'relay',serverIceConfigured:true,streamTokenEnv:'OMNISTREAM_REMOTE_STREAM_TOKEN',iceServersEnv:'OMNISTREAM_REMOTE_ICE'
  }]}));
  const child=spawn(process.execPath,['mcp/server.mjs'],{cwd:path.resolve(import.meta.dirname,'..'),windowsHide:true,
    env:{...process.env,OMNISTREAM_HOME:home,OMNISTREAM_REMOTE_STREAM_TOKEN:'protocol-private-fixture-credential',
      OMNISTREAM_REMOTE_ICE:JSON.stringify([{urls:'turns:relay.example.test:443?transport=tcp',username:'fixture-user',credential:'private-turn-fixture'}])},stdio:['pipe','pipe','pipe']});
  const pending=new Map();let buffer='',sequence=0;let stderr='';child.stderr.on('data',data=>stderr+=data.toString());
  child.stdout.on('data',data=>{buffer+=data.toString();let end;while((end=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,end);buffer=buffer.slice(end+1);if(!line.trim())continue;const message=JSON.parse(line);const call=pending.get(message.id);if(call){pending.delete(message.id);clearTimeout(call.timer);call.resolve(message);}}});
  const request=(method,params)=>new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>{pending.delete(id);reject(new Error('MCP remote contract timed out.'));},5000);pending.set(id,{resolve,timer});child.stdin.write(JSON.stringify({jsonrpc:'2.0',id,method,params})+'\n');});
  const call=(name,args={})=>request('tools/call',{name,arguments:args});
  t.after(async()=>{child.stdin.end();if(child.exitCode===null)await new Promise(resolve=>child.once('exit',resolve));for(const entry of pending.values())clearTimeout(entry.timer);rmSync(home,{recursive:true,force:true});});
  await request('initialize',{protocolVersion:'2025-06-18',capabilities:{},clientInfo:{name:'remote-contract-test',version:'1'}});
  const tools=await request('tools/list',{});
  for(const action of ['open','exchange','close'])assert.deepEqual(tools.result.tools.find(item=>item.name===`${action}_omniverse_remote_signaling`)._meta.ui.visibility,['app']);
  const closeSchema=tools.result.tools.find(item=>item.name==='close_omniverse_remote_signaling').inputSchema;
  assert.ok(closeSchema.properties.code,'NVIDIA application close codes must cross the actual MCP boundary');
  const listed=await call('list_omniverse_remote_sessions');assert.equal(listed.result.structuredContent.profiles[0].accessConfigured,true);
  const unknown=await call('attach_omniverse_remote_stream',{profileId:'unknown'});assert.ok(unknown.error);
  const attached=await call('attach_omniverse_remote_stream',{profileId:'external-test'});
  const id=attached.result.structuredContent.attachmentId;
  assert.equal(attached.result.structuredContent.video,'unverified');
  assert.equal(attached.result._meta['omnistream/remoteStreamConfiguration'].iceServerConfiguration.iceTransportPolicy,'relay');
  assert.doesNotMatch(JSON.stringify([listed.result.structuredContent,attached.result.structuredContent,attached.result.content]),/private-fixture|private-turn|fixture-user/);
  for(const name of ['start_omniverse_stream','launch_omniverse_simulation','stop_omniverse_stream','load_omniverse_stage','navigate_omniverse_camera']){
    const refused=await call(name);assert.ok(refused.error,`${name} must not cross from a remote viewer into a local runtime`);
    assert.match(refused.error.message,/distant|remote/);
  }
  const forbidden=await call('open_omniverse_remote_signaling',{attachmentId:id,peerId:'peer-1',url:'wss://other.example.test/sign_in'});assert.ok(forbidden.error);
  const detached=await call('detach_omniverse_remote_stream',{attachmentId:id});assert.equal(detached.result.structuredContent.remoteRuntimeStopped,false);
  const stale=await call('detach_omniverse_remote_stream',{attachmentId:id});assert.ok(stale.error);
  const state=await call('get_omniverse_stream_status');assert.equal(state.result.structuredContent.processAlive,false);
  assert.doesNotMatch(stderr,/protocol-private|private-turn/);
});
