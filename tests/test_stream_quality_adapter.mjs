import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { forwardDirectStreamQuality } from '../web/sdk/ov-web-rtc-quality.mjs';

const sdk = readFileSync(new URL('../web/node_modules/@nvidia/ov-web-rtc/dist/ov-web-rtc.js', import.meta.url), 'utf8');

test('real pinned Direct wrapper forwards fidelity controls into the native downstream request', async () => {
  const patched = forwardDirectStreamQuality(sdk);
  const from = patched.indexOf('async startButtonClick(){', patched.indexOf('class Ba{'));
  const to = patched.indexOf('async stopButtonClick(){', from);
  assert.ok(from > 0 && to > from);
  // Execute the actual vendor wrapper method with a recording stream client;
  // verify its request, rather than a duplicate of our profile implementation.
  const make = new Function('R', 'wa', `return new (class { ${patched.slice(from, to)} })()`);
  const wrapper = make({ CursorType:{ FREE:0 } }, value=>value);
  let request;
  wrapper.attemptLabel=()=>''; wrapper.logConnectionAttempt=()=>{};
  wrapper.isSecure=()=>false;
  wrapper._streamClient={startStreaming(value){request=value;}};
  for (const [width,height,codec] of [[1920,1080,'H264'],[3840,2160,'AV1']]) {
    wrapper._props = {width,height,fps:30,videoElementId:'quality-test',codec,maxBitrateKbps:60000,dynamicStreamingMode:0};
    await wrapper.startButtonClick();
    assert.deepEqual(request.downstreamParams,[{videoTagId:'quality-test',codec,width,height,fps:30,maxBitrateKbps:60000,dynamicStreamingMode:0}]);
  }
});

test('an SDK drift cannot silently drop the requested fidelity policy', () => {
  assert.throws(()=>forwardDirectStreamQuality(sdk.replace('fps:this._props.fps},s=this._props.authenticate','changed-wrapper')),/no longer matches/);
  assert.throws(()=>forwardDirectStreamQuality(sdk+sdk),/no longer matches/);
});

test('real SDK creation applies the explicit bitrate override with the SDK kb/s units', async () => {
  const patched=forwardDirectStreamQuality(sdk);
  const from=patched.indexOf('async create(){',patched.indexOf('class Ba{'));
  const to=patched.indexOf('async startButtonClick(){',from);
  const overrides=[];
  const make=new Function('R','Ma','Ua',`return new (class { ${patched.slice(from,to)} })()`);
  const wrapper=make({configureOverrideSettings(value){overrides.push(value);},createStreamClient(){return {}; }},class {},class {});
  wrapper._props={maxBitrateKbps:60000};
  await wrapper.create();
  assert.deepEqual(overrides,[{overrideData:'bitrate=60000'}]);
  overrides.length=0;wrapper._props.maxBitrateKbps=Infinity;
  await wrapper.create();assert.deepEqual(overrides,[]);
});
