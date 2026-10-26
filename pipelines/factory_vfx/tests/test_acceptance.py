import importlib.util
import json
from pathlib import Path
import unittest

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('evaluate_factory', root / 'evaluate.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AcceptanceTests(unittest.TestCase):
    def test_empty_or_partial_native_run_never_qualifies(self):
        report = {'configuration': json.loads((root / 'cases.json').read_text()), 'cases': [], 'run_id': 'incomplete'}
        result = module.evaluate(report, process_exit_code=0)
        self.assertFalse(result['functional_response_passed'])
        self.assertFalse(result['physical_fire_calibrated'])
        self.assertFalse(result['g4_full_scene_ready'])

    def test_wrong_wind_direction_fails_even_with_nonempty_native_field(self):
        case = {'case': {'id': 'smoke_wind_negative'}, 'completed': True,
                'source_unchanged': True, 'captures': [], 'measurements': [
                    {'fields': {'smoke': {'centroid_m': [4, 0, 2]}}}]}
        report = {'configuration': json.loads((root / 'cases.json').read_text()),
                  'cases': [case], 'run_id': 'wrong-direction'}
        result = module.evaluate(report, process_exit_code=-11)
        checks = {c['name']: c for c in result['checks']}
        self.assertFalse(checks['smoke_wind_negative']['passed'])
        self.assertFalse(checks['native_process_exit_success']['passed'])


if __name__ == '__main__':
    unittest.main()
