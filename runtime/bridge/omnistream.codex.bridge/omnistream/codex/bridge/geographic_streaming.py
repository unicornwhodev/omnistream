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
    if not isinstance(data, dict) or set(data) != keys or data['schema'] != SCHEMA:
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
        nx, ny = manifest['tile_counts']
        self.tiles = {f'tile_{x:02d}_{y:02d}': (x, y) for x in range(nx) for y in range(ny)}
        self.detail = set()
        self.asset_tiles = set()
        self.prototype_paths = set()
        self.status = {'mode': 'overview', 'terrainTiles': len(self.tiles), 'detailTiles': 0,
                       'vegetationTiles': 0, 'buildingTiles': 0, 'updates': 0,
                       'sourceLayersModified': False, 'focusSource': 'selected-camera-command'}
        paths = {f'/World/Terrain/{ident}' for ident in self.tiles}
        for path in paths:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.HasPayload():
                raise ValueError('Geographic terrain payload is missing')
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            for path in paths:
                stage.GetPrimAtPath(path).GetVariantSets().GetVariantSet('lod').SetVariantSelection('8')
        stage.LoadAndUnload(paths, set(), Usd.LoadWithoutDescendants)

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
        stage = self.stage
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            for ident in self.detail ^ detail:
                prim = stage.GetPrimAtPath(f'/World/Terrain/{ident}')
                prim.GetVariantSets().GetVariantSet('lod').SetVariantSelection('1' if ident in detail else '8')
        stage.LoadAndUnload(desired - self.asset_tiles, self.asset_tiles - desired, Usd.LoadWithoutDescendants)
        # Loading the instancer without descendants leaves all 18 prototype
        # payloads unloaded. Load precisely those its composed indices use.
        prototypes = set()
        for ident in vegetation:
            inst = UsdGeom.PointInstancer.Get(stage, f'/World/Vegetation/{ident}/Canopy')
            if not inst:
                raise ValueError('Geographic vegetation instancer is missing')
            targets = inst.GetPrototypesRel().GetTargets()
            used = set(inst.GetProtoIndicesAttr().Get() or [])
            if len(targets) > 18 or any(i < 0 or i >= len(targets) for i in used):
                raise ValueError('Invalid geographic prototype indices')
            prototypes.update(targets[i] for i in used)
        previous = {p for p in self.prototype_paths - prototypes if stage.GetPrimAtPath(p)}
        if prototypes or previous:
            stage.LoadAndUnload(prototypes, previous, Usd.LoadWithDescendants)
        self.prototype_paths = prototypes
        self.detail = detail; self.asset_tiles = desired
        self.status.update(mode='detail' if detail else 'overview', detailTiles=len(detail),
                           vegetationTiles=len(vegetation), buildingTiles=len(buildings),
                           updates=self.status['updates']+1)
        return dict(self.status)
