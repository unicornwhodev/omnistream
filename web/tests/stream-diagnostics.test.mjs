import test from 'node:test';
import assert from 'node:assert/strict';
import {policyDiagnostic,streamEventDiagnostic,installRtcDiagnostics} from '../../test-results/panel-state/stream-diagnostics.js';

test('CSP diagnosis classifies the resource without retaining private URLs',()=>{
 const event={effectiveDirective:'connect-src',disposition:'enforce'};
 for(const [blockedURI,pattern] of [
  ['data:image/avif;base64,private-payload',/data:/],
  ['blob:https://private.example/private-id',/blob:/],
  ['ws://user:private-password@127.0.0.1:49100/sign_in?token=private-secret',/ws:\/\/127\.0\.0\.1:49100/],
  ['https://private.example/private-path?token=private-secret',/destination masquée/],
  ['private-invalid-value',/non identifiée/],
 ]) {
  const result=policyDiagnostic({...event,blockedURI});
  assert.match(result,pattern);assert.doesNotMatch(result,/private-|private\./);
 }
 assert.equal(policyDiagnostic({...event,effectiveDirective:'script-src',blockedURI:'private'}),null);
 assert.match(policyDiagnostic({...event,disposition:'private-value',blockedURI:'data:'}),/unknown/);
});

test('SDK diagnosis never copies arbitrary info, but retains recognized error codes',()=>{
 const result=streamEventDiagnostic({action:'stop',status:'error',info:'NVST_R_INVALID_STATE 800b1000 https://private.example/?token=private-secret'});
 assert.match(result,/stop\/error.*NVST_R_INVALID_STATE 800b1000/);
 assert.doesNotMatch(result,/private|https/);
 assert.equal(streamEventDiagnostic({action:'stop',status:'error',info:'Session stopped: NETWORK_ERROR'}),'SDK vidéo : stop/error [NETWORK_ERROR].');
 assert.doesNotMatch(streamEventDiagnostic({info:'Session stopped: private-value'}),/private/);
 assert.equal(streamEventDiagnostic({action:'private-action',status:'private-status',info:Error('private-message')}),'SDK vidéo : event/unknown.');
});

test('native RTC observation preserves peers, omits ICE addresses and cleans up',async()=>{
 class Peer extends EventTarget {
  connectionState='new';iceConnectionState='new';signalingState='stable';closed=false;
  async getStats(){return new Map([['private-id',{type:'inbound-rtp',kind:'video',bytesReceived:4096,framesDecoded:3,remoteAddress:'private-address'}]]);}
  close(){this.closed=true;}
 }
 const target={RTCPeerConnection:Peer},messages=[];
 const observer=installRtcDiagnostics(target,message=>messages.push(message));
 const peer=new target.RTCPeerConnection();assert.ok(peer instanceof Peer);
 peer.connectionState='connected';peer.dispatchEvent(new Event('connectionstatechange'));
 peer.iceConnectionState='connected';peer.dispatchEvent(new Event('iceconnectionstatechange'));
 const error=new Event('icecandidateerror');Object.assign(error,{errorCode:701,address:'private-address',url:'private-url'});peer.dispatchEvent(error);
 await new Promise(resolve=>setImmediate(resolve));
 assert.ok(messages.some(message=>message.includes('4096 octets, 3 images')));
 assert.ok(messages.some(message=>message.includes('ICE 701')));
 assert.doesNotMatch(messages.join('\n'),/private/);
 observer.dispose();assert.equal(target.RTCPeerConnection,Peer);assert.equal(peer.closed,false);
 const count=messages.length;peer.dispatchEvent(new Event('iceconnectionstatechange'));assert.equal(messages.length,count);
});
