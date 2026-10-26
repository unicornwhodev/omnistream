"""Restore original scene archives one at a time, with bounded memory and receipts.

No archive is executed. Existing differing files are never overwritten. Only an
explicit archive whose SHA-256 and every extracted member were verified can be
consumed. Source archives on Drive are never modified.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import time
import zipfile

CHUNK = 1024 * 1024


def sha256(path, limiter=None):
    with Path(path).open('rb') as stream:
        if limiter is None:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
        digest=hashlib.sha256()
        while chunk:=stream.read(CHUNK):
            digest.update(chunk);limiter.account(len(chunk))
        return digest.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.part')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def bounded_path(root, name):
    relative = PurePosixPath(name)
    if (relative.is_absolute() or not relative.parts or any(p in ('', '.', '..') for p in relative.parts)
            or relative.as_posix() != name or '\\' in name or ':' in name
            or any(p.rstrip(' .') != p for p in relative.parts)
            or any(p.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                    *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
                   for p in relative.parts)):
        raise ValueError('Unsafe archive member path')
    target = root.joinpath(*relative.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Archive member escapes destination')
    for p in [target, *target.parents]:
        if p == root.parent:
            break
        if p.is_symlink() or (p.exists() and p.lstat().st_file_attributes & 0x400 if os.name == 'nt' else False):
            raise ValueError('Reparse points are not accepted')
    return target


def no_links(path):
    """Check the lexical path before resolving; resolve would hide a junction."""
    path = Path(os.path.abspath(path))
    for parent in [path, *path.parents]:
        if parent.is_symlink() or (parent.exists() and
                getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Reparse points are not accepted')
    return path


def restore(archive, root, archive_record, files, *, consume=False, min_free_bytes=16_000_000_000, limiter=None):
    archive, root = no_links(archive), no_links(root)
    if not archive.is_file() or archive.is_symlink():
        raise ValueError('Archive is not a regular file')
    if archive.name != archive_record['name'] or archive.stat().st_size != archive_record['bytes']:
        raise ValueError('Archive name/size does not match the delivery manifest')
    if sha256(archive, limiter) != archive_record['sha256']:
        raise ValueError('Archive checksum does not match the delivery manifest')
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError('Destination is a link')
    expected = {row['path']: row for row in files}
    receipt_path = root.parent / 'restore-receipts' / (archive.name + '.json')
    with zipfile.ZipFile(archive) as package:
        members = [m for m in package.infolist() if not m.is_dir()]
        names = [m.filename for m in members]
        if len(names) != len(set(n.casefold() for n in names)):
            raise ValueError('Duplicate archive members')
        if archive_record.get('files') is not None and len(members) != archive_record['files']:
            raise ValueError('Archive member count mismatch')
        required = 0
        for member in members:
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError('Archive symlink rejected')
            target = bounded_path(root, member.filename)
            entry = expected.get(member.filename)
            if entry is None or entry['bytes'] != member.file_size:
                raise ValueError('Member missing from manifest or size differs')
            if target.exists():
                if not target.is_file() or target.stat().st_size != entry['bytes'] or sha256(target, limiter) != entry['sha256']:
                    raise ValueError('An existing file differs; preserve it and stop')
            else:
                required += member.file_size
        if shutil.disk_usage(root).free < required + min_free_bytes:
            raise RuntimeError('Insufficient disk reserve for this archive')
        committed = []
        for member in members:
            entry = expected[member.filename]
            target = bounded_path(root, member.filename)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                partial = target.with_name(target.name + '.restore-part')
                bounded_path(root, partial.relative_to(root).as_posix())
                if partial.exists():
                    raise RuntimeError('Incomplete extraction retained for explicit recovery')
                digest = hashlib.sha256()
                with package.open(member) as source, partial.open('xb') as dest:
                    while chunk := source.read(CHUNK):
                        if shutil.disk_usage(root).free < min_free_bytes + len(chunk):
                            raise RuntimeError('Disk reserve reached during extraction')
                        digest.update(chunk)
                        dest.write(chunk)
                        if limiter:limiter.account(len(chunk))
                    dest.flush()
                    os.fsync(dest.fileno())
                if digest.hexdigest() != entry['sha256'] or sha256(partial, limiter) != entry['sha256']:
                    raise ValueError('Extracted member checksum failed')
                os.replace(partial, target)
            committed.append({'path': entry['path'], 'bytes': entry['bytes'], 'sha256': entry['sha256']})
    receipt = {'schema': 'omnistream.scene-restore.v1', 'archive': archive.name,
               'archive_sha256': archive_record['sha256'], 'files': committed,
               'verified': True, 'archive_consumed': False, 'verified_at_unix_s': time.time()}
    atomic_json(receipt_path, receipt)
    if consume:
        # Recheck the exact source immediately before removing only this copy.
        if sha256(archive, limiter) != archive_record['sha256']:
            raise ValueError('Source changed before consumption')
        if any(sha256(bounded_path(root, r['path']), limiter) != r['sha256'] for r in committed):
            raise ValueError('Destination changed before source consumption')
        archive.unlink()
        receipt['archive_consumed'] = True
        atomic_json(receipt_path, receipt)
    return {'archive': archive.name, 'files_verified': len(committed),
            'bytes_verified': sum(r['bytes'] for r in committed),
            'archive_consumed': receipt['archive_consumed']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', required=True)
    p.add_argument('--root', required=True)
    p.add_argument('--delivery', required=True)
    p.add_argument('--files', required=True)
    p.add_argument('--consume', action='store_true')
    p.add_argument('--min-free-bytes', type=int, default=16_000_000_000)
    args = p.parse_args()
    delivery = json.loads(Path(args.delivery).read_text())
    record = next(row for row in delivery['archives'] if row['name'] == Path(args.archive).name)
    files = json.loads(Path(args.files).read_text())['files']
    print(json.dumps(restore(args.archive, args.root, record, files, consume=args.consume,
                             min_free_bytes=args.min_free_bytes)))
