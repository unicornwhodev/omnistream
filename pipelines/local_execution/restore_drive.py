"""Restore only manifest-listed Drive archives, one at a time. No cloud deletion.

Uses an independently authorized rclone configuration. Never reads browser
cookies, accepts credentials on the command line, or modifies sharing.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from restore_scene import atomic_json, bounded_path, no_links, restore, sha256
from host_budget import ByteRateLimit, background_mode, exclusive_heavy_work


def temporary_api_quota(message):
    """Only transient request quotas; never storage, authentication or daily quotas."""
    text = message.casefold()
    if any(value in text for value in ('dailylimitexceeded', 'daily limit',
                                       'storagequotaexceeded', 'storage quota')):
        return False
    return any(value in text for value in (
        'rate_limit_exceeded', 'ratelimitexceeded', 'rate limit exceeded',
        'requests per minute', 'googleapi: error 429'))


def download_archive(command, archive, log, *, check_admission, max_attempts=4,
                     run=subprocess.run, sleep=time.sleep, clock=time.monotonic):
    """Retry backend-initialization rate limits, keeping every attempt private.

    rclone's own copy retries do not cover failure to initialize its Drive backend.
    A partial local archive is retained and stops automatic retries; it is never
    overwritten or mistaken for a verified archive.
    """
    if not 1 <= max_attempts <= 4:
        raise ValueError('Transfer attempts must be between one and four')
    if archive.exists():
        raise RuntimeError('Existing archive must be verified, not overwritten')
    started = clock()
    attempts = []
    receipt = log.parent/(archive.name+'.process.json')
    for number in range(1, max_attempts+1):
        check_admission()
        attempt_start = clock()
        offset = log.stat().st_size if log.exists() else 0
        try:
            with log.open('ab') as diagnostic:
                result = run(command, stdout=diagnostic, stderr=diagnostic,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                             timeout=900)
            exit_code, reason = result.returncode, 'process_exit'
        except subprocess.TimeoutExpired:
            exit_code, reason = None, 'transfer_wall_timeout'
        with log.open('rb') as diagnostic:
            diagnostic.seek(max(offset, log.stat().st_size-65536))
            message = diagnostic.read(65536).decode('utf-8', errors='replace')
        retryable = exit_code not in (None, 0) and temporary_api_quota(message)
        attempts.append({'attempt':number, 'exit_code':exit_code, 'reason':reason,
                         'wall_s':clock()-attempt_start, 'temporary_api_quota':retryable})
        atomic_json(receipt, {'exit_code':exit_code, 'wall_s':clock()-started,
                             'attempts':attempts, 'local_copy_retained':archive.exists()})
        if exit_code == 0:
            if not archive.is_file():
                raise RuntimeError('Drive command succeeded but produced no archive')
            return
        if not retryable or archive.exists() or number == max_attempts:
            raise RuntimeError(f'Drive download failed with exit {exit_code}; private diagnostic retained, no source deleted')
        delay = min(30 * 2**(number-1), 120)
        print(json.dumps({'event':'drive_api_quota_backoff','archive':archive.name,
                          'attempt':number,'retry_after_s':delay}),flush=True)
        # A stop request or memory floor also applies during backoff.
        for _ in range(delay//5):
            sleep(5)
            check_admission()


def restoration_plan(delivery, index):
    result = []
    for record in delivery['archives']:
        matches = [item for item in index if item['title'] == record['name']]
        if len(matches) != 1 or int(matches[0]['size']) != record['bytes']:
            raise ValueError('Drive index does not identify one exact archive')
        file_id = matches[0]['id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', file_id):
            raise ValueError('Invalid Drive file identifier')
        result.append({**record, 'drive_id': file_id})
    return result


def restored(record, root, expected, limiter=None):
    receipt = root.parent/'restore-receipts'/(record['name']+'.json')
    if not receipt.exists():
        return False
    value = json.loads(receipt.read_text(encoding='utf-8'))
    if not (value.get('verified') and value.get('archive_sha256') == record['sha256']
            and len(value.get('files', [])) == record['files']):
        raise ValueError('Invalid existing restoration receipt')
    seen = set()
    for item in value['files']:
        if item['path'] in seen or item != expected.get(item['path']):
            raise ValueError('Restoration receipt differs from canonical file manifest')
        seen.add(item['path'])
        path = bounded_path(root, item['path'])
        if not path.is_file() or path.stat().st_size != item['bytes'] or sha256(path,limiter) != item['sha256']:
            raise ValueError('Previously restored scene file changed; preserve and stop')
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', required=True)
    p.add_argument('--rclone', required=True)
    p.add_argument('--config', required=True)
    p.add_argument('--remote', required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--reserve-bytes', type=int, default=16_000_000_000)
    p.add_argument('--io-mib-s', type=float, default=32)
    p.add_argument('--download-mib-s', type=float, default=8)
    p.add_argument('--max-archives',type=int)
    p.add_argument('--min-available-ram-bytes',type=int,default=8_000_000_000)
    args = p.parse_args()
    background_mode()
    with exclusive_heavy_work(no_links(args.workspace)):
        restore_workspace(args)


def restore_workspace(args):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', args.remote):
        raise ValueError('Use a configured remote name, not a connection string')
    if args.download_mib_s<=0 or (args.max_archives is not None and args.max_archives<=0):
        raise ValueError('Transfer limits must be positive')
    limiter=ByteRateLimit(args.io_mib_s*1024*1024)
    import psutil
    if psutil.virtual_memory().available < args.min_available_ram_bytes:
        raise RuntimeError('Available RAM floor reached; no scene work started')
    work = no_links(args.workspace)
    root = work/'scene'
    metadata = work/'metadata'
    delivery = json.loads((metadata/'delivery.json').read_text())
    files_path = metadata/'scene-files.json'
    if sha256(files_path) != delivery['scene_files_sha256']:
        raise ValueError('Scene manifest checksum changed')
    files = json.loads(files_path.read_text())['files']
    expected = {r['path']: r for r in files}
    if len(expected) != len(files):
        raise ValueError('Duplicate canonical file entries')
    plan = restoration_plan(delivery, json.loads((metadata/'source-files.private.json').read_text()))
    pending = []
    for ordinal,record in enumerate(plan,1):
        verified = restored(record, root, expected, limiter)
        if not verified:
            pending.append(record)
        print(json.dumps({'event':'archive_audited','archive':record['name'],
                          'index':ordinal,'total':len(plan),'already_verified':verified}),flush=True)
    additional = sum(r['bytes'] for r in files if not bounded_path(root, r['path']).exists())
    max_archive = max((r['bytes'] for r in pending), default=0)
    report = {'schema': 'omnistream.local-restoration-plan.v1', 'archives_total': len(plan),
              'archives_verified': len(plan)-len(pending), 'archives_pending': len(pending),
              'full_scene_bytes': sum(r['bytes'] for r in files), 'additional_scene_bytes': additional,
              'max_single_archive_bytes': max_archive, 'reserve_bytes': args.reserve_bytes,
              'io_mib_s':args.io_mib_s,'download_mib_s':args.download_mib_s,
              'execution_policy':'single heavy operation; background CPU/disk/memory scheduling',
              'disk_free_bytes': shutil.disk_usage(work).free, 'entire_scene_preserved': True}
    atomic_json(work/'restoration-plan.json', report)
    print(json.dumps(report), flush=True)
    if not args.execute:
        return
    if report['disk_free_bytes'] < additional+max_archive+args.reserve_bytes:
        raise RuntimeError('Insufficient space for full original scene plus one archive and reserve')
    transfer = work/'transfer'
    transfer.mkdir(exist_ok=True)
    processed=0
    def transfer_admission():
        if (work/'stop-restoration.request').exists():
            raise RuntimeError('Restoration stop request; no new Drive request')
        if psutil.virtual_memory().available < args.min_available_ram_bytes:
            raise RuntimeError('Available RAM floor reached; no new Drive request')
        if shutil.disk_usage(work).free < args.reserve_bytes:
            raise RuntimeError('Disk reserve reached; no new Drive request')
    for record in pending:
        if (work/'stop-restoration.request').exists():
            print(json.dumps({'event':'stopped_at_archive_boundary','reason':'stop request'}),flush=True)
            return
        if psutil.virtual_memory().available < args.min_available_ram_bytes:
            raise RuntimeError('Available RAM floor reached; stop before another archive')
        archive = bounded_path(transfer, record['name'])
        # The Drive source is copied by its known ID; originals never move.
        if not archive.exists():
            log = transfer/(record['name']+'.transfer.log')
            command = [str(no_links(args.rclone)), '--config', str(no_links(args.config)),
                       '--transfers', '1', '--checkers', '1', '--buffer-size', '8Mi',
                       '--multi-thread-streams', '0', '--retries', '3', '--low-level-retries', '3',
                       '--bwlimit',str(args.download_mib_s)+'Mi','--tpslimit','2',
                       '--timeout', '2m', '--log-level', 'INFO',
                       'backend', 'copyid', args.remote+':', record['drive_id'], str(archive)]
            print(json.dumps({'event':'downloading', 'archive':record['name']}), flush=True)
            download_archive(command, archive, log, check_admission=transfer_admission)
        result = restore(archive, root, record, files, consume=True, min_free_bytes=args.reserve_bytes,limiter=limiter)
        print(json.dumps(result), flush=True)
        processed+=1
        if args.max_archives is not None and processed>=args.max_archives:
            print(json.dumps({'event':'stopped_at_requested_boundary','archives_processed':processed}),flush=True)
            return
    # Receipt proves the original delivered file set, independent of later USD overrides.
    for item in files:
        target = bounded_path(root, item['path'])
        if target.stat().st_size != item['bytes'] or sha256(target,limiter) != item['sha256']:
            raise ValueError('Final original-scene audit failed')
    atomic_json(work/'scene-restored.json', {'schema':'omnistream.scene-restored.v1',
                'file_count':len(files), 'bytes':sum(r['bytes'] for r in files),
                'source_manifest_sha256':sha256(files_path), 'verified':True})


if __name__ == '__main__':
    main()
