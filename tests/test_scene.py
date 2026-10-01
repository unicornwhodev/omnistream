"""Offline contracts plus optional REAL USD integration (never a fake pxr).
python -m unittest discover -s tests -v
USD tests skip explicitly when pxr is absent; Kit/PhysX remain a separate gate.
"""
import copy
import importlib
import importlib.util
import math
import os
import pathlib
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

BRIDGE = pathlib.Path(__file__).resolve().parents[1] / 'runtime/bridge/omnistream.codex.bridge/omnistream/codex/bridge'
package = types.ModuleType('omnistream_test_bridge')
package.__path__ = [str(BRIDGE)]
sys.modules[package.__name__] = package
policy = importlib.import_module(package.__name__ + '.scene_policy')
telemetry = importlib.import_module(package.__name__ + '.telemetry')
TRS = {'translation': [0, 0, 0], 'rotation': [0, 0, 0], 'scale': [1, 1, 1]}

class PolicyTests(unittest.TestCase):
    def test_supported_operations(self):
        ops = [
            {'op':'transform','primPath':'/World/Cube',**TRS},
            {'op':'animate_transform','primPath':'/World/Cube','keys':[{'timeSeconds':0,**TRS},{'timeSeconds':1,**TRS}]},
            {'op':'rigid_body','primPath':'/World/Cube','mass':1,'kinematic':False,'collider':True},
            {'op':'collider','primPath':'/World/Floor','enabled':True},
            {'op':'physics_scene','primPath':'/World/Physics','gravityDirection':[0,0,-0.5],'gravityMagnitude':9.81},
            {'op':'attribute','primPath':'/World/Cube','attribute':'physics:mass','value':2},
            {'op':'playback_range','startSeconds':0,'endSeconds':3,'framesPerSecond':30},
        ]
        self.assertEqual(len(policy.validate_operations(ops)),7)
        self.assertEqual(policy.validate_operations(ops)[4]['gravityDirection'],[0,0,-1])
    def test_finite_numbers(self):
        for value in (True,False,None,'2',float('inf'),float('nan'),-float('inf'),1e12):
            with self.subTest(value=value), self.assertRaises(ValueError): policy.number(value,'test')
    def test_paths(self):
        for value in ('/', '', '../Cube','C:/World','/World/../Cube','/World.attr','/World/Cube;eval','/World//Cube','/World/é',None):
            with self.subTest(value=value), self.assertRaises(ValueError): policy.prim_path(value)
        self.assertEqual(policy.prim_path('/World/Cube_1'),'/World/Cube_1')
        self.assertEqual(policy.prim_path('/',True),'/')
    def test_unknown_fields_and_execution(self):
        for op in ({'op':'python','primPath':'/World','code':'print(1)'},{'op':'transform','primPath':'/World',**TRS,'script':'x'}):
            with self.assertRaises(ValueError): policy.validate_operations([op])
    def test_operation_bounds(self):
        for ops in ([],[{'op':'transform','primPath':'/World',**TRS}]*33,None,{},[None]):
            with self.assertRaises(ValueError): policy.validate_operations(ops)
    def test_keyframes(self):
        for times in ([0,0],[2,1],[0],list(range(121))):
            with self.subTest(times=len(times)), self.assertRaises(ValueError):
                policy.validate_operations([{'op':'animate_transform','primPath':'/World','keys':[{'timeSeconds':t,**TRS} for t in times]}])
        with self.assertRaises(ValueError): policy.validate_operations([{'op':'animate_transform','primPath':'/World','keys':[TRS,TRS]}])
    def test_gravity_zero(self):
        with self.assertRaises(ValueError): policy.validate_operations([{'op':'physics_scene','primPath':'/World/P','gravityDirection':[0,0,0],'gravityMagnitude':9.81}])
    def test_attribute_allowlist_types(self):
        for name,value in [('script:code','execute'),('physics:mass',-1),('physics:mass',True),('physics:collisionEnabled',1),('physics:gravityDirection',[0,0,0]),('physics:restitution',2)]:
            with self.subTest(name=name,value=value), self.assertRaises(ValueError): policy.validate_operations([{'op':'attribute','primPath':'/World','attribute':name,'value':value}])
    def test_playback_range(self):
        for start,end,fps in [(2,1,30),(0,0,30),(0,2,0),(0,2,300),(0,0.001,30)]:
            with self.assertRaises(ValueError): policy.validate_operations([{'op':'playback_range','startSeconds':start,'endSeconds':end,'framesPerSecond':fps}])
    def test_watches(self):
        value={'primPath':'/World','attribute':'physics:mass'}
        self.assertEqual(policy.validate_watches([value,value]),[value])
        with self.assertRaises(ValueError): policy.validate_watches([value]*17)
        with self.assertRaises(ValueError): policy.validate_watches([{'primPath':'/World','attribute':'attr;call()'}])
    def test_zero_scale(self):
        with self.assertRaises(ValueError): policy.validate_operations([{'op':'transform','primPath':'/World',**TRS,'scale':[1,0,1]}])
    def test_booleans_not_truthy(self):
        with self.assertRaises(ValueError): policy.validate_operations([{'op':'rigid_body','primPath':'/World','mass':1,'kinematic':'false','collider':True}])

class TelemetryTests(unittest.TestCase):
    def test_redaction(self):
        value=telemetry.sanitize('token=TOPSECRET password="secret words" Authorization: Bearer ABCDEF')
        for secret in ['TOPSECRET','secret words','ABCDEF']: self.assertNotIn(secret,value)
    def test_bound(self):
        self.assertEqual(len(telemetry.sanitize('a'*2000)),1200)
    def test_ring_and_cursor(self):
        b=telemetry.TelemetryBuffer(3)
        for i in range(8): b.emit('test',{'i':i})
        self.assertEqual(b.dropped,5)
        self.assertEqual([e['sequence'] for e in b.drain(2)],[6,7])
        self.assertEqual([e['sequence'] for e in b.drain()],[8])
        self.assertEqual(b.drain(),[])
    def test_thread_safety(self):
        b=telemetry.TelemetryBuffer(1000)
        def work():
            for _ in range(100): b.log('module','WARN','token=secret')
        threads=[threading.Thread(target=work) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        rows=b.drain(1000)
        self.assertEqual(len(rows),500)
        self.assertEqual([e['sequence'] for e in rows],list(range(1,501)))
        self.assertTrue(all('secret' not in e['data']['message'] for e in rows))
    def test_extension_no_local_carb_shadowing(self):
        # Python dotted imports can shadow carb in on_startup before validation.
        import ast
        tree=ast.parse((BRIDGE/'extension.py').read_text())
        startup=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='on_startup')
        self.assertFalse(any(isinstance(n,ast.Import) and any(x.name.startswith('carb.') for x in n.names) for n in ast.walk(startup)))

HAS_USD = importlib.util.find_spec('pxr') is not None
if os.environ.get('OMNISTREAM_REQUIRE_USD') == '1' and not HAS_USD:
    raise RuntimeError('USD is mandatory for this gate; install the declared test dependency before running')
if HAS_USD:
    from pxr import Usd, UsdGeom, UsdPhysics, Sdf
    Service=importlib.import_module(package.__name__+'.scene_service').SceneService

class Timeline:
    def __init__(self): self.playing=False; self.stopped=True; self.time=0
    def is_playing(self): return self.playing
    def is_stopped(self): return self.stopped
    def get_current_time(self): return self.time
    def get_start_time(self): return 0
    def set_current_time(self,value): self.time=value
    def set_looping(self,value): self.loop=value
    def play(self): self.playing=True; self.stopped=False
    def stop(self): self.playing=False; self.stopped=True; self.time=0
    def pause(self): self.playing=False; self.stopped=False
    def commit(self): pass

@unittest.skipUnless(HAS_USD,'Real pxr/OpenUSD not installed; no USD execution claimed')
class RealUsdTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.temp.name)
        self.stage=Usd.Stage.CreateNew(str(self.root/'scene.usda'))
        UsdGeom.Xform.Define(self.stage,'/World')
        UsdGeom.Cube.Define(self.stage,'/World/Cube')
        self.stage.GetRootLayer().Save()
        self.source=(self.root/'scene.usda').read_bytes()
        self.timeline=Timeline(); self.events=[]
        self.service=Service(lambda:self.stage,lambda:self.timeline,self.root,lambda k,d:self.events.append((k,d)))
    def tearDown(self):
        self.service.close(); self.service=None; self.stage=None; self.temp.cleanup()
    def args(self):
        ident=self.service.identity()
        return {'stageId':ident['stageId'],'expectedRevision':ident['revision']}
    def preview(self,ops): return self.service.preview({**self.args(),'operations':ops})
    def apply(self,ops):
        p=self.preview(ops)
        return self.service.apply({**self.args(),'previewId':p['previewId']})
    def transform(self,x=2): return [{'op':'transform','primPath':'/World/Cube',**TRS,'translation':[x,0,0]}]
    def test_preview_does_not_mutate_live(self):
        before=self.stage.GetSessionLayer().ExportToString(); ident=self.args()
        self.preview(self.transform())
        self.assertEqual(self.stage.GetSessionLayer().ExportToString(),before)
        self.assertEqual(self.args(),ident)
        self.assertEqual((self.root/'scene.usda').read_bytes(),self.source)
    def test_apply_undo(self):
        self.apply(self.transform())
        prim=self.stage.GetPrimAtPath('/World/Cube')
        self.assertEqual(list(prim.GetAttribute('xformOp:translate:omnistream').Get()),[2,0,0])
        self.service.undo(self.args())
        self.assertFalse(prim.GetAttribute('xformOp:translate:omnistream'))
        self.assertEqual((self.root/'scene.usda').read_bytes(),self.source)
    def test_animation_and_metadata_undo(self):
        original=self.stage.GetTimeCodesPerSecond()
        self.apply([{'op':'playback_range','startSeconds':0,'endSeconds':2,'framesPerSecond':30},
                    {'op':'animate_transform','primPath':'/World/Cube','keys':[{'timeSeconds':0,**TRS},{'timeSeconds':2,**TRS,'translation':[6,0,0]}]}])
        attr=self.stage.GetPrimAtPath('/World/Cube').GetAttribute('xformOp:translate:omnistream')
        self.assertEqual(attr.GetNumTimeSamples(),2)
        self.assertEqual(list(attr.Get(Usd.TimeCode(30))),[3,0,0])
        self.service.undo(self.args())
        self.assertEqual(self.stage.GetTimeCodesPerSecond(),original)
    def test_stale_revision_rejected(self):
        p=self.preview(self.transform()); args=self.args()
        self.stage.DefinePrim('/World/External')
        with self.assertRaisesRegex(ValueError,'revision_conflict'): self.service.apply({**args,'previewId':p['previewId']})
    def test_animation_seconds_survive_cadence_changes_and_export(self):
        animation={'op':'animate_transform','primPath':'/World/Cube','keys':[{'timeSeconds':0,**TRS},{'timeSeconds':2,**TRS,'translation':[6,0,0]}]}
        self.apply([animation])
        self.apply([{'op':'playback_range','startSeconds':0,'endSeconds':2,'framesPerSecond':60}])
        attr=self.stage.GetPrimAtPath('/World/Cube').GetAttribute('xformOp:translate:omnistream')
        self.assertEqual(attr.GetTimeSamples(),[0,120])
        self.assertEqual(list(attr.Get(Usd.TimeCode(60))),[3,0,0])
        self.apply([animation])
        self.assertEqual(attr.GetTimeSamples(),[0,120])
        self.assertEqual(list(attr.Get(Usd.TimeCode(60))),[3,0,0])
        self.service.export({**self.args(),'relativePath':'animation.usda','confirm':True})
        exported=Usd.Stage.Open(str(self.root/'animation.usda'))
        exported_attr=exported.GetPrimAtPath('/World/Cube').GetAttribute('xformOp:translate:omnistream')
        rate=exported.GetTimeCodesPerSecond()
        self.assertEqual(exported_attr.GetTimeSamples(),[0,2*rate])
        self.assertEqual(list(exported_attr.Get(Usd.TimeCode(rate))),[3,0,0])
        self.assertEqual(exported.GetEndTimeCode()/rate,2)
        self.assertEqual((self.root/'scene.usda').read_bytes(),self.source)
    def test_animation_before_playback_range_keeps_seconds(self):
        self.apply([{'op':'animate_transform','primPath':'/World/Cube','keys':[{'timeSeconds':0,**TRS},{'timeSeconds':2,**TRS,'translation':[6,0,0]}]},
                    {'op':'playback_range','startSeconds':0,'endSeconds':2,'framesPerSecond':30}])
        attr=self.stage.GetPrimAtPath('/World/Cube').GetAttribute('xformOp:translate:omnistream')
        self.assertEqual(attr.GetTimeSamples(),[0,60])
        self.assertEqual(list(attr.Get(Usd.TimeCode(30))),[3,0,0])
    def test_export_new_file_only(self):
        self.apply(self.transform())
        self.service.export({**self.args(),'relativePath':'patch.usda','confirm':True})
        self.assertTrue((self.root/'patch.usda').exists())
        with self.assertRaises(FileExistsError): self.service.export({**self.args(),'relativePath':'patch.usda','confirm':True})
        with self.assertRaises(ValueError): self.service.export({**self.args(),'relativePath':'../bad.usda','confirm':True})
    def test_physics_requires_stopped(self):
        self.timeline.pause()
        with self.assertRaisesRegex(RuntimeError,'stop_required'): self.preview([{'op':'rigid_body','primPath':'/World/Cube','mass':1,'kinematic':False,'collider':True}])
    def test_physics_capability_not_fabricated(self):
        with self.assertRaisesRegex(RuntimeError,'physics_unavailable'): self.service.run({**self.args(),'mode':'physics'})
    def test_transaction_rolls_back(self):
        p=self.preview(self.transform()); before=self.stage.GetSessionLayer().ExportToString()
        with patch.object(self.service,'_sync_playback_metadata',side_effect=RuntimeError('injected')):
            with self.assertRaisesRegex(RuntimeError,'injected'): self.service.apply({**self.args(),'previewId':p['previewId']})
        self.assertEqual(self.stage.GetSessionLayer().ExportToString(),before)
        self.assertFalse(self.service.identity()['hasSessionEdits'])
    def test_watch_and_wall_limit(self):
        self.apply(self.transform())
        self.service.watch({**self.args(),'properties':[{'primPath':'/World/Cube','attribute':'xformOp:translate:omnistream'}]})
        self.service.run({**self.args(),'mode':'animation','wallTimeLimitSeconds':1})
        self.assertEqual(self.service.sample()['watches'][0]['value'],[2,0,0])
        self.service._run['deadline']=0
        self.assertFalse(self.service.sample()['playing'])
    def test_dynamic_animation_rejected(self):
        self.apply([{'op':'rigid_body','primPath':'/World/Cube','mass':1,'kinematic':False,'collider':True}])
        with self.assertRaises(ValueError): self.preview([{'op':'animate_transform','primPath':'/World/Cube','keys':[{'timeSeconds':0,**TRS},{'timeSeconds':1,**TRS}]}])

    def test_false_collider_actually_disables_existing_collision(self):
        self.apply([{'op':'rigid_body','primPath':'/World/Cube','mass':1,'kinematic':False,'collider':True}])
        prim=self.stage.GetPrimAtPath('/World/Cube')
        self.assertTrue(UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get())
        self.apply([{'op':'rigid_body','primPath':'/World/Cube','mass':2,'kinematic':True,'collider':False}])
        self.assertFalse(UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get())
    def test_simple_transform_capture_is_from_actual_usd(self):
        self.apply(self.transform())
        actual=self.service.inspect_prim({**self.args(),'primPath':'/World/Cube'})
        self.assertEqual(actual['editableTrs']['translation'],[2,0,0])
    def test_nonstandard_transform_is_not_invented_as_trs(self):
        prim=self.stage.GetPrimAtPath('/World/Cube')
        x=UsdGeom.Xformable(prim)
        x.ClearXformOpOrder()
        x.AddRotateYOp().Set(17)
        self.assertIsNone(self.service.inspect_prim({**self.args(),'primPath':'/World/Cube'})['editableTrs'])
    def test_scan_limit_is_not_a_missing_scene_diagnosis(self):
        self.apply([{'op':'rigid_body','primPath':'/World/Cube','mass':1,'kinematic':False,'collider':True}])
        diagnostic=self.service.diagnose({**self.args(),'maxPrims':1})
        self.assertTrue(diagnostic['scanCapped'])
        self.assertNotIn('missing_physics_scene',[i['code'] for i in diagnostic['issues']])
        self.assertIn('scan_incomplete',[i['code'] for i in diagnostic['issues']])
    def test_capped_scan_blocks_automatic_execution(self):
        with patch.object(self.service,'diagnose',return_value={'scanCapped':True}):
            with self.assertRaisesRegex(ValueError,'diagnostic_incomplete'):
                self.service.run({**self.args(),'mode':'animation'})

if __name__=='__main__': unittest.main(verbosity=2)
