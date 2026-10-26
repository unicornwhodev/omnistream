"""Negative native-renderer control: no fire source, no production evidence.

Run via the bounded Kit launcher with an explicit private probeContext. This
isolates renderer initialization from Flow scene population and evolution.
"""
import asyncio,json,sys,time,traceback
from pathlib import Path
import carb.settings
import omni.kit.app

sys.path.insert(0,str(Path(__file__).resolve().parent))
from restore_scene import atomic_json,sha256
from native_capture import wait_for_png


async def probe():
    import omni.usd
    import omni.timeline
    from pxr import Gf,Sdf,UsdGeom,UsdLux
    settings=carb.settings.get_settings()
    context=json.loads(Path(settings.get('/exts/omnistream.local/probeContext')).read_text())
    out=Path(context['output']);out.mkdir(parents=True,exist_ok=False)
    report={'schema':'omnistream.renderer-only-control.v1','completed':False,
            'production_evidence':False,'fire_or_smoke_validation':False,'flow_prims':0}
    product=annotator=viewport=None
    settings.set('/rtx/flow/enabled',False)
    settings.set('/rtx/flow/compositeEnabled',False)
    settings.set('/rtx/flow/pathTracingEnabled',False)
    try:
        usd=omni.usd.get_context()
        if 'rtx' not in usd.get_attached_hydra_engine_names():omni.usd.create_hydra_engine('rtx',usd)
        await usd.new_stage_async()
        stage=usd.get_stage()
        UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z);UsdGeom.SetStageMetersPerUnit(stage,1)
        floor=UsdGeom.Cube.Define(stage,'/World/Floor')
        floor.CreateSizeAttr(1);floor.CreateDisplayColorAttr([Gf.Vec3f(.25,.3,.24)])
        x=UsdGeom.Xformable(floor);x.AddTranslateOp().Set(Gf.Vec3d(0,0,-1));x.AddScaleOp().Set(Gf.Vec3f(1400,1400,2))
        light=UsdLux.DistantLight.Define(stage,'/World/Sun');light.CreateIntensityAttr(2500)
        UsdGeom.Xformable(light).AddRotateXYZOp().Set(Gf.Vec3f(-35,-20,0))
        camera=UsdGeom.Camera.Define(stage,'/World/Camera')
        camera.CreateFocalLengthAttr(35);camera.CreateHorizontalApertureAttr(36)
        camera.CreateClippingRangeAttr(Gf.Vec2f(.1,2000))
        UsdGeom.Xformable(camera).AddTransformOp().Set(Gf.Matrix4d().SetLookAt(
            Gf.Vec3d(20,-100,30),Gf.Vec3d(0,0,7),Gf.Vec3d(0,0,1)).GetInverse())
        report['settings']={k:settings.get(k) for k in ('/rtx/rendermode','/rtx/flow/enabled',
            '/rtx/flow/pathTracingEnabled','/persistent/rtx/modes/pt/enabled',
            '/persistent/rtx/modes/rt2/enabled','/app/vulkan')}
        if report['settings']['/rtx/rendermode']!='RaytracedLighting':raise RuntimeError('Control requires classic RTX')
        if any(report['settings'][k] for k in ('/rtx/flow/enabled','/persistent/rtx/modes/pt/enabled','/persistent/rtx/modes/rt2/enabled')):
            raise RuntimeError('Unexpected enabled component in renderer-only control')
        omni.timeline.get_timeline_interface().pause()
        capture_backend=context.get('capture_backend','replicator')
        report['capture_backend']=capture_backend
        atomic_json(out/'progress.json',{'phase':'First native renderer-only frame'})
        start=time.perf_counter()
        p=out/'negative-control.png'
        if capture_backend=='native_viewport':
            from omni.kit.viewport.utility import create_viewport_window,capture_viewport_to_file
            viewport=create_viewport_window('Renderer negative control',width=320,height=180,
                camera_path=Sdf.Path('/World/Camera'))
            viewport.viewport_api.set_texture_resolution((320,180))
            capture=capture_viewport_to_file(viewport.viewport_api,str(p))
            await capture.wait_for_result()
            report['png_verification']=await wait_for_png(p,(320,180))
        elif capture_backend=='replicator':
            import omni.replicator.core as rep
            import numpy as np
            from PIL import Image
            rep.orchestrator.set_capture_on_play(False)
            product=rep.create.render_product('/World/Camera',(320,180),force_new=True)
            annotator=rep.AnnotatorRegistry.get_annotator('rgb');annotator.attach(product)
            await rep.orchestrator.step_async(delta_time=0.0,rt_subframes=1)
            data=np.asarray(annotator.get_data())
            if data.dtype!=np.uint8 or data.shape[:2]!=(180,320):raise RuntimeError('Native RGB missing')
            Image.fromarray(data).save(p)
            with Image.open(p) as image:image.load()
        else:raise ValueError('Unknown negative-control capture backend')
        report['initialization_and_render_wall_s']=time.perf_counter()-start
        report['settings_after_capture']={key:settings.get(key) for key in report['settings']}
        if report['settings_after_capture']!=report['settings']:
            raise RuntimeError('Renderer policy changed during first-frame initialization')
        report['image']={'file':p.name,'sha256':sha256(p),'bytes':p.stat().st_size,'resolution_px':[320,180]}
        report['completed']=True
    except Exception:
        report['error']=traceback.format_exc();raise
    finally:
        if annotator and product:annotator.detach(product)
        if product:product.hydra_texture.set_updates_enabled(False);product.destroy()
        if viewport:
            viewport.viewport_api.updates_enabled=False
            viewport.destroy()
        atomic_json(out/'receipt.json',report)


async def run():
    try:await probe();code=0
    except Exception:traceback.print_exc();code=1
    omni.kit.app.get_app().post_quit(code)

_task=asyncio.ensure_future(run())
