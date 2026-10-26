"""Own one bounded native worker and persist its actual exit and acceptance.

Run with the notebook Python. It does not accept credentials, install software,
change the GPU allocation or restart a failed worker automatically.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def atomic_json(path, value):
    part = path.with_suffix('.partial')
    with part.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    part.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True)
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--config')
    parser.add_argument('--tag', required=True)
    parser.add_argument('--deadline-s', type=int, default=1800)
    args = parser.parse_args()
    if os.name != 'posix' or not 60 <= args.deadline_s <= 3600:
        raise ValueError('Bounded Colab Linux worker required')
    if not args.tag or any(c not in '0123456789TZ' for c in args.tag):
        raise ValueError('UTC run tag required')
    context = json.loads(Path(args.context).read_text())
    work = Path(context['qualification_root']).resolve(strict=True)
    if not str(work).startswith('/content/'):
        raise ValueError('Qualification must remain on Colab')
    runtime = json.loads(Path(args.runtime).read_text())
    if runtime.get('eula_accepted') is not True:
        raise ValueError('Previously recorded NVIDIA approval required')
    code = Path(__file__).resolve().parent
    log_path = work / ('response-' + args.tag + '.log')
    receipt_path = work / ('process-exit-' + args.tag + '.json')
    if receipt_path.exists() or log_path.exists():
        raise FileExistsError('A supervisor run tag cannot overwrite prior evidence')
    started = time.monotonic()
    env = dict(os.environ, **runtime['environment'])
    env.update(OMNI_KIT_ACCEPT_EULA='YES', PXR_WORK_THREAD_LIMIT='2')
    with log_path.open('w') as log:
        command = [
            'timeout', '--signal=TERM', '--kill-after=30s', str(args.deadline_s),
            runtime['python'], '-u', str(code / 'qualify.py'), '--context', args.context,
        ]
        if args.config:
            command.extend(['--config', args.config])
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env)
        atomic_json(work / 'response-process.json', {
            'supervisor_pid': os.getpid(), 'wrapper_pid': process.pid,
            'log_name': log_path.name, 'exit_receipt': receipt_path.name,
            'scope': 'factory-vfx-only', 'started_utc': args.tag,
        })
        exit_code = process.wait()
        log.flush()
        os.fsync(log.fileno())
    # qualify.py uses this exact content identity, independent of timestamps.
    config = json.loads(Path(args.config).read_text()) if args.config else json.loads((code / 'cases.json').read_text())
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in code.iterdir() if p.suffix in ('.py', '.kit')}
    fingerprint = hashlib.sha256(json.dumps({'config': config, 'code': hashes}, sort_keys=True).encode()).hexdigest()
    folder = work / 'response-tests' / fingerprint[:16]
    from evaluate import evaluate
    report_path = folder / 'report.json'
    receipt = {'schema': 'fireviewer.factory-native-process.v1', 'run_id': fingerprint[:16],
               'exit_code': exit_code, 'elapsed_wall_s': time.monotonic() - started,
               'deadline_wall_s': args.deadline_s, 'log_file': log_path.name,
               'log_sha256': hashlib.sha256(log_path.read_bytes()).hexdigest(),
               'report_present': report_path.is_file()}
    if report_path.is_file():
        receipt['report_sha256'] = hashlib.sha256(report_path.read_bytes()).hexdigest()
        acceptance = evaluate(json.loads(report_path.read_text()), process_exit_code=exit_code)
        atomic_json(folder / 'acceptance.json', acceptance)
        receipt['functional_response_passed'] = acceptance['functional_response_passed']
        receipt['failed_checks'] = [c['name'] for c in acceptance['checks'] if not c['passed']]
    atomic_json(receipt_path, receipt)
    print(json.dumps(receipt), flush=True)
    if exit_code or receipt.get('functional_response_passed') is not True:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
