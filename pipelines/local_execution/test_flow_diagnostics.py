import unittest
from flow_diagnostics import require_native_progress


class FlowDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.initial = {'last_absolute_sim_time_s':0.0,'last_block_fault_sim_time_s':0.0,
            'active_blocks':0,'max_blocks':0,'interface_active_blocks':0,'interface_max_blocks':0}
        self.active = {**self.initial,'last_absolute_sim_time_s':1.0,
            'active_blocks':24,'max_blocks':512,'interface_active_blocks':24,'interface_max_blocks':512}

    def test_empty_native_solver_is_not_accepted(self):
        with self.assertRaisesRegex(RuntimeError,'timeline motion is insufficient'):
            require_native_progress(self.initial,self.initial,512)

    def test_actual_progress_is_not_physical_calibration(self):
        report = require_native_progress(self.initial,self.active,512)
        self.assertEqual(report['native_clock_advanced_s'],1.0)
        self.assertFalse(report['physical_fire_calibrated'])

    def test_allocation_fault_and_unbounded_pool_are_rejected(self):
        for patch in ({'last_block_fault_sim_time_s':.5},{'interface_max_blocks':4096},
                      {'last_absolute_sim_time_s':float('nan')}):
            with self.assertRaises(RuntimeError):
                require_native_progress(self.initial,{**self.active,**patch},512)
