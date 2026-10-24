import test from 'node:test';
import assert from 'node:assert/strict';
import {McpSignalingSocket,installMcpSignaling,isOwnedSignalingUrl} from '../../test-results/panel-state/mcp-signaling.js';

const url='ws://127.0.0.1:49100/sign_in?peer_id=peer-fixture&version=2&peer_role=1';
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function harness(){
 const calls=[];const waits=[];
 const invoke=async(name,args)=>{calls.push({name,args});if(name==='open_omniverse_signaling')return{channelId:'fixture-channel',state:'open'};if(name==='close_omniverse_signaling')return{state:'closed'};return new Promise(resolve=>waits.push({resolve,args}));};
 return{calls,invoke,waits,reply(events=[],ack=0,state='open'){const current=waits.shift();assert.ok(current);current.resolve({channelId:'fixture-channel',state,ackClientSequence:ack,events});},stop(){for(const waiting of waits.splice(0))waiting.resolve({channelId:'fixture-channel',state:'closed',ackClientSequence:0,events:[]});}};
}
test('only the owned Kit signaling URL is routed; unrelated networking retains its native constructor',async t=>{
 const h=harness();const nativeCalls=[];
 class Native{constructor(...args){nativeCalls.push(args);}}
 const target={WebSocket:Native};const route=installMcpSignaling(target,49100,h.invoke);t.after(()=>{route.dispose();h.stop();});
 for(const other of ['wss://outside.example/sign_in','ws://localhost:49100/sign_in?peer_id=x&version=2&peer_role=1',url.replace(':49100',':49102'),url+'&target=elsewhere',url+'&peer_id=duplicate']){
  assert.equal(isOwnedSignalingUrl(other,49100),false);new target.WebSocket(other);
 }
 assert.equal(nativeCalls.length,5);
 const socket=new target.WebSocket(url,['authorization.bearer.private-panel-fixture']);await flush();
 assert.ok(socket instanceof McpSignalingSocket);assert.equal(nativeCalls.length,5);
 assert.doesNotMatch(JSON.stringify(h.calls),/private-panel-fixture|authorization|bearer/);
 route.dispose();assert.equal(target.WebSocket,Native);
});
test('the SDK WebSocket interface exchanges real signaling strings without claiming video success',async t=>{
 const h=harness();const socket=new McpSignalingSocket(url,h.invoke);t.after(()=>{socket.close();h.stop();});
 const messages=[];socket.onopen=()=>socket.send('fixture-offer');socket.onmessage=e=>messages.push(e.data);
 await flush();assert.equal(socket.readyState,socket.OPEN);assert.equal(socket.bufferedAmount,'fixture-offer'.length);
 assert.deepEqual(h.waits[0].args.messages,[{sequence:1,data:'fixture-offer'}]);
 h.reply([{sequence:1,type:'message',data:'fixture-answer'}],1);await flush();
 assert.deepEqual(messages,['fixture-answer']);assert.equal(socket.bufferedAmount,0);
 assert.equal(h.waits[0].args.afterSequence,1);assert.equal(socket.framesDecoded,undefined);
});
test('SDK pairing and session metadata reach the local relay but its bearer stays private',async t=>{
 const h=harness();class Native{}
 const target={WebSocket:Native};const route=installMcpSignaling(target,49100,h.invoke);t.after(()=>{route.dispose();h.stop();});
 new target.WebSocket(url+'&pairing_id=pair-fixture&reconnect=1',['x-nv-sessionid.session-fixture','authorization.bearer.private-panel-fixture']);
 await flush();assert.deepEqual(h.calls[0].args,{peerId:'peer-fixture',pairingId:'pair-fixture',sessionId:'session-fixture',reconnect:true});
 assert.doesNotMatch(JSON.stringify(h.calls),/private-panel-fixture|authorization/);
});
test('duplicate receive events are ignored and a missing event closes signaling',async t=>{
 const h=harness();const socket=new McpSignalingSocket(url,h.invoke);t.after(()=>{socket.close();h.stop();});
 const messages=[];let errors=0;socket.onmessage=e=>messages.push(e.data);socket.onerror=()=>errors++;
 await flush();h.reply([{sequence:1,type:'message',data:'one'}]);await flush();
 h.reply([{sequence:1,type:'message',data:'one'},{sequence:2,type:'message',data:'two'}]);await flush();
 assert.deepEqual(messages,['one','two']);
 h.reply([{sequence:4,type:'message',data:'gap'}]);await flush();
 assert.equal(socket.readyState,socket.CLOSED);assert.equal(errors,1);assert.deepEqual(messages,['one','two']);
 assert.ok(h.calls.some(c=>c.name==='close_omniverse_signaling'));
});
test('close before a late channel open prevents a second connection and closes that exact channel',async()=>{
 let release;const calls=[];const opening=new Promise(resolve=>release=resolve);
 const socket=new McpSignalingSocket(url,async(name,args)=>{calls.push({name,args});return name==='open_omniverse_signaling'?opening:{state:'closed'};});
 let opened=0;socket.onopen=()=>opened++;socket.close();release({channelId:'late-fixture',state:'open'});await flush();
 assert.equal(opened,0);assert.equal(socket.readyState,socket.CLOSED);
 assert.deepEqual(calls.filter(c=>c.name==='close_omniverse_signaling'),[{name:'close_omniverse_signaling',args:{channelId:'late-fixture'}}]);
});
test('binary, oversized or malformed responses fail closed',async t=>{
 const h=harness();const socket=new McpSignalingSocket(url,h.invoke);t.after(()=>{socket.close();h.stop();});
 assert.throws(()=>socket.send('before-open'),/connecting/);await flush();
 socket.send(new Uint8Array([1,2]));assert.equal(socket.readyState,socket.CLOSED);
 assert.equal(h.calls.filter(c=>c.name==='exchange_omniverse_signaling').length,1);
});
test('remote close releases the controller channel once and preserves its close status',async t=>{
 const h=harness();const socket=new McpSignalingSocket(url,h.invoke);t.after(()=>h.stop());let close;
 socket.onclose=event=>close=event;await flush();h.reply([{sequence:1,type:'close',code:1000}],0,'closed');await flush();
 assert.equal(close.code,1000);assert.equal(close.wasClean,true);socket.close();
 assert.equal(h.calls.filter(c=>c.name==='close_omniverse_signaling').length,1);
});
test('client close is asynchronous so SDK cleanup cannot see its own close as a remote disconnect',async t=>{
 const h=harness();const socket=new McpSignalingSocket(url,h.invoke);t.after(()=>h.stop());
 await flush();let sdkSocket=socket;let disconnected=false;
 socket.onclose=()=>{if(sdkSocket===socket)disconnected=true;};
 socket.close();assert.equal(socket.readyState,socket.CLOSING);sdkSocket=null;
 await flush();assert.equal(socket.readyState,socket.CLOSED);assert.equal(disconnected,false);
 assert.equal(h.calls.filter(c=>c.name==='close_omniverse_signaling').length,1);
});

test('SDK application close codes survive the panel-to-MCP boundary',async t=>{
 const h=harness();const socket=new McpSignalingSocket(url,h.invoke);t.after(()=>h.stop());
 await flush();socket.close(4001);await flush();
 assert.deepEqual(h.calls.filter(c=>c.name==='close_omniverse_signaling'),[
  {name:'close_omniverse_signaling',args:{channelId:'fixture-channel',code:4001}},
 ]);
});
