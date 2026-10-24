import importlib.util
import unittest
import tempfile
from pathlib import Path
import hashlib
import numpy as np
from helpers import config,state,front
from fireviewer_capture.benchmark import policy_plan
from fireviewer_capture.models import ContractError,Activity
from fireviewer_capture.activity import ZoneActivityTracker
from fireviewer_capture.qualification import resource_stability


class ExtraContractTests(unittest.TestCase):
    def test_initial_post_extinction_without_history_is_not_a_negative(self):
        c=config(1);tracker=ZoneActivityTracker(c['zones'],c['activity'])
        with self.assertRaises(ContractError):tracker.update(state(0,[front(phase=Activity.POST_EXTINCTION)]))
    def test_active_front_cannot_hide_an_unknown_relevant_front(self):
        c=config(1);tracker=ZoneActivityTracker(c['zones'],c['activity'])
        with self.assertRaises(ContractError):tracker.update(state(0,[front(ident='known'),front(ident='unknown',phase=Activity.UNKNOWN)]))
    def test_memory_gate_requires_vram_and_post_warmup_cycles(self):
        samples=[{'cycle':i,'process_rss_bytes':1000,'device_vram_used_bytes':None} for i in range(10)]
        self.assertFalse(resource_stability(samples,3,1,1)['passed'])
        for s in samples:s['device_vram_used_bytes']=500
        self.assertTrue(resource_stability(samples,3,1,1)['passed'])
        for s in samples:s['device_vram_used_bytes']=500+s['cycle']*10
        self.assertFalse(resource_stability(samples,3,1,1)['passed'])


class PlanTests(unittest.IsolatedAsyncioTestCase):
    async def test_count_benchmark_preserves_negatives_and_both_smoke_edges(self):
        c=config(1,600);c['activity']['enter_hold_sim_s']=30
        events=[state(),state(10,[front(phase=Activity.INACTIVE,smoke=True)]),state(11,[])]
        event=await policy_plan(c,events);uniform=await policy_plan(c,events,60)
        self.assertGreaterEqual(event['groups'],3);self.assertEqual(uniform['groups'],10)
        self.assertFalse(event['GPU_render_measured'])


@unittest.skipUnless(importlib.util.find_spec('pxr'),'OpenUSD is required')
class USDTests(unittest.TestCase):
    def test_entrypoint_authors_metric_axis_clock_and_preserves_sources(self):
        from pxr import Usd,UsdGeom
        from fireviewer_capture.usd_cameras import create_configured_cameras,read_camera,create_capture_entrypoint
        c=config(1)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);base=root/'base.usda';cameras=root/'cameras.usda'
            for path in [base,cameras]:
                stage=Usd.Stage.CreateNew(str(path));UsdGeom.SetStageUpAxis(stage,'Z');UsdGeom.SetStageMetersPerUnit(stage,1)
                stage.SetDefaultPrim(UsdGeom.Xform.Define(stage,'/World').GetPrim())
                if path==cameras:create_configured_cameras(stage,c)
                stage.GetRootLayer().Save()
            before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in [base,cameras]}
            receipt=create_capture_entrypoint(root/'capture_ready.usda',c,cameras,base)
            stage=Usd.Stage.Open(receipt['entrypoint'],load=Usd.Stage.LoadNone)
            self.assertEqual(UsdGeom.GetStageUpAxis(stage),'Z');self.assertEqual(UsdGeom.GetStageMetersPerUnit(stage),1)
            self.assertEqual(stage.GetTimeCodesPerSecond(),1);self.assertEqual(stage.GetEndTimeCode(),1200)
            self.assertAlmostEqual(read_camera(stage,c['cameras'][0],c)['focal_length_mm'],22,places=5)
            self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before})
            with self.assertRaises(ContractError):create_capture_entrypoint(root/'capture_ready.usda',c,cameras,base)

    def test_camera_read_rejects_composed_root_with_default_units_and_axis(self):
        from pxr import Usd,UsdGeom,Sdf
        from fireviewer_capture.usd_cameras import create_configured_cameras,read_camera
        c=config(1)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'metric.usda';stage=Usd.Stage.CreateNew(str(source))
            UsdGeom.SetStageUpAxis(stage,'Z');UsdGeom.SetStageMetersPerUnit(stage,1);create_configured_cameras(stage,c);stage.GetRootLayer().Save()
            layer=Sdf.Layer.CreateNew(str(root/'missing-root-metadata.usda'));layer.subLayerPaths=['./metric.usda'];layer.Save()
            composed=Usd.Stage.Open(layer,load=Usd.Stage.LoadNone)
            with self.assertRaises(ContractError):read_camera(composed,c['cameras'][0],c)

    def test_fifty_fixed_cameras_have_correct_metric_optics_and_pose(self):
        from pxr import Usd,UsdGeom
        from fireviewer_capture.usd_cameras import create_configured_cameras,read_camera
        c=config(10);s=Usd.Stage.CreateInMemory();UsdGeom.SetStageUpAxis(s,'Z');UsdGeom.SetStageMetersPerUnit(s,1)
        create_configured_cameras(s,c)
        for camera in c['cameras']:
            value=read_camera(s,camera,c);m=np.asarray(value['camera_to_world_usd_row_vector'])
            self.assertTrue(np.allclose(m[3,:3],camera['position_m']))
            self.assertAlmostEqual(value['focal_length_mm'],camera['focal_length_mm'],places=5)
            point=np.asarray(value['world_to_camera_cv_column_vector'])@np.r_[camera['look_at_m'],1]
            self.assertGreater(point[2],0);pixel=np.asarray(value['intrinsic_K'])@point[:3];pixel=pixel[:2]/pixel[2]
            self.assertTrue(np.allclose(pixel,np.asarray(c['render']['resolution_px'])/2,atol=1e-9))
