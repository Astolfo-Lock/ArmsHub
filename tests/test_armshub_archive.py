from pathlib import Path
import tempfile
import unittest

from armshub.archive import write_shared_vpk
from charmstudio.vpk import VPK, write_vpk


class SharedArchiveTests(unittest.TestCase):
    def test_identical_vvd_and_vtx_alias_payloads_and_roundtrip(self):
        vertices = bytes(range(256))*1024
        indices = b'\x07\0\0\0VTX'+bytes(range(128))*300
        files = {'models/armshub/rifle_a.vvd': vertices,
                 'models/armshub/shotgun_b.vvd': vertices,
                 'models/armshub/rifle_a.dx90.vtx': indices,
                 'models/armshub/shotgun_b.dx90.vtx': indices,
                 'models/armshub/rifle_a.mdl': b'distinct mdl profile A',
                 'models/armshub/shotgun_b.mdl': b'distinct mdl profile B'}
        with tempfile.TemporaryDirectory() as directory:
            path, ordinary = Path(directory)/'shared.vpk', Path(directory)/'ordinary.vpk'
            stats = write_shared_vpk(path, files)
            write_vpk(ordinary, files)
            archive = VPK(path)
            for name, contents in files.items():
                self.assertEqual(archive.read(name), contents)
                entry = archive.entries[name]
                self.assertEqual(entry.archive, 0x7fff)
                self.assertEqual(entry.preload, b'')
                self.assertLessEqual(archive.data_start+entry.offset+entry.size, path.stat().st_size)
            self.assertEqual(archive.entries['models/armshub/rifle_a.vvd'].offset,
                             archive.entries['models/armshub/shotgun_b.vvd'].offset)
            self.assertEqual(archive.entries['models/armshub/rifle_a.dx90.vtx'].offset,
                             archive.entries['models/armshub/shotgun_b.dx90.vtx'].offset)
            self.assertNotEqual(archive.entries['models/armshub/rifle_a.mdl'].offset,
                                archive.entries['models/armshub/shotgun_b.mdl'].offset)
            self.assertEqual(stats.saved_payload_bytes, len(vertices)+len(indices))
            self.assertEqual(stats.file_count, 6)
            self.assertEqual(stats.unique_payloads, 4)
            self.assertEqual(stats.logical_payload_bytes, sum(map(len, files.values())))
            self.assertEqual(stats.stored_payload_bytes+stats.saved_payload_bytes,
                             stats.logical_payload_bytes)
            self.assertEqual(stats.archive_bytes, path.stat().st_size)
            self.assertEqual(ordinary.stat().st_size-path.stat().st_size, stats.saved_payload_bytes)

    def test_deterministic_and_only_whole_identical_files_share(self):
        files = {'x.vvd': b'arms'+b'charm A', 'y.vvd': b'arms'+b'charm B',
                 'copy.vvd': b'arms'+b'charm A', 'empty': b''}
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory)/'first.vpk', Path(directory)/'second.vpk'
            stats = write_shared_vpk(first, files)
            write_shared_vpk(second, dict(reversed(list(files.items()))))
            self.assertEqual(first.read_bytes(), second.read_bytes())
            archive = VPK(first)
            self.assertNotEqual(archive.entries['x.vvd'].offset, archive.entries['y.vvd'].offset)
            self.assertEqual(archive.read('empty'), b'')
            self.assertEqual(stats.saved_payload_bytes, len(files['copy.vvd']))

    def test_reject_malformed_and_duplicate_paths_before_writing(self):
        invalid = ['', '../a', '/a', '\\a', 'a/../b', 'a//b', 'a/./b',
                   'a/', 'C:/a', 'a\0b', ' a', 'a/ b', 'a\nb']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'rejected.vpk'
            for name in invalid:
                with self.subTest(path=name), self.assertRaises(ValueError):
                    write_shared_vpk(path, {name: b'content'})
                self.assertFalse(path.exists())
            with self.assertRaises(ValueError):
                write_shared_vpk(path, {'arms/A.vvd': b'a', 'arms/a.vvd': b'b'})
            with self.assertRaises(TypeError):
                write_shared_vpk(path, {'a.vvd': 'not bytes'})


if __name__ == '__main__':
    unittest.main()
