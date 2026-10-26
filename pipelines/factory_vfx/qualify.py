"""Run bounded, native factory Flow response tests inside approved Isaac Sim.

No geographic pilot, propagation engine or stream is involved. Sources stay
immutable; output is a separate laboratory qualification, never an automatic
activation of a factory recipe or a claim of empirical fire calibration.
"""
from pathlib import Path
import argparse
import asyncio
import gc
import hashlib
import json
import os
import time
import traceback


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.partial')
    with temporary.open('w') as file:
        json.dump(value, file, indent=2)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True)
    parser.add_argument('--config', default=str(Path(__file__).with_name('cases.json')))
    parser.add_argument('--only', nargs='+')
    args = parser.parse_args()
    context = json.loads(Path(args.context).read_text())
    root = Path(context['factory_root']).resolve(strict=True)
    work = Path(context['qualification_root']).resolve(strict=True)
    config = json.loads(Path(args.config).read_text())
    if os.name != 'posix' or not str(work).startswith('/content/'):
        raise RuntimeError('Run this qualification on the authorized Colab runtime')
    if json.loads((root / 'reports/omniverse_eula_approval.json').read_text()).get('accepted') is not True:
        raise RuntimeError('Existing NVIDIA approval required')
    selected = [c for c in config['cases'] if not args.only or c['id'] in args.only]
    if not selected or (args.only and set(args.only) != {c['id'] for c in selected}):
        raise ValueError('Select actual configured cases')
    code_hashes = {p.name: sha(p) for p in Path(__file__).parent.iterdir() if p.suffix in ('.py', '.kit')}
    fingerprint = hashlib.sha256(json.dumps({'config': config, 'code': code_hashes}, sort_keys=True).encode()).hexdigest()
    out = work / 'response-tests' / fingerprint[:16]
    out.mkdir(parents=True, exist_ok=True)
    report = {'schema': 'fireviewer.factory-flow-response.v1', 'run_id': fingerprint[:16],
              'configuration': config, 'code_sha256': code_hashes, 'cases': [],
              'native_runtime': True, 'physical_fire_calibrated': False,
              'geographic_pilot_loaded': False, 'completed': False,
              'shutdown_mode': 'SimulationApp supported standalone fast_shutdown',
              'graceful_plugin_unload_qualified': False}

    def status(event, **extra):
        atomic_json(out / 'status.json', {'event': event, 'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **extra})
        print('FACTORY_RESPONSE', event, json.dumps(extra), flush=True)

    status('starting_isaac', cases=[c['id'] for c in selected])
    # This is a separate Python process launched by the notebook, not its
    # IPython kernel. Inherited notebook markers select inappropriate Isaac
    # startup/shutdown integration for this standalone process.
    for key in ('JPY_PARENT_PID', 'ISAAC_JUPYTER_PYTHON_PACKAGE', 'ISAAC_JUPYTER_KERNEL'):
        os.environ.pop(key, None)
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    from isaacsim import SimulationApp
    isaac_root = Path(os.environ['ISAAC_PATH'])
    extension_args = []
    for folder in ('exts', 'extscache', 'extsDeprecated'):
        extension_args.extend(['--ext-folder', str(isaac_root / folder)])
    app = SimulationApp({'headless': True, 'renderer': 'RayTracedLighting',
                         'width': 320, 'height': 180, 'disable_viewport_updates': True,
                         'anti_aliasing': 2,
                         'fast_shutdown': True, 'extra_args': extension_args},
                         experience=str(Path(__file__).with_name('factory.kit')))
    exit_error = None
    def native_body():
        import carb.settings
        import omni.kit.app
        import omni.timeline
        import omni.usd
        import omni.replicator.core as rep
        import numpy as np
        import psutil
        import pynvml
        from PIL import Image
        from pxr import Gf, Usd, UsdGeom, UsdLux, UsdPhysics
        from field_metrics import read_volume
        from profiles import apply_response_profile

        manager = omni.kit.app.get_app().get_extension_manager()
        if manager.set_extension_enabled_immediate('omni.flowusd', True) is False:
            raise RuntimeError('Installed Flow extension did not enable')
        for _ in range(12):
            app.update()
        report['flow_extension'] = Path(manager.get_extension_path_by_module('omni.flowusd')).name
        report['isaac_version'] = '5.1.0.0'
        settings = carb.settings.get_settings()
        for key in ('enabled', 'rayTracedReflectionsEnabled', 'rayTracedTranslucencyEnabled'):
            settings.set('/rtx/flow/' + key, True)
        settings.set('/rtx/flow/maxBlocks', 2048)
        rep.orchestrator.set_capture_on_play(False)
        rep.set_global_seed(config['seed'])
        pynvml.nvmlInit()
        gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
        process = psutil.Process()
        inventory = json.loads((work / 'source-inventory.json').read_text())
        timeline = omni.timeline.get_timeline_interface()
        resources = []

        def resource_sample():
            vram = pynvml.nvmlDeviceGetMemoryInfo(gpu)
            memory = psutil.virtual_memory()
            row = {'wall_s': time.perf_counter(), 'rss_bytes': process.memory_info().rss,
                   'available_ram_bytes': memory.available, 'vram_used_bytes': vram.used,
                   'vram_total_bytes': vram.total}
            resources.append(row)
            if vram.used / vram.total > config['max_vram_fraction']:
                raise RuntimeError('Configured VRAM safety ceiling reached')
            if memory.available < config['min_available_ram_gib'] * 1024 ** 3:
                raise RuntimeError('Configured available RAM floor reached')
            return row

        def run_async(coroutine):
            task = asyncio.ensure_future(coroutine)
            while not task.done():
                app.update()
            return task.result()

        class ManualWriter(rep.Writer):
            def __init__(self):
                self.annotators = [rep.AnnotatorRegistry.get_annotator('rgb')]
                self.data_structure = 'legacy'
                self.armed = False
                self.image = None
                self.unsolicited = 0

            def write_metadata(self, *unused, **kwargs):
                pass

            def write(self, data):
                if not self.armed:
                    self.unsolicited += 1
                    return
                self.armed = False
                keys = [k for k in data if k == 'rgb' or k.startswith('rgb-')]
                if len(keys) != 1:
                    raise RuntimeError('Ambiguous native RGB writer result')
                self.image = np.asarray(data[keys[0]])[:, :, :3].copy()

        for case in selected:
            case_out = out / case['id']
            case_out.mkdir(exist_ok=True)
            receipt = case_out / 'result.json'
            if receipt.is_file():
                old = json.loads(receipt.read_text())
                if old.get('completed') and old.get('run_fingerprint') == fingerprint:
                    for capture in old.get('captures', []):
                        if sha(case_out / capture['file']) != capture['sha256']:
                            raise RuntimeError('Completed checkpoint image changed')
                    report['cases'].append(old)
                    status('verified_checkpoint_reused', case=case['id'])
                    continue
                raise RuntimeError('Incomplete case exists; preserve it and use a fresh run revision')
            recipe = next(r for r in inventory if r['family'] == case['family']
                          and r['preset'] == case.get('preset', 'soutenu')
                          and r['parameters']['dimension_profile'] == case.get('dimension_profile', 'local')
                          and (not case.get('recipe_id') or r['id'] == case['recipe_id']))
            source = root / 'fx/flow/recipes' / recipe['id'] / 'effect.usda'
            if sha(source) != recipe['stage_sha256']:
                raise RuntimeError('Actual factory source changed after inventory')
            result = {'case': case, 'recipe_id': recipe['id'], 'source_sha256': sha(source),
                      'run_fingerprint': fingerprint, 'completed': False,
                      'physical_fire_calibrated': False, 'factory_parameters': recipe['parameters'],
                      'measurements': [], 'captures': []}
            status('opening_factory_recipe', case=case['id'], recipe=recipe['id'])
            product = None
            writer = None
            preparation_rgb = None
            stage = None
            try:
                timeline.stop()
                timeline.commit()
                # Author the derived USD before loading it into the live Flow
                # engine. Changing an emitter type in a loaded stage retained
                # the original native emitter shape in the initial test.
                stage = Usd.Stage.Open(str(source))
                if UsdGeom.GetStageMetersPerUnit(stage) != 1 or UsdGeom.GetStageUpAxis(stage) != 'Z':
                    raise RuntimeError('Metres and Z-up required')
                stage.SetEditTarget(stage.GetSessionLayer())
                sims = [p for p in stage.Traverse() if p.GetTypeName() == 'FlowSimulate']
                if len(sims) != 1:
                    raise RuntimeError('One native Flow simulator required per laboratory case')
                sim = sims[0]
                result['profile'] = apply_response_profile(stage, '/FVFX', wind_m_s=case['wind_m_s'],
                    hot=case['hot'], emission_end_s=case.get('emission_end_s'),
                    source_up_m_s=case.get('source_up_m_s', 0))
                solver_rate = case.get('solver_steps_per_second', config['solver_steps_per_second'])
                sim.GetAttribute('stepsPerSecond').Set(float(solver_rate))
                if 'voxel_size_m' in case:
                    sim.GetAttribute('densityCellSize').Set(float(case['voxel_size_m']))
                    result['derived_voxel_size_m'] = float(case['voxel_size_m'])
                physics = UsdPhysics.Scene.Define(stage, '/QA/Physics')
                physics.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1))
                physics.CreateGravityMagnitudeAttr(9.81)
                floor = UsdGeom.Mesh.Define(stage, '/QA/ReferenceFloor')
                floor_extent = case.get('floor_half_extent_m', 60)
                floor.CreatePointsAttr([Gf.Vec3f(x, y, z) for z in [-2, 0]
                    for y in [-floor_extent, floor_extent] for x in [-floor_extent, floor_extent]])
                floor.CreateFaceVertexCountsAttr([4] * 6)
                floor.CreateFaceVertexIndicesAttr([4, 5, 7, 6, 0, 2, 3, 1, 0, 1, 5, 4, 2, 6, 7, 3, 0, 4, 6, 2, 1, 3, 7, 5])
                floor.CreateSubdivisionSchemeAttr('none')
                floor.CreateDisplayColorAttr([Gf.Vec3f(.18, .2, .22)])
                for index, height in enumerate(case.get('scale_markers_m', [])):
                    marker = UsdGeom.Cylinder.Define(stage, '/QA/Scale/Height_' + str(index))
                    marker.CreateHeightAttr(float(height))
                    marker.CreateRadiusAttr(max(.04, float(height) * .012))
                    marker.CreateAxisAttr('Z')
                    marker.CreateDisplayColorAttr([Gf.Vec3f(.9, .75, .05)])
                    UsdGeom.Xformable(marker).AddTranslateOp().Set(Gf.Vec3d(
                        case.get('marker_x_m', -8) - index * max(1, float(height) * .1),
                        case.get('marker_y_m', -3), float(height) / 2))
                    marker.GetPrim().SetCustomDataByKey('qualification:height_m', float(height))
                UsdPhysics.CollisionAPI.Apply(floor.GetPrim())
                UsdPhysics.MeshCollisionAPI.Apply(floor.GetPrim()).CreateApproximationAttr('none')
                result['laboratory_ground'] = {'type': 'static closed USD/PhysX triangle mesh', 'top_z_m': 0,
                    'gravity_m_s2': 9.81, 'flow_collision_enabled': sim.GetAttribute('physicsCollisionEnabled').Get(),
                    'flow_physx_convex_hull_callback': False,
                    'ground_eraser_disabled': True}
                nano = stage.GetPrimAtPath(str(sim.GetPath()) + '/nanoVdbExport')
                cache_folder = case_out / 'native-fields'
                cache_folder.mkdir(exist_ok=False)
                for key, value in {'enabled': False, 'smokeEnabled': True, 'temperatureEnabled': True,
                    'fuelEnabled': False, 'burnEnabled': False, 'velocityEnabled': False,
                    'readbackOpenVDB': False, 'readbackEnabled': False,
                    'readbackDirectory': str(cache_folder),
                    'readbackClearOnStart': False, 'readbackClearOnStop': False}.items():
                    attr = nano.GetAttribute(key)
                    if not attr:
                        raise RuntimeError('Missing native NanoVDB attribute: ' + key)
                    attr.Set(value)
                camera = UsdGeom.Camera.Define(stage, '/QA/Camera')
                camera.CreateFocalLengthAttr(35)
                camera.CreateHorizontalApertureAttr(36)
                camera.CreateVerticalApertureAttr(36 * 9 / 16)
                camera.CreateClippingRangeAttr(Gf.Vec2f(.05, case.get('camera_far_clip_m', 300)))
                eye, target = ([14, -40, 18], [0, 0, 12]) if case['family'] == 'feu_cime' else ([10, -30, 13], [0, 0, 7])
                eye, target = case.get('camera_eye_m', eye), case.get('camera_target_m', target)
                UsdGeom.Xformable(camera).AddTransformOp().Set(Gf.Matrix4d().SetLookAt(
                    Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1)).GetInverse())
                UsdLux.DomeLight.Define(stage, '/QA/Sky').CreateIntensityAttr(800)
                result['camera'] = {'usd_path': '/QA/Camera', 'position_m': eye, 'look_at_m': target,
                    'focal_length_mm': 35, 'horizontal_aperture_mm': 36, 'vertical_aperture_mm': 20.25}
                result['inspection_cameras'] = [result['camera']]
                if 'far_camera_eye_m' in case:
                    far = UsdGeom.Camera.Define(stage, '/QA/FarCamera')
                    far.CreateFocalLengthAttr(35)
                    far.CreateHorizontalApertureAttr(36)
                    far.CreateVerticalApertureAttr(20.25)
                    far.CreateClippingRangeAttr(Gf.Vec2f(.05, case.get('camera_far_clip_m', 300)))
                    far_eye, far_target = case['far_camera_eye_m'], case['far_camera_target_m']
                    UsdGeom.Xformable(far).AddTransformOp().Set(Gf.Matrix4d().SetLookAt(
                        Gf.Vec3d(*far_eye), Gf.Vec3d(*far_target), Gf.Vec3d(0, 0, 1)).GetInverse())
                    result['inspection_cameras'].append({**result['camera'], 'usd_path': '/QA/FarCamera',
                        'position_m': far_eye, 'look_at_m': far_target})
                derived = case_out / 'laboratory-input.usda'
                stage.Flatten().Export(str(derived))
                result['laboratory_input_sha256'] = sha(derived)
                if not omni.usd.get_context().open_stage(str(derived)):
                    raise RuntimeError('Derived factory laboratory stage did not open')
                for _ in range(12):
                    app.update()
                stage = omni.usd.get_context().get_stage()
                stage.SetEditTarget(stage.GetSessionLayer())
                sims = [p for p in stage.Traverse() if p.GetTypeName() == 'FlowSimulate']
                sim = sims[0]
                nano = stage.GetPrimAtPath(str(sim.GetPath()) + '/nanoVdbExport')
                # A cheap product drives actual Flow/PhysX during preparation.
                # Final 4K rendering is performed only after freezing both engines.
                product = rep.create.render_product('/QA/Camera', (320, 180), force_new=True)
                preparation_rgb = rep.AnnotatorRegistry.get_annotator('rgb')
                preparation_rgb.attach(product)
                writer = ManualWriter()
                writer.attach(product, trigger=None)
                sim.GetAttribute('forceDisableCoreSimulation').Set(True)
                sim.GetAttribute('forceDisableEmitters').Set(True)
                rep.orchestrator.step(delta_time=0.0, rt_subframes=1)
                timeline.set_current_time(0)
                sim.GetAttribute('forceDisableCoreSimulation').Set(False)
                sim.GetAttribute('forceDisableEmitters').Set(False)
                timeline.play()
                dt = case.get('update_interval_s', config['update_interval_s'])
                rep.settings.set_physx_timestep(dt)
                if dt * solver_rate > 8.000001:
                    raise ValueError('Update interval exceeds the solver step budget')
                samples = iter(case.get('sample_times_s', config['sample_times_s']))
                next_sample = next(samples, None)
                simulation_wall = 0
                steps = 0
                duration = case.get('simulated_duration_s', config['simulated_duration_s'])
                while timeline.get_current_time() < duration - 1e-6:
                    if next_sample is not None and timeline.get_current_time() >= next_sample - 2 * dt - 1e-6:
                        nano.GetAttribute('enabled').Set(True)
                        nano.GetAttribute('readbackEnabled').Set(True)
                    before = time.perf_counter()
                    rep.orchestrator.step(delta_time=dt, rt_subframes=1, pause_timeline=False)
                    simulation_wall += time.perf_counter() - before
                    steps += 1
                    actual = timeline.get_current_time()
                    if steps > duration / dt + 5:
                        raise RuntimeError('The actual simulation clock failed to advance as configured')
                    if next_sample is not None and actual >= next_sample - 1e-6:
                        status('measuring_native_fields', case=case['id'], simulated_s=actual)
                        timeline.pause()
                        sim.GetAttribute('forceDisableCoreSimulation').Set(True)
                        sim.GetAttribute('forceDisableEmitters').Set(True)
                        # Execute export nodes while the field evolution and
                        # emitters are disabled. Pausing alone skips readback.
                        sim.GetAttribute('forceSimulate').Set(True)
                        sim.GetAttribute('simulateWhenPaused').Set(True)
                        before_freeze_files = set(cache_folder.glob('*.nvdb'))
                        folder = cache_folder
                        # Stress the explicit Flow freeze with positive carrier
                        # clock ticks so export executes. All laboratory
                        # collision geometry is static. Restore the scenario
                        # clock before any accepted zero-delta image capture.
                        timeline.play()
                        # The asynchronous NanoVDB export may lag the last
                        # dynamic frame, especially with half-rate carrier
                        # ticks. Drain at least eight complete solver periods.
                        freeze_ticks = max(16, int(8 / (dt * solver_rate) + .999999))
                        for _ in range(freeze_ticks):
                            rep.orchestrator.step(delta_time=dt, rt_subframes=1, pause_timeline=False)
                        timeline.pause()
                        diagnostic_clock = timeline.get_current_time()
                        timeline.set_current_time(actual)
                        timeline.commit()
                        files = sorted(folder.glob('*.nvdb'), key=lambda p: p.stat().st_mtime_ns)
                        measurements = {}
                        for field in ('Smoke', 'Temperature'):
                            candidates = [p for p in files if field in p.name]
                            if not candidates:
                                raise RuntimeError('Native readback missing ' + field)
                            values = [read_volume(p, config['threshold_model_units']) for p in candidates[-2:]]
                            measurements[field.lower()] = dict(values[-1])
                            measurements[field.lower()]['relative_file'] = str(candidates[-1].relative_to(case_out))
                            # Header hashes can change with export frame counters.
                            # Compare every measured physical field statistic separately.
                            comparable = [dict(v) for v in values]
                            for v in comparable:
                                for key in ('file', 'sha256'):
                                    v.pop(key, None)
                            measurements[field.lower()]['frozen_export_statistics_identical'] = len(values) == 2 and comparable[0] == comparable[1]
                            measurements[field.lower()]['frozen_export_file_hashes'] = [v['sha256'] for v in values]
                        measurements['new_exports_during_freeze'] = len(set(folder.glob('*.nvdb')) - before_freeze_files)
                        measurements['freeze_diagnostic_carrier_clock_s'] = diagnostic_clock
                        measurements['scenario_clock_restored_s'] = timeline.get_current_time()
                        nano.GetAttribute('readbackEnabled').Set(False)
                        nano.GetAttribute('enabled').Set(False)
                        result['measurements'].append({'simulated_time_s': actual, 'fields': measurements})
                        atomic_json(case_out / 'progress.json', result)
                        resource_sample()
                        next_sample = next(samples, None)
                        if next_sample is not None:
                            sim.GetAttribute('forceSimulate').Set(False)
                            sim.GetAttribute('simulateWhenPaused').Set(False)
                            sim.GetAttribute('forceDisableCoreSimulation').Set(False)
                            sim.GetAttribute('forceDisableEmitters').Set(False)
                            timeline.play()
                result['simulation_wall_s'] = simulation_wall
                result['simulation_rendering_resolution_px'] = [320, 180]
                result['solver_steps_per_second'] = solver_rate
                result['simulation_update_steps'] = steps
                result['simulated_time_s'] = timeline.get_current_time()
                timeline.pause()
                timeline.commit()
                nano.GetAttribute('readbackEnabled').Set(False)
                sim.GetAttribute('forceDisableCoreSimulation').Set(True)
                sim.GetAttribute('forceDisableEmitters').Set(True)
                preparation_rgb.detach()
                preparation_rgb = None
                # Preserve the same render engine and live Flow grid. Destroying
                # the preparation product before creating the final product
                # produced an empty image even though native grids existed.
                product.hydra_texture.width = config['resolution_px'][0]
                product.hydra_texture.height = config['resolution_px'][1]
                status('rendering_native_4k', case=case['id'])
                clock = timeline.get_current_time()
                for view_index, view in enumerate(result['inspection_cameras']):
                    product.hydra_texture.set_updates_enabled(True)
                    camera_binding = stage.GetPrimAtPath(str(product.path)).GetRelationship('camera')
                    if not camera_binding or not camera_binding.SetTargets([view['usd_path']]):
                        raise RuntimeError('The actual Render Product camera binding could not be set')
                    writer.image = None
                    started = time.perf_counter()
                    run_async(rep.orchestrator.step_async(delta_time=0.0, rt_subframes=1))
                    if writer.unsolicited:
                        raise RuntimeError('Unscheduled writer callback during priming')
                    writer.armed = True
                    writer.schedule_write()
                    run_async(rep.orchestrator.step_async(delta_time=0.0, rt_subframes=4))
                    render_wall = time.perf_counter() - started
                    product.hydra_texture.set_updates_enabled(False)
                    if writer.unsolicited or writer.image is None:
                        raise RuntimeError('Explicit writer did not produce exactly the requested image')
                    result['capture_clock_check'] = {'before_s': clock, 'after_s': timeline.get_current_time()}
                    if abs(timeline.get_current_time() - clock) > 1e-9:
                        raise RuntimeError('Simulation time moved during frozen capture')
                    image = writer.image
                    if image.shape != (config['resolution_px'][1], config['resolution_px'][0], 3) or image.dtype != np.uint8:
                        raise RuntimeError('Native writer resolution/data mismatch')
                    path = case_out / ('native-4k.png' if view_index == 0 else 'native-4k-far.png')
                    started = time.perf_counter()
                    with path.with_suffix('.partial').open('wb') as file:
                        Image.fromarray(image).save(file, format='PNG')
                        file.flush()
                        os.fsync(file.fileno())
                    path.with_suffix('.partial').replace(path)
                    with Image.open(path) as verified:
                        verified.load()
                        if not np.array_equal(np.asarray(verified), image):
                            raise RuntimeError('PNG readback differs from the native writer buffer')
                    result['captures'].append({'file': path.name, 'sha256': sha(path), 'resolution_px': config['resolution_px'],
                        'camera': view, 'simulated_time_s': clock, 'render_and_readback_wall_s': render_wall,
                        'png_write_and_verify_wall_s': time.perf_counter() - started,
                        'gpu_execution_s': None, 'gpu_timer_source': None, 'writer_trigger': 'explicit schedule_write',
                        'renderer': 'RTX RayTracedLighting', 'antialiasing_op': settings.get('/rtx/post/aa/op'),
                        'upscaling_requested': False,
                        'capture_step_delta_s': 0, 'unsolicited_callbacks': writer.unsolicited,
                        'warm_color_candidate_pixels_estimated': int(((image[:, :, 0].astype(float) > 80)
                            & (image[:, :, 0] > image[:, :, 1].astype(float) * 1.4)
                            & (image[:, :, 1] > image[:, :, 2].astype(float) * 1.15)).sum()),
                        'annotation_provenance': 'actual USD pose and Flow model state; no calibrated wildfire labels'})
                stage.Flatten().Export(str(case_out / 'laboratory-scene.usda'))
                result['source_unchanged'] = sha(source) == result['source_sha256']
                if not result['source_unchanged']:
                    raise RuntimeError('Factory source changed')
                result['resources'] = resource_sample()
                result['completed'] = True
                status('case_completed', case=case['id'], simulated_s=clock,
                       smoke_centroid_m=result['measurements'][-1]['fields']['smoke']['centroid_m'])
            except Exception as error:
                result['error'] = str(error)
                result['traceback'] = traceback.format_exc()
                status('case_failed', case=case['id'], error=str(error))
                raise
            finally:
                atomic_json(receipt, result)
                report['cases'].append(result)
                atomic_json(out / 'report.json', report)
                timeline.stop()
                if writer:
                    writer.armed = False
                    writer.image = None
                    writer.detach()
                if product:
                    if preparation_rgb:
                        preparation_rgb.detach()
                    product.hydra_texture.set_updates_enabled(False)
                    product.destroy()
                omni.usd.get_context().close_stage()
                stage = None
                gc.collect()
        report['resources'] = resources
        report['completed'] = all(r['completed'] for r in report['cases'])
        atomic_json(out / 'report.json', report)
        status('matrix_completed', completed_cases=len(report['cases']))
    try:
        native_body()
    except Exception as error:
        exit_error = RuntimeError(str(error))
        report['error'] = str(error)
        atomic_json(out / 'report.json', report)
        status('failed', error=str(error))
        traceback.print_exc()
    finally:
        # Release the native-body scope and collect its Python cycles while
        # Kit plugins are still alive. Earlier probes crashed in interpreter
        # garbage collection after teardown; exit status remains an acceptance
        # gate, never hidden by an immediate process exit.
        gc.collect()
        import omni.kit.app
        extension_manager = omni.kit.app.get_app().get_extension_manager()
        extension_manager.set_extension_enabled_immediate('omni.flowusd', False)
        for _ in range(5):
            app.update()
        del extension_manager
        gc.collect()
        # All writers, source hashes and case receipts were verified before
        # closing. Use Isaac 5.1's documented standalone default; graceful
        # plugin hot-unload remains a separately recorded failing lifecycle.
        # Do not substitute an immediate Python/OS exit for SimulationApp.
        app.close()
    if exit_error:
        raise exit_error


if __name__ == '__main__':
    main()
