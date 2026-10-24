"""Bounded payload/LOD residency for an explicitly declared tiled USD scene.

Only fixed terrain, vegetation and building paths are managed. All opinions are
session-only; this module never executes scene code or saves a source layer.
"""
import json
import math
import pathlib
import re

SCHEMA = 'omnistream.geographic-streaming.v1'
_ID = re.compile(r'tile_([0-9]{2})_([0-9]{2})\Z')


def validate_manifest(data):
    keys = {'schema', 'tile_counts', 'tile_size_m', 'origin_local_m',
            'vegetation_tiles', 'building_tiles', 'overview_camera'}
    optional = {'active_tiles', 'qualification_scope'}
    if not isinstance(data, dict) or not keys.issubset(data) or set(data)-keys-optional or data['schema'] != SCHEMA:
        raise ValueError('Invalid geographic streaming manifest schema')
    counts = data['tile_counts']
    if (not isinstance(counts, list) or len(counts) != 2 or
            any(type(n) is not int or not 1 <= n <= 64 for n in counts)):
        raise ValueError('Geographic grid is limited to 64 by 64 tiles')
    size = data['tile_size_m']
    origin = data['origin_local_m']
    if (type(size) not in (int, float) or not math.isfinite(size) or not 10 <= size <= 2000 or
            not isinstance(origin, list) or len(origin) != 2 or
            any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e6 for v in origin)):
        raise ValueError('Invalid geographic metric grid')
    valid = {f'tile_{x:02d}_{y:02d}' for x in range(counts[0]) for y in range(counts[1])}
    if ('active_tiles' in data) != ('qualification_scope' in data):
        raise ValueError('A restricted tile scope must be explicitly identified as qualification')
    if 'active_tiles' in data:
        active = data['active_tiles']; scope = data['qualification_scope']
        if (not isinstance(active, list) or not 1 <= len(active) <= 256 or
                any(not isinstance(v, str) or v not in valid for v in active) or len(set(active)) != len(active) or
                not isinstance(scope, str) or not re.fullmatch(r'pilot-[a-z0-9-]{1,56}', scope)):
            raise ValueError('Invalid explicit geographic qualification scope')
    for key in ('vegetation_tiles', 'building_tiles'):
        values = data[key]
        if (not isinstance(values, list) or len(values) > len(valid) or
                any(not isinstance(v, str) or not _ID.fullmatch(v) or v not in valid for v in values) or
                len(set(values)) != len(values)):
            raise ValueError('Invalid or duplicate geographic asset tile')
    camera = data['overview_camera']
    if not isinstance(camera, str) or not re.fullmatch(r'/World/Cameras/[A-Za-z_][A-Za-z0-9_]{0,63}', camera):
        raise ValueError('Invalid geographic overview camera')
    return dict(data)


def load_manifest(stage_path):
    path = pathlib.Path(stage_path).parent / 'omnistream-geographic.json'
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Invalid geographic manifest file')
    if not path.resolve().is_relative_to(pathlib.Path(stage_path).resolve().parent):
        raise ValueError('Geographic manifest must remain beside the USD entrypoint')
    return validate_manifest(json.loads(path.read_text(encoding='utf-8')))


class GeographicStreaming:
    def __init__(self, stage, manifest):
        from pxr import Usd
        self.stage = stage
        self.manifest = validate_manifest(manifest)
        nx, ny = self.manifest['tile_counts']
        self.tiles = {f'tile_{x:02d}_{y:02d}': (x, y) for x in range(nx) for y in range(ny)}
        if 'active_tiles' in self.manifest:
            active = set(self.manifest['active_tiles'])
            self.tiles = {key: value for key, value in self.tiles.items() if key in active}
            self.manifest = {**self.manifest,
                             'vegetation_tiles': [key for key in self.manifest['vegetation_tiles'] if key in active],
                             'building_tiles': [key for key in self.manifest['building_tiles'] if key in active]}
        self.detail = set()
        self.asset_tiles = set()
        self.prototype_paths = set()
        self.complete_assets = False
        self._tile_prototypes = {}
        self._last_focus = None
        self.suspend_dynamic_updates = False
        self._canopy_bounds = {}
        self.status = {'mode': 'overview', 'terrainTiles': len(self.tiles), 'detailTiles': 0,
                       'vegetationTiles': 0, 'buildingTiles': 0, 'updates': 0,
                       'sourceLayersModified': False, 'focusSource': 'selected-camera-command'}
        if 'qualification_scope' in self.manifest:
            self.status.update(qualificationScope=self.manifest['qualification_scope'],
                               sourceTerrainTiles=nx*ny, scopeIsProductionCase=False)
        paths = {f'/World/Terrain/{ident}' for ident in self.tiles}
        for path in paths:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.HasPayload():
                raise ValueError('Geographic terrain payload is missing')
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            for path in paths:
                stage.GetPrimAtPath(path).GetVariantSets().GetVariantSet('lod').SetVariantSelection('8')
        stage.LoadAndUnload(paths, set(), Usd.LoadWithoutDescendants)

    def needs_focus(self, eye):
        if len(eye) != 3 or not all(math.isfinite(float(v)) for v in eye):
            raise ValueError('Invalid geographic camera position')
        return not self.suspend_dynamic_updates and (self._last_focus is None or
            math.dist(tuple(float(v) for v in eye), self._last_focus) >= 10 or
            (eye[2] >= 4000) != (self._last_focus[2] >= 4000))

    def _update_tree_lods(self, eye):
        """Root variants only: never author inside an instance proxy.

        World canopy bounds conservatively include the actual instances.
        The 20 m
        anticipation plus hysteresis avoids late refinement during navigation.
        Assets that do not expose these real root variants are left unchanged.
        """
        from pxr import Usd, UsdGeom
        counts = {}
        size = self.manifest['tile_size_m']; ox, oy = self.manifest['origin_local_m']
        bounds_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
        with Usd.EditContext(self.stage, self.stage.GetSessionLayer()):
            for ident, paths in self._tile_prototypes.items():
                x, y = self.tiles[ident]
                dx = max(ox+x*size-eye[0], 0, eye[0]-(ox+(x+1)*size))
                dy = max(oy+y*size-eye[1], 0, eye[1]-(oy+(y+1)*size))
                distance = math.hypot(dx, dy)
                if ident not in self._canopy_bounds:
                    canopy = self.stage.GetPrimAtPath('/World/Vegetation/' + ident + '/Canopy')
                    if canopy and canopy.IsLoaded():
                        bounds = bounds_cache.ComputeWorldBound(canopy).ComputeAlignedRange()
                        if not bounds.IsEmpty():
                            self._canopy_bounds[ident] = (tuple(bounds.GetMin()), tuple(bounds.GetMax()))
                if ident in self._canopy_bounds:
                    low, high = self._canopy_bounds[ident]
                    distance = math.sqrt(sum(max(low[i]-eye[i], 0, eye[i]-high[i])**2 for i in range(3)))
                for path in paths:
                    prim = self.stage.GetPrimAtPath(path)
                    if not prim or not prim.IsLoaded():
                        continue
                    lod = prim.GetVariantSet('lod')
                    if not {'lod0', 'lod1', 'lod2'}.issubset(lod.GetVariantNames()):
                        continue
                    previous = lod.GetVariantSelection()
                    near = 140 if previous == 'lod0' else 120
                    middle = 440 if previous == 'lod1' else 420
                    selected = 'lod0' if distance <= near else 'lod1' if distance <= middle else 'lod2'
                    if previous != selected:
                        lod.SetVariantSelection(selected)
                    counts[selected] = counts.get(selected, 0)+1
        self.status.update(treeLOD0ObservationDistanceM=100, treeLODDistanceMetric='conservative-world-canopy-bounds',
                           treeLODCounts=counts)

    def focus(self, eye):
        """Keep the whole territory, refine <=25 nearby tiles, load assets nearby."""
        from pxr import Usd, UsdGeom
        if len(eye) != 3 or not all(math.isfinite(float(v)) for v in eye):
            raise ValueError('Invalid geographic camera position')
        size = self.manifest['tile_size_m']; ox, oy = self.manifest['origin_local_m']
        # Above 4 km use the complete overview. A fixed residency bound prevents
        # an individual camera command from loading all forest prototypes.
        near = [] if eye[2] >= 4000 else sorted(
            (math.hypot(ox+(x+.5)*size-eye[0], oy+(y+.5)*size-eye[1]), ident)
            for ident, (x, y) in self.tiles.items())
        detail = {ident for distance, ident in near[:25] if distance <= 1100}
        vegetation = detail.intersection(self.manifest['vegetation_tiles'])
        buildings = detail.intersection(self.manifest['building_tiles'])
        desired = {f'/World/Vegetation/{i}' for i in vegetation} | {f'/World/Buildings/{i}' for i in buildings}
        if self.complete_assets:
            desired |= self.asset_tiles
            vegetation |= {path.rsplit('/', 1)[1] for path in self.asset_tiles if path.startswith('/World/Vegetation/')}
            buildings |= {path.rsplit('/', 1)[1] for path in self.asset_tiles if path.startswith('/World/Buildings/')}
        stage = self.stage
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            for ident in self.detail ^ detail:
                prim = stage.GetPrimAtPath(f'/World/Terrain/{ident}')
                prim.GetVariantSets().GetVariantSet('lod').SetVariantSelection('1' if ident in detail else '8')
        stage.LoadAndUnload(desired - self.asset_tiles, self.asset_tiles - desired, Usd.LoadWithoutDescendants)
        # Preserve every canonical prototype slot. A sparse table with unloaded
        # targets can be compacted by the native scene delegate without an
        # equivalent protoIndices remap. USD instances share scene composition;
        # actual renderer memory reuse must be measured independently.
        prototypes = set()
        for ident in vegetation:
            if self.complete_assets and ident in self._tile_prototypes:
                prototypes.update(self._tile_prototypes[ident])
                continue
            inst = UsdGeom.PointInstancer.Get(stage, f'/World/Vegetation/{ident}/Canopy')
            if not inst:
                raise ValueError('Geographic vegetation instancer is missing')
            targets = inst.GetPrototypesRel().GetTargets()
            used = set(inst.GetProtoIndicesAttr().Get() or [])
            if len(targets) > 18 or any(i < 0 or i >= len(targets) for i in used):
                raise ValueError('Invalid geographic prototype indices')
            tile_prototypes = set(targets)
            with Usd.EditContext(stage, stage.GetSessionLayer()):
                for path in tile_prototypes:
                    prototype = stage.GetPrimAtPath(path)
                    if not prototype or not prototype.HasPayload():
                        raise ValueError('Geographic prototype payload is missing')
                    prototype.SetInstanceable(True)
            self._tile_prototypes[ident] = tile_prototypes
            prototypes.update(tile_prototypes)
        previous = {p for p in self.prototype_paths - prototypes if stage.GetPrimAtPath(p)}
        if prototypes or previous:
            stage.LoadAndUnload(prototypes, previous, Usd.LoadWithDescendants)
        self.prototype_paths = prototypes
        self._update_tree_lods(eye)
        self._last_focus = tuple(float(v) for v in eye)
        self.detail = detail; self.asset_tiles = desired
        self.status.update(mode='detail' if detail else 'overview', detailTiles=len(detail),
                           vegetationTiles=len(vegetation), buildingTiles=len(buildings),
                           updates=self.status['updates']+1)
        return dict(self.status)

    def load_complete_assets(self, batch_size=8):
        """Load every declared asset tile without thinning instance populations.

        The caller must yield to Kit between batches and monitor its resources.
        This is distinct from the nearby terrain refinement policy. Sources and
        coordinates are preserved. A partial iteration never reports complete.
        """
        from pxr import Usd, UsdGeom
        if type(batch_size) is not int or not 1 <= batch_size <= 32:
            raise ValueError('Asset load batch must contain 1 to 32 tiles')
        self.complete_assets = True
        vegetation = set(self.manifest['vegetation_tiles'])
        buildings = set(self.manifest['building_tiles'])
        all_paths = sorted({f'/World/Vegetation/{i}' for i in vegetation} |
                           {f'/World/Buildings/{i}' for i in buildings})
        # Include previously loaded tiles in this verification, rather than
        # assuming the earlier nearby-tile state proves their instances.
        actual_instances = 0
        self.status.update(assetResidencyMode='complete_requested', completeAssetResidency=False)
        for start in range(0, len(all_paths), batch_size):
            batch = set(all_paths[start:start+batch_size])
            for path in batch:
                prim = self.stage.GetPrimAtPath(path)
                if not prim or not prim.HasPayload():
                    raise ValueError('Declared geographic asset payload is missing')
            self.stage.LoadAndUnload(batch - self.asset_tiles, set(), Usd.LoadWithoutDescendants)
            prototypes = set()
            for path in batch:
                if not self.stage.GetPrimAtPath(path).IsLoaded():
                    raise ValueError('Geographic asset payload did not load')
                if path.startswith('/World/Vegetation/'):
                    inst = UsdGeom.PointInstancer.Get(self.stage, path+'/Canopy')
                    if not inst:
                        raise ValueError('Geographic vegetation instancer is missing')
                    positions = inst.GetPositionsAttr().Get()
                    indices = inst.GetProtoIndicesAttr().Get()
                    targets = inst.GetPrototypesRel().GetTargets()
                    if positions is None or indices is None or len(positions) != len(indices):
                        raise ValueError('Geographic instance population is inconsistent')
                    actual_instances += len(positions)
                    used = set(indices)
                    if len(targets) > 18 or any(i < 0 or i >= len(targets) for i in used):
                        raise ValueError('Invalid geographic prototype indices')
                    tile_prototypes = set(targets)
                    with Usd.EditContext(self.stage, self.stage.GetSessionLayer()):
                        for target in tile_prototypes:
                            prototype = self.stage.GetPrimAtPath(target)
                            if not prototype or not prototype.HasPayload():
                                raise ValueError('Geographic prototype payload is missing')
                            prototype.SetInstanceable(True)
                    self._tile_prototypes[path.rsplit('/', 1)[1]] = tile_prototypes
                    prototypes.update(tile_prototypes)
            if prototypes:
                self.stage.LoadAndUnload(prototypes - self.prototype_paths, set(), Usd.LoadWithDescendants)
                if any(not self.stage.GetPrimAtPath(path).IsLoaded() for path in prototypes):
                    raise ValueError('Geographic prototype payload did not load')
            self.prototype_paths |= prototypes
            self.asset_tiles |= batch
            self.status.update(vegetationTiles=sum(p.startswith('/World/Vegetation/') for p in self.asset_tiles),
                               buildingTiles=sum(p.startswith('/World/Buildings/') for p in self.asset_tiles),
                               assetTilesPending=len(set(all_paths)-self.asset_tiles),
                               verifiedCanopyInstances=actual_instances,
                               updates=self.status['updates']+1)
            yield dict(self.status)
        self.status.update(completeAssetResidency=True, assetResidencyMode='complete', assetTilesPending=0)
        shared = {str(self.stage.GetPrimAtPath(path).GetPrototype().GetPath())
                  for path in self.prototype_paths if self.stage.GetPrimAtPath(path).IsInstance()}
        self.status['sharedNativePrototypes'] = len(shared)
        yield dict(self.status)
