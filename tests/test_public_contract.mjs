import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, existsSync, readdirSync} from 'node:fs';
import path from 'node:path';
import {parseToolResult, observedState} from '../web/src/tool-result.mjs';
import {sceneRoutes, sceneTools, liveTool, validateSchema} from '../mcp/scene-tools.mjs';
const root=path.resolve(import.meta.dirname,'..');
const read=(s)=>readFileSync(path.join(root,s),'utf8');

test('incomplete tool output cannot masquerade as success',()=>{
 for(const data of [undefined,null,{},{structuredContent:{}},[],{content:[{type:'text',text:'success'}]},{result:{}},{structuredContent:[]}])assert.throws(()=>parseToolResult(data),/incomplète/);
});
test('tool errors are propagated even when a success-shaped result is present',()=>{
 for(const payload of [{isError:true,structuredContent:{ok:true}},{structuredContent:{ok:false,message:'rejected'}},{error:{message:'bad rpc'}},{result:{isError:true,content:[{type:'text',text:'denied'}]}}])assert.throws(()=>parseToolResult(payload));
});
test('successful direct and JSON-RPC envelope responses preserve actual data',()=>{
 const data={ready:false,checks:[],runtime:{processAlive:false}};
 assert.deepEqual(parseToolResult({structuredContent:data}),data);
 assert.deepEqual(parseToolResult({result:{structuredContent:data}}),data);
});
test('absent values are unknown, never an idle/ready measurement',()=>{
 assert.equal(observedState(undefined),'Non vérifié');
 assert.equal(observedState('ready'),'Prêt');
 assert.equal(observedState('stale'),'État ancien');
});
test('production entry does not import test fixtures or a replacement transport',()=>{
 for(const file of readdirSync(path.join(root,'web/src'))){
  if(!/\.(tsx?|mjs)$/.test(file))continue;
  const source=read('web/src/'+file);
  assert.doesNotMatch(source, /from\s+["'][^"']*(?:fixtures|harness|\/tests\/|mock)/i);
  assert.doesNotMatch(source, /window\.openai\s*=/);
  assert.doesNotMatch(source, /initialKeys|mockScene|demoScene|fakeStream|setInterval\([^]*?Math\.random/);
 }
 assert.match(read('web/src/main.tsx'), /from "@nvidia\/ov-web-rtc"/);
});
test('installer never seeds the workspace; reference USD stays in tests only',()=>{
 const installer=read('installer/Install-OmniStream.ps1');
 assert.doesNotMatch(installer,/\$exampleDir|\$exampleSource|OmniStream Examples|physics-lab\.usda/);
 assert.equal(existsSync(path.join(root,'examples')),false);
 assert.ok(existsSync(path.join(root,'tests/fixtures/physics-lab.usda')));
});
test('scene tools dispatch to actual Python implementation methods',()=>{
 const extension=read('runtime/bridge/omnistream.codex.bridge/omnistream/codex/bridge/extension.py');
 const service=read('runtime/bridge/omnistream.codex.bridge/omnistream/codex/bridge/scene_service.py');
 for(const {method} of sceneRoutes.values()){
  const match=extension.match(new RegExp('"'+method.replace('.', '\\.')+'": "(\\w+)"'));
  assert.ok(match,'Missing dispatch '+method);
  assert.match(service,new RegExp('def '+match[1]+'\\('));
 }
});
test('every scene tool has bounded schemas and explicit UI access',()=>{
 for(const tool of [...sceneTools,liveTool]){
  assert.equal(tool.inputSchema.additionalProperties,false);
  assert.equal(tool._meta['openai/widgetAccessible'],true);
  assert.throws(()=>validateSchema({arbitraryScript:'x'},tool.inputSchema));
 }
});
test('scene preview lifetime and host availability gate destructive UI paths',()=>{
 const source=read('web/src/SceneWorkbench.tsx');
 assert.match(source,/now < preview\.expiresAt/);
 assert.match(source,/localBusy \|\| externalBusy \|\| !available/);
 assert.match(source,/scene\.capabilities\?\.authoring !== true/);
 assert.match(source,/await confirm\(\{\s*title: "Abandonner/);
 assert.match(source,/await confirm\(\{\s*title: "Exporter/);
});
test('periodic supervision cannot reset the draft fields',()=>{
 const source=read('web/src/main.tsx');
 const fn=source.slice(source.indexOf('const applySupervision'),source.indexOf('const callSimulationTool'));
 assert.doesNotMatch(fn,/syncConfiguration\(/);
 assert.match(source,/supervisionBusy\.current/);
 assert.match(source,/setHostError\(errorText\(error\)\)/);
});
test('no browser confirm dialogs in the application sandbox',()=>{
 assert.doesNotMatch(read('web/src/main.tsx'),/window\.confirm/);
 assert.doesNotMatch(read('web/src/SceneWorkbench.tsx'),/window\.confirm/);
 assert.match(read('web/src/Confirmation.tsx'),/showModal\(/);
});
test('developer-only HTTP harness checks authority, origin, JSON and per-session header',()=>{
 const source=read('mcp/panel-runtime-harness.mjs');
 assert.match(source,/request\.headers\.host !== authority/);
 assert.match(source,/request\.headers\.origin !== origin/);
 assert.match(source,/x-omnistream-session/);
 assert.match(source,/startsWith\("application\/json"\)/);
 assert.doesNotMatch(source,/copyFileSync|fixtureName|__test_info/);
});
