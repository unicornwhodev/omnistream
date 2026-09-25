import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
const root = path.resolve(import.meta.dirname, '..');
const strict = process.argv.includes('--strict');
try {
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'release-manifest.json'), 'utf8'));
  const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
  if (manifest.schemaVersion !== 1 || manifest.version !== pkg.version || !Array.isArray(manifest.files) || !manifest.files.length) throw Error('Invalid release manifest/version');
  const seen = new Set();
  for (const entry of manifest.files) {
    if (typeof entry.path !== 'string' || !entry.path || entry.path.includes('\\') || entry.path.includes(':') || path.isAbsolute(entry.path) || entry.path.split('/').some(p => !p || p === '.' || p === '..') || seen.has(entry.path)) throw Error('Invalid/duplicate manifest path');
    if (!Number.isSafeInteger(entry.size) || entry.size < 0 || !/^[0-9a-f]{64}$/.test(entry.sha256)) throw Error('Invalid manifest metadata');
    seen.add(entry.path);
    const target = path.resolve(root, entry.path), real = fs.realpathSync(target), relative = path.relative(root, real);
    if (relative.startsWith('..') || path.isAbsolute(relative) || fs.lstatSync(target).isSymbolicLink()) throw Error('Manifest path escapes release');
    const data = fs.readFileSync(target);
    if (data.length !== entry.size || createHash('sha256').update(data).digest('hex') !== entry.sha256) throw Error('Integrity mismatch: ' + entry.path);
  }
  for (const required of ['package.json', '.codex-plugin/plugin.json', '.mcp.json', 'installer/install.cmd']) {
    if (!seen.has(required)) throw Error('Required release file not covered: ' + required);
  }
  if (strict) {
    function walk(directory) {
      for (const file of fs.readdirSync(directory, {withFileTypes: true})) {
        const full = path.join(directory, file.name), relative = path.relative(root, full).replaceAll('\\', '/');
        if (file.isSymbolicLink()) throw Error('Unexpected symlink: ' + relative);
        if (file.isDirectory()) walk(full);
        else if (relative !== 'release-manifest.json' && !seen.has(relative)) throw Error('Unmanifested release file: ' + relative);
      }
    }
    walk(root);
  }
  console.log(`PASS: ${seen.size} source hashes verified${strict ? ', no extra files' : ''}. Integrity only: NOT a digital signature or certification.`);
} catch (error) { console.error(error.message); process.exitCode = 1; }
