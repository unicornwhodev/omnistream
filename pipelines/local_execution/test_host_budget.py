import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from host_budget import ByteRateLimit, exclusive_heavy_work


class Clock:
    def __init__(self):
        self.now = 0
        self.waits = []

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


class HostBudgetTests(unittest.TestCase):
    def test_large_read_cannot_bypass_pacing(self):
        clock = Clock()
        limiter = ByteRateLimit(1024, lambda: clock.now, clock.sleep)
        for count in (512, 1024, 4096):
            limiter.account(count)
        self.assertAlmostEqual(clock.now, 5.5)

    def test_idle_time_does_not_accumulate_burst_credit(self):
        clock = Clock()
        limiter = ByteRateLimit(1024, lambda: clock.now, clock.sleep)
        limiter.account(1024)
        clock.now += 100
        limiter.account(1024)
        self.assertAlmostEqual(clock.waits[-1], 1)

    def test_invalid_budgets_fail_closed(self):
        for rate in (0, -1, float('nan'), float('inf')):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                ByteRateLimit(rate)
        limiter = ByteRateLimit(1)
        with self.assertRaises(ValueError):
            limiter.account(-1)

    def test_other_worker_is_rejected_then_can_acquire(self):
        script = (
            'import sys;from host_budget import exclusive_heavy_work;'
            '\ntry:\n with exclusive_heavy_work(sys.argv[1]):pass'
            '\nexcept RuntimeError:sys.exit(23)'
        )
        with tempfile.TemporaryDirectory() as directory:
            command = [sys.executable, '-c', script, directory]
            cwd = Path(__file__).resolve().parent
            with exclusive_heavy_work(directory):
                blocked = subprocess.run(command, cwd=cwd, capture_output=True, timeout=10)
            allowed = subprocess.run(command, cwd=cwd, capture_output=True, timeout=10)
            self.assertEqual(blocked.returncode, 23, blocked.stderr.decode())
            self.assertEqual(allowed.returncode, 0, allowed.stderr.decode())

    def test_exception_releases_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'fixture'):
                with exclusive_heavy_work(directory):
                    raise ValueError('fixture')
            with exclusive_heavy_work(directory):
                pass


if __name__ == '__main__':
    unittest.main()
