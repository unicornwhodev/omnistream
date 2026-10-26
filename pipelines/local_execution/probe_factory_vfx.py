"""Native RTX Minimal optical probe of an unchanged factory Flow recipe.

Run via Kit --exec. Paths come from /exts/omnistream.local/probeContext.
This is a laboratory visibility probe, not the geographic simulation and not a
physics calibration. It deliberately reports field-freeze verification pending.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

import carb.settings
import omni.kit.app

PIPELINES = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINES/'event_capture/src'))
sys.path.insert(0, str(PIPELINES/'factory_vfx'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from restore_scene import atomic_json, sha256
from render_profile import load_render_profile
from render_policy import enforce_policy, assert_policy
from flow_diagnostics import require_native_progress


async def probe():
    import omni.usd
    import omni.timeline
    import omni.replicator.core as rep
    import numpy as np
    from PIL import Image
    from pxr import Gf, Usd, UsdGeom, UsdLux, UsdPhysics
    from profiles import apply_response_profile
    from fireviewer_capture.usd_cameras import create_configured_cameras
    from fireviewer_capture.omniverse_driver import OmniverseRenderDriver

    settings = carb.settings.get_settings()
    context = json.loads(Path(settings.get('/exts/omnistream.local/probeContext')).read_text())
    # An explicit diagnostic option, disabled by default. This controls Flow
    # volume inclusion, not the renderer mode: Minimal remains mandatory and
    # the PathTracing, RT and RT2 modes remain disabled in both policies.
    flow_volume_gate = bool(context.get('flow_volume_gate', False))
    def enforce_native_policy():
        return enforce_policy(settings, flow_volume_gate=flow_volume_gate)
    def assert_native_policy():
        return assert_policy(settings, flow_volume_gate=flow_volume_gate)
    profile_name, profile = load_render_profile(context.get('render_profile'))
    resolution = tuple(profile['capture_resolution_px'])
    source = Path(context['recipe_stage']).resolve(strict=True)
    metadata = json.loads(source.with_name('recipe.json').read_text())
    original_hash = sha256(source)
    if original_hash != metadata['stage_sha256']:
        raise RuntimeError('Factory USD differs from its recorded source digest')
    out = Path(context['output']).resolve()
    out.mkdir(parents=True, exist_ok=False)
    started_probe = time.perf_counter()

    def progress(phase, **values):
        record = {'phase': phase, 'wall_s': time.perf_counter()-started_probe, **values}
        atomic_json(out/'progress.json', record)
        with (out/'phases.jsonl').open('a', encoding='utf-8') as journal:
            journal.write(json.dumps(record)+'\n')
        print('NATIVE_PROBE_PHASE '+json.dumps(record), flush=True)

    report = {'schema':'omnistream.native-factory-optical-probe.v1','completed':False,
              'accepted_for_production':False,
              'recipe_id':metadata['id'],'source_sha256':original_hash,
              'production_fire_simulation':False,'physical_fire_calibrated':False,
              'render_profile':profile_name,'render_profile_settings':profile,
              'all_producer_freeze_verified':False,'captures':[],'timings':{}}
    driver = warmup = preparation_rgb = diagnostic_viewport = None
    timeline = omni.timeline.get_timeline_interface()
    try:
        usd_context = omni.usd.get_context()
        # Apply allocation limits before engine attachment and stage loading.
        settings.set('/rtx/flow/maxBlocks',int(context.get('max_flow_blocks',1024)))
        settings.set('/rtx/flow/pathTracingEnabled',False)
        progress('Prepare factory source before native population')
        # Native Flow retains some emitter/grid initialization. Prepare the
        # session opinions before the live engine first sees this stage.
        stage = Usd.Stage.Open(str(source))
        if UsdGeom.GetStageMetersPerUnit(stage) != 1 or UsdGeom.GetStageUpAxis(stage) != 'Z':
            raise RuntimeError('Factory source must use metres and Z-up')
        stage.SetEditTarget(stage.GetSessionLayer())
        effect = str(stage.GetDefaultPrim().GetPath())
        report['response_profile'] = apply_response_profile(stage,effect,
                                            wind_m_s=context.get('wind_m_s',[4,1,0]))
        simulations = [p for p in stage.Traverse() if p.GetTypeName()=='FlowSimulate']
        if len(simulations)!=1:
            raise RuntimeError('This optical probe requires one explicit Flow simulator')
        flow = simulations[0]
        fields = out/'native-fields'
        if context.get('measure_fields'):
            fields.mkdir()
            nano = stage.GetPrimAtPath(str(flow.GetPath())+'/nanoVdbExport')
            for key,value in {'enabled':False,'readbackEnabled':False,
                'readbackDirectory':str(fields),'readbackOpenVDB':False,
                'readbackClearOnStart':False,'readbackClearOnStop':False,
                'smokeEnabled':True,'temperatureEnabled':True,
                'fuelEnabled':False,'velocityEnabled':False,'burnEnabled':False}.items():
                attr = nano.GetAttribute(key)
                if not attr:raise RuntimeError('Missing native export setting '+key)
                attr.Set(value)
        flow.GetAttribute('densityCellSize').Set(float(context.get('voxel_size_m',0.3)))
        settings.set('/rtx/flow/maxBlocks',int(context.get('max_flow_blocks',1024)))
        for key,value in {'/rtx/rendermode':'MinimalRendering','/rtx/minimal/mode':3,
                          '/rtx/flow/enabled':True,'/rtx/flow/compositeEnabled':True,
                          '/rtx/flow/pathTracingEnabled':False}.items():
            settings.set(key,value)
        report['renderer_settings'] = {k:settings.get(k) for k in (
            '/rtx/rendermode','/rtx/minimal/mode','/rtx/flow/enabled',
            '/rtx/flow/compositeEnabled','/rtx/flow/maxBlocks',
            '/app/useFabricSceneDelegate')}
        manager = omni.kit.app.get_app().get_extension_manager()
        report['extensions'] = {m:Path(manager.get_extension_path_by_module(m)).name
                                 for m in ('omni.flowusd','omni.replicator.core')}
        ground = UsdGeom.Cube.Define(stage,'/World/Probe/Ground')
        ground.CreateSizeAttr(1)
        ground.CreateDisplayColorAttr([Gf.Vec3f(.25,.3,.24)])
        transform = UsdGeom.Xformable(ground)
        transform.AddTranslateOp().Set(Gf.Vec3d(0,0,-1))
        transform.AddScaleOp().Set(Gf.Vec3f(1400,1400,2))
        UsdPhysics.CollisionAPI.Apply(ground.GetPrim())
        physics = UsdPhysics.Scene.Define(stage,'/World/Probe/Physics')
        physics.CreateGravityDirectionAttr(Gf.Vec3f(0,0,-1));physics.CreateGravityMagnitudeAttr(9.81)
        light = UsdLux.DistantLight.Define(stage,'/World/Probe/Sun')
        light.CreateIntensityAttr(2500)
        UsdGeom.Xformable(light).AddRotateXYZOp().Set(Gf.Vec3f(-35,-20,0))
        cameras = context['cameras']
        config = {'execution_environment':'local','seed':20261017,'cameras':cameras,
                  'render':{'resolution_px':list(resolution),
                            'max_active_products':profile['max_active_products'],
                            'rt_subframes':profile['rt_subframes'],
                            'writer_timeout_wall_s':30,'initialization_timeout_wall_s':60,
                            'render_timeout_wall_s':60}}
        create_configured_cameras(stage,config)
        derived = stage.Flatten()
        layer_data = dict(derived.customLayerData)
        layer_data['renderSettings'] = {
            'rtx:rendermode':'MinimalRendering', 'rtx:minimal:mode':3,
            'rtx:flow:enabled':True, 'rtx:flow:pathTracingEnabled':False}
        derived.customLayerData = layer_data
        prepared = out/'probe.usda'
        if not derived.Export(str(prepared)):
            raise RuntimeError('Could not save the derived laboratory stage')
        report['derived_stage_sha256'] = sha256(prepared)
        stage = None
        before_engines = list(usd_context.get_attached_hydra_engine_names())
        report['hydra_engines_before'] = before_engines
        progress('Attach native RTX engine')
        if 'rtx' not in before_engines:
            report['created_hydra_engine_uid'] = int(omni.usd.create_hydra_engine('rtx',usd_context))
        report['policy_after_attachment'] = enforce_native_policy()
        report['hydra_engines_after'] = list(usd_context.get_attached_hydra_engine_names())
        if 'rtx' not in report['hydra_engines_after']:
            raise RuntimeError('Native RTX Hydra engine did not attach to the probe context')
        progress('Open prepared factory stage', hydra_engines=report['hydra_engines_after'])
        opened = await usd_context.open_stage_async(str(prepared))
        if isinstance(opened,tuple) and not opened[0]:
            raise RuntimeError('Prepared factory stage did not open')
        stage = usd_context.get_stage()
        flow = next(p for p in stage.Traverse() if p.GetTypeName()=='FlowSimulate')
        stage.SetEditTarget(stage.GetSessionLayer())
        # These are the shipped Flow telemetry nodes, not a synthetic front API.
        # Their native clock and allocated blocks distinguish timeline motion
        # from actual work flushed through the GPU solver.
        import omni.graph.core as og
        from omni.flowusd import _flowusd
        flow_interface = _flowusd.acquire_flowusd_interface()
        graph, _, _, _ = og.Controller.edit(
            {'graph_path':'/World/Probe/FlowTelemetry','evaluator_name':'execution'},
            {og.Controller.Keys.CREATE_NODES:[
                ('Time','omni.flowusd.FlowSimTime'),
                ('Blocks','omni.flowusd.FlowBlocks')]})
        def native_flow_state():
            og.Controller.evaluate_sync(graph)
            root = '/World/Probe/FlowTelemetry/'
            result = {name:og.Controller.get(og.Controller.attribute(root+attribute))
                    for name,attribute in {
                        'last_absolute_sim_time_s':'Time.outputs:lastAbsoluteSimTime',
                        'last_block_fault_sim_time_s':'Time.outputs:lastFaultAbsoluteSimTime',
                        'active_blocks':'Blocks.outputs:activeBlockCount',
                        'max_blocks':'Blocks.outputs:maxBlockCount'}.items()}
            result['interface_active_blocks'] = flow_interface.get_active_block_count()
            result['interface_max_blocks'] = flow_interface.get_max_block_count()
            return result
        # Engine/stage initialization can restore renderer defaults even when
        # the app and derived layer request a smaller mode. Enforce and read
        # back the policy after native population, before submitting work.
        report['policy_after_stage_load'] = enforce_native_policy()
        settings.set('/rtx/flow/maxBlocks',int(context.get('max_flow_blocks',1024)))
        atomic_json(out/'native-policy.json', {
            'after_attachment':report['policy_after_attachment'],
            'after_stage_load':report['policy_after_stage_load']})
        progress('Factory stage opened', renderer_mode=settings.get('/rtx/rendermode'),
                 flow_path_tracing=settings.get('/rtx/flow/pathTracingEnabled'))
        rep.orchestrator.set_capture_on_play(False)
        rep.set_global_seed(config['seed'])
        warmup = rep.create.render_product(cameras[0]['usd_path'],(320,180),force_new=True)
        # An explicit RGB annotator supplies the render graph dependency. A
        # product with no consumer can leave the first orchestrator step waiting.
        preparation_rgb = rep.AnnotatorRegistry.get_annotator('rgb')
        preparation_rgb.attach(warmup)
        progress('Warmup product created')
        flow.GetAttribute('forceDisableCoreSimulation').Set(True)
        flow.GetAttribute('forceDisableEmitters').Set(True)
        progress('Initialize native RGB graph with frozen Flow')
        await rep.orchestrator.step_async(delta_time=0.0,rt_subframes=1)
        assert_native_policy()
        initial = np.asarray(preparation_rgb.get_data())
        if initial.dtype != np.uint8 or initial.shape[:2] != (180,320):
            raise RuntimeError('Native preparation RGB was not delivered')
        progress('Native RGB graph initialized', shape=list(initial.shape))
        report['flow_telemetry_initial'] = native_flow_state()
        timeline.set_current_time(0)
        timeline.set_end_time(float(context['duration_sim_s'])+1)
        timeline.set_looping(False)
        flow.GetAttribute('forceDisableCoreSimulation').Set(False)
        flow.GetAttribute('forceDisableEmitters').Set(False)
        flow.GetAttribute('forceSimulate').Set(bool(context.get('explicit_flow_step',False)))
        timeline.play()
        started = time.perf_counter()
        steps = round(float(context['duration_sim_s'])*60)
        native_updates = context.get('advance_mode') == 'native_app_updates'
        if context.get('native_viewport_diagnostic'):
            if not native_updates:
                raise ValueError('Viewport diagnostic requires ordinary native app updates')
            from omni.kit.viewport.utility import create_viewport_window
            from pxr import Sdf
            warmup.hydra_texture.set_updates_enabled(False)
            diagnostic_viewport = create_viewport_window(
                'Flow diagnostic',width=320,height=180,
                camera_path=Sdf.Path(cameras[0]['usd_path']))
            if diagnostic_viewport is None:
                raise RuntimeError('Native diagnostic viewport was not created')
            diagnostic_viewport.viewport_api.set_texture_resolution((320,180))
            diagnostic_viewport.viewport_api.updates_enabled = True
            report['native_viewport_diagnostic'] = True
        if native_updates:
            rep.orchestrator.pause()
            warmup.hydra_texture.set_updates_enabled(diagnostic_viewport is None)
            timeline.play()
        for step in range(steps):
            if step == 0:
                progress('First native Flow step submitted')
            if native_updates:
                await omni.kit.app.get_app().next_update_async()
            else:
                await rep.orchestrator.step_async(delta_time=1/60,rt_subframes=1,pause_timeline=False)
            assert_native_policy()
            if step == 0 or (step+1)%60==0:
                progress('Flow evolution', steps_completed=step+1,
                         steps_total=steps,timeline_s=timeline.get_current_time(),
                         native_flow=native_flow_state())
        report['timings']['simulation_wall_s'] = time.perf_counter()-started
        report['flow_telemetry_after_evolution'] = native_flow_state()
        report['advance_mode'] = context.get('advance_mode','replicator_fixed_step')
        # Preserve the native preparation frame for diagnosing whether an
        # effect disappears when a capture product is created or destroyed.
        if diagnostic_viewport is None:
            Image.fromarray(np.asarray(preparation_rgb.get_data())).save(out/'preparation-native.png')
        report['solver_progress'] = require_native_progress(
            report['flow_telemetry_initial'],report['flow_telemetry_after_evolution'],
            int(context.get('max_flow_blocks',1024)))
        timeline.pause()
        flow.GetAttribute('forceDisableCoreSimulation').Set(True)
        flow.GetAttribute('forceDisableEmitters').Set(True)
        if context.get('measure_fields'):
            from field_metrics import read_volume
            scenario_clock = timeline.get_current_time()
            nano = stage.GetPrimAtPath(str(flow.GetPath())+'/nanoVdbExport')
            nano.GetAttribute('enabled').Set(True)
            nano.GetAttribute('readbackEnabled').Set(True)
            flow.GetAttribute('forceSimulate').Set(True)
            flow.GetAttribute('simulateWhenPaused').Set(True)
            timeline.play()
            progress('Read frozen native Flow fields')
            for _ in range(16):
                if diagnostic_viewport:
                    await omni.kit.app.get_app().next_update_async()
                else:
                    await rep.orchestrator.step_async(delta_time=1/60,rt_subframes=1,pause_timeline=False)
                if sum(p.stat().st_size for p in fields.glob('*.nvdb')) > 128*1024**2:
                    raise RuntimeError('Native field diagnostic spool budget exceeded')
            timeline.pause()
            timeline.set_current_time(scenario_clock)
            timeline.commit()
            nano.GetAttribute('readbackEnabled').Set(False)
            report['native_fields'] = {}
            for field in ('Smoke','Temperature'):
                candidates = sorted((p for p in fields.glob('*.nvdb') if field in p.name),
                                    key=lambda p:p.stat().st_mtime_ns)
                if not candidates:
                    raise RuntimeError('Native Flow did not export '+field)
                report['native_fields'][field] = read_volume(candidates[-1],max_allocated_voxels=4_194_304)
            atomic_json(out/'field-measurements.json',report['native_fields'])
        flow.GetAttribute('forceSimulate').Set(False)
        flow.GetAttribute('simulateWhenPaused').Set(False)
        if diagnostic_viewport:
            diagnostic_viewport.viewport_api.updates_enabled = False
            warmup.hydra_texture.set_updates_enabled(True)
        for _ in range(16):
            await rep.orchestrator.step_async(delta_time=0.0,rt_subframes=1)
        report['simulated_time_s'] = timeline.get_current_time()
        report['freeze_commands'] = {'timeline_paused':not timeline.is_playing(),
            'forceDisableCoreSimulation':flow.GetAttribute('forceDisableCoreSimulation').Get(),
            'forceDisableEmitters':flow.GetAttribute('forceDisableEmitters').Get(),
            'grid_hash_verification':'pending; this optical probe does not certify frozen multi-camera data'}
        preparation_rgb.detach(warmup);preparation_rgb=None
        # Keep the paused source product alive until capture is complete. Flow
        # resources can belong to the renderer; destruction is not a freeze.
        warmup.hydra_texture.set_updates_enabled(False)
        driver = OmniverseRenderDriver()
        await driver.initialize(config)
        for camera in cameras:
            atomic_json(out/'progress.json',{'phase':'Create manual capture product','camera':camera['id']})
            before = timeline.get_current_time()
            handle = await driver.create_product(camera,config)
            await driver.prepare_batch({camera['id']:handle},{camera['id']:{}},config)
            driver.set_updates(handle,True)
            atomic_json(out/'progress.json',{'phase':'Native RGB writer','camera':camera['id'],
                        'resolution_px':list(resolution)})
            result = await driver.trigger({camera['id']:handle},{},config)
            array = np.asarray(result.frames[camera['id']])
            image_path = out/(camera['id']+'.png')
            started = time.perf_counter()
            Image.fromarray(array).save(image_path)
            with Image.open(image_path) as image:
                image.load()
                if image.size!=resolution:raise RuntimeError('Native image dimensions differ')
            if abs(timeline.get_current_time()-before)>1e-8:
                raise RuntimeError('Zero-delta capture changed the timeline')
            report['captures'].append({'file':image_path.name,'bytes':image_path.stat().st_size,
                'sha256':sha256(image_path),'resolution_px':list(resolution),
                'camera':driver.camera_metadata(camera,config),'render_wall_s':result.render_wall_s,
                'gpu_render_execution_s':result.gpu_render_execution_s,
                'write_and_verification_wall_s':time.perf_counter()-started,
                'flame_visible':None,'smoke_visible':None,'visual_review':'pending'})
            await driver.destroy_product(handle)
        report['completed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        timeline.pause()
        if preparation_rgb and warmup:
            preparation_rgb.detach(warmup)
        if warmup:
            warmup.hydra_texture.set_updates_enabled(False);warmup.destroy()
        if driver:await driver.close()
        if diagnostic_viewport:
            diagnostic_viewport.viewport_api.updates_enabled = False
            diagnostic_viewport.destroy()
        report['source_unchanged'] = sha256(source)==original_hash
        if not report['source_unchanged']:
            report['completed'] = False
            report['error'] = 'Factory source changed during qualification'
        atomic_json(out/'receipt.json',report)
        if not report['source_unchanged']:
            raise RuntimeError(report['error'])


async def run_and_exit():
    try:
        await probe()
        code=0
    except Exception:
        traceback.print_exc();code=1
    omni.kit.app.get_app().post_quit(code)


_probe_task = asyncio.ensure_future(run_and_exit())
