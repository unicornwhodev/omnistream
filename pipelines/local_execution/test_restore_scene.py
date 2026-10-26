import hashlib
import tempfile
import unittest
from pathlib import Path
import zipfile

from restore_scene import restore, sha256


class RestoreTests(unittest.TestCase):
    def package(self, root, names=None):
        path = root / 'part.zip'
        rows = []
        with zipfile.ZipFile(path, 'w') as z:
            for name, value in (names or {'scene.usda': b'#usda 1.0', 'assets/a.txt': b'asset'}).items():
                z.writestr(name, value)
                rows.append({'path': name, 'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()})
        return path, {'name': path.name, 'bytes': path.stat().st_size, 'sha256': sha256(path), 'files': len(rows)}, rows

    def test_verify_before_consumption(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p, record, rows = self.package(root)
            result = restore(p, root/'scene', record, rows, consume=True, min_free_bytes=0)
            self.assertTrue(result['archive_consumed'])
            self.assertFalse(p.exists())
            self.assertEqual((root/'scene/assets/a.txt').read_bytes(), b'asset')

    def test_reject_corruption_and_keep_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p, record, rows = self.package(root)
            rows[0]['sha256'] = '0'*64
            with self.assertRaises(ValueError):
                restore(p, root/'scene', record, rows, consume=True, min_free_bytes=0)
            self.assertTrue(p.exists())

    def test_existing_changed_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p, record, rows = self.package(root)
            (root/'scene').mkdir()
            (root/'scene/scene.usda').write_bytes(b'valuable edit')
            with self.assertRaises(ValueError):
                restore(p, root/'scene', record, rows, consume=True, min_free_bytes=0)
            self.assertEqual((root/'scene/scene.usda').read_bytes(), b'valuable edit')
            self.assertTrue(p.exists())

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p, record, rows = self.package(root, {'../escape': b'x'})
            with self.assertRaises(ValueError):
                restore(p, root/'scene', record, rows, consume=True, min_free_bytes=0)
            self.assertFalse((root/'escape').exists())
            self.assertTrue(p.exists())

    def test_disk_reserve_stops_before_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p, record, rows = self.package(root)
            with self.assertRaises(RuntimeError):
                restore(p, root/'scene', record, rows, consume=True, min_free_bytes=10**20)
            self.assertFalse((root/'scene/scene.usda').exists())
            self.assertTrue(p.exists())


if __name__ == '__main__':
    unittest.main()
