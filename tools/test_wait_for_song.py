import struct
import tempfile
from pathlib import Path
import unittest
from wait_for_song import complete_mp4


class DownloadTests(unittest.TestCase):
    def test_paused_download_is_not_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'song.mp4'
            atom = lambda kind, data: struct.pack('>I4s', len(data)+8, kind)+data
            prefix = atom(b'ftyp', b'isom')+atom(b'moov', b'header')
            full = prefix+atom(b'mdat', b'1234567890')
            path.write_bytes(full[:-3])
            self.assertFalse(complete_mp4(path))
            path.write_bytes(full)
            self.assertTrue(complete_mp4(path))

    def test_missing_movie_metadata_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'song.mp4'
            path.write_bytes(struct.pack('>I4s', 8,b'mdat'))
            self.assertFalse(complete_mp4(path))


if __name__ == '__main__': unittest.main()
