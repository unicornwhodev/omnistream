import test from 'node:test';
import assert from 'node:assert/strict';
import { RemoteSessions, parseRemoteProfiles } from '../mcp/remote-sessions.mjs';

const profile = { id: 'gpu-session', label: 'Existing GPU session', provider: 'generic',
  signalingUrl: 'wss://gpu.example.test/kit/sign_in', mediaServer: 'media.example.test', mediaPort: 47998,
  streamTokenEnv: 'OMNISTREAM_REMOTE_STREAM_TOKEN', mediaConnectivity: 'direct' };
const env = { OMNISTREAM_REMOTE_STREAM_TOKEN: 'private-fixture-token-never-output',
  OMNISTREAM_REMOTE_ICE: JSON.stringify([{urls:'turns:relay.example.test:443?transport=tcp',username:'fixture-user',credential:'private-turn-fixture'}]) };
class Socket extends EventTarget {
  static instances=[];
  constructor(url, protocols) { super(); this.url=url;this.protocols=protocols;this.sent=[];Socket.instances.push(this);queueMicrotask(()=>this.dispatchEvent(new Event('open'))); }
  send(data) {this.sent.push(data);}
  close(){if(this.closed)return;this.closed=true;this.dispatchEvent(new Event('close'));}
}
const setup=(t,profiles=[profile])=>{const remote=new RemoteSessions({profiles,env,WebSocketClass:Socket});t.after(()=>remote.dispose());return remote;};

test('profiles reject notebook/proxy links, plaintext endpoints and inline secrets without echoing credentials',()=>{
  for(const changes of [ {signalingUrl:'https://colab.research.google.com/drive/not-a-stream#private-fixture'},
    {signalingUrl:'ws://gpu.example.test/sign_in'}, {signalingUrl:'wss://user:private-fixture@gpu.example.test/sign_in'},
    {signalingUrl:'wss://gpu.example.test/sign_in?token=private-fixture'}, {token:'private-fixture'},
    {streamTokenEnv:'OTHER_SECRET'}, {mediaServer:'127.0.0.1/path'}, {mediaPort:0} ]) {
    assert.throws(()=>parseRemoteProfiles([{...profile,...changes}]), error=>!error.message.includes('private-fixture'));
  }
  assert.throws(()=>parseRemoteProfiles([profile,profile]),/duplicate/);
});
test('provider profiles require a concrete relay path rather than treating an HTTP proxy as media',()=>{
  for(const provider of ['runpod','colab']) {
    assert.throws(()=>parseRemoteProfiles([{...profile,provider}]),/relay path/);
    assert.throws(()=>parseRemoteProfiles([{...profile,provider,mediaConnectivity:'relay'}]),/ICE/);
    assert.equal(parseRemoteProfiles([{...profile,provider,mediaConnectivity:'relay',serverIceConfigured:true,iceServersEnv:'OMNISTREAM_REMOTE_ICE'}]).length,1);
  }
});
test('public listing and attachment never disclose credentials or claim a decoded image',t=>{
  const remote=setup(t);const before=remote.list();assert.equal(before.attachment,null);
  const attached=remote.attach(profile.id);const publicResult=JSON.stringify([before,remote.list(),attached.attachment]);
  assert.doesNotMatch(publicResult,/private-fixture|private-turn|streamTokenEnv|iceServerConfiguration/);
  assert.equal(attached.attachment.video,'unverified');assert.equal(attached.attachment.ownership,'external');
  assert.equal(attached.attachment.controlBridgeAvailable,false);assert.equal(attached.privateConfiguration.mediaServer,'media.example.test');
});
test('WSS signaling uses only the selected immutable endpoint and backend credential',async t=>{
  const remote=setup(t);const attached=remote.attach(profile.id);const args={attachmentId:attached.attachment.attachmentId,peerId:'peer-1'};
  const opened=await remote.open(args);const socket=Socket.instances.at(-1);
  assert.equal(socket.url,'wss://gpu.example.test/kit/sign_in?peer_id=peer-1&version=2&peer_role=1');
  assert.deepEqual(socket.protocols,['authorization.bearer.'+env.OMNISTREAM_REMOTE_STREAM_TOKEN]);
  assert.equal(opened.state,'open');assert.equal(opened.video,undefined);
});
test('reopen retains the attachment but switching profiles needs explicit disconnect',t=>{
  const remote=setup(t,[profile,{...profile,id:'another'}]);const first=remote.attach(profile.id);
  assert.equal(remote.attach(profile.id).attachment.attachmentId,first.attachment.attachmentId);
  assert.throws(()=>remote.attach('another'),/Disconnect/);
});
test('detach closes signaling, preserves the external runtime and rejects stale attachment requests',async t=>{
  const remote=setup(t);const id=remote.attach(profile.id).attachment.attachmentId;
  const {channelId}=await remote.open({attachmentId:id,peerId:'peer-2'});const socket=Socket.instances.at(-1);
  assert.deepEqual(remote.detach(id),{detached:true,remoteRuntimeStopped:false});assert.equal(socket.closed,true);
  const next=remote.attach(profile.id).attachment.attachmentId;assert.notEqual(next,id);
  await assert.rejects(remote.exchange({attachmentId:id,channelId,messages:[{sequence:1,data:'forbidden'}]}),/changed/);
  assert.deepEqual(socket.sent,[]);assert.throws(()=>remote.detach(id),/changed/);assert.equal(remote.describe().attachmentId,next);
});
test('missing stream/ICE credentials block attachment; private TURN configuration stays app-only',t=>{
  const remote=new RemoteSessions({profiles:[profile],env:{},WebSocketClass:Socket});t.after(()=>remote.dispose());
  assert.equal(remote.list().profiles[0].accessConfigured,false);assert.throws(()=>remote.attach(profile.id),/credentials/);
  const relay=setup(t,[{...profile,provider:'runpod',mediaConnectivity:'relay',serverIceConfigured:true,iceServersEnv:'OMNISTREAM_REMOTE_ICE'}]);
  const attached=relay.attach(profile.id);assert.equal(attached.privateConfiguration.iceServerConfiguration.iceTransportPolicy,'relay');
  assert.doesNotMatch(JSON.stringify(attached.attachment),/fixture-user|private-turn/);
});
test('disposal only releases sockets and invalidates this viewers attachment',async t=>{
  const remote=setup(t);const id=remote.attach(profile.id).attachment.attachmentId;
  await remote.open({attachmentId:id,peerId:'peer-3'});const socket=Socket.instances.at(-1);remote.dispose();
  assert.equal(socket.closed,true);assert.equal(remote.describe(),null);
});

test('Tailscale permits provider streams only to the exact private overlay peer',async t=>{
  const privateProfile={...profile,provider:'colab',mediaConnectivity:'tailscale',
    signalingUrl:'ws://100.78.12.34:49100/sign_in',mediaServer:'100.78.12.34'};
  delete privateProfile.streamTokenEnv;
  for(const change of [{signalingUrl:'ws://192.168.1.5:49100/sign_in'},
    {signalingUrl:'ws://100.63.12.34:49100/sign_in'},{mediaServer:'100.78.12.35'},
    {iceServersEnv:'OMNISTREAM_REMOTE_ICE'}]) assert.throws(()=>parseRemoteProfiles([{...privateProfile,...change}]));
  let checked=null;
  const remote=new RemoteSessions({profiles:[privateProfile],env:{},WebSocketClass:Socket,
    verifyPrivatePeer:async address=>{checked=address;}});t.after(()=>remote.dispose());
  assert.equal(remote.list().profiles[0].accessConfigured,true);
  const id=remote.attach(privateProfile.id).attachment.attachmentId;
  await remote.open({attachmentId:id,peerId:'private-peer'});
  assert.equal(checked,'100.78.12.34');assert.deepEqual(Socket.instances.at(-1).protocols,[]);
});

test('an unavailable or replaced private peer opens no signaling socket',async t=>{
  const privateProfile={...profile,mediaConnectivity:'tailscale',
    signalingUrl:'ws://100.78.12.34:49100/sign_in',mediaServer:'100.78.12.34'};
  const remote=new RemoteSessions({profiles:[privateProfile],env,WebSocketClass:Socket,
    verifyPrivatePeer:async()=>{throw new Error('Private peer offline');}});t.after(()=>remote.dispose());
  const id=remote.attach(privateProfile.id).attachment.attachmentId;const count=Socket.instances.length;
  await assert.rejects(remote.open({attachmentId:id,peerId:'private-peer'}),/offline/);
  assert.equal(Socket.instances.length,count);
  remote.verifyPrivatePeer=async()=>{remote.detach(id);remote.attach(privateProfile.id);};
  await assert.rejects(remote.open({attachmentId:id,peerId:'private-peer'}),/changed/);
  assert.equal(Socket.instances.length,count);
});

test('operator profile updates are revalidated without a controller reload',async t=>{
  let configured=[{...profile}];
  const remote=new RemoteSessions({getProfiles:()=>configured,env,WebSocketClass:Socket});t.after(()=>remote.dispose());
  const first=remote.attach(profile.id).attachment.attachmentId;
  const {channelId}=await remote.open({attachmentId:first,peerId:'before-update'});const socket=Socket.instances.at(-1);
  configured=[{...profile,label:'Replacement GPU',signalingUrl:'wss://replacement.example.test/sign_in',mediaServer:'replacement.example.test'}];
  const listed=remote.list();assert.equal(listed.profiles[0].label,'Replacement GPU');assert.equal(listed.attachment,null);assert.equal(socket.closed,true);
  await assert.rejects(remote.exchange({attachmentId:first,channelId,messages:[]}),/changed/);
  const second=remote.attach(profile.id).attachment.attachmentId;assert.notEqual(second,first);
  await remote.open({attachmentId:second,peerId:'after-update'});
  assert.match(Socket.instances.at(-1).url,/^wss:\/\/replacement\.example\.test\/sign_in\?/);
  assert.doesNotMatch(JSON.stringify(listed),/private-fixture/);
});

test('removed and invalid operator profiles close old channels without disclosing source errors',async t=>{
  let configured=[profile];let unavailable=false;
  const remote=new RemoteSessions({getProfiles:()=>{if(unavailable)throw new Error('private-fixture-source-error');return configured;},env,WebSocketClass:Socket});t.after(()=>remote.dispose());
  const first=remote.attach(profile.id).attachment.attachmentId;await remote.open({attachmentId:first,peerId:'removed'});const socket=Socket.instances.at(-1);
  configured=[];assert.equal(remote.list().attachment,null);assert.equal(socket.closed,true);assert.throws(()=>remote.attach(profile.id),/Unknown/);
  configured=[profile];const second=remote.attach(profile.id).attachment.attachmentId;await remote.open({attachmentId:second,peerId:'invalid'});const nextSocket=Socket.instances.at(-1);
  configured=[{...profile,signalingUrl:'https://not-a-stream.example.test/'}];
  await assert.rejects(remote.exchange({attachmentId:second,messages:[]}),/configuration is unavailable or invalid/);
  assert.equal(nextSocket.closed,true);assert.equal(remote.describe(),null);
  unavailable=true;assert.throws(()=>remote.list(),error=>!error.message.includes('private-fixture'));
});

test('unchanged operator profiles retain attachments and a private peer change during verification opens no socket',async t=>{
  const privateProfile={...profile,provider:'colab',mediaConnectivity:'tailscale',signalingUrl:'ws://100.78.12.34:49100/sign_in',mediaServer:'100.78.12.34'};
  let configured=[privateProfile];
  const remote=new RemoteSessions({getProfiles:()=>configured,env,WebSocketClass:Socket,verifyPrivatePeer:async()=>{
    configured=[{...privateProfile,signalingUrl:'ws://100.78.12.35:49100/sign_in',mediaServer:'100.78.12.35'}];
  }});t.after(()=>remote.dispose());
  const id=remote.attach(privateProfile.id).attachment.attachmentId;
  configured=JSON.parse(JSON.stringify(configured));assert.equal(remote.list().attachment.attachmentId,id);assert.equal(remote.attach(privateProfile.id).attachment.attachmentId,id);
  const before=Socket.instances.length;await assert.rejects(remote.open({attachmentId:id,peerId:'changed-during-check'}),/changed/);
  assert.equal(Socket.instances.length,before);assert.equal(remote.describe(),null);
});
