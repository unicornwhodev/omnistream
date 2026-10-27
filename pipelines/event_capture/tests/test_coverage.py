import unittest
from unittest.mock import AsyncMock, Mock, patch
import sys
import types
import numpy as np
from fireviewer_capture.coverage import (HeightField, ground_samples, assess_coverage,
    design_overview_cameras, frustum_samples, terrain_visibility, assign_to_existing_zones)
from fireviewer_capture.residency import (aabb_in_frustum, influence_margin,
    plan_static_tiles, require_residency_contract)
from fireviewer_capture.models import ContractError


def camera(eye=(0, 0, 100), target=(0, 0, 0), up=(0, 1, 0)):
    return dict(id='test', position_m=list(eye), look_at_m=list(target), up=list(up),
                focal_length_mm=20, horizontal_aperture_mm=40, clipping_range_m=[.1, 1000])


class CoverageTests(unittest.TestCase):
    def test_mesh_diagonal_and_no_extrapolation(self):
        h = HeightField(np.array([[0., 0.], [0., 10.]]), (0, 0), 1.)
        self.assertEqual(float(h.sample([.25, .25])), 0)
        self.assertEqual(float(h.sample([.75, .75])), 5)
        with self.assertRaises(ValueError): h.sample([1.01, 0])

    def test_nonfinite_spatial_inputs_are_rejected(self):
        with self.assertRaises(ValueError): HeightField(np.zeros((2, 2)), (0, 0), np.nan)
        with self.assertRaises(ValueError): HeightField(np.zeros((2, 2)), (np.nan, 0), 1.)
        with self.assertRaises(ValueError):
            aabb_in_frustum(camera(), (200, 100), [0, 0, 0], [1, 1, np.inf])

    def test_exact_frustum_edge_and_behind(self):
        hit, scale = frustum_samples(camera(), (200, 100),
            [[100, 50, 0], [100.01, 0, 0], [0, 50.01, 0], [0, 0, 101]])
        self.assertEqual(hit.tolist(), [True, False, False, False])
        self.assertAlmostEqual(scale[0], 1.)

    def test_ridge_occludes_target(self):
        heights = np.zeros((201, 201)); heights[:, 99:102] = 40
        h = HeightField(heights, (-100, -100), 1.)
        c = camera((-90, 0, 20), (90, 0, 2), (0, 0, 1))
        visible = terrain_visibility(c, np.array([[90, 0, 2], [-80, 0, 2]]), h, ray_step_m=1.)
        self.assertEqual(visible.tolist(), [False, True])

    def test_flat_overview_covers_entire_sampled_area(self):
        h = HeightField(np.zeros((201, 201)), (-100, -100), 1.)
        xyz, _ = ground_samples(h, 10.)
        cams = design_overview_cameras(h, columns=2, rows=1)
        report, _, counts, _ = assess_coverage(cams, (1920, 1080), xyz, h)
        self.assertEqual(report['terrain_visible_fraction'], 1)
        self.assertTrue(np.all(counts >= 1))
        self.assertFalse(report['actual_render_tested'])

    def test_overview_preserves_zone_membership(self):
        from helpers import config
        c = config(10)
        # Use the real rectangular zone layout rather than the unit fixture's
        # arbitrary positions; test identity allocation on a miniature extent.
        c['zones'] = []
        for row in range(2):
            for col in range(5):
                z = f'zone_{row*5+col+1:02d}'
                x, y = col*40, row*100
                c['zones'].append(dict(id=z, camera_ids=[z+f'_cam_{i:02d}' for i in range(1, 6)],
                    geometry=dict(type='Polygon', coordinates=[[[x,y],[x+40,y],[x+40,y+100],[x,y+100],[x,y]]])))
        h = HeightField(np.zeros((201, 201)), (0, 0), 1.)
        proposal = assign_to_existing_zones(design_overview_cameras(h, columns=5, rows=10), c)
        self.assertEqual(len(proposal), 50)
        for zone in c['zones']:
            self.assertEqual([p['id'] for p in proposal if p['zone_id'] == zone['id']], zone['camera_ids'])
        with self.assertRaises(ValueError):
            assign_to_existing_zones(design_overview_cameras(h, columns=10, rows=5), c)

    def test_aabb_crossing_edge_is_kept(self):
        self.assertTrue(aabb_in_frustum(camera(), (200, 100), [90, -1, 0], [110, 1, 1]))
        self.assertFalse(aabb_in_frustum(camera(), (200, 100), [110, -1, 0], [120, 1, 1]))
        self.assertTrue(aabb_in_frustum(camera(), (200, 100), [-500, -500, -500], [500, 500, 500]))

    def test_static_plan_is_not_a_physics_certificate(self):
        tiles = [dict(id='near', bounds_xy_m=[0, 0, 10, 10], height_range_m=[0, 1]),
                 dict(id='offscreen', bounds_xy_m=[200, 0, 210, 10], height_range_m=[0, 1])]
        plan = plan_static_tiles(camera(), (200, 100), tiles, assumed_asset_height_m=0, context_margin_m=150)
        self.assertEqual(plan['frustum_static_tile_ids'], ['near'])
        self.assertIn('offscreen', plan['static_context_tile_ids'])
        with self.assertRaises(ContractError): require_residency_contract(plan, 'state-1')

    def test_smoke_can_enter_from_outside_view(self):
        self.assertEqual(influence_margin(wind_speed_bound_m_s=10, transport_horizon_sim_s=300,
            propagation_speed_bound_m_s=1, uncertainty_m=100), 3400)
        with self.assertRaises(ContractError):
            influence_margin(wind_speed_bound_m_s=None, transport_horizon_sim_s=300,
                propagation_speed_bound_m_s=1, uncertainty_m=100)

    def test_frozen_state_mismatch_rejected(self):
        receipt = {key: True for key in ('visible_assets_complete', 'offscreen_illumination_complete',
            'smoke_dependencies_complete', 'physics_dependencies_complete',
            'all_producers_frozen', 'no_uncheckpointed_producer_unloaded')}
        receipt['state_fingerprint'] = 'a'
        with self.assertRaises(ContractError): require_residency_contract(receipt, 'b')
        self.assertIs(require_residency_contract(receipt, 'a'), receipt)


class ResidencyDriverTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_visibility_only_receipt_cannot_enable_rendering(self):
        from fireviewer_capture.omniverse_driver import OmniverseRenderDriver
        provider = Mock(); provider.prepare = AsyncMock(return_value={'visible_assets_complete': True})
        driver = OmniverseRenderDriver(residency_provider=provider)
        with self.assertRaises(ContractError):
            await driver.prepare_batch({}, {'camera': {'state_fingerprint': 'a'}}, {})

    async def test_preparation_refuses_mixed_states_before_calling_provider(self):
        from fireviewer_capture.omniverse_driver import OmniverseRenderDriver
        provider = Mock(); provider.prepare = AsyncMock()
        driver = OmniverseRenderDriver(residency_provider=provider)
        with self.assertRaises(ContractError):
            await driver.prepare_batch({}, {'a': {'state_fingerprint': 'a'}, 'b': {'state_fingerprint': 'b'}}, {})
        provider.prepare.assert_not_called()

    async def test_qualified_dependency_receipt_resets_accumulation(self):
        from fireviewer_capture.omniverse_driver import OmniverseRenderDriver
        receipt = {key: True for key in ('visible_assets_complete', 'offscreen_illumination_complete',
            'smoke_dependencies_complete', 'physics_dependencies_complete',
            'all_producers_frozen', 'no_uncheckpointed_producer_unloaded')}
        receipt['state_fingerprint'] = 'a'
        provider = Mock(); provider.prepare = AsyncMock(return_value=receipt)
        driver = OmniverseRenderDriver(residency_provider=provider)
        context = Mock()
        omni = types.ModuleType('omni'); usd = types.ModuleType('omni.usd'); omni.usd = usd
        usd.get_context = lambda: context
        with patch.dict(sys.modules, {'omni': omni, 'omni.usd': usd}):
            await driver.prepare_batch({}, {'a': {'state_fingerprint': 'a'}}, {})
        context.reset_renderer_accumulation.assert_called_once_with()


if __name__ == '__main__': unittest.main()
