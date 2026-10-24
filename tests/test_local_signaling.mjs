import test from 'node:test';
import assert from 'node:assert/strict';
import {LocalSignalingRelay} from '../mcp/local-signaling.mjs';

class Socket extends EventTarget {
  static instances=[];
  constructor(url,protocols){super();this.url=url;this.protocols=protocols;this.sent=[];this.closed=false;Socket.instances.push(this);queueMicrotask(()=>this.dispatchEvent(new Event('open')));}
  send(data){this.sent.push(data);}
  message(data){this.dispatchEvent(new MessageEvent('message',{data}));}
  close(code=1000){if(this.closed)return;this.closed=true;this.closeCode=code;this.dispatchEvent(new Event('close'));}
}
function setup(t){let session={identity:{},token:'private-fixture-credential'};let now=100;const relay=new LocalSignalingRelay({getSession:()=>session,port:49100,WebSocketClass:Socket,now:()=>now,idleMs:1000});t.after(()=>relay.dispose());return{relay,replace:()=>session={identity:{},token:'new-private-fixture'},advance:()=>now+=1001};}

test('signaling is authenticated and fixed to the owned Kit loopback endpoint',async t=>{
 const {relay}=setup(t);const opened=await relay.open('peer-123');const socket=Socket.instances.at(-1);
 assert.equal(socket.url,'ws://127.0.0.1:49100/sign_in?peer_id=peer-123&version=2&peer_role=1');
 assert.deepEqual(socket.protocols,['authorization.bearer.private-fixture-credential']);
 assert.doesNotMatch(JSON.stringify(opened),/private-fixture|bearer/);
 await assert.rejects(relay.open('peer&host=other'),/identity/);
});
test('signaling batch retries do not send duplicate messages and events remain until acknowledged',async t=>{
 const {relay}=setup(t);const {channelId}=await relay.open('peer-1');const socket=Socket.instances.at(-1);
 socket.message('{"sdp":"private-fixture-offer"}');
 const args={channelId,afterSequence:0,messages:[{sequence:1,data:'answer'}],waitMs:0};
 const first=await relay.exchange(args);const retried=await relay.exchange(args);
 assert.deepEqual(socket.sent,['answer']);assert.deepEqual(retried.events,first.events);
 assert.equal(first.ackClientSequence,1);
 assert.deepEqual((await relay.exchange({channelId,afterSequence:first.events[0].sequence,waitMs:0})).events,[]);
});
test('Kit pairing and reconnect metadata are preserved without accepting a caller bearer',async t=>{
 const {relay}=setup(t);await relay.open('peer-session',{pairingId:'pair-fixture',sessionId:'session-fixture',reconnect:true});
 const socket=Socket.instances.at(-1);assert.match(socket.url,/&pairing_id=pair-fixture&reconnect=1$/);
 assert.deepEqual(socket.protocols,['x-nv-sessionid.session-fixture','authorization.bearer.private-fixture-credential']);
 await assert.rejects(relay.open('peer-other',{pairingId:'bad&endpoint=external'}),/pairing/);
});
test('invalid or oversized batches have no partial signaling side effect',async t=>{
 const {relay}=setup(t);const {channelId}=await relay.open('peer-2');const socket=Socket.instances.at(-1);
 for(const messages of [[{sequence:1,data:'valid'},{sequence:3,data:'gap'}],[{sequence:1,data:'x'.repeat(131073)}],Array.from({length:5},(_,i)=>({sequence:i+1,data:'x'.repeat(131072)}))])
  await assert.rejects(relay.exchange({channelId,messages,waitMs:0}));
 assert.deepEqual(socket.sent,[]);
});
test('replacement or idle expiry closes the old channel before any further send',async t=>{
 const h=setup(t);const opened=await h.relay.open('peer-3');const socket=Socket.instances.at(-1);
 h.replace();await assert.rejects(h.relay.exchange({channelId:opened.channelId,messages:[{sequence:1,data:'forbidden'}],waitMs:0}),/changed/);
 assert.equal(socket.closed,true);assert.deepEqual(socket.sent,[]);
 const next=await h.relay.open('peer-4');h.advance();h.relay.expire();
 await assert.rejects(h.relay.exchange({channelId:next.channelId,waitMs:0}),/expired/);
});
test('event storage is bounded and overflow closes signaling without reporting media success',async t=>{
 const {relay}=setup(t);const {channelId}=await relay.open('peer-5');const socket=Socket.instances.at(-1);
 for(let i=0;i<6;i++)socket.message('x'.repeat(131072));
 const state=await relay.exchange({channelId,waitMs:0});
 assert.equal(state.state,'closed');assert.equal(socket.closed,true);
 assert.ok(JSON.stringify(state.events).length<150000);assert.equal(state.video,undefined);
});
test('safe close releases pending polling and bounds concurrent channels',async t=>{
 const {relay}=setup(t);const first=await relay.open('peer-6');await relay.open('peer-7');
 await assert.rejects(relay.open('peer-8'),/previous/);
 const reading=relay.exchange({channelId:first.channelId,waitMs:1000});relay.closeAll();
 assert.equal((await reading).state,'closed');assert.equal(relay.channels.size,0);
});

test('SDK reconnect close code reaches Kit unchanged instead of requesting normal teardown',async t=>{
 const {relay}=setup(t);const first=await relay.open('peer-handoff');const socket=Socket.instances.at(-1);
 assert.throws(()=>relay.close(first.channelId,1006),/close code/);
 assert.equal(socket.closed,false,'Invalid close codes must not close the managed channel.');
 relay.close(first.channelId,4001);
 assert.equal(socket.closeCode,4001,'Code 1000 would tell Kit to tear down the media session during SDK reconnect.');
 assert.equal(relay.channels.size,0);
 const next=await relay.open('peer-reconnect',{reconnect:true});const nextSocket=Socket.instances.at(-1);
 assert.match(nextSocket.url,/reconnect=1$/);
 relay.close(next.channelId);assert.equal(nextSocket.closeCode,1000,'Explicit normal close keeps the existing stop behavior.');
});
