"""Inspect the real Isaac/Flow schema and NanoVDB output on a factory recipe.

Run only inside the approved Colab Isaac Python with its Vulkan environment.
This initial probe establishes native bindings; it does not certify fire physics.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--context', required=True)
    args = parser.parse_args()
    context = json.loads(Path(args.context).read_text())
    root = Path(context['factory_root']).resolve(strict=True)
    work = Path(context['qualification_root']).resolve(strict=True)
    if os.name != 'posix' or not str(work).startswith('/content/'):
        raise RuntimeError('Run the factory qualification on Colab')
    approval = json.loads((root / 'reports/omniverse_eula_approval.json').read_text())
    if approval.get('accepted') is not True:
        raise RuntimeError('The existing NVIDIA approval is required')
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    from isaacsim import SimulationApp
    app = SimulationApp({'headless': True, 'renderer': 'RayTracedLighting',
                         'width': 640, 'height': 480, 'disable_viewport_updates': True})
    try:
        import omni.kit.app
        import omni.timeline
        import omni.usd
        import omni.replicator.core as rep
        import carb.settings
        import numpy as np
        from PIL import Image
        from pxr import Gf, UsdGeom, UsdLux

        manager = omni.kit.app.get_app().get_extension_manager()
        if manager.set_extension_enabled_immediate('omni.flowusd', True) is False:
            raise RuntimeError('The installed Flow extension did not enable')
        for _ in range(12):
            app.update()
        ext = Path(manager.get_extension_path_by_module('omni.flowusd'))
        inventory = json.loads((work / 'source-inventory.json').read_text())
        recipe = next(r for r in inventory if r['family'] == 'fumee_sombre'
                      and r['preset'] == 'soutenu' and r['parameters']['dimension_profile'] == 'local')
        source = root / 'fx/flow/recipes' / recipe['id'] / 'effect.usda'
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != recipe['stage_sha256']:
            raise RuntimeError('Factory recipe changed after inventory')
        tag = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
        out = work / 'schema-probes' / tag
        out.mkdir(parents=True, exist_ok=False)
        report = {'schema': 'fireviewer.factory-flow-native-probe.v1', 'recipe_id': recipe['id'],
                  'source_sha256': digest, 'flow_extension': ext.name, 'completed': False,
                  'physical_fire_calibrated': False, 'fields': [], 'observations': []}
        try:
            if not omni.usd.get_context().open_stage(str(source)):
                raise RuntimeError('The actual factory USD did not open')
            for _ in range(20):
                app.update()
            stage = omni.usd.get_context().get_stage()
            if UsdGeom.GetStageMetersPerUnit(stage) != 1 or UsdGeom.GetStageUpAxis(stage) != 'Z':
                raise RuntimeError('Factory effect is not authored in metres/Z-up')
            stage.SetEditTarget(stage.GetSessionLayer())
            simulations = [p for p in stage.Traverse() if p.GetTypeName() == 'FlowSimulate']
            if len(simulations) != 1:
                raise RuntimeError('Probe requires exactly one real Flow simulator')
            simulation = simulations[0]
            report['flow_attributes'] = {a.GetName(): str(a.Get()) for a in simulation.GetAttributes()}
            nano = stage.GetPrimAtPath(str(simulation.GetPath()) + '/nanoVdbExport')
            if not nano:
                raise RuntimeError('The installed factory schema has no NanoVDB export prim')
            report['nano_export_attributes'] = {a.GetName(): str(a.Get()) for a in nano.GetAttributes()}
            cache = out / 'grids'
            cache.mkdir()
            for key, value in {'enabled': True, 'smokeEnabled': True, 'temperatureEnabled': True,
                               'fuelEnabled': False, 'burnEnabled': False, 'velocityEnabled': False,
                               'statisticsEnabled': True, 'readbackEnabled': True,
                               'readbackOpenVDB': False, 'readbackClearOnStart': False,
                               'readbackClearOnStop': False, 'readbackDirectory': str(cache)}.items():
                attribute = nano.GetAttribute(key)
                if not attribute:
                    raise RuntimeError('Installed NanoVDB schema misses ' + key)
                attribute.Set(value)
            for key, value in {'simulateWhenPaused': False, 'forceSimulate': False,
                               'forceDisableCoreSimulation': False, 'forceDisableEmitters': False,
                               'timeScale': 1.0}.items():
                simulation.GetAttribute(key).Set(value)
            cam = UsdGeom.Camera.Define(stage, '/QA/Camera')
            cam.CreateFocalLengthAttr(35)
            cam.CreateHorizontalApertureAttr(36)
            cam.CreateVerticalApertureAttr(27)
            cam.CreateClippingRangeAttr(Gf.Vec2f(.05, 300))
            UsdGeom.Xformable(cam).AddTransformOp().Set(Gf.Matrix4d().SetLookAt(
                Gf.Vec3d(14, -40, 18), Gf.Vec3d(0, 0, 12), Gf.Vec3d(0, 0, 1)).GetInverse())
            UsdLux.DomeLight.Define(stage, '/QA/Sky').CreateIntensityAttr(800)
            settings = carb.settings.get_settings()
            for key in ('enabled', 'rayTracedReflectionsEnabled', 'rayTracedTranslucencyEnabled'):
                settings.set('/rtx/flow/' + key, True)
            settings.set('/rtx/flow/maxBlocks', 2048)
            rep.orchestrator.set_capture_on_play(False)
            product = rep.create.render_product('/QA/Camera', (640, 480), force_new=True)
            rgb = rep.AnnotatorRegistry.get_annotator('rgb')
            rgb.attach(product)
            timeline = omni.timeline.get_timeline_interface()
            timeline.set_current_time(0)
            timeline.play()
            for frame in range(1, 121):
                rep.orchestrator.step(delta_time=1 / 30, rt_subframes=1, pause_timeline=False)
                if frame in (30, 60, 120):
                    array = rgb.get_data()[:, :, :3].copy()
                    path = out / f'actual-smoke-{frame}.png'
                    Image.fromarray(array).save(path)
                    report['observations'].append({'simulated_time_s': timeline.get_current_time(),
                        'image': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'rgb_standard_deviation': float(array.std())})
                    print('FACTORY_FLOW_PROBE_FRAME', frame, flush=True)
            timeline.pause()
            simulation.GetAttribute('forceDisableCoreSimulation').Set(True)
            simulation.GetAttribute('forceDisableEmitters').Set(True)
            for _ in range(10):
                rep.orchestrator.step(delta_time=0.0, rt_subframes=1)
            report['fields'] = [{'name': p.name, 'bytes': p.stat().st_size,
                                'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                               for p in sorted(cache.iterdir()) if p.is_file()]
            import warp as wp
            report['warp_version'] = wp.__version__
            report['volume_reader_methods'] = [name for name in ('load_from_nvdb', 'get_voxels',
                'get_grid_info', 'get_voxel_size') if hasattr(wp.Volume, name)]
            for field in report['fields'][:2]:
                try:
                    volume = wp.Volume.load_from_nvdb((cache / field['name']).read_bytes(), device='cuda')
                    info = volume.get_grid_info()
                    field['grid'] = {'name': info.name, 'type': info.type_str,
                                     'allocated_voxels': volume.get_voxel_count(),
                                     'voxel_size_m': list(volume.get_voxel_size())}
                except Exception as error:
                    field['reader_error'] = str(error)[:500]
            rgb.detach()
            product.destroy()
            report['completed'] = True
        finally:
            report['source_unchanged'] = hashlib.sha256(source.read_bytes()).hexdigest() == digest
            (out / 'report.json').write_text(json.dumps(report, indent=2))
            print('FACTORY_FLOW_NATIVE_PROBE_REPORT', json.dumps({k: v for k, v in report.items()
                if k not in ('flow_attributes', 'nano_export_attributes', 'fields')}) , flush=True)
    finally:
        app.close()


if __name__ == '__main__':
    main()
