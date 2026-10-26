import unittest
from unittest.mock import patch

from fireviewer_capture.metrics import RunMetrics


class AccelerationMetricTests(unittest.TestCase):
    def test_requested_speed_is_not_reported_as_measured_speed(self):
        with patch('fireviewer_capture.metrics.time.perf_counter',return_value=0):
            metrics=RunMetrics()
        metrics.requested_acceleration=1000
        metrics.counts['simulated_time_advanced_us']=600_000_000
        metrics.durations['simulation_advance_wall_s']=2
        with patch('fireviewer_capture.metrics.time.perf_counter',return_value=10):
            result=metrics.summary()
        self.assertEqual(result['requested_acceleration'],1000)
        self.assertEqual(result['advance_effective_acceleration'],300)
        self.assertEqual(result['pipeline_effective_acceleration'],60)

    def test_no_simulation_progress_does_not_claim_target_speed(self):
        metrics=RunMetrics();metrics.requested_acceleration=1000
        result=metrics.summary()
        self.assertIsNone(result['advance_effective_acceleration'])
        self.assertEqual(result['pipeline_effective_acceleration'],0)


if __name__=='__main__':unittest.main()
