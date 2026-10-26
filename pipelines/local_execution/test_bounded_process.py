import tempfile
import unittest
from pathlib import Path

from bounded_process import FatalLogMonitor, resource_stop_reason


class PreventiveStopTests(unittest.TestCase):
    def decide(self, **changes):
        values = dict(peak_commit=8, commit_stop=9, available_ram=5,
                      ram_reserve=4, vram=2, vram_stop=14, wall_s=5, timeout_s=60)
        values.update(changes)
        return resource_stop_reason(**values)

    def test_memory_peak_stops_before_hard_limit(self):
        self.assertEqual(self.decide(peak_commit=9), 'job_commit_headroom_threshold')
        self.assertIsNone(self.decide())

    def test_other_resources_and_cpu_only(self):
        self.assertEqual(self.decide(available_ram=3), 'host_ram_headroom_threshold')
        self.assertEqual(self.decide(vram=14), 'gpu_headroom_threshold')
        self.assertEqual(self.decide(rss=10_500_000_000), 'resident_ram_headroom_threshold')
        self.assertEqual(self.decide(wall_s=60), 'wall_timeout')
        self.assertIsNone(self.decide(vram=None))

    def test_fatal_message_split_across_polls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'stderr.log'
            path.write_bytes(b'ordinary message\nLLVM ERROR: out')
            monitor = FatalLogMonitor(p for p in [path])
            self.assertIsNone(monitor.check())
            with path.open('ab') as stream:
                stream.write(b' of memory\n')
            self.assertEqual(monitor.check(), 'native_renderer_fatal_error')

    def test_large_log_burst_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'stderr.log'
            path.write_bytes(b'x'*100000)
            monitor = FatalLogMonitor([path])
            self.assertEqual(monitor.check(), 'native_log_flood')


if __name__ == '__main__':
    unittest.main()
