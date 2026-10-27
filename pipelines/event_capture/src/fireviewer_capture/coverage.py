"""CPU camera planning, with explicit limits; never a rendered acceptance test.

Coordinates are metric, Z up. Coverage is measured on a regular set of ground
samples. Terrain line of sight is sampled, so narrow occluders can be missed.
Vegetation, buildings, atmospheric extinction and image detection are NOT
modelled here. A frustum hit is not an annotation of visible fire.
"""
from dataclasses import dataclass
import math
import numpy as np


@dataclass
class HeightField:
    values: np.ndarray  # south to north rows, west to east columns
    origin: tuple
    spacing: float

    def __post_init__(self):
        if (self.values.ndim != 2 or min(self.values.shape) < 2 or
                not np.isfinite(self.values).all() or not math.isfinite(self.spacing) or self.spacing <= 0 or
                len(self.origin) != 2 or not np.isfinite(self.origin).all()):
            raise ValueError('A complete finite height field is required')

    @property
    def bounds(self):
        return (*self.origin, self.origin[0]+(self.values.shape[1]-1)*self.spacing,
                self.origin[1]+(self.values.shape[0]-1)*self.spacing)

    def sample(self, xy):
        """Interpolate the delivered mesh's NW-SE triangle diagonal."""
        a = np.asarray(xy, dtype=float)
        if a.shape[-1] != 2 or not np.isfinite(a).all():
            raise ValueError('Finite XY coordinates required')
        u = (a-np.asarray(self.origin))/self.spacing
        maximum = np.array([self.values.shape[1]-1, self.values.shape[0]-1])
        if np.any(u < -1e-8) or np.any(u > maximum+1e-8):
            raise ValueError('No terrain extrapolation outside the source domain')
        u = np.clip(u, 0, maximum)
        ij = np.minimum(np.floor(u).astype(int), maximum-1)
        x, y = ij[..., 0], ij[..., 1]
        fx, fy = (u-ij)[..., 0], (u-ij)[..., 1]
        sw, se = self.values[y, x], self.values[y, x+1]
        nw, ne = self.values[y+1, x], self.values[y+1, x+1]
        return np.where(fx+fy <= 1, sw+fx*(se-sw)+fy*(nw-sw),
                        ne+(1-fx)*(nw-ne)+(1-fy)*(se-ne))


def camera_basis(camera):
    eye = np.asarray(camera['position_m'], dtype=float)
    forward = np.asarray(camera['look_at_m'], dtype=float)-eye
    up = np.asarray(camera['up'], dtype=float)
    if not np.isfinite([eye, forward, up]).all() or np.linalg.norm(forward) < 1e-9:
        raise ValueError('Invalid camera pose')
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up)
    if np.linalg.norm(right) < 1e-9:
        raise ValueError('Camera up is parallel to its viewing direction')
    right /= np.linalg.norm(right)
    return eye, right, np.cross(right, forward), forward


def optics(camera, resolution):
    width, height = resolution
    focal, aperture = camera['focal_length_mm'], camera['horizontal_aperture_mm']
    near, far = camera.get('clipping_range_m', [.1, 100000])
    if min(width, height, focal, aperture, near) <= 0 or far <= near:
        raise ValueError('Invalid camera optics')
    tan_x = aperture/(2*focal)
    return tan_x, tan_x*height/width, width*focal/aperture, near, far


def frustum_samples(camera, resolution, xyz):
    eye, right, up, forward = camera_basis(camera)
    tx, ty, fpx, near, far = optics(camera, resolution)
    d = np.asarray(xyz)-eye
    depth = d@forward
    inside = ((depth >= near) & (depth <= far) &
              (np.abs(d@right) <= depth*tx) & (np.abs(d@up) <= depth*ty))
    # This is an optimistic frontoparallel scale, NOT ground sampling distance
    # on sloping terrain or the projected size of vertical flames.
    return inside, depth/fpx


def terrain_visibility(camera, xyz, field, *, ray_step_m=25., chunk_size=128):
    if ray_step_m <= 0 or chunk_size <= 0:
        raise ValueError('Positive line-of-sight sampling parameters required')
    eye = camera_basis(camera)[0]
    field.sample(eye[:2])  # do not silently extrapolate camera rays
    xyz = np.asarray(xyz, dtype=float)
    result = np.ones(len(xyz), dtype=bool)
    for start in range(0, len(xyz), chunk_size):
        targets = xyz[start:start+chunk_size]
        horizontal = np.linalg.norm(targets[:, :2]-eye[:2], axis=1)
        count = max(2, math.ceil(float(horizontal.max(initial=0))/ray_step_m)+1)
        # Include both ends. The target height is explicit in the caller.
        alpha = np.linspace(0, 1, count)
        rays = eye[None, None, :]+alpha[None, :, None]*(targets[:, None, :]-eye)
        result[start:start+len(targets)] = np.all(
            rays[..., 2] >= field.sample(rays[..., :2])-.01, axis=1)
    return result


def ground_samples(field, spacing_m=100., target_height_m=2.):
    x0, y0, x1, y1 = field.bounds
    if spacing_m <= 0 or target_height_m < 0:
        raise ValueError('Invalid ground sample spacing/height')
    nx, ny = round((x1-x0)/spacing_m), round((y1-y0)/spacing_m)
    if (abs(nx*spacing_m-(x1-x0)) > 1e-6 or
            abs(ny*spacing_m-(y1-y0)) > 1e-6):
        raise ValueError('Sample spacing must divide the survey extent')
    xx, yy = np.meshgrid(x0+(np.arange(nx)+.5)*spacing_m,
                         y0+(np.arange(ny)+.5)*spacing_m)
    xy = np.column_stack((xx.ravel(), yy.ravel()))
    return np.column_stack((xy, field.sample(xy)+target_height_m)), (ny, nx)


def assess_coverage(cameras, resolution, xyz, field, *, ray_step_m=25.):
    ids = [c['id'] for c in cameras]
    if len(set(ids)) != len(ids):
        raise ValueError('Camera identifiers must be unique')
    union = np.zeros(len(xyz), dtype=bool)
    multiplicity = np.zeros(len(xyz), dtype=np.uint16)
    best_scale = np.full(len(xyz), np.inf)
    rows = []
    for camera in cameras:
        hit, scale = frustum_samples(camera, resolution, xyz)
        visible = np.zeros(len(xyz), dtype=bool)
        selected = np.flatnonzero(hit)
        visible[selected] = terrain_visibility(camera, xyz[selected], field,
                                               ray_step_m=ray_step_m)
        union |= visible
        multiplicity += visible
        best_scale[visible] = np.minimum(best_scale[visible], scale[visible])
        rows.append({'camera_id': camera['id'], 'in_frustum_samples': int(hit.sum()),
                     'terrain_visible_samples': int(visible.sum())})
    summary = {
        'sample_count': len(xyz), 'camera_count': len(cameras),
        'terrain_visible_samples': int(union.sum()),
        'terrain_visible_fraction': float(union.mean()),
        'two_or_more_views_fraction': float((multiplicity >= 2).mean()),
        'optimistic_frontoparallel_scale_m_per_pixel_median':
            float(np.median(best_scale[union])) if union.any() else None,
        'optimistic_frontoparallel_scale_m_per_pixel_p95':
            float(np.quantile(best_scale[union], .95)) if union.any() else None,
        'sample_fraction_visible_at_optimistic_scale_le_1m_per_pixel':
            float((best_scale <= 1).mean()),
        'sample_fraction_visible_at_optimistic_scale_le_0_25m_per_pixel':
            float((best_scale <= .25).mean()),
        'actual_render_tested': False,
        'vegetation_building_and_smoke_occlusion_checked': False,
        'flame_visibility_validated': False,
    }
    return summary, rows, multiplicity, best_scale


def design_overview_cameras(field, *, columns=10, rows=5, resolution=(1920, 1080),
                            footprint_padding_fraction=0.08, focal_mm=22., aperture_mm=36.):
    """Virtual overhead survey; a separate proposal, not surveyed camera sites.

    The horizontal sensor axis follows the long side of each footprint.
    Height is derived from the maximum terrain vertex within each assigned cell.
    This prioritizes territory coverage, not flame detail or natural viewpoints.
    """
    if columns <= 0 or rows <= 0 or not 0 <= footprint_padding_fraction < .5:
        raise ValueError('Invalid overview grid')
    x0, y0, x1, y1 = field.bounds
    dx, dy = (x1-x0)/columns, (y1-y0)/rows
    tan_x = aperture_mm/(2*focal_mm)
    tan_y = tan_x*resolution[1]/resolution[0]
    north_is_wide = dy >= dx
    wide, narrow = (dy, dx) if north_is_wide else (dx, dy)
    height = max(wide/(2*tan_x), narrow/(2*tan_y))*(1+footprint_padding_fraction)
    result = []
    for iy in range(rows):
        for ix in range(columns):
            xa, ya = x0+ix*dx, y0+iy*dy
            xb, yb = xa+dx, ya+dy
            i0, j0 = np.floor((np.array([xa, ya])-field.origin)/field.spacing).astype(int)
            i1, j1 = np.ceil((np.array([xb, yb])-field.origin)/field.spacing).astype(int)
            zmax = float(field.values[j0:j1+1, i0:i1+1].max())
            x, y = (xa+xb)/2, (ya+yb)/2
            z = float(field.sample([x, y]))
            camera_id = f'overview_{iy*columns+ix+1:02d}'
            result.append({'id': camera_id, 'usd_path': '/World/CoverageCameras/'+camera_id,
                'position_m': [x, y, zmax+height], 'look_at_m': [x, y, z],
                'up': [1, 0, 0] if north_is_wide else [0, 1, 0], 'focal_length_mm': focal_mm,
                'horizontal_aperture_mm': aperture_mm, 'clipping_range_m': [.1, 100000],
                'assigned_ground_bounds_m': [xa, ya, xb, yb],
                'minimum_height_above_assigned_terrain_m': height,
                'pose_provenance': 'virtual overhead coverage proposal; not a surveyed installation'})
    return result


def assign_to_existing_zones(cameras, config):
    """Preserve zone IDs and camera IDs when the proposed grid fits rectangles.

    Irregular zones or an unequal camera allocation need an explicit design;
    never silently change the configured group membership.
    """
    import copy
    remaining = list(copy.deepcopy(cameras))
    result = []
    for zone in config['zones']:
        g = zone['geometry']
        if g['type'] != 'Polygon' or len(g['coordinates']) != 1:
            raise ValueError('This overview allocation requires rectangular zones')
        ring = np.asarray(g['coordinates'][0], dtype=float)
        x0, y0 = ring.min(axis=0); x1, y1 = ring.max(axis=0)
        if (len(ring) != 5 or not np.array_equal(ring[0], ring[-1]) or
                set(map(tuple, ring[:-1])) != {(x0, y0), (x0, y1), (x1, y0), (x1, y1)}):
            raise ValueError('This overview allocation requires rectangular zones')
        signed_area = np.sum(ring[:-1, 0]*ring[1:, 1]-ring[1:, 0]*ring[:-1, 1])/2
        if not np.isclose(abs(signed_area), (x1-x0)*(y1-y0)) or x1 <= x0 or y1 <= y0:
            raise ValueError('Zone ring must enclose a nondegenerate rectangle')
        selected = [c for c in remaining if x0 < c['position_m'][0] < x1 and y0 < c['position_m'][1] < y1]
        if len(selected) != len(zone['camera_ids']):
            raise ValueError('Proposed grid does not preserve camera allocation per zone')
        selected.sort(key=lambda c: (c['position_m'][1], c['position_m'][0]))
        for c, identifier in zip(selected, zone['camera_ids']):
            remaining.remove(c)
            c.update(id=identifier, usd_path='/World/Cameras/'+identifier, zone_id=zone['id'])
            result.append(c)
    if remaining:
        raise ValueError('Proposed cameras outside the configured zones')
    return result
