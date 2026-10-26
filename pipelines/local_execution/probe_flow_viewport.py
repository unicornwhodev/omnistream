"""Bounded native Flow/PhysX viewport diagnostic for an existing factory recipe.

Run inside a compatible Kit via launch_flow_viewport.py. This is a laboratory
visibility/collision diagnostic, never a replacement for Replicator production.
The independent NanoVDB measurement pass must qualify the exported fields.
"""
import asyncio,json,sys,time,traceback
from pathlib import Path
import carb.settings,omni.kit.app

repo=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo/'pipelines/local_execution'))
sys.path.insert(0,str(repo/'pipelines/factory_vfx'))
from restore_scene import atomic_json,sha256
from render_policy import enforce_policy,assert_policy
from native_capture import wait_for_png


async def probe():
    import omni.usd,omni.timeline,omni.graph.core as og
    from pxr import Usd,Gf,Sdf,UsdGeom,UsdLux
    from omni.kit.viewport.utility import create_viewport_window,capture_viewport_to_file
    from omni.flowusd import _flowusd
    from profiles import apply_response_profile
    settings=carb.settings.get_settings()
    ctx=json.loads(Path(settings.get('/exts/omnistream.local/probeContext')).read_text())
    duration=float(ctx.get('duration_sim_s',2))
    if not 0<duration<=30:raise ValueError('Bounded diagnostic duration must be in 0..30 seconds')
    capture_resolution=tuple(ctx.get('capture_resolution_px',[320,180]))
    if capture_resolution not in ((320,180),(1280,720),(1920,1080)):raise ValueError('Unsupported bounded resolution')
    out=Path(ctx['output']);out.mkdir(exist_ok=False)
    report={'schema':'omnistream.flow-native-viewport-diagnostic.v1','completed':False,
            'accepted_for_production':False,'physical_fire_calibrated':False,
            'physics_collision_tested':False,'all_producer_freeze_verified':False,'captures':[]}
    report['requested_timeline_duration_s']=duration
    report['capture_resolution_px']=list(capture_resolution)
    report['native_clock_semantics']='absolute flushed-work timestamp; not scenario elapsed time'
    manager=omni.kit.app.get_app().get_extension_manager()
    report['extensions']={name:Path(manager.get_extension_path_by_module(name)).name
                          for name in ('omni.flowusd','omni.kit.viewport.utility')}
    report['kit_version']=omni.kit.app.get_app().get_build_version()
    collisions=ctx.get('physics_collision') is True
    viewport=flow=None
    timeline=omni.timeline.get_timeline_interface()
    policy={'renderer_mode':'realtime_classic','lightweight':True,'flow_volume_gate':False}
    def phase(name,**data):
        atomic_json(out/'progress.json',{'phase':name,**data})
        print('FLOW_VIEWPORT '+json.dumps({'phase':name,**data}),flush=True)
    try:
        source=Path(ctx['recipe_stage']);meta=json.loads(source.with_name('recipe.json').read_text())
        if sha256(source)!=meta['stage_sha256']:raise RuntimeError('Factory source digest mismatch')
        report['source_sha256']=meta['stage_sha256']
        settings.set('/rtx/flow/maxBlocks',512)
        settings.set('/exts/omni.flowusd/vdb_cache_size',134217728)
        stage=Usd.Stage.Open(str(source))
        if UsdGeom.GetStageMetersPerUnit(stage)!=1 or UsdGeom.GetStageUpAxis(stage)!='Z':
            raise RuntimeError('Unexpected factory stage units or axes')
        stage.SetEditTarget(stage.GetSessionLayer())
        report['response_profile']=apply_response_profile(stage,str(stage.GetDefaultPrim().GetPath()),
                                                         wind_m_s=ctx.get('wind_m_s',[4,1,0]))
        flows=[p for p in stage.Traverse() if p.GetTypeName()=='FlowSimulate']
        if len(flows)!=1:raise RuntimeError('One simulator required')
        flow=flows[0]
        if ctx.get('measure_fields'):
            fields=out/'native-fields';fields.mkdir()
            nano=stage.GetPrimAtPath(str(flow.GetPath())+'/nanoVdbExport')
            for key,value in {'enabled':False,'readbackEnabled':False,'readbackOpenVDB':False,
                'readbackDirectory':str(fields),'readbackClearOnStart':False,'readbackClearOnStop':False,
                'smokeEnabled':True,'temperatureEnabled':True,'fuelEnabled':False,'burnEnabled':False,
                'velocityEnabled':False}.items():nano.GetAttribute(key).Set(value)
        for key,value in {'densityCellSize':.6,'physicsCollisionEnabled':collisions,
                          'forceDisableCoreSimulation':True,'forceDisableEmitters':True,
                          'forceSimulate':False,'simulateWhenPaused':False}.items():flow.GetAttribute(key).Set(value)
        if collisions:
            from pxr import UsdPhysics
            physics=UsdPhysics.Scene.Define(stage,'/World/Physics')
            physics.CreateGravityDirectionAttr(Gf.Vec3f(0,0,-1));physics.CreateGravityMagnitudeAttr(9.81)
            floor=UsdGeom.Mesh.Define(stage,'/World/Floor')
            floor.CreatePointsAttr([Gf.Vec3f(x,y,z) for z in [-2,0] for y in [-700,700] for x in [-700,700]])
            floor.CreateFaceVertexCountsAttr([4]*6)
            floor.CreateFaceVertexIndicesAttr([4,5,7,6,0,2,3,1,0,1,5,4,2,6,7,3,0,4,6,2,1,3,7,5])
            floor.CreateSubdivisionSchemeAttr('none')
            UsdPhysics.CollisionAPI.Apply(floor.GetPrim())
            UsdPhysics.MeshCollisionAPI.Apply(floor.GetPrim()).CreateApproximationAttr('none')
        else:
            floor=UsdGeom.Cube.Define(stage,'/World/Floor');floor.CreateSizeAttr(1)
            x=UsdGeom.Xformable(floor);x.AddTranslateOp().Set(Gf.Vec3d(0,0,-1));x.AddScaleOp().Set(Gf.Vec3f(1400,1400,2))
        floor.CreateDisplayColorAttr([Gf.Vec3f(.25,.3,.24)])
        report['collision_configuration']={'enabled':collisions,'ground_eraser_enabled':False,
            'ground_geometry':'closed triangle mesh' if collisions else 'visual cube without collision',
            'physical_acceptance':'requires native field comparison'}
        light=UsdLux.DistantLight.Define(stage,'/World/Sun');light.CreateIntensityAttr(2500)
        UsdGeom.Xformable(light).AddRotateXYZOp().Set(Gf.Vec3f(-35,-20,0))
        cam=UsdGeom.Camera.Define(stage,'/World/Camera');cam.CreateFocalLengthAttr(35);cam.CreateHorizontalApertureAttr(36)
        cam.CreateClippingRangeAttr(Gf.Vec2f(.1,2000))
        UsdGeom.Xformable(cam).AddTransformOp().Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(20,-100,30),Gf.Vec3d(0,0,7),Gf.Vec3d(0,0,1)).GetInverse())
        layer=stage.Flatten();data=dict(layer.customLayerData)
        data['renderSettings']={'rtx:flow:enabled':True,'rtx:flow:compositeEnabled':True,'rtx:flow:pathTracingEnabled':False,
                               'rtx:rendermode':'RaytracedLighting'}
        layer.customLayerData=data;prepared=out/'derived.usda';layer.Export(str(prepared))
        report['derived_sha256']=sha256(prepared)
        if sha256(source)!=report['source_sha256']:raise RuntimeError('Factory source changed during preparation')
        enforce_policy(settings,**policy)
        context=omni.usd.get_context()
        if 'rtx' not in context.get_attached_hydra_engine_names():omni.usd.create_hydra_engine('rtx',context)
        phase('Open factory derivative')
        opened=await context.open_stage_async(str(prepared))
        if isinstance(opened,tuple) and not opened[0]:raise RuntimeError('Stage did not open')
        stage=context.get_stage();stage.SetEditTarget(stage.GetSessionLayer())
        flow=next(p for p in stage.Traverse() if p.GetTypeName()=='FlowSimulate')
        enforce_policy(settings,**policy)
        graph,_,_,_=og.Controller.edit({'graph_path':'/World/FlowTelemetry','evaluator_name':'execution'},
            {og.Controller.Keys.CREATE_NODES:[('Read','omni.graph.action.OnImpulseEvent'),('Time','omni.flowusd.FlowSimTime'),('Blocks','omni.flowusd.FlowBlocks')],
             og.Controller.Keys.SET_VALUES:[('Read.inputs:onlyPlayback',False)],
             og.Controller.Keys.CONNECT:[('Read.outputs:execOut','Time.inputs:execIn'),('Time.outputs:execOut','Blocks.inputs:execIn')]})
        interface=_flowusd.acquire_flowusd_interface()
        def read_state():
            og.Controller.set(og.Controller.attribute('/World/FlowTelemetry/Read.state:enableImpulse'),True)
            og.Controller.evaluate_sync(graph)
            return {'timeline_s':timeline.get_current_time(),
                'native_sim_time_s':og.Controller.get(og.Controller.attribute('/World/FlowTelemetry/Time.outputs:lastAbsoluteSimTime')),
                'native_fault_time_s':og.Controller.get(og.Controller.attribute('/World/FlowTelemetry/Time.outputs:lastFaultAbsoluteSimTime')),
                'active_blocks':int(interface.get_active_block_count()),'max_blocks':int(interface.get_max_block_count())}
        timeline.pause();viewport=create_viewport_window('Factory Flow diagnostic',width=320,height=180,camera_path=Sdf.Path('/World/Camera'))
        viewport.viewport_api.set_texture_resolution((320,180))
        phase('First native viewport frame, Flow frozen')
        p=out/'initial-negative.png'
        await capture_viewport_to_file(viewport.viewport_api,str(p)).wait_for_result()
        await wait_for_png(p,(320,180))
        await omni.kit.app.get_app().next_update_async()
        report['policy_after_initial_frame']=assert_policy(settings,**policy)
        report['initial_state']=read_state()
        # Tick the actual Kit timeline, checking its time at every completed
        # update. The realized duration is recorded, never inferred from count.
        timeline.set_current_time(0);timeline.set_end_time(duration);timeline.set_looping(False)
        flow.GetAttribute('forceDisableCoreSimulation').Set(False);flow.GetAttribute('forceDisableEmitters').Set(False)
        timeline.play();started=time.monotonic();iterations=0
        phase('Native Flow evolution',state=read_state())
        while timeline.get_current_time()<duration-1e-6 and iterations<int(duration*60)+1:
            await omni.kit.app.get_app().next_update_async();iterations+=1
            assert_policy(settings,**policy)
            if iterations%30==0:phase('Native Flow evolution',state=read_state(),updates=iterations)
            if time.monotonic()-started>120:raise RuntimeError('Flow evolution wall deadline')
        timeline.pause()
        flow.GetAttribute('forceDisableCoreSimulation').Set(True);flow.GetAttribute('forceDisableEmitters').Set(True)
        report['final_state']=read_state();phase('Capture frozen diagnostic state',state=report['final_state'])
        viewport.viewport_api.set_texture_resolution(capture_resolution)
        for _ in range(16):await omni.kit.app.get_app().next_update_async();assert_policy(settings,**policy)
        p=out/'native-flow-final.png'
        await capture_viewport_to_file(viewport.viewport_api,str(p)).wait_for_result()
        report['policy_after_capture']=assert_policy(settings,**policy)
        report['captures'].append(await wait_for_png(p,capture_resolution))
        if ctx.get('measure_fields'):
            nano=stage.GetPrimAtPath(str(flow.GetPath())+'/nanoVdbExport')
            nano.GetAttribute('enabled').Set(True);nano.GetAttribute('readbackEnabled').Set(True)
            flow.GetAttribute('forceSimulate').Set(True);flow.GetAttribute('simulateWhenPaused').Set(True)
            phase('Export frozen native smoke and temperature fields')
            scenario_clock=timeline.get_current_time()
            timeline.set_end_time(scenario_clock+1);timeline.play()
            for _ in range(16):
                await omni.kit.app.get_app().next_update_async()
                assert_policy(settings,**policy)
                if sum(p.stat().st_size for p in fields.glob('*.nvdb'))>128*1024**2:
                    raise RuntimeError('Native field spool exceeds 128 MiB')
                if all(len(list(fields.glob('Flow'+k+'*.nvdb')))>=2 for k in ('Smoke','Temperature')):
                    break
            nano.GetAttribute('readbackEnabled').Set(False)
            for _ in range(8):
                await omni.kit.app.get_app().next_update_async()
                assert_policy(settings,**policy)
            timeline.pause()
            report['field_export_carrier_time_s']=timeline.get_current_time()
            timeline.set_current_time(scenario_clock);timeline.commit()
            if sum(p.stat().st_size for p in fields.glob('*.nvdb'))>128*1024**2:
                raise RuntimeError('Native field spool exceeds 128 MiB after flush')
            report['native_field_files']=[{'file':p.name,'sha256':sha256(p),'bytes':p.stat().st_size}
                                           for p in sorted(fields.glob('*.nvdb'))]
            if not all(sum(k in f['file'] for f in report['native_field_files'])>=2 for k in ('Smoke','Temperature')):
                raise RuntimeError('Native field export incomplete')
            report['native_field_measurement_required']=True
        final=report['final_state'];initial=report['initial_state']
        if final['native_sim_time_s']<=initial['native_sim_time_s'] or not 0<final['active_blocks']<=512:
            raise RuntimeError('Actual Flow progress not confirmed')
        if final['native_fault_time_s']>initial['native_fault_time_s']:raise RuntimeError('Flow block pool exhausted')
        report['completed']=True
    except Exception:report['error']=traceback.format_exc();raise
    finally:
        timeline.pause()
        if flow:
            for k,v in {'forceDisableCoreSimulation':True,'forceDisableEmitters':True,'forceSimulate':False,'simulateWhenPaused':False}.items():flow.GetAttribute(k).Set(v)
            if ctx.get('measure_fields'):
                nano=flow.GetStage().GetPrimAtPath(str(flow.GetPath())+'/nanoVdbExport')
                nano.GetAttribute('readbackEnabled').Set(False)
                nano.GetAttribute('enabled').Set(False)
        if viewport:viewport.viewport_api.updates_enabled=False;viewport.destroy()
        atomic_json(out/'receipt.json',report)

async def run():
    try:await probe();code=0
    except Exception:traceback.print_exc();code=1
    omni.kit.app.get_app().post_quit(code)
_task=asyncio.ensure_future(run())
