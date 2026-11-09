from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from model_queue import model_slot,resource_slots


class QueueTests(unittest.TestCase):
    def test_two_resource_slots_allow_two_and_block_third_then_release(self):
        with tempfile.TemporaryDirectory() as folder:
            with resource_slots('ocr',2,folder):
                with resource_slots('ocr',2,folder):
                    with self.assertRaises(TimeoutError):
                        with resource_slots('ocr',2,folder,timeout=0):pass
                with resource_slots('ocr',2,folder,timeout=0):pass
            with self.assertRaises(ValueError):
                with resource_slots('ocr',7,folder):pass

    def test_body_error_does_not_get_retried_or_swallowed(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(TimeoutError,'body failed'):
                with resource_slots('ocr',2,folder):raise TimeoutError('body failed')
            with resource_slots('ocr',2,folder,timeout=0):pass

    def test_renderer_respects_single_thread_configuration(self):
        import os
        from unittest.mock import patch
        from project_runtime import ffmpeg_input_filter_args
        with patch.dict(os.environ,{'KARAOKE_FFMPEG_THREADS':'1'},clear=True):
            self.assertEqual(ffmpeg_input_filter_args(),['-filter_complex_threads','1','-threads','1'])
        with patch.dict(os.environ,{'KARAOKE_FFMPEG_FILTER_THREADS':'0'}):
            with self.assertRaises(ValueError):ffmpeg_input_filter_args()
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
