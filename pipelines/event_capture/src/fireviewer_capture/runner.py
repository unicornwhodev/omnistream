"""Run in an already initialized Kit app. No production adapter is fabricated."""
import importlib
import json
from pathlib import Path
from .simulation import SimulationAdapter,MissingSimulationAdapter
from .config import load_config
from .storage import CaptureStore,atomic_json
from .metrics import RunMetrics,ResourceSampler
from .replicator import ReplicatorCaptureManager
from .orchestrator import CapturePipeline
from .omniverse_driver import OmniverseRenderDriver


def load_factory(spec):
    module,sep,name=spec.partition(':')
    if not sep or not module or not name or '.' in name:raise ValueError('Factory format is module:function')
    return getattr(importlib.import_module(module),name)


async def run_in_current_kit(config_path,output,adapter_factory=None,fixture_log=None,max_groups=None,gpu_timing_factory=None,residency_factory=None,offload_factory=None):
    config=load_config(config_path)
    if bool(adapter_factory)==bool(fixture_log):
        raise MissingSimulationAdapter('Provide one real adapter factory, or an explicitly marked qualification fixture log')
    if fixture_log:
        from .kit_replay import KitFixtureAdapter
        from .models import SimulationState
        payload=json.loads(Path(fixture_log).read_text())
        adapter=KitFixtureAdapter([SimulationState.from_dict(x) for x in payload['states']])
    else:adapter=load_factory(adapter_factory)(config)
    if not isinstance(adapter,SimulationAdapter):raise MissingSimulationAdapter('Factory must implement SimulationAdapter')
    adapter.require_capture_contract()
    timing=load_factory(gpu_timing_factory)(config) if gpu_timing_factory else None
    residency=load_factory(residency_factory)(config) if residency_factory else None
    store=CaptureStore(output);metrics=RunMetrics();driver=OmniverseRenderDriver(timing,residency)
    offloader=load_factory(offload_factory)(config,store) if offload_factory else None
    manager=ReplicatorCaptureManager(config,driver,store,metrics);pipeline=CapturePipeline(config,adapter,manager,store,metrics,offloader)
    try:
        with ResourceSampler(metrics):result=await pipeline.run(resume=True,max_groups=max_groups)
        return result
    finally:
        summary=metrics.summary();summary['adapter_description']=adapter.capabilities.description
        summary['production_fire_adapter']=fixture_log is None
        summary['qualification_complete']=False
        summary['remaining_gates']=['native integration matrix','GPU profiler timing','memory stability','ghosting inspection','scientific annotation acceptance']
        atomic_json(store.root/'run-metrics.json',summary)
