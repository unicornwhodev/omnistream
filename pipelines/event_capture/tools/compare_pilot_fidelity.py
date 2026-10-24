"""Native, same-view fidelity comparison on the isolated 16-tile pilot only.

Invoke ``await run(stage, residency, pilot_root, snapshot, settle)`` inside the
existing Kit. ``snapshot(label)`` is the host's verified native PNG writer;
``settle(frames)`` advances rendering updates without advancing the paused clock.
This visual diagnostic is not a fire-engine or scientific capture qualification.
All source assets and the full production case remain unchanged.
"""
from pathlib import Path
import hashlib
import json
import time


async def run(stage, residency, pilot_root, snapshot, settle, view='observation100m'):
    try:
        return await _run(stage, residency, pilot_root, snapshot, settle, view)
    except Exception:
        import traceback
        traceback.print_exc()
        raise


async def _run(stage, residency, pilot_root, snapshot, settle, view):
    import carb.settings
    import omni.timeline
    from omni.kit.viewport.utility import get_active_viewport
    from pxr import Sdf, Usd, UsdGeom
    import psutil
    import pynvml

    root = Path(pilot_root).resolve()
    if residency.manifest.get('qualification_scope') != 'pilot-l4-16tiles' or len(residency.tiles) != 16:
        raise ValueError('This diagnostic is restricted to the isolated sixteen-tile pilot')
    timeline = omni.timeline.get_timeline_interface()
    if timeline.is_playing():
        raise ValueError('Pause the pilot before comparing rendering fidelity')
    flow = [p for p in stage.Traverse() if p.GetTypeName() == 'FlowSimulate']
    for prim in flow:
        if not all(prim.GetAttribute(name).Get() is True for name in ('forceDisableCoreSimulation', 'forceDisableEmitters')):
            raise ValueError('Every external Flow producer must already be explicitly frozen')
    viewport = get_active_viewport()
    original_camera = str(viewport.camera_path)
    if view not in ('observation100m', 'same_distant_view'):
        raise ValueError('Only the prepared 100 m camera or the saved distant view is allowed')
    camera = '/World/Cameras/LOD_100m' if view == 'observation100m' else '/World/Cameras/TransportComparison'
    camera_prim = stage.GetPrimAtPath(camera)
    if not camera_prim or not camera_prim.IsA(UsdGeom.Camera):
        raise ValueError('Prepare the real-tree 100 m inspection camera first')
    initial_time = timeline.get_current_time()

    def fingerprint():
        prim = stage.GetPrimAtPath(camera)
        cam = UsdGeom.Camera(prim)
        return (str(get_active_viewport().camera_path),
                str(UsdGeom.XformCache().GetLocalToWorldTransform(prim)),
                tuple(str(attr.Get()) for attr in (cam.GetFocalLengthAttr(), cam.GetHorizontalApertureAttr(), cam.GetVerticalApertureAttr())))

    initial_pose = None
    previous_suspend = residency.suspend_dynamic_updates
    session = stage.GetSessionLayer()
    settings = carb.settings.get_settings()
    aa_key = '/rtx/post/aa/op'
    aa_before = settings.get(aa_key)
    targets = sorted(str(path) for path in residency.prototype_paths)
    changed_payloads = []
    tag = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    out = root / 'fidelity-comparison' / tag
    out.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'fireviewer.pilot-fidelity-comparison.v1', 'camera': str(camera),
              'simulation_time_s': initial_time, 'scope': 'pilot-l4-16tiles',
              'scientific_acceptance': False, 'flow_grid_readback_qualified': False,
              'phases': [], 'restored': False, 'source_assets_modified': False,
              'gpu_execution_time': None, 'generated_wrapper_count': 0}
    wrappers = {}
    source_hashes = {}
    pynvml.nvmlInit()
    device = pynvml.nvmlDeviceGetHandleByIndex(0)

    def reserve():
        mem = pynvml.nvmlDeviceGetMemoryInfo(device)
        if mem.used / mem.total > .90 or psutil.virtual_memory().available < 5 * 1024**3:
            raise RuntimeError('The L4 comparison exceeded its reserved memory budget')
        return {'vram_used_bytes': mem.used, 'vram_total_bytes': mem.total,
                'rss_bytes': psutil.Process().memory_info().rss}

    async def capture(label):
        started = time.monotonic()
        for _ in range(4):
            await settle(8)
            reserve()
            if timeline.is_playing() or timeline.get_current_time() != initial_time or fingerprint() != initial_pose:
                raise RuntimeError('Camera or simulation time changed; this comparison is invalid')
        tree_levels = {}
        for path in targets:
            model = stage.GetPrimAtPath(path + '/Offset/Model')
            level = model.GetVariantSet('lod').GetVariantSelection() if model else 'unresolved'
            tree_levels[level] = tree_levels.get(level, 0) + 1
        terrain_levels = {}
        for ident in residency.tiles:
            level = stage.GetPrimAtPath('/World/Terrain/' + ident).GetVariantSet('lod').GetVariantSelection()
            terrain_levels[level] = terrain_levels.get(level, 0) + 1
        if 'tree-lod0' in label and tree_levels != {'lod0': len(targets)}:
            raise RuntimeError('The requested tree LOD did not compose into every live prototype')
        image = await snapshot('fidelity-' + tag + '-' + label)
        report['phases'].append({'label': label, 'native_png': image,
                                'aa_mode': settings.get(aa_key),
                                'settle_and_write_wall_s': time.monotonic() - started,
                                'resources': reserve(), 'effective_tree_lod_counts': tree_levels,
                                'effective_terrain_lod_counts': terrain_levels})
        (out / 'progress.json').write_text(json.dumps(report, indent=2))

    try:
        reserve()
        residency.suspend_dynamic_updates = True
        viewport.camera_path = camera
        eye = UsdGeom.XformCache().GetLocalToWorldTransform(camera_prim).ExtractTranslation()
        residency.focus(tuple(float(v) for v in eye))
        initial_pose = fingerprint()
        report['observation_distance_m'] = camera_prim.GetCustomDataByKey('inspection:distance_m')
        await capture('baseline')
        settings.set(aa_key, 4)  # Native-resolution DLAA, not DLSS upscaling.
        await capture('native-dlaa')

        # Author variants inside a derived wrapper BEFORE it becomes an
        # instance. Never try to edit a descendant of an instance proxy.
        for path in targets:
            prim = stage.GetPrimAtPath(path)
            spec = session.GetPrimAtPath(path)
            before = spec.GetInfo('payload') if spec and spec.HasInfo('payload') else None
            payloads = prim.GetMetadata('payload').GetAddedOrExplicitItems()
            if len(payloads) != 1:
                raise ValueError('Expected exactly one geographic tree payload')
            source = None
            # Resolve the authored payload in the layer that actually owns it.
            for source_spec in prim.GetPrimStack():
                if source_spec.HasInfo('payload'):
                    source = Path(Sdf.ComputeAssetPathRelativeToLayer(source_spec.layer, payloads[0].assetPath)).resolve()
                    break
            if not source or not source.is_file():
                raise ValueError('Tree source payload did not resolve')
            key = str(source)
            if key not in wrappers:
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                source_hashes[key] = digest
                target = out / ('lod0-' + digest[:16] + '.usda')
                wrapper = Usd.Stage.CreateNew(str(target))
                proto = UsdGeom.Xform.Define(wrapper, '/Prototype').GetPrim()
                wrapper.SetDefaultPrim(proto)
                proto.GetReferences().AddReference(str(source))
                model = wrapper.GetPrimAtPath('/Prototype/Offset/Model')
                lod = model.GetVariantSet('lod')
                if 'lod0' not in lod.GetVariantNames():
                    raise ValueError('This tree does not expose a real lod0 variant')
                lod.SetVariantSelection('lod0')
                wrapper.GetRootLayer().Save()
                assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
                wrappers[key] = target
            changed_payloads.append((path, before))
            with Usd.EditContext(stage, session):
                prim.GetPayloads().SetPayloads([Sdf.Payload(str(wrappers[key]))])
        report['generated_wrapper_count'] = len(wrappers)
        await capture('native-dlaa-tree-lod0')
        report['completed'] = True
    except Exception as error:
        report['completed'] = False
        report['error'] = str(error)[:500]
        raise
    finally:
        with Usd.EditContext(stage, session):
            for path, before in reversed(changed_payloads):
                prim = stage.GetPrimAtPath(path)
                if before is None:
                    prim.ClearMetadata('payload')
                else:
                    prim.SetMetadata('payload', before)
        if aa_before is None:
            settings.destroy_item(aa_key)
        else:
            settings.set(aa_key, aa_before)
        restored_payloads = True
        for path, before in changed_payloads:
            spec = session.GetPrimAtPath(path)
            after = spec.GetInfo('payload') if spec and spec.HasInfo('payload') else None
            restored_payloads = restored_payloads and after == before
        viewport.camera_path = original_camera
        residency.suspend_dynamic_updates = previous_suspend
        report['restored'] = bool(restored_payloads and settings.get(aa_key) == aa_before
                                  and str(viewport.camera_path) == original_camera)
        report['source_payload_wrappers_unchanged'] = all(
            hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
            for path, digest in source_hashes.items())
        (out / 'report.json').write_text(json.dumps(report, indent=2))
        pynvml.nvmlShutdown()
    if not report['restored'] or not report['source_payload_wrappers_unchanged']:
        raise RuntimeError('The fidelity comparison did not verify exact setting restoration and source preservation')
    return report
