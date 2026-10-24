"""Bounded native 4K throughput diagnostic in the existing sixteen-tile Kit.

No SimulationAdapter is fabricated. Flow disable flags and timeline invariance
are checked, but grid-state coherence and fire physics remain unqualified.
Images are renderer diagnostics, never accepted scientific dataset samples.
The main viewport camera never changes; its updates are restored on exit.
"""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time


async def run(stage, geographic, pilot_root):
    import omni.kit.app
    import omni.timeline
    import omni.usd
    import carb.settings
    from omni.kit.viewport.utility import get_active_viewport
    from pxr import Sdf, Usd, UsdGeom, UsdRender
    import numpy as np
    import psutil
    import pynvml
    from PIL import Image

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
    from fireviewer_capture.omniverse_driver import OmniverseRenderDriver
    from fireviewer_capture.metrics import RunMetrics, ResourceSampler

    root = Path(pilot_root).resolve(strict=True)
    if (geographic.manifest.get('qualification_scope') != 'pilot-l4-16tiles'
            or len(geographic.tiles) != 16
            or Path(stage.GetRootLayer().realPath).resolve() != root / 'pilot.usda'):
        raise ValueError('Benchmark is limited to the isolated sixteen-tile pilot')
    config_path = root / '4k-trial-v1/configuration.json'
    config = json.loads(config_path.read_text())
    if config['render']['resolution_px'] != [3840, 2160]:
        raise ValueError('This trial measures native 4K only')
    config['cameras'] = config['cameras'][:5]
    config['render'].update(max_active_products=1, max_cached_products=1)
    timeline = omni.timeline.get_timeline_interface()
    viewport = get_active_viewport()
    app = omni.kit.app.get_app()
    clock = timeline.get_current_time()
    if timeline.is_playing():
        raise ValueError('Pause the pilot before this renderer-only diagnostic')
    flow = [p for p in stage.Traverse() if p.GetTypeName() == 'FlowSimulate']
    original_camera = str(viewport.camera_path)
    original_updates = viewport.updates_enabled
    original_resolution = tuple(viewport.resolution)
    original_auto = timeline.is_auto_updating()
    original_suspend = geographic.suspend_dynamic_updates
    camera_fingerprint = {
        c['id']: str(UsdGeom.XformCache().GetLocalToWorldTransform(stage.GetPrimAtPath(c['usd_path'])))
        for c in config['cameras']}
    root_hash = hashlib.sha256((root / 'pilot.usda').read_bytes()).hexdigest()
    tag = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    out = root / '4k-render-throughput' / tag
    out.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'fireviewer.native-render-throughput.v1', 'scope': 'pilot-l4-16tiles',
              'completed': False, 'restored': False, 'phases': [], 'resolution_px': [3840, 2160],
              'simulation_time_s': clock, 'renderer_diagnostic_only': True,
              'scientific_acceptance': False, 'flow_grid_readback_qualified': False,
              'fire_adapter': 'missing', 'gpu_execution_time_s': None,
              'simulation_execution_time_s': None, 'main_viewport_camera_modified': False,
              'config_sha256': hashlib.sha256(config_path.read_bytes()).hexdigest()}
    report['aa_mode_before'] = carb.settings.get_settings().get('/rtx/post/aa/op')
    report['preview_resolution_during_capture'] = [640, 360]
    metrics = RunMetrics()
    pynvml.nvmlInit()
    device = pynvml.nvmlDeviceGetHandleByIndex(0)

    def persist(name='progress.json'):
        target = out / name
        partial = target.with_suffix('.part')
        partial.write_text(json.dumps(report, indent=2))
        partial.replace(target)

    def guard():
        if timeline.is_playing() or abs(timeline.get_current_time() - clock) > 1e-9:
            raise RuntimeError('The diagnostic clock changed')
        if str(viewport.camera_path) != original_camera:
            raise RuntimeError('The main viewport camera changed')
        for prim in flow:
            if not all(prim.GetAttribute(n).Get() is True for n in ('forceDisableCoreSimulation', 'forceDisableEmitters')):
                raise RuntimeError('An external Flow producer is not explicitly disabled')
        for c in config['cameras']:
            actual = str(UsdGeom.XformCache().GetLocalToWorldTransform(stage.GetPrimAtPath(c['usd_path'])))
            if actual != camera_fingerprint[c['id']]:
                raise RuntimeError('A fixed camera pose changed')
        memory = pynvml.nvmlDeviceGetMemoryInfo(device)
        if memory.used / memory.total > .90 or psutil.virtual_memory().available < 5 * 1024**3:
            raise RuntimeError('Diagnostic exceeded its reserved memory budget')

    class CompletePilotResidency:
        async def prepare(self, current_stage, contexts, current_config):
            if current_stage != stage or not geographic.status.get('completeAssetResidency'):
                raise RuntimeError('Declared pilot assets are incomplete')
            for path in geographic.asset_tiles | geographic.prototype_paths:
                if not stage.GetPrimAtPath(path).IsLoaded():
                    raise RuntimeError('A declared pilot payload is unloaded')
            for ident in geographic.tiles:
                if not stage.GetPrimAtPath('/World/Terrain/' + ident).IsLoaded():
                    raise RuntimeError('A pilot terrain tile is unloaded')
            return {'visible_assets_complete': True, 'coverage_is_limited_to_pilot': True}

    def write_frame(array, path):
        started = time.perf_counter()
        if array.dtype != np.uint8 or array.shape != (2160, 3840, 3):
            raise RuntimeError('Native RGB is not 3840 x 2160')
        part = path.with_suffix('.part')
        Image.fromarray(array).save(part, format='PNG', compress_level=3)
        with part.open('rb') as stream:
            os.fsync(stream.fileno())
        part.replace(path)
        with Image.open(path) as image:
            image.verify()
        data = path.read_bytes()
        return {'file': path.name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                'encode_write_verify_wall_s': time.perf_counter() - started}

    driver = OmniverseRenderDriver(residency_provider=CompletePilotResidency())
    sampler = ResourceSampler(metrics)
    try:
        guard()
        geographic.suspend_dynamic_updates = True
        timeline.set_auto_update(False)
        timeline.commit_silently()
        viewport.resolution = (640, 360)
        for _ in range(4):
            await app.next_update_async()
        viewport.updates_enabled = False
        if viewport.updates_enabled:
            raise RuntimeError('Main viewport refresh was not disabled')
        idle_started = time.perf_counter()
        for _ in range(12):
            await app.next_update_async()
        report['viewport_disabled_update_wall_mean_s'] = (time.perf_counter() - idle_started) / 12
        await driver.initialize(config)
        with sampler:
            shared_handle = None
            for mode, subframes in [('retarget', 1), ('retarget', 4), ('retarget', 16), ('retarget-repeat', 16)]:
                label = f'{mode}-{subframes}-subframes'
                phase = {'label': label, 'rt_subframes': subframes, 'frames': []}
                report['phases'].append(phase)
                c = copy.deepcopy(config)
                c['render']['rt_subframes'] = subframes
                handle = shared_handle
                phase_started = time.perf_counter()
                try:
                    for camera in c['cameras']:
                        guard()
                        report['current_camera'] = camera['id']
                        persist()
                        started = time.perf_counter()
                        if mode == 'rebuild' or handle is None:
                            handle = await driver.create_product(camera, c)
                            binding = 'created'
                        else:
                            if handle.enabled or handle.writer.pending is not None:
                                raise RuntimeError('Cannot rebind an active or armed product')
                            # USD camera relationship is the render-product binding;
                            # fixed camera prims and their exposures are untouched.
                            with Usd.EditContext(stage, stage.GetSessionLayer()):
                                product = UsdRender.Product.Get(stage, str(handle.product.path))
                                product.GetCameraRel().SetTargets([Sdf.Path(camera['usd_path'])])
                            handle.camera_id = camera['id']
                            handle.primed = False
                            binding = 'retargeted'
                        product = UsdRender.Product.Get(stage, str(handle.product.path))
                        if [str(p) for p in product.GetCameraRel().GetTargets()] != [camera['usd_path']]:
                            raise RuntimeError('Render product did not bind the requested camera')
                        binding_wall = time.perf_counter() - started
                        started = time.perf_counter()
                        geographic.focus(tuple(camera['position_m']))
                        await driver.prepare_batch({camera['id']: handle}, {}, c)
                        prepare_wall = time.perf_counter() - started
                        driver.set_updates(handle, True)
                        batch = await driver.trigger({camera['id']: handle}, {}, c)
                        guard()
                        written = await asyncio.to_thread(write_frame, batch.frames[camera['id']],
                                                        out / (label + '-' + camera['id'] + '.png'))
                        phase['frames'].append({**written, 'camera_id': camera['id'],
                            'camera_usd_path': camera['usd_path'], 'binding': binding,
                            'binding_wall_s': binding_wall, 'prepare_wall_s': prepare_wall,
                            'render_and_readback_wall_s': batch.render_wall_s,
                            'gpu_execution_time_s': batch.gpu_render_execution_s,
                            'camera': driver.camera_metadata(camera, c), 'simulation_time_s': timeline.get_current_time()})
                        if any(p.enabled for p in driver.products):
                            raise RuntimeError('A Render Product is updating between explicit captures')
                        if mode == 'rebuild':
                            await driver.destroy_product(handle)
                            handle = None
                        persist()
                finally:
                    shared_handle = handle
                    phase['group_wall_s'] = time.perf_counter() - phase_started
                    phase['actual_aa_mode'] = carb.settings.get_settings().get('/rtx/post/aa/op')
                    phase['images_per_wall_second'] = len(phase['frames']) / phase['group_wall_s']
                    persist()
            # Same cameras/time, after independent history resets. This numeric
            # comparison cannot establish exact external-volume freeze or visual acceptance.
            comparisons = []
            for camera in config['cameras']:
                reference = np.asarray(Image.open(out / f'retarget-16-subframes-{camera["id"]}.png')).astype(np.int16)
                for label in ('retarget-1-subframes', 'retarget-4-subframes'):
                    candidate = np.asarray(Image.open(out / (label + '-' + camera['id'] + '.png'))).astype(np.int16)
                    delta = np.abs(reference - candidate)
                    mean = float(delta.mean()); p99 = float(np.percentile(delta, 99))
                    comparisons.append({'camera_id': camera['id'], 'candidate': label,
                        'reference': 'retarget-16-subframes', 'mean_absolute_error': mean,
                        'p99_absolute_error': p99, 'thresholds': {'mean': 2, 'p99': 12},
                        'numeric_thresholds_passed': mean <= 2 and p99 <= 12})
            report['cross_strategy_numeric_comparisons'] = comparisons
            repeated = []
            for camera in config['cameras']:
                first = np.asarray(Image.open(out / f'retarget-16-subframes-{camera["id"]}.png')).astype(np.int16)
                second = np.asarray(Image.open(out / f'retarget-repeat-16-subframes-{camera["id"]}.png')).astype(np.int16)
                delta = np.abs(first - second)
                mean = float(delta.mean()); p99 = float(np.percentile(delta, 99))
                repeated.append({'camera_id': camera['id'], 'mean_absolute_error': mean,
                    'p99_absolute_error': p99, 'thresholds': {'mean': 2, 'p99': 12},
                    'numeric_thresholds_passed': mean <= 2 and p99 <= 12})
            report['repeated_16_subframes_numeric'] = repeated
        report['completed'] = True
    except Exception as error:
        report['error'] = str(error)[:1000]
        raise
    finally:
        try:
            await driver.close()
            eye = UsdGeom.XformCache().GetLocalToWorldTransform(stage.GetPrimAtPath(original_camera)).ExtractTranslation()
            geographic.focus(tuple(float(v) for v in eye))
        finally:
            geographic.suspend_dynamic_updates = original_suspend
            timeline.set_auto_update(original_auto)
            timeline.commit_silently()
            viewport.resolution = original_resolution
            viewport.updates_enabled = original_updates
        # Kit settings and render-texture retirement commit on app updates.
        for _ in range(2):
            await app.next_update_async()
        report['restoration_readback'] = {
            'camera': str(viewport.camera_path), 'expected_camera': original_camera,
            'viewport_updates': viewport.updates_enabled, 'expected_updates': original_updates,
            'viewport_resolution': list(viewport.resolution), 'expected_resolution': list(original_resolution),
            'auto_update': timeline.is_auto_updating(), 'expected_auto_update': original_auto,
            'clock_s': timeline.get_current_time(), 'expected_clock_s': clock,
            'root_sha256': hashlib.sha256((root / 'pilot.usda').read_bytes()).hexdigest(),
            'expected_root_sha256': root_hash}
        report['restored'] = (str(viewport.camera_path) == original_camera
            and viewport.updates_enabled == original_updates
            and tuple(viewport.resolution) == original_resolution
            and timeline.is_auto_updating() == original_auto
            and timeline.get_current_time() == clock
            and hashlib.sha256((root / 'pilot.usda').read_bytes()).hexdigest() == root_hash)
        report['remaining_products'] = len(driver.products)
        report['unsolicited_writer_callbacks'] = driver.unsolicited_callbacks
        report['resources'] = {'peak_device_vram_bytes': max((s['device_vram_used_bytes'] or 0 for s in metrics.samples), default=0),
            'peak_process_rss_bytes': max((s['process_rss_bytes'] for s in metrics.samples), default=0),
            'sample_count': len(metrics.samples), 'device_memory_scope': 'whole GPU, including live transport'}
        persist('report.json')
        pynvml.nvmlShutdown()
    if not report['restored'] or driver.products or driver.unsolicited_callbacks:
        raise RuntimeError('Diagnostic did not restore the viewport and release its render products')
    return report
