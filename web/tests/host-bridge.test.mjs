import test from 'node:test';
import assert from 'node:assert/strict';
import {App} from '@modelcontextprotocol/ext-apps';
import {createHostBridge} from '../node_modules/.cache/omnistream-bridge-tests/host-bridge.js';

test('embedded panel gates tools on one completed handshake even when the legacy alias is present', async () => {
  let finish, connects=0, sdkCalls=0, legacyCalls=0;
  const bridge=createHostBridge({
    connect:()=>{connects++;return new Promise(resolve=>{finish=resolve;});},
    callServerTool:async params=>{sdkCalls++;return params;},
  }, {embedded:true,legacyCallTool:async()=>{legacyCalls++;}});
  assert.equal(bridge.isReady(),false);
  await assert.rejects(bridge.callTool('read',{}),/pas initialisée/);
  const first=bridge.start(), second=bridge.start();
  assert.equal(first,second); assert.equal(connects,1);
  await assert.rejects(bridge.callTool('read',{}),/pas initialisée/);
  finish(); assert.equal(await first,true); assert.equal(bridge.phase,'mcp');
  assert.deepEqual(await bridge.callTool('read',{value:3}),{name:'read',arguments:{value:3}});
  assert.equal(sdkCalls,1); assert.equal(legacyCalls,0);
});

test('failed embedded handshake never falls back to a premature legacy tool call', async () => {
  let legacyCalls=0;
  const bridge=createHostBridge({connect:async()=>{throw Error('fixture failure');},callServerTool:async()=>{}},
    {embedded:true,legacyCallTool:async()=>{legacyCalls++;}});
  assert.equal(await bridge.start(),false); assert.equal(bridge.phase,'failed');
  await assert.rejects(bridge.callTool('read',{}),/pas initialisée/);
  assert.equal(legacyCalls,0);
});

test('standalone harness uses its explicit local shim without initiating an Apps handshake', async () => {
  let connects=0;
  const bridge=createHostBridge({connect:async()=>{connects++;},callServerTool:async()=>{}},
    {embedded:false,legacyCallTool:async(name,args)=>({name,args})});
  assert.equal(await bridge.start(),true); assert.equal(bridge.phase,'legacy');
  assert.deepEqual(await bridge.callTool('read',{value:2}),{name:'read',args:{value:2}});
  assert.equal(connects,0);
});

test('standalone page without a controller stays offline', async () => {
  const bridge=createHostBridge({connect:async()=>{throw Error('must not connect');},callServerTool:async()=>{}},{embedded:false});
  assert.equal(await bridge.start(),false); assert.equal(bridge.phase,'offline');
  await assert.rejects(bridge.callTool('read',{}),/pas initialisée/);
});

test('real Apps SDK sends initialize and initialized before tools/call and preserves private result metadata', async t => {
  const messages=[];
  const transport={
    async start(){}, async close(){this.onclose?.();},
    async send(message){
      messages.push(message);
      if(message.method==='ui/initialize') {
        queueMicrotask(()=>this.onmessage?.({jsonrpc:'2.0',id:message.id,result:{
          protocolVersion:message.params.protocolVersion,hostInfo:{name:'strict-fixture',version:'1'},
          hostCapabilities:{serverTools:{}},hostContext:{theme:'dark',displayMode:'inline'},
        }}));
      } else if(message.method==='tools/call') {
        assert.ok(messages.some(m=>m.method==='ui/notifications/initialized'));
        queueMicrotask(()=>this.onmessage?.({jsonrpc:'2.0',id:message.id,result:{
          content:[],structuredContent:{ok:true},_meta:{fixtureOnly:'private-response-metadata'},
        }}));
      }
    },
  };
  const app=new App({name:'OmniStream handshake test',version:'1'}, {}, {autoResize:false,strict:true});
  t.after(()=>app.close());
  const bridge=createHostBridge({connect:()=>app.connect(transport,{timeout:1000}),
    callServerTool:params=>app.callServerTool(params,{timeout:1000})},{embedded:true});
  assert.equal(await bridge.start(),true);
  const result=await bridge.callTool('supervise_omniverse_simulation',{});
  assert.deepEqual(messages.map(m=>m.method),['ui/initialize','ui/notifications/initialized','tools/call']);
  assert.deepEqual(result.structuredContent,{ok:true});
  assert.equal(result._meta.fixtureOnly,'private-response-metadata');
});
