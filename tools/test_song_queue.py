import argparse
import io
import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
import server_batch as server
from song_cleanup import remove_generated

class QueueTests(unittest.TestCase):
    def test_six_slots_refill_before_other_songs_finish(self):
        first_six=threading.Event();release_first=threading.Event()
        release_rest=threading.Event();seventh=threading.Event();guard=threading.Lock()
        active=0;peak=0;started=[];result=[]
        def worker(index):
            nonlocal active,peak
            with guard:
                active+=1;peak=max(peak,active);started.append(index)
                if len(started)==6:first_six.set()
                if index==6:seventh.set()
            (release_first if index==0 else release_rest).wait(5)
            with guard:active-=1
            return 'done'
        thread=threading.Thread(target=lambda:result.extend(server.run_queue(range(9),worker,6)))
        thread.start()
        try:
            self.assertTrue(first_six.wait(3))
            self.assertFalse(seventh.is_set())
            release_first.set()
            self.assertTrue(seventh.wait(3))
        finally:
            release_first.set();release_rest.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual(peak,6);self.assertEqual(len(result),9)

    def test_failure_does_not_stop_queue(self):
        def worker(i):
            if i==1:raise ValueError('intentional')
            return 'done'
        result=server.run_queue(range(8),worker,6)
        self.assertEqual(result.count('done'),7);self.assertEqual(result.count('failed'),1)

    def test_cleanup_only_completed_song(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);jobs=root/'jobs';jobs.mkdir()
            a=jobs/'a';a.mkdir();(a/'stem.wav').write_bytes(b'a')
            b=jobs/'b';b.mkdir();(b/'stem.wav').write_bytes(b'b')
            output=root/'final.mp4';output.write_bytes(b'output')
            remove_generated(a,jobs,[output])
            self.assertFalse(a.exists());self.assertTrue((b/'stem.wav').exists())
            with self.assertRaises(ValueError):remove_generated(root,jobs,[output])
            with self.assertRaises(ValueError):remove_generated(b,jobs,[b/'stem.wav'])

    def test_export_then_cleanup_with_real_subprocess(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'tools').mkdir();media=root/'media';media.mkdir()
            source=media/'Artist - Song.mp4';source.write_bytes(b'source')
            logo=root/'logo';logo.write_bytes(b'logo')
            runtime=types.ModuleType('project_runtime');runtime.LOGO=logo;runtime.OUT=root/'out'
            workflow=types.ModuleType('workflow');workflow.normalize=lambda job:({},root/'job')
            (root/'karaoke.py').write_text("import os,pathlib\np=pathlib.Path(os.environ['KARAOKE_OUTPUT_DIR']);p.mkdir(parents=True,exist_ok=True);(p/'job_DRAFT.mp4').write_bytes(b'video')\n")
            args=argparse.Namespace(language='da',model='htdemucs',threads=1,retry_failed=False,parallel=False,cleanup_song=True)
            with patch.object(server,'ROOT',root),patch.dict('sys.modules',{'workflow':workflow,'project_runtime':runtime}):
                self.assertEqual(server.run_one(source,media,media/'karaoke',root/'reports',args),'draft_exported')
            self.assertEqual(len(list((media/'karaoke').glob('*.mp4'))),1)
            self.assertEqual(list((root/'work/server-jobs').iterdir()),[])
            self.assertEqual(list((root/'reports').iterdir()),[])
            self.assertEqual(source.read_bytes(),b'source')

if __name__=='__main__':unittest.main()
