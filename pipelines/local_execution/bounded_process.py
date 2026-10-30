"""Windows process-tree memory ceiling and conservative GPU watchdog.

Creates the child suspended, assigns it to a Job Object, then resumes it.
The OS enforces committed-memory limits. GPU polling is a watchdog, not a
driver-level allocation cap; its headroom and observed overshoot are reported.
No unrelated process is modified or terminated.
"""
import argparse
import json
import mmap
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from restore_scene import atomic_json, no_links
from host_budget import exclusive_heavy_work


def resource_stop_reason(*, peak_commit, commit_stop, available_ram, ram_reserve,
                         vram, vram_stop, wall_s, timeout_s, rss=0,
                         rss_stop=10_500_000_000):
    """Stop before allocation refusal; a hard Job limit alone can crash LLVM.

    The peak is deliberately conservative: once a process has crossed the soft
    budget, a temporary dip must not let an unstable run continue.
    """
    if peak_commit >= commit_stop:
        return 'job_commit_headroom_threshold'
    if rss >= rss_stop:
        return 'resident_ram_headroom_threshold'
    if available_ram < ram_reserve:
        return 'host_ram_headroom_threshold'
    if vram is not None and vram >= vram_stop:
        return 'gpu_headroom_threshold'
    if wall_s >= timeout_s:
        return 'wall_timeout'
    return None


class FatalLogMonitor:
    """Bounded incremental scan of this child only, including split messages."""
    PATTERNS = (b'LLVM ERROR: out of memory', b'A GPU crash occurred',
                b'HRESULT: 0x887a0005', b'HydraEngine::render failed')

    def __init__(self, paths):
        self.offsets = {Path(path): 0 for path in paths}
        self.tails = {path: b'' for path in self.offsets}

    def check(self):
        for path, offset in self.offsets.items():
            with path.open('rb') as stream:
                stream.seek(offset)
                # Very noisy stderr is itself a reason to stop the run rather
                # than let this monitor grow in memory or fall behind forever.
                data = stream.read(65537)
                self.offsets[path] = stream.tell()
            if len(data) > 65536:
                return 'native_log_flood'
            joined = self.tails[path] + data
            self.tails[path] = joined[-128:]
            if any(pattern in joined for pattern in self.PATTERNS):
                return 'native_renderer_fatal_error'
        return None


def process_tree_rss(process):
    import psutil
    try:
        tree = [process, *process.children(recursive=True)]
    except psutil.NoSuchProcess:
        return 0
    total = 0
    for child in tree:
        try:
            total += child.memory_info().rss
        except psutil.NoSuchProcess:
            # A normally exiting helper must not look like a failed monitor.
            continue
    return total


def run_bounded(command, output, *, ram_bytes=11_500_000_000,
                vram_ceiling_bytes=15_000_000_000, vram_stop_bytes=14_000_000_000,
                gpu_index=0, monitor_gpu=True, timeout_s=3600,
                min_available_ram_bytes=4_000_000_000, ram_stop_bytes=None,
                log_paths=None, working_directory=None):
    if sys.platform != 'win32':
        raise RuntimeError('This launcher requires Windows Job Objects')
    if (ram_bytes <= 0 or min_available_ram_bytes <= 0 or timeout_s <= 0
            or not 0 < vram_stop_bytes < vram_ceiling_bytes):
        raise ValueError('Invalid memory limits')
    # Windows stores the Job limit in whole pages. Round down explicitly so
    # the verified limit never exceeds the requested decimal-byte budget.
    enforced_ram_bytes = ram_bytes // mmap.PAGESIZE * mmap.PAGESIZE
    if enforced_ram_bytes == 0:
        raise ValueError('RAM budget is smaller than one memory page')
    if ram_bytes > 12_000_000_000 or vram_ceiling_bytes > 15_000_000_000:
        raise ValueError('Requested limits exceed the authorized local resource ceilings')
    if ram_stop_bytes is None:
        ram_stop_bytes = min(9_000_000_000, int(enforced_ram_bytes * 0.8))
    if not 0 < ram_stop_bytes < enforced_ram_bytes:
        raise ValueError('The soft commit threshold must precede the hard Job limit')
    import win32api
    import win32con
    import win32event
    import win32file
    import win32job
    import win32process
    import win32security
    import psutil

    available_ram = psutil.virtual_memory().available
    required_ram = ram_bytes + min_available_ram_bytes
    if available_ram < required_ram:
        raise RuntimeError(f'Available host RAM {available_ram} bytes is below the required '
                           f'job plus reserve {required_ram} bytes; no process started')
    output = no_links(output)
    output.mkdir(parents=True, exist_ok=False)
    gpu = nvml = None
    if monitor_gpu:
        import pynvml as nvml
        nvml.nvmlInit()
        gpu = nvml.nvmlDeviceGetHandleByIndex(gpu_index)
        if nvml.nvmlDeviceGetMemoryInfo(gpu).used >= vram_stop_bytes:
            nvml.nvmlShutdown()
            raise RuntimeError('Insufficient GPU headroom; no process started')
    job = win32job.CreateJobObject(None, 'OmniStream-'+uuid.uuid4().hex)
    limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    limits['BasicLimitInformation']['LimitFlags'] = (win32job.JOB_OBJECT_LIMIT_JOB_MEMORY |
                                                   win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)
    limits['JobMemoryLimit'] = enforced_ram_bytes
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
    applied = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    if applied['JobMemoryLimit'] != enforced_ram_bytes:
        win32api.CloseHandle(job)
        if nvml:nvml.nvmlShutdown()
        raise RuntimeError('Job memory limit readback differs; no process started')
    # No breakaway flag: child processes remain subject to this job.
    security = win32security.SECURITY_ATTRIBUTES()
    security.bInheritHandle = True
    handles = []
    process = thread = None
    started = time.monotonic()
    max_vram = max_rss = 0
    reason = 'normal_exit'
    exit_code = None
    try:
        logs = ([output/'stdout.private.log',output/'stderr.private.log'] if log_paths is None
                else [no_links(p) for p in log_paths])
        if len(logs) != 2 or logs[0] == logs[1]:
            raise ValueError('Two distinct owned log paths are required')
        for log in logs:
            handles.append(win32file.CreateFile(str(log), win32con.GENERIC_WRITE,
                           win32con.FILE_SHARE_READ, security, win32con.CREATE_NEW, 0, None))
        handles.append(win32file.CreateFile('NUL', win32con.GENERIC_READ,
                       win32con.FILE_SHARE_READ|win32con.FILE_SHARE_WRITE, security,
                       win32con.OPEN_EXISTING, 0, None))
        startup = win32process.STARTUPINFO()
        startup.dwFlags |= win32con.STARTF_USESTDHANDLES
        startup.hStdOutput, startup.hStdError, startup.hStdInput = handles
        process, thread, pid, _ = win32process.CreateProcess(str(Path(command[0]).resolve()),
            subprocess.list2cmdline(command), None, None, True,
            win32con.CREATE_NO_WINDOW|win32con.CREATE_SUSPENDED|win32process.BELOW_NORMAL_PRIORITY_CLASS,
            dict(os.environ), str(no_links(working_directory) if working_directory
                                  else Path(command[0]).resolve().parent), startup)
        try:
            win32job.AssignProcessToJobObject(job, process)
        except Exception:
            win32api.TerminateProcess(process, 87)
            raise RuntimeError('Could not enforce Job Object limit; child never resumed') from None
        atomic_json(output/'process.json', {'pid':pid, 'job_commit_limit_bytes':enforced_ram_bytes,
                      'requested_job_commit_limit_bytes':ram_bytes,
                      'job_commit_stop_bytes':ram_stop_bytes,
                      'resident_ram_stop_bytes':10_500_000_000,
                      'gpu_stop_bytes':vram_stop_bytes, 'gpu_requested_ceiling_bytes':vram_ceiling_bytes,
                      'host_available_ram_floor_bytes':min_available_ram_bytes,
                      'gpu_is_polled_not_hard_capped':True})
        owned = psutil.Process(pid)
        fatal_logs = FatalLogMonitor(logs)
        win32process.ResumeThread(thread)
        with (output/'resources.jsonl').open('w',encoding='utf-8') as journal:
            while win32event.WaitForSingleObject(process, 100) == win32con.WAIT_TIMEOUT:
                now = time.monotonic()-started
                try:
                    rss = process_tree_rss(owned)
                    available_ram = psutil.virtual_memory().available
                    vram = int(nvml.nvmlDeviceGetMemoryInfo(gpu).used) if monitor_gpu else None
                    job_info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
                except Exception:
                    reason = 'resource_monitor_unavailable'
                    win32job.TerminateJobObject(job, 88)
                    break
                max_rss = max(max_rss, rss)
                max_vram = max(max_vram, vram or 0)
                journal.write(json.dumps({'wall_s':now,'owned_tree_rss_bytes':rss,
                    'host_available_ram_bytes':available_ram,
                    'device_vram_bytes':vram,'job_peak_commit_bytes':int(job_info['PeakJobMemoryUsed'])})+'\n')
                journal.flush()
                stop = resource_stop_reason(peak_commit=int(job_info['PeakJobMemoryUsed']),
                    commit_stop=ram_stop_bytes, available_ram=available_ram,
                    ram_reserve=min_available_ram_bytes, vram=vram,
                    vram_stop=vram_stop_bytes, wall_s=now, timeout_s=timeout_s, rss=rss)
                try:
                    stop = stop or fatal_logs.check()
                except OSError:
                    stop = stop or 'resource_monitor_unavailable'
                if stop:
                    reason = stop
                    win32job.TerminateJobObject(job, 92)
                    break
            win32event.WaitForSingleObject(process, 10000)
            exit_code = win32process.GetExitCodeProcess(process)
            if reason == 'normal_exit' and exit_code != 0:
                reason = 'process_failed'
        info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        receipt = {'schema':'omnistream.bounded-process.v1','exit_code':exit_code,'reason':reason,
                   'wall_s':time.monotonic()-started,'ram_job_commit_limit_bytes':enforced_ram_bytes,
                   'requested_ram_job_commit_limit_bytes':ram_bytes,
                   'ram_job_commit_stop_bytes':ram_stop_bytes,
                   'resident_ram_stop_bytes':10_500_000_000,
                   'monitor_interval_ms':100,
                   'ram_job_limit_readback_bytes':int(applied['JobMemoryLimit']),
                   'host_available_ram_floor_bytes':min_available_ram_bytes,
                   'peak_job_commit_bytes':int(info['PeakJobMemoryUsed']), 'peak_owned_rss_bytes':max_rss,
                   'peak_device_vram_bytes':max_vram if monitor_gpu else None,
                   'gpu_stop_threshold_bytes':vram_stop_bytes if monitor_gpu else None,
                   'requested_gpu_ceiling_bytes':vram_ceiling_bytes,
                   'observed_gpu_ceiling_exceeded':max_vram>vram_ceiling_bytes if monitor_gpu else None,
                   'gpu_limit_is_watchdog_not_allocation_cap':True}
        atomic_json(output/'receipt.json',receipt)
        return receipt
    finally:
        # Closing the job terminates only this child tree if it is still alive.
        win32api.CloseHandle(job)
        for handle in [thread, process, *handles]:
            if handle is not None:
                win32api.CloseHandle(handle)
        if nvml:
            nvml.nvmlShutdown()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True)
    p.add_argument('--ram-bytes',type=int,default=11_500_000_000)
    p.add_argument('--ram-stop-bytes',type=int)
    p.add_argument('--vram-ceiling-bytes',type=int,default=15_000_000_000)
    p.add_argument('--vram-stop-bytes',type=int,default=14_000_000_000)
    p.add_argument('--timeout-s',type=float,default=3600)
    p.add_argument('--min-available-ram-bytes',type=int,default=4_000_000_000)
    p.add_argument('--no-gpu',action='store_true',help='For CPU-only preparation/testing, never a renderer')
    p.add_argument('command',nargs=argparse.REMAINDER)
    a = p.parse_args()
    command = a.command[1:] if a.command and a.command[0]=='--' else a.command
    if not command:p.error('A child executable is required after --')
    with exclusive_heavy_work(no_links(a.output).parent):
        receipt = run_bounded(command,a.output,ram_bytes=a.ram_bytes,
            vram_ceiling_bytes=a.vram_ceiling_bytes,vram_stop_bytes=a.vram_stop_bytes,
            monitor_gpu=not a.no_gpu,timeout_s=a.timeout_s,
            min_available_ram_bytes=a.min_available_ram_bytes,ram_stop_bytes=a.ram_stop_bytes)
    print(json.dumps(receipt))
    raise SystemExit(0 if receipt['exit_code']==0 and receipt['reason']=='normal_exit' else 1)
