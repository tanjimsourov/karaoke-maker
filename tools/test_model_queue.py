from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from model_queue import model_slot


class QueueTests(unittest.TestCase):
    def test_ocr_and_audio_have_distinct_slots(self):
        with tempfile.TemporaryDirectory() as folder:
            with model_slot(folder,name='model'):
                with model_slot(folder,name='ocr',timeout=.1):pass
            with self.assertRaises(ValueError):
                with model_slot(folder,name='../unsafe'):pass

    def test_jobs_cannot_overlap_and_lock_releases(self):
        with tempfile.TemporaryDirectory() as folder:
            code='from model_queue import model_slot;import sys\nwith model_slot(sys.argv[1],timeout=.1):print("acquired")'
            command=[sys.executable,'-c',code,folder]
            with model_slot(folder):
                blocked=subprocess.run(command,cwd=Path(__file__).parent,capture_output=True,text=True)
                self.assertNotEqual(blocked.returncode,0)
                self.assertIn('TimeoutError',blocked.stderr)
            released=subprocess.run(command,cwd=Path(__file__).parent,capture_output=True,text=True)
            self.assertEqual(released.returncode,0,released.stderr)
            self.assertIn('acquired',released.stdout)


if __name__=='__main__':unittest.main()
