import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, copyFileSync, writeFileSync, rmSync, symlinkSync, readFileSync} from 'node:fs';
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
