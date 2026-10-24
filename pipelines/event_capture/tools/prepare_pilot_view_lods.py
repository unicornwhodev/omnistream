"""Expose real tree LOD variants at instance roots in the isolated pilot.

Source factory files are only referenced. Derived wrappers and the inspection
camera belong to the pilot; no production layer is saved or rewritten.
"""
from pathlib import Path
import hashlib


def prepare(stage, residency, pilot_root):
    from pxr import Usd, UsdGeom, Sdf, Gf
    if residency.manifest.get('qualification_scope') != 'pilot-l4-16tiles' or len(residency.tiles) != 16:
        raise ValueError('The view-LOD trial is restricted to the isolated sixteen-tile pilot')
    directory = Path(pilot_root).resolve() / 'view-lod-100m-v1'
    directory.mkdir(exist_ok=True)
    wrappers = {}
    for path in sorted(residency.prototype_paths):
        prim = stage.GetPrimAtPath(path)
        payloads = prim.GetMetadata('payload').GetAddedOrExplicitItems()
        if len(payloads) != 1:
            raise ValueError('Expected one declared tree payload')
        source = None
        for spec in prim.GetPrimStack():
            if spec.HasInfo('payload'):
                source = Path(Sdf.ComputeAssetPathRelativeToLayer(spec.layer, payloads[0].assetPath)).resolve()
                break
        if not source or not source.is_file():
            raise ValueError('Tree source payload did not resolve')
        if source not in wrappers:
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            target = directory / ('tree-' + digest[:20] + '.usda')
            if not target.exists():
                wrapper = Usd.Stage.CreateNew(str(target))
                root = UsdGeom.Xform.Define(wrapper, '/Prototype').GetPrim()
                wrapper.SetDefaultPrim(root)
                root.GetReferences().AddReference(str(source))
                variants = root.GetVariantSets().AddVariantSet('lod')
                for level in ('lod0', 'lod1', 'lod2'):
                    variants.AddVariant(level)
                    variants.SetVariantSelection(level)
                    with variants.GetVariantEditContext():
                        model = wrapper.GetPrimAtPath('/Prototype/Offset/Model')
                        if level not in model.GetVariantSet('lod').GetVariantNames():
                            raise ValueError('The source tree lacks the required real LOD')
                        model.GetVariantSet('lod').SetVariantSelection(level)
                variants.SetVariantSelection('lod2')
                wrapper.GetRootLayer().customLayerData = {'source_sha256': digest}
                wrapper.GetRootLayer().Save()
            check = Usd.Stage.Open(str(target))
            if check.GetRootLayer().customLayerData.get('source_sha256') != digest:
                raise ValueError('A prior derived wrapper belongs to a different source')
            assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
            wrappers[source] = target
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            prim.GetPayloads().SetPayloads([Sdf.Payload(str(wrappers[source]))])

    # Target an actual canopy instance, at its real scaled model midpoint.
    ident = sorted(residency.tiles)[0]
    path = '/World/Vegetation/' + ident + '/Canopy'
    instancer = UsdGeom.PointInstancer.Get(stage, path)
    positions = instancer.GetPositionsAttr().Get()
    indices = instancer.GetProtoIndicesAttr().Get()
    index = len(positions) // 2
    prototypes = instancer.GetPrototypesRel().GetTargets()
    prototype = stage.GetPrimAtPath(prototypes[indices[index]])
    bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render']).ComputeLocalBound(prototype).ComputeAlignedRange()
    midpoint = bounds.GetMidpoint()
    scales = instancer.GetScalesAttr().Get()
    scale = scales[index] if scales else (1, 1, 1)
    position = positions[index]
    local_target = Gf.Vec3d(*(position[i] + midpoint[i] * scale[i] for i in range(3)))
    target = UsdGeom.XformCache().GetLocalToWorldTransform(instancer.GetPrim()).Transform(local_target)
    eye = target + Gf.Vec3d(0, -60, 80)
    with Usd.EditContext(stage, stage.GetSessionLayer()):
        camera = UsdGeom.Camera.Define(stage, '/World/Cameras/LOD_100m')
        camera.CreateFocalLengthAttr(40)
        camera.CreateHorizontalApertureAttr(36)
        camera.CreateVerticalApertureAttr(20.25)
        camera.CreateClippingRangeAttr(Gf.Vec2f(.1, 5000))
        xform = UsdGeom.Xformable(camera)
        xform.ClearXformOpOrder()
        xform.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(eye, target, Gf.Vec3d(0, 0, 1)).GetInverse())
        camera.GetPrim().SetCustomDataByKey('inspection:distance_m', float((eye-target).GetLength()))
        camera.GetPrim().SetCustomDataByKey('inspection:instancer', path)
        camera.GetPrim().SetCustomDataByKey('inspection:instance_index', index)
    return {'derived_wrappers': len(wrappers), 'observation_distance_m': float((eye-target).GetLength()),
            'camera': str(camera.GetPath()), 'source_assets_modified': False,
            'lod0_distance_m': 100, 'distance_policy': 'conservative-world-canopy-bounds'}
