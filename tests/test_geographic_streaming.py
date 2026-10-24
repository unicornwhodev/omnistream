"""Manifest boundaries and real USD residency regression tests."""
import copy
import importlib.util
import pathlib
import sys
import tempfile
import unittest

MODULE = pathlib.Path(__file__).resolve().parents[1] / 'runtime/bridge/omnistream.codex.bridge/omnistream/codex/bridge/geographic_streaming.py'
# The Colab test runner sets this path to its verified copy.
if not MODULE.is_file():
    MODULE = pathlib.Path(__file__).resolve().parent / 'geographic_streaming.py'
spec = importlib.util.spec_from_file_location('geographic_streaming_under_test', MODULE)
geo = importlib.util.module_from_spec(spec); spec.loader.exec_module(geo)


def manifest():
    return {'schema': geo.SCHEMA, 'tile_counts': [2, 2], 'tile_size_m': 500,
            'origin_local_m': [-500, -500], 'vegetation_tiles': ['tile_00_00', 'tile_00_01'],
            'building_tiles': [], 'overview_camera': '/World/Cameras/Overview'}


class ManifestTests(unittest.TestCase):
    def test_paths_sizes_duplicates_and_nonfinite_are_rejected(self):
        cases = [('vegetation_tiles', ['../private']), ('building_tiles', ['tile_02_00']),
                 ('vegetation_tiles', ['tile_00_00'] * 2), ('tile_counts', [65, 64]),
                 ('tile_counts', [True, 2]), ('tile_size_m', float('nan')),
                 ('origin_local_m', [0, float('inf')]), ('overview_camera', '/World/../Script'),
                 ('script', 'execute')]
        for key, value in cases:
            data = manifest(); data[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): geo.validate_manifest(data)
        self.assertEqual(geo.validate_manifest(manifest()), manifest())
        restricted=manifest();restricted['active_tiles']=['tile_00_00']
        with self.assertRaises(ValueError):geo.validate_manifest(restricted)
        restricted['qualification_scope']='pilot-l4-16tiles'
        self.assertEqual(geo.validate_manifest(restricted),restricted)
        for values in [['tile_02_00'],['tile_00_00','tile_00_00'],[{}]]:
            with self.subTest(active=values), self.assertRaises(ValueError):
                geo.validate_manifest({**restricted,'active_tiles':values})


HAS_USD = importlib.util.find_spec('pxr') is not None
if HAS_USD:
    from pxr import Usd, UsdGeom, Sdf


@unittest.skipUnless(HAS_USD, 'Real OpenUSD required for the residency gate')
class ResidencyTests(unittest.TestCase):
    def test_real_root_lod_refines_before_100m_and_native_camera_motion_is_observed(self):
        from pxr import Usd, UsdGeom
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            tree = Usd.Stage.CreateNew(str(root/'tree.usda'))
            prim = UsdGeom.Xform.Define(tree, '/Tree').GetPrim(); tree.SetDefaultPrim(prim)
            lod = prim.GetVariantSets().AddVariantSet('lod')
            for level, size in [('lod0', 3), ('lod1', 2), ('lod2', 1)]:
                lod.AddVariant(level); lod.SetVariantSelection(level)
                with lod.GetVariantEditContext(): UsdGeom.Cube.Define(tree, '/Tree/Shape').CreateSizeAttr(size)
            lod.SetVariantSelection('lod2'); tree.GetRootLayer().Save()
            terrain = Usd.Stage.CreateNew(str(root/'terrain.usda'))
            prim = UsdGeom.Xform.Define(terrain, '/Tile').GetPrim(); terrain.SetDefaultPrim(prim)
            for level in ['1', '8']:
                lod=prim.GetVariantSets().AddVariantSet('lod'); lod.AddVariant(level); lod.SetVariantSelection(level)
            terrain.GetRootLayer().Save()
            forest = Usd.Stage.CreateNew(str(root/'forest.usda'))
            prim = UsdGeom.Xform.Define(forest, '/Tile').GetPrim(); forest.SetDefaultPrim(prim)
            inst = UsdGeom.PointInstancer.Define(forest, '/Tile/Canopy')
            inst.CreatePositionsAttr([(10,10,0)]); inst.CreateProtoIndicesAttr([0])
            proto=UsdGeom.Xform.Define(forest, '/Tile/Canopy/P0').GetPrim(); proto.GetPayloads().AddPayload('./tree.usda')
            inst.CreatePrototypesRel().SetTargets([proto.GetPath()]); forest.GetRootLayer().Save()
            stage = Usd.Stage.CreateNew(str(root/'scene.usda'))
            UsdGeom.Xform.Define(stage, '/World/Terrain/tile_00_00').GetPrim().GetPayloads().AddPayload('./terrain.usda')
            UsdGeom.Xform.Define(stage, '/World/Vegetation/tile_00_00').GetPrim().GetPayloads().AddPayload('./forest.usda')
            stage.GetRootLayer().Save()
            before={p.name:p.read_bytes() for p in root.glob('*.usda')}
            m=manifest();m.update(tile_counts=[1,1],origin_local_m=[0,0],vegetation_tiles=['tile_00_00'])
            residency=geo.GeographicStreaming(stage,m);list(residency.load_complete_assets())
            path='/World/Vegetation/tile_00_00/Canopy/P0'
            def current():return stage.GetPrimAtPath(path).GetVariantSet('lod').GetVariantSelection()
            residency.focus((110,10,0));self.assertEqual(current(),'lod0')  # 100 m from the actual instance center
            self.assertFalse(residency.needs_focus((115,10,0)))
            self.assertTrue(residency.needs_focus((120,10,0)))
            residency.focus((140,10,0));self.assertEqual(current(),'lod0')  # hysteresis
            residency.focus((160,10,0));self.assertEqual(current(),'lod1')
            residency.focus((510,10,0));self.assertEqual(current(),'lod2')
            residency.focus((130,10,0));self.assertEqual(current(),'lod0')  # anticipates the 100 m boundary
            residency.focus((10,10,1000));self.assertEqual(current(),'lod2')  # high aerial views must use real 3D distance
            residency.focus((110,10,0));self.assertEqual(current(),'lod0')
            self.assertEqual(residency.status['treeLOD0ObservationDistanceM'],100)
            residency.suspend_dynamic_updates=True
            self.assertFalse(residency.needs_focus((0,0,80)))
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.glob('*.usda')})

    def test_overview_detail_prototype_switch_and_unload_preserve_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for lod in (1, 8):
                s = Usd.Stage.CreateNew(str(root/f'lod{lod}.usda'))
                p = UsdGeom.Xform.Define(s, '/Tile').GetPrim(); s.SetDefaultPrim(p)
                UsdGeom.Cube.Define(s, '/Tile/Mesh'); s.GetRootLayer().Save()
            s = Usd.Stage.CreateNew(str(root/'tile.usda')); p = UsdGeom.Xform.Define(s, '/Tile').GetPrim(); s.SetDefaultPrim(p)
            v = p.GetVariantSets().AddVariantSet('lod')
            for lod in (1, 8):
                v.AddVariant(str(lod)); v.SetVariantSelection(str(lod))
                with v.GetVariantEditContext(): p.GetReferences().AddReference(f'./lod{lod}.usda')
            v.SetVariantSelection('8'); s.GetRootLayer().Save()
            s = Usd.Stage.CreateNew(str(root/'vegetation.usda')); p = UsdGeom.Xform.Define(s, '/Tile').GetPrim(); s.SetDefaultPrim(p)
            inst = UsdGeom.PointInstancer.Define(s, '/Tile/Canopy'); inst.CreatePositionsAttr([(0, 0, 1)]); inst.CreateProtoIndicesAttr([0])
            targets = []
            for i in range(2):
                p = UsdGeom.Xform.Define(s, f'/Tile/Canopy/P{i}').GetPrim(); p.GetPayloads().AddPayload('./lod1.usda'); targets.append(p.GetPath())
            inst.CreatePrototypesRel().SetTargets(targets); s.GetRootLayer().Save()
            s = Usd.Stage.CreateNew(str(root/'scene.usda')); UsdGeom.Xform.Define(s, '/World')
            for x in range(2):
                for y in range(2): UsdGeom.Xform.Define(s, f'/World/Terrain/tile_{x:02d}_{y:02d}').GetPrim().GetPayloads().AddPayload('./tile.usda')
            for ident in ('tile_00_00', 'tile_00_01'):
                UsdGeom.Xform.Define(s, '/World/Vegetation/'+ident).GetPrim().GetPayloads().AddPayload('./vegetation.usda')
            s.GetRootLayer().Save()
            before = {p.name: p.read_bytes() for p in root.glob('*.usda')}
            s = Usd.Stage.Open(str(root/'scene.usda'), load=Usd.Stage.LoadNone)
            residency = geo.GeographicStreaming(s, manifest())
            path = '/World/Vegetation/tile_00_00/Canopy'
            self.assertFalse(s.GetPrimAtPath(path))
            self.assertEqual(residency.focus((0, 0, 100))['vegetationTiles'], 2)
            self.assertTrue(s.GetPrimAtPath(path+'/P0/Mesh')); self.assertTrue(s.GetPrimAtPath(path+'/P1/Mesh'))
            with Usd.EditContext(s, s.GetSessionLayer()): UsdGeom.PointInstancer.Get(s, path).GetProtoIndicesAttr().Set([1])
            residency.focus((0, 0, 100))
            self.assertTrue(s.GetPrimAtPath(path+'/P0/Mesh')); self.assertTrue(s.GetPrimAtPath(path+'/P1/Mesh'))
            self.assertEqual(residency.focus((0, 0, 15000))['detailTiles'], 0)
            # The session's protoIndices override retains an inert prim spec;
            # unloading must remove the payload's instance positions/geometry.
            self.assertFalse(s.GetPrimAtPath('/World/Vegetation/tile_00_00').IsLoaded())
            self.assertFalse(UsdGeom.PointInstancer.Get(s, path).GetPositionsAttr().Get())
            self.assertFalse(s.GetPrimAtPath(path+'/P1/Mesh'))
            progress = list(residency.load_complete_assets(batch_size=1))
            self.assertFalse(progress[0]['completeAssetResidency'])
            self.assertTrue(progress[-1]['completeAssetResidency'])
            self.assertEqual(progress[-1]['verifiedCanopyInstances'], 2)
            self.assertEqual(progress[-1]['sharedNativePrototypes'], 1)
            self.assertTrue(s.GetPrimAtPath(path+'/P1/Mesh'))
            self.assertEqual(residency.focus((20000, 20000, 15000))['vegetationTiles'], 2)
            self.assertTrue(s.GetPrimAtPath(path+'/P1/Mesh'))
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.glob('*.usda')})
            scoped=manifest();scoped.update(active_tiles=['tile_00_00'],qualification_scope='pilot-test')
            pilot=Usd.Stage.Open(str(root/'scene.usda'),load=Usd.Stage.LoadNone)
            pilot_residency=geo.GeographicStreaming(pilot,scoped)
            loaded=list(pilot_residency.load_complete_assets(batch_size=1))[-1]
            self.assertEqual(loaded['terrainTiles'],1)
            self.assertEqual(loaded['vegetationTiles'],1)
            self.assertEqual(loaded['verifiedCanopyInstances'],1)
            self.assertFalse(loaded['scopeIsProductionCase'])
            self.assertEqual(loaded['sourceTerrainTiles'],4)
            self.assertFalse(pilot.GetPrimAtPath('/World/Terrain/tile_00_01').IsLoaded())
            self.assertFalse(pilot.GetPrimAtPath('/World/Vegetation/tile_00_01').IsLoaded())
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.glob('*.usda')})


if __name__ == '__main__': unittest.main(verbosity=2)
