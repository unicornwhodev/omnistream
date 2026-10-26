import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

from restore_drive import download_archive, temporary_api_quota


class DriveRetryTests(unittest.TestCase):
    def execute(self, results, *, stop=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        archive, log = root/'part.zip', root/'private.log'
        calls, sleeps = [], []
        def run(command, **kwargs):
            calls.append(command)
            code, message, content = results[len(calls)-1]
            kwargs['stderr'].write(message.encode())
            if content is not None:
                archive.write_bytes(content)
            if code is None:
                raise subprocess.TimeoutExpired(command,900)
            return SimpleNamespace(returncode=code)
        def admission():
            if stop and sleeps:
                raise RuntimeError('stop')
        def operation():
            download_archive(['rclone-test'],archive,log,check_admission=admission,
                             run=run,sleep=sleeps.append)
        return operation, archive, root/'part.zip.process.json', calls, sleeps

    def test_backend_quota_retried_then_file_required(self):
        operation, archive, receipt, calls, sleeps = self.execute([
            (1,'googleapi: Error 403 RATE_LIMIT_EXCEEDED',None),
            (0,'',b'archive')])
        operation()
        self.assertEqual(len(calls),2)
        self.assertEqual(sum(sleeps),30)
        self.assertEqual(archive.read_bytes(),b'archive')
        self.assertEqual(len(json.loads(receipt.read_text())['attempts']),2)

    def test_authentication_storage_and_daily_quotas_not_retried(self):
        for message in ('insufficientPermissions', 'storageQuotaExceeded',
                        'dailyLimitExceeded rateLimitExceeded'):
            self.assertFalse(temporary_api_quota(message))
            operation, _, _, calls, sleeps = self.execute([(1,message,None)])
            with self.assertRaises(RuntimeError): operation()
            self.assertEqual(len(calls),1)
            self.assertEqual(sleeps,[])

    def test_partial_copy_preserved_without_retry(self):
        operation, archive, _, calls, _ = self.execute([
            (1,'RATE_LIMIT_EXCEEDED',b'partial')])
        with self.assertRaises(RuntimeError): operation()
        self.assertEqual(archive.read_bytes(),b'partial')
        self.assertEqual(len(calls),1)

    def test_retry_limit_and_stop_during_wait(self):
        operation, _, receipt, calls, sleeps = self.execute(
            [(1,'RATE_LIMIT_EXCEEDED',None)]*4)
        with self.assertRaises(RuntimeError): operation()
        self.assertEqual(len(calls),4)
        self.assertEqual(sum(sleeps),210)
        self.assertEqual(len(json.loads(receipt.read_text())['attempts']),4)
        operation, _, _, calls, _ = self.execute(
            [(1,'RATE_LIMIT_EXCEEDED',None)],stop=True)
        with self.assertRaisesRegex(RuntimeError,'stop'): operation()
        self.assertEqual(len(calls),1)

    def test_timeout_is_not_retried(self):
        operation, _, receipt, calls, _ = self.execute([(None,'',None)])
        with self.assertRaises(RuntimeError): operation()
        self.assertEqual(len(calls),1)
        self.assertEqual(json.loads(receipt.read_text())['attempts'][0]['reason'],
                         'transfer_wall_timeout')

    def test_false_success_without_archive_rejected(self):
        operation, _, _, _, _ = self.execute([(0,'',None)])
        with self.assertRaisesRegex(RuntimeError,'no archive'): operation()


if __name__ == '__main__':
    unittest.main()
