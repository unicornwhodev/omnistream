"""Explicit CPU test doubles: these never certify Kit, GPU time or real images."""
from pathlib import Path
import importlib.util
import copy
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reference_config',ROOT/'tools/build_reference_config.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

from fireviewer_capture.drivers import RenderDriver,RenderBatch
from fireviewer_capture.models import SimulationState,FrontObservation,Provenance,Activity,simulated_us
from fireviewer_capture.metrics import RunMetrics
from fireviewer_capture.storage import CaptureStore
from fireviewer_capture.replicator import ReplicatorCaptureManager
from fireviewer_capture.orchestrator import CapturePipeline
from fireviewer_capture.simulation import RecordedStateAdapter


def config(groups=10,duration_s=1200,cap=5):
    from datetime import timedelta
    from fireviewer_capture.models import aware_time
    c=module.reference_config();c['zones']=c['zones'][:groups]
    ids={i for z in c['zones'] for i in z['camera_ids']};c['cameras']=[x for x in c['cameras'] if x['id'] in ids]
    c['period']['end_exclusive']=(aware_time(c['period']['start'])+timedelta(seconds=duration_s)).isoformat()
    c['activity'].update(enter_hold_sim_s=0,exit_hold_sim_s=0,poll_interval_sim_s=3600)
    c['render'].update(resolution_px=[32,18],max_active_products=cap,max_cached_products=max(cap,5))
    return c


def front(zone=0,ident='front_01',phase=Activity.ACTIVE_RAPID,smoke=False,point=None):
    x=-8000+(zone%5)*4000;y=-5000+(zone//5)*10000
    p={'type':'Point','coordinates':point or [x,y]}
    return FrontObservation(ident,p,phase,Provenance('test_fixture','explicit-unit-test-state'),
                            p if smoke else None,smoke,{})


def state(seconds=0,fronts=(),revision='fixture_00',environment=None):
    return SimulationState(simulated_us(seconds),revision,tuple(fronts),environment or {},{'kind':'test_fixture'})


class FakeDriver(RenderDriver):
    descriptor={'native_omniverse':False,'kind':'CPU test fixture; no GPU rendering'}
    def __init__(self,fail_on_call=None):
        self.handles=[];self.calls=[];self.created=0;self.destroyed=0;self.initializations=0
        self.fail_on_call=fail_on_call;self.peak=0;self.on_render=None
    async def initialize(self,config):self.initializations+=1
    async def create_product(self,camera,config):
        h={'id':camera['id'],'enabled':False};self.handles.append(h);self.created+=1;return h
    def set_updates(self,handle,enabled):handle['enabled']=enabled
    def camera_metadata(self,camera,config):
        return {'id':camera['id'],'usd_path':camera['usd_path'],'camera_to_world_usd_row_vector':np.eye(4).tolist(),
                'world_to_camera_cv_column_vector':np.eye(4).tolist(),'intrinsic_K':np.eye(3).tolist(),
                'pose_source':'explicit CPU test double','physical_hardware_calibrated':False}
    async def trigger(self,handles,contexts,config):
        enabled={h['id'] for h in self.handles if h['enabled']};assert enabled==set(handles)
        self.peak=max(self.peak,len(enabled));self.calls.append({'cameras':sorted(handles),'contexts':copy.deepcopy(contexts)})
        if self.on_render:self.on_render()
        if len(self.calls)==self.fail_on_call:raise RuntimeError('Injected rendering interruption')
        width,height=config['render']['resolution_px'];frames={i:np.full((height,width,3),32+len(self.calls)%100,dtype='uint8') for i in handles}
        return RenderBatch(frames,.001,None,None)
    async def destroy_product(self,handle):
        assert not handle['enabled'];self.handles.remove(handle);self.destroyed+=1


def pipeline(root,cfg,states,driver=None):
    adapter=RecordedStateAdapter(states);driver=driver or FakeDriver();store=CaptureStore(root);metrics=RunMetrics()
    manager=ReplicatorCaptureManager(cfg,driver,store,metrics)
    return CapturePipeline(cfg,adapter,manager,store,metrics),driver,store,metrics
