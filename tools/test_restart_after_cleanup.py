from pathlib import Path
import tempfile
import unittest
from restart_after_cleanup import generated_data_cleared


class FreshStartTests(unittest.TestCase):
    def test_restart_waits_until_both_generated_folders_are_clear(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.assertTrue(generated_data_cleared(root))
            work=root/'work';work.mkdir();(work/'old.wav').write_bytes(b'old')
            self.assertFalse(generated_data_cleared(root))
            (work/'old.wav').unlink()
            self.assertTrue(generated_data_cleared(root))
            temp=root/'tmp';temp.mkdir();(temp/'old.log').write_text('old')
            self.assertFalse(generated_data_cleared(root))
            (temp/'old.log').unlink()
            self.assertTrue(generated_data_cleared(root))


if __name__=='__main__':unittest.main()
