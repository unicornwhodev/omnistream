"""SDK boundary regression tests; these do not qualify an Omniverse runtime."""
import types
import sys
import unittest
from unittest.mock import patch
import numpy as np

from fireviewer_capture.omniverse_driver import OmniverseRenderDriver
from fireviewer_capture.models import ContractError


class FakeReplicator:
    def __init__(self,status='STEPPED'):
        self.status=status;self.time=12.5;self.writers=[];self.events=[];self.steps=0;self.created=0
        self.change_clock_on_pause=False
        states=types.SimpleNamespace(STEPPED='STEPPED',STOPPED='STOPPED',PAUSED='PAUSED')
        self.orchestrator=types.SimpleNamespace(Status=states,get_status=lambda:self.status,
            get_is_paused=lambda:self.status=='PAUSED',pause=self.pause,step_async=self.step)
        owner=self
        class Writer:
            def attach(self,product,trigger):
                owner.events.append(('attach',owner.status,trigger));owner.writers.append(self)
            def schedule_write(self):owner.events.append(('schedule',self))
        self.Writer=Writer
        self.AnnotatorRegistry=types.SimpleNamespace(get_annotator=lambda name:name)
        self.create=types.SimpleNamespace(render_product=self.create_product)

    def pause(self):
        self.status='PAUSED'
        if self.change_clock_on_pause:self.time+=1

    def create_product(self,*args,**kwargs):
        self.created+=1
        texture=types.SimpleNamespace(set_updates_enabled=lambda enabled:None)
        return types.SimpleNamespace(hydra_texture=texture,destroy=lambda:None)

    async def step(self,**kwargs):
        assert kwargs['delta_time']==0.0
        self.steps+=1
        scheduled=[e[1] for e in self.events if e[0]=='schedule']
        if self.steps==1:
            assert not scheduled and all(w.pending is None for w in self.writers)
        else:
            for writer in scheduled:writer.write({'rgb':np.zeros((2,3,4),dtype=np.uint8)})
        self.status='STEPPED'


class WriterBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def environment(self,fake):
        omni=types.ModuleType('omni');timeline=types.ModuleType('omni.timeline')
        timeline.get_timeline_interface=lambda:types.SimpleNamespace(get_current_time=lambda:fake.time)
        omni.timeline=timeline
        return patch.dict(sys.modules,{'omni':omni,'omni.timeline':timeline})

    async def create(self,fake):
        driver=OmniverseRenderDriver();driver.rep=fake
        config={'render':{'resolution_px':[3,2],'max_active_products':5,'rt_subframes':1}}
        with self.environment(fake):
            product=await driver.create_product({'id':'camera','usd_path':'/Camera'},config)
        return driver,product,config

    async def test_new_writer_attaches_paused_without_advancing_simulation(self):
        fake=FakeReplicator();driver,product,_=await self.create(fake)
        self.assertEqual(fake.time,12.5)
        self.assertEqual(fake.events,[('attach','PAUSED',None)])
        self.assertFalse(product.enabled)

    async def test_clock_change_during_capture_pause_is_rejected_before_creation(self):
        fake=FakeReplicator();fake.change_clock_on_pause=True
        with self.assertRaises(ContractError):await self.create(fake)
        self.assertEqual(fake.created,0)

    async def test_busy_orchestrator_is_rejected_before_creation(self):
        fake=FakeReplicator('STEPPING')
        with self.assertRaises(ContractError):await self.create(fake)
        self.assertEqual(fake.created,0)

    async def test_graph_is_primed_before_explicit_zero_time_capture(self):
        fake=FakeReplicator();driver,product,config=await self.create(fake)
        driver.set_updates(product,True)
        result=await driver.trigger({'camera':product},{'camera':{}},config)
        self.assertEqual(fake.steps,2)
        self.assertEqual(result.frames['camera'].shape,(2,3,3))
        self.assertEqual(driver.unsolicited_callbacks,0)
        self.assertFalse(product.enabled)
        self.assertTrue(product.primed)
