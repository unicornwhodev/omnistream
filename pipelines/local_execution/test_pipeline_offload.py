"""CPU contract tests only: no native fire or authenticated Drive claim."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

event_root=Path(__file__).resolve().parents[1]/'event_capture'
sys.path.insert(0,str(event_root/'src'))
sys.path.insert(0,str(event_root/'tests'))
from helpers import config,state,pipeline
from fireviewer_capture.models import ContractError
from fireviewer_capture.orchestrator import CapturePipeline
from spool_adapter import SpoolOffloader
from verified_spool import VerifiedSpool,SpoolBlocked
from test_verified_spool import MemoryRemote


class OffloadPipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.root=Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.remote=MemoryRemote()

    def make(self,cfg,*,spool_bytes=6_000_000,policy='test-cloud-destination'):
        ordinary,driver,store,metrics=pipeline(self.root,cfg,[state()])
        spool=VerifiedSpool(self.root,self.remote,max_bytes=spool_bytes,reserve_bytes=0)
        offloader=SpoolOffloader(spool,{'destination':policy})
        result=CapturePipeline(cfg,ordinary.adapter,ordinary.manager,store,metrics,offloader)
        return result,driver,store,metrics

    async def test_ten_groups_offload_per_group_with_every_producer_frozen(self):
        p,driver,store,metrics=self.make(config(10,duration_s=1,cap=1))
        original=self.remote.upload_verified
        def upload(*args):
            self.assertTrue(p.adapter._frozen)
            self.assertFalse(any(h['enabled'] for h in driver.handles))
            self.assertEqual(len(store.read_checkpoint()['pending_offloads']),1)
            return original(*args)
        self.remote.upload_verified=upload
        result=await p.run()
        self.assertEqual(result['committed_groups'],10)
        self.assertEqual(metrics.counts['groups_offloaded_verified'],10)
        self.assertFalse(list(self.root.glob('frames/*/*.png')))
        self.assertEqual(len(list(self.root.glob('frames/*/*.json'))),50)
        self.assertEqual(store.read_checkpoint()['pending_offloads'],[])
        self.assertEqual(driver.peak,1)

    async def test_transfer_failure_stops_time_then_resumes_without_rerender(self):
        cfg=config(1,duration_s=1)
        p,driver,store,_=self.make(cfg)
        self.remote.fail=True
        with self.assertRaises(SpoolBlocked):await p.run()
        self.assertEqual(p.adapter.now,0)
        self.assertEqual(len(list(self.root.glob('frames/*/*.png'))),5)
        self.assertEqual(len(store.read_checkpoint()['pending_offloads']),1)
        self.remote.fail=False
        resumed,driver,store,metrics=self.make(cfg)
        result=await resumed.run()
        self.assertTrue(result['complete'])
        self.assertFalse(driver.calls)
        self.assertEqual(metrics.counts['groups_offloaded_verified'],1)
        self.assertFalse(list(self.root.glob('frames/*/*.png')))

    async def test_interrupt_after_pruning_rechecks_cloud_before_advance(self):
        cfg=config(1,duration_s=1)
        p,_,store,_=self.make(cfg)
        original=p.offloader.offload_group
        async def crash(group_id):
            await original(group_id)
            raise RuntimeError('interrupted before pending checkpoint cleared')
        p.offloader.offload_group=crash
        with self.assertRaisesRegex(RuntimeError,'interrupted'):await p.run()
        self.assertFalse(list(self.root.glob('frames/*/*.png')))
        self.assertEqual(len(store.read_checkpoint()['pending_offloads']),1)
        resumed,driver,_,_=self.make(cfg)
        self.remote.corrupt=True
        with self.assertRaises(SpoolBlocked):await resumed.run()
        self.assertEqual(resumed.adapter.now,0)
        self.assertFalse(driver.calls)
        self.remote.corrupt=False
        resumed,driver,_,_=self.make(cfg)
        self.assertTrue((await resumed.run())['complete'])
        self.assertFalse(driver.calls)

    async def test_missing_or_changed_destination_refuses_resume(self):
        cfg=config(1,duration_s=1)
        p,_,_,_=self.make(cfg)
        await p.run()
        missing,driver,_,_=pipeline(self.root,cfg,[state()])
        with self.assertRaises(ContractError):await missing.run()
        self.assertEqual(driver.created,0)
        changed,driver,_,_=self.make(cfg,policy='different-folder')
        with self.assertRaises(ContractError):await changed.run()
        self.assertEqual(driver.created,0)

    async def test_capacity_checked_before_any_render(self):
        p,driver,_,_=self.make(config(1,duration_s=1),spool_bytes=1_000)
        with self.assertRaises(SpoolBlocked):await p.run()
        self.assertFalse(driver.calls)
        self.assertEqual(p.adapter.now,0)
        self.assertFalse(list(self.root.glob('frames/*/*.png')))


if __name__=='__main__':unittest.main()
