import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, copyFileSync, writeFileSync, rmSync, symlinkSync, readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
const root=path.resolve(import.meta.dirname,'..');
function audit(arrange) {
 const dir=mkdtempSync(path.join(tmpdir(),'omnistream-release-audit-'));
 try {
  mkdirSync(path.join(dir,'scripts'));copyFileSync(path.join(root,'scripts/publication-audit.mjs'),path.join(dir,'scripts/publication-audit.mjs'));
  writeFileSync(path.join(dir,'README.md'),'Source-only release');arrange?.(dir);
  return spawnSync(process.execPath,[path.join(dir,'scripts/publication-audit.mjs')],{encoding:'utf8'});
 } finally {rmSync(dir,{recursive:true,force:true});}
}
test('publication audit accepts clean source tree',()=>assert.equal(audit().status,0));
test('publication audit refuses native executable instead of ignoring it',()=>{const r=audit(d=>writeFileSync(path.join(d,'runtime.exe'),'binary'));assert.equal(r.status,1);assert.match(r.stderr,/runtime\.exe/);});
test('publication audit refuses hidden binary bytes with a text extension',()=>{const r=audit(d=>writeFileSync(path.join(d,'payload.mjs'),Buffer.from([0,1,2,3])));assert.equal(r.status,1);assert.match(r.stderr,/binary data/);});
test('publication audit refuses nested dependencies',()=>{const r=audit(d=>{mkdirSync(path.join(d,'node_modules'));});assert.equal(r.status,1);});
test('publication audit refuses unreviewed oversized text',()=>{const r=audit(d=>writeFileSync(path.join(d,'large.js'),'a'.repeat(2*1024*1024+1)));assert.equal(r.status,1);});
test('publication audit refuses symlinks', {skip:process.platform==='win32'?'Symlink privileges vary on Windows; clean tree validation still checks links':false},()=>{const r=audit(d=>symlinkSync(path.join(d,'README.md'),path.join(d,'alias.md')));assert.equal(r.status,1);});
test('Windows release script keeps plugin dotfiles in archive and verifies entries',()=>{const source=readFileSync(path.join(root,'installer/Build-Release.ps1'),'utf8');assert.match(source,/ZipFile\]::CreateFromDirectory/);assert.match(source,/\.codex-plugin\/plugin\.json/);assert.doesNotMatch(source,/^Compress-Archive /m);});
test('Windows installer probes actual prerequisite versions', {skip:process.platform!=='win32'},()=>{
 const source=readFileSync(path.join(root,'installer/Install-OmniStream.ps1'),'utf8');
 const functions=source.slice(source.indexOf('function Refresh-ProcessPath'),source.indexOf('function Wait-ForExternalInstall'));
 const script=functions+`\n$ErrorActionPreference='Stop'\nif (-not (Test-Tool 'node' @('--version') ([Version]'20.18.1'))) { throw 'Node probe failed' }\nif (-not (Test-Tool 'npm' @('--version') ([Version]'10.2.3'))) { throw 'npm probe failed' }\nif (-not (Test-Tool 'git' @('--version') ([Version]'2.40.0'))) { throw 'Git probe failed' }\n`;
 const result=spawnSync('powershell.exe',['-NoProfile','-EncodedCommand',Buffer.from(script,'utf16le').toString('base64')],{encoding:'utf8',timeout:30000,windowsHide:true});
 assert.equal(result.status,0,result.stderr || result.error?.message);
});
test('Windows validation serializes checks on success and failure', {skip:process.platform!=='win32'},()=>{
 const source=readFileSync(path.join(root,'installer/Test-OmniStream.ps1'),'utf8');
 const functions=source.slice(source.indexOf('function Save-Report'),source.indexOf('\ntry {',source.indexOf('function Save-Report')));
 const dir=mkdtempSync(path.join(tmpdir(),'omnistream-validation-report-'));
 try {
  const script=`$ErrorActionPreference='Stop'\n$InstallRoot='qualification'\n$SkipRuntimeSmoke=$false\n$SkipKitTests=$false\n$startedAt='qualification'\n$checks=New-Object System.Collections.Generic.List[object]\n$checks.Add(@{name='native check';ok=$true})\n${functions}\n$ReportFile=Join-Path $env:OMNISTREAM_TEST_REPORT 'pass.json'\nSave-Report $true\n$ReportFile=Join-Path $env:OMNISTREAM_TEST_REPORT 'fail.json'\nSave-Report $false 'observed failure'\n`;
  const result=spawnSync('powershell.exe',['-NoProfile','-EncodedCommand',Buffer.from(script,'utf16le').toString('base64')],{encoding:'utf8',env:{...process.env,OMNISTREAM_TEST_REPORT:dir},timeout:30000,windowsHide:true});
  assert.equal(result.status,0,result.stderr || result.error?.message);
  for (const name of ['pass','fail']) {
   const report=JSON.parse(readFileSync(path.join(dir,name+'.json'),'utf8'));
   assert.equal(report.ok,name==='pass');assert.equal(report.checks.length,1);
   assert.equal(report.runtimeSmokeSkipped,false);assert.equal(report.kitTestsSkipped,false);
  }
 } finally {rmSync(dir,{recursive:true,force:true});}
});
test('CMD entry points load Windows PowerShell modules from a PowerShell 7 environment', {skip:process.platform!=='win32'},()=>{
 const dir=mkdtempSync(path.join(tmpdir(),'omnistream-cmd-modules-'));
 try {
  const installDir=path.join(dir,'installer');mkdirSync(installDir);
  for (const name of ['Install','Test','Uninstall','Diagnose']) {
   writeFileSync(path.join(installDir,name+'-OmniStream.ps1'),`$ErrorActionPreference='Stop'\nif ($PSVersionTable.PSEdition -ne 'Desktop') { throw 'Expected Windows PowerShell' }\nGet-Command Get-FileHash -ErrorAction Stop | Out-Null\nexit 0\n`);
  }
  for (const name of ['install','repair','test','diagnose','uninstall']) {
   const filename=path.join(installDir,name+'.cmd');copyFileSync(path.join(root,'installer',name+'.cmd'),filename);
   const result=spawnSync('cmd.exe',['/d','/s','/c',`call "${filename}"`],{encoding:'utf8',timeout:30000,windowsHide:true,windowsVerbatimArguments:true});
   assert.equal(result.status,0,name+': '+(result.stderr || result.stdout || result.error?.message));
  }
 } finally {rmSync(dir,{recursive:true,force:true});}
});
function verifyVersions(change) {
 const dir=mkdtempSync(path.join(tmpdir(),'omnistream-version-check-'));
 try {
  const files={
   'package.json':'{"version":"1.0.0-rc3"}',
   '.codex-plugin/plugin.json':'{"version":"1.0.0-rc3"}',
   '.mcp.json':'{}','installer/install.cmd':'@echo off\n',
   'web/package.json':'{"version":"1.0.0-rc3"}',
   'runtime/bridge/omnistream.codex.bridge/config/extension.toml':'[package]\nversion = "1.0.0-rc3"\n',
   'README.md':'# OmniStream for Codex — 1.0.0-rc3\n',
   'scripts/verify-release.mjs':readFileSync(path.join(root,'scripts/verify-release.mjs'),'utf8')
  };
  change?.(files);
  for(const [file,content] of Object.entries(files)){mkdirSync(path.dirname(path.join(dir,file)),{recursive:true});writeFileSync(path.join(dir,file),content);}
  const entries=Object.keys(files).map(file=>{const data=readFileSync(path.join(dir,file));return {path:file,size:data.length,sha256:createHash('sha256').update(data).digest('hex')};});
  writeFileSync(path.join(dir,'release-manifest.json'),JSON.stringify({schemaVersion:1,version:'1.0.0-rc3',files:entries}));
  return spawnSync(process.execPath,[path.join(dir,'scripts/verify-release.mjs'),'--strict'],{encoding:'utf8'});
 } finally {rmSync(dir,{recursive:true,force:true});}
}
test('strict manifest verifies consistent product versions',()=>assert.equal(verifyVersions().status,0));
test('strict manifest rejects mismatched versions even with correct hashes',()=>{
 for (const file of ['.codex-plugin/plugin.json','web/package.json','runtime/bridge/omnistream.codex.bridge/config/extension.toml','README.md']) {
  const result=verifyVersions(files=>{files[file]=files[file].replaceAll('1.0.0-rc3','1.0.0');});
  assert.equal(result.status,1,file);assert.match(result.stderr,/Version mismatch/);
 }
});
