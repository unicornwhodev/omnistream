"""Private-configured guard used by OmniStream's Windows hidden launcher.

The native process is assigned to the memory Job before its first instruction.
The existing PowerShell launcher reads process.json and returns the exact native
creation identity to MCP; this guard continues to own and monitor the Job.
No credential is serialized: the control token is inherited in the environment.
"""
import argparse
import ctypes
from ctypes import wintypes
import json
import math
from pathlib import Path
import sys

from bounded_process import run_bounded
from host_budget import exclusive_heavy_work
from restore_scene import atomic_json, no_links


def split_windows_command(command_line):
    shell = ctypes.WinDLL('shell32',use_last_error=True)
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR,ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel.LocalFree.restype = wintypes.HLOCAL
    count = ctypes.c_int()
    result = shell.CommandLineToArgvW(command_line,ctypes.byref(count))
    if not result:raise ctypes.WinError(ctypes.get_last_error())
    try:return [result[i] for i in range(count.value)]
    finally:kernel.LocalFree(ctypes.cast(result,wintypes.HLOCAL))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',required=True)
    args = parser.parse_args()
    request_path = no_links(args.request)
    if request_path.stat().st_size > 65536:raise ValueError('Oversize guarded launch request')
    request = json.loads(request_path.read_text(encoding='utf-8-sig'))
    budget = request['budget']
    if budget['schema'] != 'omnistream.local-resource-budget.v1':raise ValueError('Unknown budget schema')
    wall = float(budget.get('wall_timeout_s',1800))
    ram = int(budget.get('ram_job_bytes',11_500_000_000))
    soft = int(budget.get('ram_stop_bytes',10_500_000_000))
    if not math.isfinite(wall) or not 0 < wall <= 1800 or not 0 < soft < ram <= 11_500_000_000:
        raise ValueError('Invalid conservative local budget')
    work = no_links(budget['workspace'])
    output = no_links(request['output'])
    command = [str(no_links(request['executable'])),*split_windows_command('kit '+request['argument_line'])[1:]]
    extras = budget.get('additional_arguments',[])
    if (not isinstance(extras,list) or len(extras)>40
            or any(not isinstance(a,str) or not a or len(a)>2048 or '\x00' in a for a in extras)):
        raise ValueError('Invalid operator-configured extra arguments')
    command.extend(extras)
    # Bounds are enforced again inside run_bounded; no permissive fallback.
    with exclusive_heavy_work(work):
        receipt = run_bounded(command,output,ram_bytes=ram,
            ram_stop_bytes=soft,vram_ceiling_bytes=15_000_000_000,
            vram_stop_bytes=14_000_000_000,min_available_ram_bytes=4_000_000_000,
            timeout_s=wall,
            log_paths=[request['stdout'],request['stderr']],working_directory=request['working_directory'])
    return 0 if receipt['reason']=='normal_exit' and receipt['exit_code']==0 else 1


if __name__ == '__main__':
    try:raise SystemExit(main())
    except Exception as error:
        # Keep paths, command line and environment out of console diagnostics.
        print('Guarded Kit launch failed: '+type(error).__name__,file=sys.stderr,flush=True)
        raise SystemExit(1)
