import assert from 'node:assert/strict';
import test from 'node:test';
import net from 'node:net';
import { once } from 'node:events';
import { LiveEventStore } from './live-events.mjs';
import { LoopbackControlServer } from './control-rpc.mjs';
import { sceneTools, sceneRoutes, liveTool, validateSchema } from './scene-tools.mjs';
const validate=(name,data)=>validateSchema(data,sceneRoutes.get(name)?.inputSchema??liveTool.inputSchema);
const identity={stageId:'s1',expectedRevision:0};
const trx={op:'transform',primPath:'/World/Cube',translation:[0,1,2],rotation:[0,0,0],scale:[1,1,1]};
const event=(n,kind='telemetry')=>({sequence:n,atUnixMs:1000+n,kind,data:{playing:false}});
test('all scene tools have unique names, explicit bounds and truthful annotations',()=>{
  assert.equal(new Set(sceneTools.map(t=>t.name)).size,10);
  assert.equal(sceneRoutes.size,10);
  for(const t of [...sceneTools,liveTool]){assert.ok(t.title);assert.equal(t.inputSchema.additionalProperties,false);}
  assert.equal(liveTool.annotations.openWorldHint,false);
  assert.equal(sceneTools.find(t=>t.name==='apply_omniverse_scene_patch').annotations.readOnlyHint,false);
});
test('valid patch matches the discriminated schema',()=>validate('preview_omniverse_scene_patch',{...identity,operations:[trx]}));
test('missing revision, arbitrary execution, unknown fields rejected',()=>{
  for(const args of [{stageId:'s1',operations:[trx]},{...identity,operations:[{op:'python',code:'foo'}]},{...identity,operations:[trx],exec:'evil'}])
    assert.throws(()=>validate('preview_omniverse_scene_patch',args));
});
test('nonfinite, Boolean numerical, path traversal and oversized vectors rejected',()=>{
  for(const change of [{translation:[NaN,0,0]},{translation:[true,0,0]},{primPath:'/World/../Cube'},{scale:[0,1,1]},{translation:[0,0,0,0]}])
    assert.throws(()=>validate('preview_omniverse_scene_patch',{...identity,operations:[{...trx,...change}]}));
});
test('export/discard need explicit true; bounded runtime required',()=>{
  assert.throws(()=>validate('export_omniverse_scene_patch',{...identity,relativePath:'out.usda',confirm:false}));
  assert.throws(()=>validate('run_omniverse_scene',{stageId:'s1',mode:'physics',wallTimeLimitSeconds:10000}));
  validate('run_omniverse_scene',{stageId:'s1',mode:'animation',wallTimeLimitSeconds:60});
});
test('array limits prevent context and main-thread floods',()=>{
  assert.throws(()=>validate('preview_omniverse_scene_patch',{...identity,operations:Array(33).fill(trx)}));
  assert.throws(()=>validate('configure_omniverse_scene_watch',{stageId:'s1',properties:Array(17).fill({primPath:'/World',attribute:'physics:mass'})}));
  assert.throws(()=>validate('read_omniverse_live_telemetry',{limit:101}));
});
test('no telemetry means explicitly stale, never green/healthy',()=>{
  const s=new LiveEventStore(); assert.equal(s.read({},true).stale,true);assert.equal(s.read({},true).latest,null);
});
test('freshness derives from local arrival and connection',()=>{
  let now=100;const s=new LiveEventStore(4,()=>now);s.accept(event(1));
  assert.equal(s.read({},true).stale,false);now=2700;assert.equal(s.read({},true).stale,true);
  now=101;assert.equal(s.read({},false).stale,true);
});
test('bounded cache reports drops, pagination and cursor gap',()=>{
  const s=new LiveEventStore(3);for(let n=1;n<=6;n++)s.accept(event(n));
  const first=s.read({limit:2},true);assert.equal(first.cacheDropped,3);assert.equal(first.cursorGap,true);
  assert.deepEqual(first.events.map(e=>e.sequence),[4,5]);assert.equal(first.moreAvailable,true);
  assert.deepEqual(s.read({afterSequence:first.nextSequence},true).events.map(e=>e.sequence),[6]);
});
test('new runtime uses a new cache identity; old cursors can recover',()=>{
  const a=new LiveEventStore(),b=new LiveEventStore();assert.notEqual(a.cacheId,b.cacheId);
  b.accept(event(1));assert.equal(b.read({afterSequence:300},true).events.length,1);
});
test('invalid or oversized events never enter the cache',()=>{
  const s=new LiveEventStore();for(const e of [null,{},event(NaN),event(2,'unknown'),{...event(1),data:[]},{...event(1),data:{text:'x'.repeat(33000)}}])s.accept(e);
  assert.equal(s.events.length,0);
});
test('authenticated socket multiplexes telemetry and request responses',async()=>{
  const store=new LiveEventStore();const bridge=new LoopbackControlServer({onEvent:e=>store.accept(e)});
  let socket;
  try{
    const address=await bridge.start();
    socket=net.createConnection({host:'127.0.0.1',port:address.port});await once(socket,'connect');
    let buffer='';socket.on('data',raw=>{
      buffer+=raw.toString();for(;;){const i=buffer.indexOf('\n');if(i<0)break;const msg=JSON.parse(buffer.slice(0,i));buffer=buffer.slice(i+1);
        if(msg.type==='request')socket.write(JSON.stringify({type:'response',id:msg.id,ok:true,result:{inspected:true}})+'\n');
      }
    });
    socket.write(JSON.stringify({type:'hello',protocol:1,token:bridge.token})+'\n');
    await bridge.waitForConnection(1000);
    socket.write(JSON.stringify({type:'event',event:event(1)})+'\n');
    assert.deepEqual(await bridge.request('scene.inspect',{}),{inspected:true});
    assert.equal(store.read({},true).latest.playing,false);
  }finally{socket?.destroy();await bridge.close();}
});
