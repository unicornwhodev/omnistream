import importlib.util
from pathlib import Path
import unittest
import numpy as np

path = Path(__file__).resolve().parents[1] / 'field_metrics.py'
spec = importlib.util.spec_from_file_location('field_metrics', path)
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


class FieldMetricTests(unittest.TestCase):
    def test_density_weighted_centroid_and_world_cell_volume(self):
        result = metrics.summarize_samples([1, 3, 0], [[0, 0, 1], [4, 0, 3], [100, 0, 100]], [2, 2, 2])
        self.assertEqual(result['centroid_m'], [3, 0, 2.5])
        self.assertEqual(result['support_integral_model_units_m3'], 32)
        self.assertEqual(result['support_voxels'], 2)
        self.assertEqual(result['bounds_m'], {'min': [-1, -1, 0], 'max': [5, 1, 4]})

    def test_empty_grid_cannot_be_mistaken_for_visible_smoke(self):
        result = metrics.summarize_samples(np.zeros(4), np.zeros((4, 3)), [0.1] * 3)
        self.assertEqual(result['support_voxels'], 0)
        self.assertIsNone(result['centroid_m'])
        self.assertIsNone(result['bounds_m'])

    def test_nonfinite_data_are_rejected(self):
        with self.assertRaises(ValueError):
            metrics.summarize_samples([float('nan')], [[0, 0, 0]], [1, 1, 1])

    def test_ground_leak_fraction_uses_field_weights(self):
        result = metrics.summarize_samples([1, 9], [[0, 0, -2], [0, 0, 2]], [1, 1, 1])
        self.assertEqual(result['below_ground_weight_fraction'], 0.1)


if __name__ == '__main__':
    unittest.main()
