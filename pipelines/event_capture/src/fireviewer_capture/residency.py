"""Conservative spatial planning only; does not certify or change USD loads.

Rendering dependencies and simulation domains are different. Unknown smoke,
collision or illumination dependencies must block production culling, rather
than silently treating the viewing frustum as a closed physical system.
"""
import math
import numpy as np
from .coverage import camera_basis, optics
from .models import ContractError


def aabb_in_frustum(camera, resolution, lower, upper):
    eye, right, up, forward = camera_basis(camera)
    tx, ty, _, near, far = optics(camera, resolution)
    lower, upper = np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)
    if (lower.shape != (3,) or upper.shape != (3,) or np.any(upper < lower) or
            not np.isfinite(lower).all() or not np.isfinite(upper).all()):
        raise ValueError('Invalid world-space bounding box')
    # A positive vertex outside any plane rejects the entire AABB. This may
    # overselect boxes at frustum corners; it never rejects an intersecting box.
    planes = [(forward, -float(forward@eye)-near),
              (-forward, float(forward@eye)+far)]
    for normal in (tx*forward-right, tx*forward+right,
                   ty*forward-up, ty*forward+up):
        planes.append((normal, -float(normal@eye)))
    return all(float(n @ np.where(n >= 0, upper, lower))+d >= -1e-7
               for n, d in planes)


def plan_static_tiles(camera, resolution, tiles, *, assumed_asset_height_m=100.,
                      context_margin_m=500.):
    if min(assumed_asset_height_m, context_margin_m) < 0:
        raise ValueError('Planning bounds must be nonnegative')
    visible = []
    context = []
    for tile in tiles:
        x0, y0, x1, y1 = tile['bounds_xy_m']
        z0, z1 = tile['height_range_m']
        if aabb_in_frustum(camera, resolution, [x0, y0, z0],
                           [x1, y1, z1+assumed_asset_height_m]):
            visible.append(tile['id'])
        if aabb_in_frustum(camera, resolution,
                           [x0-context_margin_m, y0-context_margin_m, z0],
                           [x1+context_margin_m, y1+context_margin_m, z1+assumed_asset_height_m]):
            context.append(tile['id'])
    return {'camera_id': camera['id'], 'frustum_static_tile_ids': visible,
            'static_context_tile_ids': context,
            'assumed_asset_height_bound_m': assumed_asset_height_m,
            'context_margin_m': context_margin_m,
            'visible_assets_complete': False,
            'production_culling_allowed': False,
            'reason': 'Planning bounds are not verified asset extents, light dependencies or smoke domains'}


def influence_margin(*, wind_speed_bound_m_s, transport_horizon_sim_s,
                     propagation_speed_bound_m_s, uncertainty_m):
    values = (wind_speed_bound_m_s, transport_horizon_sim_s,
              propagation_speed_bound_m_s, uncertainty_m)
    if any(v is None or not math.isfinite(v) or v < 0 for v in values):
        raise ContractError('Explicit finite simulator bounds are required; unknown influence cannot be culled')
    return ((wind_speed_bound_m_s+propagation_speed_bound_m_s)*
            transport_horizon_sim_s+uncertainty_m)


def require_residency_contract(receipt, expected_state_fingerprint):
    """Check a provider's declaration and identity, not its physical accuracy.

    The provider and its native evidence need separate qualification. A numeric
    halo alone does not establish a valid simulation boundary.
    """
    required = ('visible_assets_complete', 'offscreen_illumination_complete',
                'smoke_dependencies_complete', 'physics_dependencies_complete',
                'all_producers_frozen', 'no_uncheckpointed_producer_unloaded')
    missing = [key for key in required if receipt.get(key) is not True]
    if missing or not expected_state_fingerprint or receipt.get('state_fingerprint') != expected_state_fingerprint:
        raise ContractError('Residency contract missing or mismatched: '+', '.join(missing or ['state_fingerprint']))
    return receipt
