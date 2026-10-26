"""Measurements of real Flow NanoVDB data, with explicit model-field units.

Warp imports are deferred until after Isaac/Kit starts. No smoke or heat field
is synthesized here. Colour masks are never substituted for volume contents.
"""
import hashlib
from pathlib import Path
import numpy as np


def summarize_samples(values, world_positions, voxel_size_m, threshold=0.005):
    values = np.asarray(values)
    positions = np.asarray(world_positions)
    voxel = np.asarray(voxel_size_m, dtype=float)
    if values.ndim != 1 or positions.shape != (len(values), 3):
        raise ValueError('Field values and world positions have inconsistent dimensions')
    if voxel.shape != (3,) or not np.isfinite(voxel).all() or np.any(voxel <= 0):
        raise ValueError('Positive finite world-space voxel dimensions are required')
    if not np.isfinite(values).all() or not np.isfinite(positions).all():
        raise ValueError('Native volume contains non-finite samples')
    if not np.isfinite(threshold) or threshold < 0:
        raise ValueError('The support threshold must be finite and non-negative')
    selected = values > threshold
    weight = values[selected].astype(np.float64)
    points = positions[selected].astype(np.float64)
    total = float(weight.sum())
    return {'allocated_voxels_measured': len(values), 'support_voxels': int(selected.sum()),
            'support_threshold_model_units': threshold,
            'value_min': float(values.min()) if len(values) else None,
            'value_max': float(values.max()) if len(values) else None,
            'negative_voxels': int((values < 0).sum()),
            'support_integral_model_units_m3': total * float(np.prod(voxel)),
            'centroid_m': ((points * weight[:, None]).sum(axis=0) / total).tolist() if total else None,
            'bounds_m': {'min': (points.min(axis=0) - voxel / 2).tolist(),
                         'max': (points.max(axis=0) + voxel / 2).tolist()} if total else None,
            'below_ground_weight_fraction': float(weight[points[:, 2] < -voxel[2]].sum() / total) if total else None,
            'finite': True, 'units': 'native Flow scalar units; not kg/m3, kelvin or heat-release rate'}


def read_volume(path, threshold=0.005, max_allocated_voxels=16_777_216):
    """Read every allocated voxel, refusing an unreported measurement cap."""
    import warp as wp
    path = Path(path)
    data = path.read_bytes()
    volume = wp.Volume.load_from_nvdb(data, device='cuda')
    info = volume.get_grid_info()
    if info.type_str not in ('float', 'Float', 'float32'):
        raise ValueError('A qualified scalar float NanoVDB binding is required: ' + info.type_str)
    count = volume.get_voxel_count()
    if count > max_allocated_voxels:
        raise ValueError('Native volume exceeds the explicit full-measurement voxel budget')
    coordinates = volume.get_voxels()
    values = wp.empty(count, dtype=wp.float32, device='cuda')
    world = wp.empty(count, dtype=wp.vec3, device='cuda')

    @wp.kernel
    def sample_native_grid(grid: wp.uint64, coords: wp.array2d(dtype=wp.int32),
                           value_out: wp.array(dtype=wp.float32),
                           world_out: wp.array(dtype=wp.vec3)):
        i = wp.tid()
        c = wp.vec3i(coords[i, 0], coords[i, 1], coords[i, 2])
        value_out[i] = wp.volume_lookup_f(grid, c[0], c[1], c[2])
        world_out[i] = wp.volume_index_to_world(grid, wp.vec3(float(c[0]), float(c[1]), float(c[2])))

    if count:
        wp.launch(sample_native_grid, dim=count, inputs=[volume.id, coordinates, values, world], device='cuda')
        wp.synchronize()
    scalar_values = values.numpy()
    indices = coordinates.numpy()
    order = np.lexsort((indices[:, 2], indices[:, 1], indices[:, 0]))
    field_hash = hashlib.sha256()
    field_hash.update(np.asarray(indices[order], dtype='<i4').tobytes())
    field_hash.update(np.asarray(scalar_values[order], dtype='<f4').tobytes())
    result = summarize_samples(scalar_values, world.numpy(), volume.get_voxel_size(), threshold)
    return {'file': path.name, 'sha256': hashlib.sha256(data).hexdigest(),
            'canonical_voxel_values_sha256': field_hash.hexdigest(),
            'grid_name': info.name, 'grid_type': info.type_str,
            'voxel_size_m': list(volume.get_voxel_size()), **result}


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('volumes', nargs='+')
    parser.add_argument('--output', required=True)
    parser.add_argument('--threshold', type=float, default=.005)
    args = parser.parse_args()
    result = [read_volume(p, args.threshold) for p in args.volumes]
    Path(args.output).write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)
