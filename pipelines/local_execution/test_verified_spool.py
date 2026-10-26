import hashlib
import tempfile
import unittest
from pathlib import Path

from verified_spool import VerifiedSpool, SpoolBlocked


class MemoryRemote:
    def __init__(self):
        self.objects = {}
        self.fail = False
        self.corrupt = False

    def upload_verified(self, source, relative, expected):
        if self.fail:
            raise SpoolBlocked('Disconnected')
        value = Path(source).read_bytes()
        if relative in self.objects and self.objects[relative] != value:
            raise SpoolBlocked('Immutable remote collision')
        self.objects[relative] = value
        actual = self.readback(relative)
        if actual != expected:
            raise SpoolBlocked('Bad readback')
        return {'path':relative, **actual}

    def readback(self, relative):
        value = self.objects[relative]
        return {'bytes':len(value), 'sha256':hashlib.sha256(value).hexdigest() if not self.corrupt else '0'*64}


class SpoolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.remote = MemoryRemote()
        self.spool = VerifiedSpool(self.root, self.remote, max_bytes=100_000, reserve_bytes=0)
        path = self.root/'frames/ab/image.png'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'completed native frame fixture')
        self.entry = {'path':path.relative_to(self.root).as_posix(), 'bytes':path.stat().st_size,
                      'sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'prune':True}
        self.bundle_id = 'a'*64

    def tearDown(self):
        self.temp.cleanup()

    def test_remote_readback_before_pruning_and_idempotent_retry(self):
        self.spool.offload(self.bundle_id, [self.entry])
        self.assertFalse((self.root/self.entry['path']).exists())
        self.assertTrue((self.root/'offload-receipts'/(self.bundle_id+'.json')).exists())
        self.assertTrue(any(k.startswith('receipts/') for k in self.remote.objects))
        self.spool.offload(self.bundle_id, [self.entry])

    def test_disconnect_keeps_capture(self):
        self.remote.fail = True
        with self.assertRaises(SpoolBlocked):
            self.spool.offload(self.bundle_id, [self.entry])
        self.assertTrue((self.root/self.entry['path']).exists())

    def test_remote_corruption_keeps_capture(self):
        self.remote.corrupt = True
        with self.assertRaises(SpoolBlocked):
            self.spool.offload(self.bundle_id, [self.entry])
        self.assertTrue((self.root/self.entry['path']).exists())

    def test_incomplete_bundle_never_deletes_good_frame(self):
        incomplete = {**self.entry, 'path':'frames/missing.png'}
        with self.assertRaises(SpoolBlocked):
            self.spool.offload(self.bundle_id, [self.entry, incomplete])
        self.assertTrue((self.root/self.entry['path']).exists())
        self.assertFalse(self.remote.objects)

    def test_local_change_is_preserved(self):
        (self.root/self.entry['path']).write_bytes(b'user correction')
        with self.assertRaises(SpoolBlocked):
            self.spool.offload(self.bundle_id, [self.entry])
        self.assertEqual((self.root/self.entry['path']).read_bytes(), b'user correction')

    def test_scene_file_not_pruned(self):
        entry = {**self.entry, 'path':'scene/terrain.png'}
        with self.assertRaises(ValueError):
            self.spool.offload(self.bundle_id, [entry])

    def test_budget_blocks_next_group_and_counts_partial_files(self):
        (self.root/'incomplete.part').write_bytes(b'x'*90_000)
        with self.assertRaises(SpoolBlocked):
            self.spool.capacity(10_000)

    def test_resume_checks_remote_again(self):
        self.spool.offload(self.bundle_id, [self.entry])
        self.remote.corrupt = True
        with self.assertRaises(SpoolBlocked):
            self.spool.offload(self.bundle_id, [self.entry])


if __name__ == '__main__':
    unittest.main()
