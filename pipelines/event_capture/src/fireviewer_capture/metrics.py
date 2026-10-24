"""Wall-time/resource measurements are never used as capture-policy intervals."""
from collections import defaultdict
import time
import threading


class RunMetrics:
    def __init__(self):
        self.started=time.perf_counter();self.durations=defaultdict(float);self.counts=defaultdict(int)
        self.samples=[];self.gpu_timing_unavailable_batches=0

    def add_render(self,wall_seconds,gpu_seconds=None,gpu_source=None):
        self.durations["render_wall_s"]+=wall_seconds
        self.counts["render_batches"]+=1
        if gpu_seconds is None:self.gpu_timing_unavailable_batches+=1
        else:
            self.durations["gpu_render_execution_s"]+=gpu_seconds
            self.gpu_source=gpu_source

    def summary(self):
        elapsed=time.perf_counter()-self.started;new=self.counts["images_written_new"]
        return {"wall_total_s":elapsed,"durations":dict(self.durations),"counts":dict(self.counts),
                "new_images_per_wall_second":new/elapsed if elapsed else None,
                "gpu_render_execution_s":self.durations.get("gpu_render_execution_s") if not self.gpu_timing_unavailable_batches else None,
                "gpu_timing_unavailable_batches":self.gpu_timing_unavailable_batches,
                "gpu_timing_source":getattr(self,"gpu_source",None),
                "render_wall_is_not_gpu_execution_time":True,"resources":self.samples}


class ResourceSampler:
    """NVML device memory and process RSS, with explicit unavailable values."""
    def __init__(self,metrics,wall_interval_s=.25):
        self.metrics=metrics;self.interval=wall_interval_s;self.stop_event=threading.Event();self.thread=None
        self.nvml=None;self.handle=None
        try:
            import pynvml
            pynvml.nvmlInit();self.nvml=pynvml;self.handle=pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception:pass

    def sample(self):
        import psutil
        sample={"wall_offset_s":time.perf_counter()-self.metrics.started,
                "process_rss_bytes":psutil.Process().memory_info().rss,
                "device_vram_used_bytes":None,"device_gpu_utilization_percent":None,
                "vram_scope":"whole GPU device; not attributed exclusively to this renderer"}
        if self.nvml and self.handle is not None:
            try:
                sample["device_vram_used_bytes"]=int(self.nvml.nvmlDeviceGetMemoryInfo(self.handle).used)
                sample["device_gpu_utilization_percent"]=int(self.nvml.nvmlDeviceGetUtilizationRates(self.handle).gpu)
            except Exception:pass
        self.metrics.samples.append(sample)

    def _run(self):
        while not self.stop_event.wait(self.interval):self.sample()
    def __enter__(self):
        self.sample();self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start();return self
    def __exit__(self,*args):
        self.stop_event.set();self.thread.join(timeout=2);self.sample()
