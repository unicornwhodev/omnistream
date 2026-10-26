import hashlib
from pathlib import Path
import sys
import tempfile
import time
import unittest

from verified_spool import RcloneBackend,SpoolBlocked


class ReadbackProcessTests(unittest.TestCase):
    def backend(self,code,deadline):
        # A real child with deterministic stdout; no credentials or network.
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        config=Path(temporary.name)/'unused.private.conf'
        config.write_text('')
        backend=RcloneBackend(sys.executable,config,'test','test',readback_timeout_s=deadline)
        backend.command=[sys.executable,'-u','-c',code]
        return backend

    def test_silent_child_is_killed_at_deadline(self):
        backend=self.backend('import time;time.sleep(20)',.25)
        started=time.monotonic()
        with self.assertRaises(SpoolBlocked):backend.readback('probe')
        self.assertLess(time.monotonic()-started,5)

    def test_actual_child_bytes_are_hashed(self):
        backend=self.backend("import sys;sys.stdout.buffer.write(b'known data'*200000)",5)
        result=backend.readback('probe')
        self.assertEqual(result,{'bytes':2_000_000,
                                'sha256':hashlib.sha256(b'known data'*200000).hexdigest()})


if __name__=='__main__':unittest.main()
