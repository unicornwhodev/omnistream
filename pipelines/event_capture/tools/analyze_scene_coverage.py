"""Read terrain tiles one at a time; compare existing and proposed coverage.

Run in a Python environment with the scene's compatible OpenUSD bindings.
This command does not start Kit, load vegetation, or change the source scene.
Use a bounded CPU process on a resource-constrained host.
"""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('PXR_WORK_THREAD_LIMIT', '1')
import numpy as np


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_terrain(scene, output):
    from pxr import Usd, UsdGeom
    geographic = json.loads((scene/'omnistream-geographic.json').read_text())
    nx, ny = geographic['tile_counts']
    size = geographic['tile_size_m']
    origin = geographic['origin_local_m']
    values = None
    records = []
    for ix in range(nx):
        for iy in range(ny):
            tile_id = f'tile_{ix:02d}_{iy:02d}'
            metadata_path = scene/'terrain'/tile_id/'lod8.json'
            meta = json.loads(metadata_path.read_text())
            source = scene/'terrain'/tile_id/'lod8.usdc'
            source_sha = sha(source)
            if source_sha != meta['sha256']:
                raise ValueError('Terrain file hash mismatch: '+tile_id)
            stage = Usd.Stage.Open(str(source), load=Usd.Stage.LoadNone)
            meshes = [UsdGeom.Mesh(p) for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
            if len(meshes) != 1:
                raise ValueError('Expected one terrain mesh: '+tile_id)
            mesh = meshes[0]
            points = np.asarray(mesh.GetPointsAttr().Get(), dtype=np.float32)
            n = round(len(points)**.5)
            if n*n != len(points):
                raise ValueError('Non-square terrain grid')
            x0, y0 = origin[0]+ix*size, origin[1]+iy*size
            expected_x = np.linspace(x0, x0+size, n)
            expected_y = np.linspace(y0+size, y0, n)
            p = points.reshape(n, n, 3)
            if (not np.allclose(p[..., 0], expected_x[None, :], atol=.002, rtol=0) or
                    not np.allclose(p[..., 1], expected_y[:, None], atol=.002, rtol=0)):
                raise ValueError('Unexpected terrain order or coordinates: '+tile_id)
            if not np.array_equal(np.asarray(mesh.GetFaceVertexIndicesAttr().Get())[:4], [0, n, n+1, 1]):
                raise ValueError('Unexpected mesh quad ordering')
            if values is None:
                steps = n-1
                values = np.full((ny*steps+1, nx*steps+1), np.nan, dtype=np.float32)
            elif n-1 != steps:
                raise ValueError('Mixed terrain spacing')
            z = p[::-1, :, 2]
            dest = values[iy*steps:iy*steps+n, ix*steps:ix*steps+n]
            present = np.isfinite(dest)
            if np.any(np.abs(dest[present]-z[present]) > .01):
                raise ValueError('Height discontinuity at tile seam: '+tile_id)
            dest[:] = z
            records.append({'id': tile_id, 'bounds_xy_m': [x0, y0, x0+size, y0+size],
                            'height_range_m': [float(z.min()), float(z.max())],
                            'terrain_file': source.relative_to(scene).as_posix(),
                            'sha256': source_sha})
            del meshes, mesh, stage, points, p, z, dest
        gc.collect()
        print(json.dumps({'terrain_tiles_read': len(records), 'total': nx*ny}), flush=True)
    if not np.isfinite(values).all():
        raise ValueError('Unfilled terrain samples')
    np.save(output/'terrain-lod8.npy', values, allow_pickle=False)
    receipt = {'schema': 'fireviewer.terrain-coverage-input.v1', 'origin_m': origin,
               'spacing_m': size/steps, 'shape': list(values.shape), 'tiles': records,
               'all_tile_hashes_verified': True, 'tile_seams_checked': True,
               'height_field_sha256': sha(output/'terrain-lod8.npy'),
               'source_scene_modified': False, 'vegetation_loaded': False, 'kit_started': False}
    write_json(output/'terrain-input.json', receipt)
    return values, receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scene', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sample-spacing-m', type=float, default=100.)
    parser.add_argument('--ray-spacing-m', type=float, default=25.)
    parser.add_argument('--terrain-cache', type=Path)
    parser.add_argument('--overview-columns', type=int, default=5)
    parser.add_argument('--overview-rows', type=int, default=10)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
    from fireviewer_capture.coverage import (HeightField, ground_samples, assess_coverage,
                                             design_overview_cameras, assign_to_existing_zones)
    from fireviewer_capture.residency import plan_static_tiles
    from fireviewer_capture.usd_cameras import create_configured_cameras, read_camera
    from pxr import Usd, UsdGeom
    started = time.monotonic()
    args.output.mkdir(parents=True, exist_ok=False)
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if args.terrain_cache:
        terrain_receipt = json.loads((args.terrain_cache/'terrain-input.json').read_text())
        data = args.terrain_cache/'terrain-lod8.npy'
        if sha(data) != terrain_receipt['height_field_sha256']:
            raise ValueError('Terrain cache hash mismatch')
        values = np.load(data, allow_pickle=False)
    else:
        values, terrain_receipt = read_terrain(args.scene, args.output)
    field = HeightField(values, tuple(terrain_receipt['origin_m']), terrain_receipt['spacing_m'])
    xyz, shape = ground_samples(field, args.sample_spacing_m, target_height_m=2.)
    resolution = config['render']['resolution_px']
    overview = assign_to_existing_zones(design_overview_cameras(field,
        columns=args.overview_columns, rows=args.overview_rows, resolution=resolution), config)
    reports = {}
    for name, cameras in [('existing', config['cameras']), ('overview_proposal', overview)]:
        report, per_camera, counts, scales = assess_coverage(cameras, resolution, xyz, field,
                                                            ray_step_m=args.ray_spacing_m)
        reports[name] = report
        write_json(args.output/(name+'-per-camera.json'), per_camera)
        np.savez_compressed(args.output/(name+'-samples.npz'),
                            multiplicity=counts.reshape(shape),
                            optimistic_scale_m_per_pixel=scales.reshape(shape))
        plans = [plan_static_tiles(c, resolution, terrain_receipt['tiles']) for c in cameras]
        write_json(args.output/(name+'-tile-plans.json'), plans)
        count = [len(p['static_context_tile_ids']) for p in plans]
        report['assumed_static_context_tiles'] = {'min': min(count), 'max': max(count),
                                                 'median': float(np.median(count)),
                                                 'total_scene_tiles': len(terrain_receipt['tiles']),
                                                 'memory_usage_measured': False}
        print(json.dumps({'coverage': name, **report}), flush=True)
    proposed = {'schema': 'fireviewer.camera-coverage-proposal.v1',
                'active_capture_config_replaced': False, 'cameras': overview, 'zones': config['zones'],
                'render': {'resolution_px': resolution}, 'coordinate_system': 'scene_local_metric_Z_up'}
    write_json(args.output/'overview-cameras.json', proposed)
    stage = Usd.Stage.CreateNew(str(args.output/'overview-cameras.usda'))
    UsdGeom.SetStageUpAxis(stage, 'Z'); UsdGeom.SetStageMetersPerUnit(stage, 1)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, '/World').GetPrim())
    create_configured_cameras(stage, proposed); stage.GetRootLayer().Save()
    readback = [read_camera(stage, c, proposed) for c in overview]
    write_json(args.output/'overview-composed-cameras.json', readback)
    report = {'schema': 'fireviewer.camera-coverage-report.v1',
        'status': 'CPU planning only; not native rendering acceptance',
        'source_config_sha256': sha(args.config),
        'terrain_height_field_sha256': terrain_receipt['height_field_sha256'],
        'terrain_mesh_spacing_m': field.spacing,
        'survey_bounds_xy_m': list(field.bounds),
        'area_km2': (field.bounds[2]-field.bounds[0])*(field.bounds[3]-field.bounds[1])/1e6,
        'ground_sample_spacing_m': args.sample_spacing_m,
        'sample_target_height_above_terrain_m': 2.,
        'maximum_horizontal_los_sample_spacing_m': args.ray_spacing_m,
        'resolution_px': resolution, 'comparison': reports,
        'cameras_read_back_from_usd': len(readback),
        'full_simulation_started': False,
        'limitations': ['Sampled terrain line of sight can miss narrow ridges.',
            'Vegetation, buildings, smoke extinction, light dependencies and sensor detection are untested.',
            'Optimistic frontoparallel scale is not terrain GSD or projected flame size.',
            'Overview poses are virtual aerial positions, not field-surveyed surveillance sites.',
            'The proposal preserves 10 groups of five IDs but does not replace the active camera configuration.',
            'Tile count is not a RAM or VRAM guarantee.',
            'Per-camera independent physics reruns are not qualified.'],
        'wall_seconds': time.monotonic()-started}
    write_json(args.output/'coverage-report.json', report)
    manifest = {p.name: sha(p) for p in args.output.iterdir() if p.is_file()}
    write_json(args.output/'artifact-sha256.json', manifest)
    print(json.dumps({'complete': True, 'wall_seconds': report['wall_seconds']}), flush=True)


if __name__ == '__main__': main()
