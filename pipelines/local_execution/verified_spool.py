"""Bounded capture offload: local commit -> cloud readback -> receipt -> prune.

The original scene is never inside the spool. No cloud move/delete/sync command
is used. Keep small local metadata/checkpoints for recovery. Call only after the
five-camera group AND its scheduler checkpoint have committed, while every
simulation producer remains frozen. A failed transfer must block advancement.
"""
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import threading
import time

from restore_scene import atomic_json, bounded_path, no_links, sha256


class SpoolBlocked(RuntimeError):
    pass


def safe_relative(value):
    path = PurePosixPath(value)
    if (path.is_absolute() or not path.parts or path.as_posix() != value or
            any(p in ('.', '..') for p in path.parts) or '\\' in value or ':' in value):
        raise ValueError('Unsafe remote object path')
    return value


class RcloneBackend:
    """One authorized remote rooted at the designated output folder ID."""
    def __init__(self, executable, config, remote, folder_id, *, readback_timeout_s=150):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', remote) or not re.fullmatch(r'[A-Za-z0-9_-]+', folder_id):
            raise ValueError('Expected configured remote name and explicit output folder ID')
        self.command = [str(no_links(executable)), '--config', str(no_links(config)),
                        '--drive-root-folder-id', folder_id, '--drive-chunk-size', '8Mi',
                        '--transfers', '1', '--checkers', '1', '--buffer-size', '8Mi',
                        '--multi-thread-streams', '0', '--retries', '2', '--low-level-retries', '2',
                        '--timeout', '1m', '--tpslimit', '2', '--bwlimit', '8Mi', '--log-level', 'ERROR']
        self.remote = remote
        self.folder_id = folder_id
        self.flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        if not math.isfinite(readback_timeout_s) or not 0 < readback_timeout_s <= 900:
            raise ValueError('Readback deadline must be positive and at most 900 seconds')
        self.readback_timeout_s = readback_timeout_s

    def location(self, relative):
        return self.remote+':'+safe_relative(relative)

    def readback(self, relative):
        """Stream remote bytes through SHA-256, never a second local media copy."""
        process = subprocess.Popen(self.command+['cat', self.location(relative)],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   creationflags=self.flags)
        digest = hashlib.sha256()
        size = 0
        # wait(timeout) after a blocking stdout.read does not bound a stalled
        # stream. A timer kills only this owned rclone process, unblocking read.
        expired = threading.Event()
        def expire():
            expired.set()
            if process.poll() is None:process.kill()
        timer = threading.Timer(self.readback_timeout_s,expire)
        timer.daemon = True
        timer.start()
        try:
            while block := process.stdout.read(1024*1024):
                digest.update(block)
                size += len(block)
                if size > 512_000_000:
                    raise SpoolBlocked('Remote object exceeds readback limit; local file retained')
            if process.wait(timeout=5) or expired.is_set():
                raise SpoolBlocked('Remote readback failed; local file retained')
        finally:
            timer.cancel()
            process.stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait()
        return {'bytes':size, 'sha256':digest.hexdigest()}

    def upload_verified(self, source, relative, expected):
        # --immutable prevents replacing a different existing object. A retry
        # with an already uploaded object still requires a fresh full readback.
        result = subprocess.run(self.command+['copyto', str(source), self.location(relative),
                                             '--immutable', '--checksum'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=self.flags, timeout=900)
        if result.returncode:
            raise SpoolBlocked('Cloud copy failed or destination differs; local file retained')
        actual = self.readback(relative)
        if actual != expected:
            raise SpoolBlocked('Remote SHA-256/byte count differs; local file retained')
        return {'folder_id':self.folder_id, 'path':relative, **actual,
                'verified_by':'full remote byte stream SHA-256', 'verified_at_unix_s':time.time()}


class VerifiedSpool:
    def __init__(self, root, backend, *, max_bytes=512_000_000, reserve_bytes=16_000_000_000):
        self.root = no_links(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.backend = backend
        self.max_bytes = max_bytes
        self.reserve_bytes = reserve_bytes
        if max_bytes <= 0 or reserve_bytes < 0:
            raise ValueError('Invalid spool limits')

    def capacity(self, next_group_max_bytes):
        """Admission must precede a group; include PNG buffers and sidecars."""
        if next_group_max_bytes <= 0 or next_group_max_bytes > self.max_bytes:
            raise SpoolBlocked('Next complete group exceeds the configured spool')
        used = 0
        for path in self.root.rglob('*'):
            no_links(path)
            if path.is_file():
                used += path.stat().st_size
        if used+next_group_max_bytes > self.max_bytes:
            raise SpoolBlocked('Spool budget reached; drain verified groups before advancing')
        if shutil.disk_usage(self.root).free < self.reserve_bytes+next_group_max_bytes:
            raise SpoolBlocked('Disk reserve reached; stop capture production')
        return used

    def offload(self, bundle_id, entries):
        """entries: path, bytes, sha256, prune (media only). No discovery deletion."""
        if not re.fullmatch(r'[a-f0-9]{64}', bundle_id):
            raise ValueError('Bundle ID must be a deterministic SHA-256')
        paths = [r['path'] for r in entries]
        if not entries or len(paths) != len(set(p.casefold() for p in paths)):
            raise ValueError('Bundle must have unique explicit entries')
        if sum(r['bytes'] for r in entries) > self.max_bytes:
            raise SpoolBlocked('Bundle exceeds spool budget')
        receipt_path = self.root/'offload-receipts'/(bundle_id+'.json')
        old = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
        if old and (old.get('verified') is not True or old.get('entries') != entries):
            raise SpoolBlocked('Existing bundle receipt differs; preserve and stop')
        # Preflight every local entry before network writes or deletion.
        for entry in entries:
            path = bounded_path(self.root, entry['path'])
            if entry.get('prune') and (not entry['path'].startswith(('frames/', 'demos/')) or
                                      path.suffix.lower() not in ('.png', '.mp4', '.webm')):
                raise ValueError('Only explicitly committed capture/demo media may be pruned')
            if not re.fullmatch(r'[a-f0-9]{64}', entry['sha256']) or entry['bytes'] < 0:
                raise ValueError('Invalid content digest/size')
            if path.exists():
                if not path.is_file() or path.stat().st_size != entry['bytes'] or sha256(path) != entry['sha256']:
                    raise SpoolBlocked('Local capture changed; preserve and stop')
            elif not (old and entry.get('prune')):
                raise SpoolBlocked('Incomplete local bundle has no verified remote receipt')
        remote = []
        for entry in entries:
            path = bounded_path(self.root, entry['path'])
            expected = {k:entry[k] for k in ('bytes', 'sha256')}
            destination = safe_relative('bundles/'+bundle_id+'/'+entry['path'])
            if path.exists():
                remote.append(self.backend.upload_verified(path, destination, expected))
            else:
                actual = self.backend.readback(destination)
                if actual != expected:
                    raise SpoolBlocked('Pruned capture is no longer verifiable on Drive')
                remote.append({'path':destination, **actual, 'verified_by':'full remote byte stream SHA-256'})
        receipt = {'schema':'omnistream.capture-offload.v1', 'bundle_id':bundle_id,
                   'entries':entries, 'remote':remote, 'verified':True,
                   'verified_at_unix_s':time.time()}
        atomic_json(receipt_path, receipt)
        # A durable cloud receipt precedes local pruning, too.
        expected_receipt = {'bytes':receipt_path.stat().st_size, 'sha256':sha256(receipt_path)}
        receipt_object = 'receipts/'+bundle_id+'/'+expected_receipt['sha256']+'.json'
        self.backend.upload_verified(receipt_path, receipt_object, expected_receipt)
        for entry in entries:
            if entry.get('prune'):
                path = bounded_path(self.root, entry['path'])
                if path.exists():
                    if path.stat().st_size != entry['bytes'] or sha256(path) != entry['sha256']:
                        raise SpoolBlocked('Local capture changed before pruning; preserve and stop')
                    path.unlink()
        return receipt

    def offload_group(self, group_id):
        """Use after CapturePipeline's checkpoint, never on partial frame writes."""
        path = bounded_path(self.root, 'groups/'+group_id+'.json')
        group = json.loads(path.read_text())
        if group.get('verified') is not True or group.get('group_id') != group_id or len(group['frames']) != 5:
            raise SpoolBlocked('Only fully committed five-camera groups can be offloaded')
        entries = []
        for frame in group['frames']:
            metadata = bounded_path(self.root, frame['metadata_path'])
            record = json.loads(metadata.read_text())
            if (sha256(metadata) != frame['metadata_sha256'] or record['image']['sha256'] != frame['image_sha256']
                    or record['sim_time_us'] != group['sim_time_us']
                    or record['state_fingerprint'] != group['state_fingerprint']):
                raise SpoolBlocked('Group metadata or time changed')
            entries.extend([
                {'path':frame['image_path'], 'bytes':record['image']['bytes'],
                 'sha256':frame['image_sha256'], 'prune':True},
                {'path':frame['metadata_path'], 'bytes':metadata.stat().st_size,
                 'sha256':frame['metadata_sha256'], 'prune':False}])
        entries.append({'path':'groups/'+group_id+'.json', 'bytes':path.stat().st_size,
                        'sha256':sha256(path), 'prune':False})
        return self.offload(group_id, entries)
