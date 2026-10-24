"""Actual RTX qualification fixture; never presented as the Justin/fire scene."""
from pathlib import Path
import json,os,sys,time,asyncio,traceback,copy,gc,argparse,hashlib
parser=argparse.ArgumentParser(description='Native geometric fixture qualification, never Justin/fire acceptance')
parser.add_argument('--output',required=True)
args=parser.parse_args()
if os.name!='posix' or not Path('/content').is_dir():raise RuntimeError('Keep Kit qualification on Colab')
if os.environ.get('OMNI_KIT_ACCEPT_EULA')!='YES':raise RuntimeError('Use an already accepted NVIDIA agreement; this script does not accept terms')
SOURCE=Path(__file__).resolve().parents[1]
W=Path(args.output).resolve()
if W.exists():raise RuntimeError('Use a new output directory; performance trials must not resume old images')
W.mkdir(parents=True);OUT=W/'native';OUT.mkdir()
source_hashes={str(p.relative_to(SOURCE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((SOURCE/'src').rglob('*.py'))}
source_hashes['examples/reference_50_cameras.json']=hashlib.sha256((SOURCE/'examples/reference_50_cameras.json').read_bytes()).hexdigest()

def status(phase,**data):
 (W/'native-state.json').write_text(json.dumps({'phase':phase,'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),**data},indent=2));print(phase,data,flush=True)
assert os.name=='posix' and W.is_dir()
from isaacsim import SimulationApp
status('starting_kit_fixture')
app=SimulationApp({'headless':True,'renderer':'RayTracedLighting','width':1280,'height':720,'anti_aliasing':3,'disable_viewport_updates':True})
import numpy as np
from PIL import Image
from pxr import Usd,UsdGeom,UsdLux,Gf
import omni.usd,omni.kit.app
from fireviewer_capture.models import SimulationState,FrontObservation,Provenance,Activity,simulated_us
from fireviewer_capture.config import validate_config
from fireviewer_capture.usd_cameras import create_configured_cameras
from fireviewer_capture.kit_replay import KitFixtureAdapter
from fireviewer_capture.omniverse_driver import OmniverseRenderDriver
from fireviewer_capture.replicator import ReplicatorCaptureManager
from fireviewer_capture.orchestrator import CapturePipeline
from fireviewer_capture.storage import CaptureStore,atomic_json
from fireviewer_capture.metrics import RunMetrics,ResourceSampler
from fireviewer_capture.benchmark import benchmark_in_kit,subset_config
from fireviewer_capture.qualification import compare_repeated_view,resource_stability
from fireviewer_capture.cli import verify_output
from datetime import timedelta

def configuration(groups=10,duration=20,cap=5):
 c=json.loads((SOURCE/'examples/reference_50_cameras.json').read_text())
 c=subset_config(c,groups);c['scenario_id']='qualification-fixture';c['scene_revision']='qualification-fixture-v1'
 start=__import__('datetime').datetime.fromisoformat(c['period']['start']);c['period']['end_exclusive']=(start+timedelta(seconds=duration)).isoformat()
 c['activity'].update(enter_hold_sim_s=0,exit_hold_sim_s=0,poll_interval_sim_s=3600)
 c['render'].update(max_active_products=cap,max_cached_products=5,writer_timeout_wall_s=20)
 return validate_config(c)

def front(i=0,ident=None,activity=Activity.ACTIVE_RAPID,smoke=False):
 x=-8000+(i%5)*4000;y=-5000+(i//5)*10000;p={'type':'Point','coordinates':[x,y]}
 return FrontObservation(ident or f'fixture_front_{i:02d}',p,activity,Provenance('test_fixture','explicit renderer qualification log'),p if smoke else None,smoke,{})
def snapshot(seconds=0,fronts=(),revision='fixture-input'):
 return SimulationState(simulated_us(seconds),revision,tuple(fronts),{'provenance':'test_fixture; no real weather'}, {'fixture':True,'real_fire_solver':False,'external_smoke_solver':False})

async def case(config,states,path,driver=None):
 adapter=KitFixtureAdapter(states);driver=driver or OmniverseRenderDriver();store=CaptureStore(path);metrics=RunMetrics()
 manager=ReplicatorCaptureManager(config,driver,store,metrics);pipeline=CapturePipeline(config,adapter,manager,store,metrics)
 try:
  with ResourceSampler(metrics):result=await pipeline.run()
  verification=verify_output(path)
  for p in Path(path).glob('frames/*/*.png'):
   array=np.asarray(Image.open(p).convert('RGB'))
   assert array.shape==(720,1280,3) and float(array.std())>1,'Empty/malformed native RGB frame'
  return {'result':result,'verification':{k:v for k,v in verification.items() if k!='checkpoint'},'metrics':metrics.summary(),
          'unsolicited_writer_callbacks':driver.unsolicited_callbacks,'remaining_products':len(driver.products)}
 finally:atomic_json(Path(path)/'native-metrics.json',metrics.summary())

class NativeInterrupted(OmniverseRenderDriver):
 def __init__(self):super().__init__();self.calls=0
 async def trigger(self,handles,contexts,config):
  self.calls+=1
  if self.calls==2:raise RuntimeError('intentional native capture interruption')
  return await super().trigger(handles,contexts,config)

async def main():
 status('preparing_marked_fixture')
 await omni.usd.get_context().new_stage_async();stage=omni.usd.get_context().get_stage()
 UsdGeom.SetStageUpAxis(stage,'Z');UsdGeom.SetStageMetersPerUnit(stage,1);stage.SetTimeCodesPerSecond(1)
 world=UsdGeom.Xform.Define(stage,'/World');stage.SetDefaultPrim(world.GetPrim());world.GetPrim().SetCustomDataByKey('qualification:fixture',True)
 # Geometric markers, explicitly not a fire or a geographic landscape.
 for i in range(10):
  x=-8000+(i%5)*4000;y=-5000+(i//5)*10000
  cube=UsdGeom.Cube.Define(stage,f'/World/FixtureMarker_{i:02d}');cube.CreateSizeAttr(30)
  UsdGeom.Xformable(cube).AddTranslateOp().Set(Gf.Vec3d(x,y,500));cube.CreateDisplayColorAttr([(0.15+(i%3)*.2,.5,.25)])
 ground=UsdGeom.Cube.Define(stage,'/World/FixtureGround');ground.CreateSizeAttr(1)
 xf=UsdGeom.Xformable(ground);xf.AddTranslateOp().Set(Gf.Vec3d(0,0,400));xf.AddScaleOp().Set(Gf.Vec3f(21000,21000,1));ground.CreateDisplayColorAttr([(.12,.16,.2)])
 sky=UsdLux.DomeLight.Define(stage,'/World/FixtureSky');sky.CreateIntensityAttr(1000)
 sun=UsdLux.DistantLight.Define(stage,'/World/FixtureSun');sun.CreateIntensityAttr(2500);UsdGeom.Xformable(sun).AddRotateXYZOp().Set(Gf.Vec3f(315,20,0))
 create_configured_cameras(stage,configuration())
 stage.GetRootLayer().Export(str(OUT/'fixture.usda'))
 report={'schema':'fireviewer.native-qualification.v1','fixture_only':True,'real_justin_scene':False,'production_fire_solver':False,
         'source_sha256':source_hashes,'results':{},'final_operational_acceptance':False}
 status('benchmark_1_2_5_10_groups')
 states=[snapshot(0,[front(i) for i in range(10)])]
 trials=await benchmark_in_kit(configuration(),states,OUT/'benchmark',KitFixtureAdapter,OmniverseRenderDriver,uniform_interval_s=10)
 for trial in trials:
  n=trial['groups_configured'];policy=trial['policy'];path=OUT/'benchmark'/f'{n:02d}-groups-{policy}'
  verified=verify_output(path);assert verified['images_verified']==n*5*(2 if policy=='uniform' else 1)
  for p in path.glob('frames/*/*.png'):
   a=np.asarray(Image.open(p));assert a.shape[:2]==(720,1280) and float(a.std())>1
 report['results']['benchmark']=trials
 status('negative_and_short_smoke_events')
 c=configuration(2,20);c['activity']['enter_hold_sim_s']=30
 result=await case(c,[snapshot(),snapshot(10,[front(activity=Activity.INACTIVE,smoke=True)],'smoke-on'),snapshot(11,[],'smoke-off')],OUT/'smoke-events')
 times={r['sim_time_us'] for r in [json.loads(p.read_text()) for p in (OUT/'smoke-events/groups').glob('*.json')]}
 assert times=={0,10_000_000,11_000_000};report['results']['short_smoke_and_negative']=result
 status('native_interruption_and_recovery')
 c=configuration(1,1,2);path=OUT/'recovery'
 try:await case(c,[snapshot()],path,NativeInterrupted())
 except RuntimeError as e:assert str(e)=='intentional native capture interruption'
 else:raise AssertionError('Interruption was not exercised')
 assert len(list(path.glob('frames/*/*.png')))==2
 victim=next(path.glob('frames/*/*.png'));victim.write_bytes(b'incomplete qualification file')
 recovered=await case(c,[snapshot()],path);assert recovered['metrics']['counts']['images_reused_verified']==1 and recovered['metrics']['counts']['images_written_new']==4
 report['results']['interruption_resume']=recovered
 status('repeated_camera_cycles')
 samples=[];memory_cases=[]
 for cycle in range(12):
  result=await case(configuration(1,1),[snapshot()],OUT/'cycles'/f'{cycle:02d}');memory_cases.append(result)
  gc.collect()
  for _ in range(4):await omni.kit.app.get_app().next_update_async()
  metrics=RunMetrics();sampler=ResourceSampler(metrics);sampler.sample();samples.append({'cycle':cycle,**metrics.samples[-1]})
 stability=resource_stability(samples,3,32*1024**2,8*1024**2)
 report['results']['memory']={'samples':samples,'stability':stability,'limits_declared_before_run':True}
 report['results']['repeated_camera_cycles']=memory_cases
 status('repeated_view_ghosting_comparison')
 # Each cycle renders A then four distinct fixed cameras. Cycle 1 repeats A
 # after another view; cycle 0 supplies an independently warmed A reference.
 def a_metadata(cycle):
  for p in (OUT/'cycles'/f'{cycle:02d}').glob('frames/*/*.json'):
   if json.loads(p.read_text())['camera']['id']=='zone_01_cam_01':return p
  raise AssertionError('Camera A native output missing')
 ghost=compare_repeated_view(a_metadata(0),a_metadata(1),2,12);report['results']['static_fixture_ghosting_numeric']=ghost
 assert all(r['remaining_products']==0 and r['unsolicited_writer_callbacks']==0 for r in memory_cases)
 atomic_json(W/'native-result.json',report)
 status('native_fixture_matrix_completed',memory_pass=stability['passed'],static_fixture_ghosting_numeric_pass=ghost['passed'],
        actual_justin_scene_validated=False,real_fire_adapter='missing',gpu_profiler_time_measured=False,final_operational_acceptance=False)
 return report

task=asyncio.ensure_future(main())
try:
 while not task.done():app.update()
 task.result()
except Exception as e:status('failed',error=str(e)[:1800]);traceback.print_exc();raise
finally:app.close()
