import argparse
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import server_batch as server

class ServerTests(unittest.TestCase):
    def test_six_workers_fill_and_drain_queue(self):
        import threading
        barrier=threading.Barrier(6);lock=threading.Lock()
        active=0;peak=0;completed=[]
        def worker(number):
            nonlocal active,peak
            with lock:active+=1;peak=max(peak,active)
            if number<6:barrier.wait(timeout=5)
            with lock:active-=1;completed.append(number)
            return number
        results=server.run_queue(list(range(18)),worker,6)
        self.assertEqual(peak,6)
        self.assertEqual(sorted(results),list(range(18)))
        self.assertEqual(sorted(completed),list(range(18)))
    def test_operational_failure_retried_but_review_stop_not_bypassed(self):
        args=argparse.Namespace(attempts=2,retry_failed=False)
        with patch.object(server,'run_one',side_effect=['failed','draft_exported']) as run,patch('server_batch.time.sleep'):
            result=server.run_with_retries(Path('song.mp4'),Path('.'),Path('out'),Path('reports'),args)
            self.assertEqual(result['status'],'draft_exported')
            self.assertEqual(result['attempts'],2)
            self.assertEqual(run.call_count,2)
        with patch.object(server,'run_one',return_value='needs_review') as run:
            result=server.run_with_retries(Path('song.mp4'),Path('.'),Path('out'),Path('reports'),args)
            self.assertEqual(result['status'],'needs_review')
            self.assertEqual(run.call_count,1)

    def test_preflight_exception_has_persistent_diagnostic(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'broken.mp4';report=root/'karaoke/.karaoke-status'
            args=argparse.Namespace(attempts=2,retry_failed=False)
            with patch.object(server,'run_one',side_effect=ValueError('bad metadata')),patch('server_batch.time.sleep'):
                result=server.run_with_retries(source,root,root/'karaoke',report,args)
            self.assertEqual(result['status'],'failed')
            record=json.loads(next(report.glob('*.json')).read_text())
            self.assertEqual(record['source'],str(source))
            self.assertEqual(record['error'],'bad metadata')

    def test_cleanup_preserves_models_sources_and_published_videos(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ('work','out','reports','tmp','models','media/karaoke','tools'):
                path=root/name;path.mkdir(parents=True,exist_ok=True)
                (path/'keep-or-remove').write_text('data')
            lock=root/'work/.server-batch-runtime.lock';lock.write_text('0')
            server.cleanup_runtime(root)
            for name in ('out','reports','tmp'):self.assertEqual(list((root/name).iterdir()),[])
            self.assertEqual(list((root/'work').iterdir()),[lock])
            for name in ('models','media/karaoke','tools'):
                self.assertTrue((root/name/'keep-or-remove').exists())

    def test_scan_excludes_output_partial_and_new_uploads(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);output=root/'karaoke';output.mkdir()
            good=root/'Artist - Song.mp4';good.write_bytes(b'video')
            os.utime(good,(time.time()-100,time.time()-100))
            (root/'new.mp4').write_bytes(b'uploading')
            (root/'partial.mp4.part').write_bytes(b'partial')
            (output/'result.mp4').write_bytes(b'generated')
            self.assertEqual(list(server.discover(root,output,30)),[good])

    def test_metadata_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'Artist - Song.mp4'
            source.with_suffix('.karaoke.json').write_text('{"title":"Correct title","language":"da"}')
            job=server.make_job(source,'auto','htdemucs',2)
            self.assertEqual(job['title'],'Correct title');self.assertEqual(job['artist'],'Artist')
            self.assertEqual(job['language'],'da')
            source.with_suffix('.karaoke.json').write_text('{"source":"elsewhere"}')
            with self.assertRaises(ValueError):server.make_job(source,'auto','htdemucs',2)

    def test_publish_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.write_bytes(b'video')
            dest=root/'karaoke/result.mp4'
            server.publish(source,dest);server.publish(source,dest)
            source.write_bytes(b'changed')
            with self.assertRaises(FileExistsError):server.publish(source,dest)
            self.assertEqual(dest.read_bytes(),b'video')

    def test_resume_requires_matching_file_hash(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'file.mp4';path.write_bytes(b'video')
            receipt={'status':'draft_exported','source_sha256':'source','recipe_sha256':'recipe',
                     'output':str(path),'output_sha256':server.sha(path)}
            self.assertTrue(server.receipt_matches(receipt,'source','recipe'))
            path.write_bytes(b'corrupt')
            self.assertFalse(server.receipt_matches(receipt,'source','recipe'))

    def test_real_child_process_publish_and_resume(self):
        # Replace only the costly karaoke implementation, not the runner/subprocess/file operations.
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'tools').mkdir();media=root/'media';media.mkdir()
            source=media/'Artist - Song.mp4';source.write_bytes(b'input')
            (root/'karaoke.py').write_text(
                "import os,pathlib\np=pathlib.Path(os.environ['KARAOKE_OUTPUT_DIR']);"
                "p.mkdir(parents=True,exist_ok=True);(p/'test-job_DRAFT.mp4').write_bytes(b'video');"
                "print('[DONE] fixture')\n")
            args=argparse.Namespace(language='da',model='htdemucs',threads=2,retry_failed=False,parallel=True,cleanup_song=False)
            with patch.object(server,'ROOT',root),patch('workflow.normalize',return_value=({},root/'work/test-job')), \
                    patch('project_runtime.OUT',root/'out'):
                self.assertEqual(server.run_one(source,media,media/'karaoke',root/'reports',args),'draft_exported')
                self.assertEqual(server.run_one(source,media,media/'karaoke',root/'reports',args),'skipped')
                output=list((media/'karaoke').glob('*.mp4'))
                self.assertEqual(len(output),1);self.assertEqual(output[0].read_bytes(),b'video')

    def test_export_published_and_cleaned_before_child_exit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'tools').mkdir();media=root/'media';media.mkdir()
            source=media/'Artist - Song.mp4';source.write_bytes(b'input')
            # Child refuses to exit until publication AND cleanup have happened.
            (root/'karaoke.py').write_text("""import os,pathlib,json,time
p=pathlib.Path(os.environ['KARAOKE_OUTPUT_DIR'])
p.mkdir(parents=True,exist_ok=True)
a=p/'test-job_DRAFT.mp4';a.write_bytes(b'video')
print('[EXPORT_READY] '+json.dumps({'path':str(a)}),flush=True)
out=pathlib.Path(__file__).parent/'media/karaoke'
for _ in range(100):
    if list(out.glob('*.mp4')) and not p.parent.exists():break
    time.sleep(.05)
else:raise RuntimeError('Publication waited for child exit')
(pathlib.Path(__file__).parent/'observed').write_text('published before exit')
""")
            args=argparse.Namespace(language='da',model='htdemucs',threads=2,retry_failed=True,parallel=False,cleanup_song=True)
            with patch.object(server,'ROOT',root),patch('workflow.normalize',return_value=({},root/'work/test-job')):
                self.assertEqual(server.run_one(source,media,media/'karaoke',root/'reports',args),'draft_exported')
            self.assertTrue((root/'observed').exists())
            self.assertEqual(source.read_bytes(),b'input')
            self.assertFalse(list((root/'reports').glob('*.log')))
            self.assertEqual(len(list((media/'karaoke').glob('*.mp4'))),1)

    def test_child_failure_not_published(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'tools').mkdir();media=root/'media';media.mkdir()
            source=media/'Artist - Song.mp4';source.write_bytes(b'input')
            (root/'karaoke.py').write_text('raise SystemExit(2)\n')
            args=argparse.Namespace(language='da',model='htdemucs',threads=2,retry_failed=False,parallel=False,cleanup_song=False)
            with patch.object(server,'ROOT',root),patch('workflow.normalize',return_value=({},root/'work/test-job')):
                self.assertEqual(server.run_one(source,media,media/'karaoke',root/'reports',args),'needs_review')
                self.assertFalse((media/'karaoke').exists())

    def test_verified_delivery_withholds_unreviewed_child_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'tools').mkdir();media=root/'media';media.mkdir()
            source=media/'Artist - Song.mp4';source.write_bytes(b'input')
            (root/'karaoke.py').write_text(
                "import os,pathlib\np=pathlib.Path(os.environ['KARAOKE_OUTPUT_DIR']);"
                "p.mkdir(parents=True,exist_ok=True);(p/'test-job_DRAFT.mp4').write_bytes(b'video')\n")
            args=argparse.Namespace(language='da',model='htdemucs',threads=2,retry_failed=True,parallel=False,cleanup_song=True,delivery_mode="verified")
            with patch.object(server,'ROOT',root),patch('workflow.normalize',return_value=({},root/'work/test-job')):
                self.assertEqual(server.run_one(source,media,media/'karaoke',root/'reports',args),'needs_review')
            self.assertFalse(list((media/'karaoke').glob('*.mp4')))
            self.assertTrue(list((root/'work/server-jobs').glob('*/exports/*_DRAFT.mp4')))
            records=[json.loads(f.read_text()) for f in (root/'reports').glob('*.json') if not f.name.endswith('.job.json')]
            self.assertFalse(records[0]['reviewed'])

    def test_reviewed_job_uses_render_and_retains_receipt_before_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'tools').mkdir();media=root/'media';media.mkdir()
            source=media/'Artist - Song.mp4';source.write_bytes(b'input')
            identity=server.hashlib.sha256(source.name.encode()).hexdigest()[:20]
            job=root/'work/server-jobs'/identity/'jobs/test-job';job.mkdir(parents=True)
            (job/'full-review.json').write_text('{}')
            for name in ['delivery-review.json','delivery-verification.json']:(job/name).write_text('{}')
            (root/'karaoke.py').write_text(
                "import os,pathlib,sys\nassert sys.argv[1]=='render' and '--keep-work' in sys.argv\n"
                "p=pathlib.Path(os.environ['KARAOKE_OUTPUT_DIR']);p.mkdir(parents=True,exist_ok=True);"
                "(p/'test-job_Karaoke.mp4').write_bytes(b'verified-fixture')\n")
            args=argparse.Namespace(language='da',model='htdemucs',threads=2,retry_failed=True,parallel=False,cleanup_song=True,delivery_mode="verified")
            with patch.object(server,'ROOT',root),patch('workflow.normalize',return_value=({},root/'work/test-job')):
                self.assertEqual(server.run_one(source,media,media/'karaoke',root/'reports',args),'verified_exported')
            receipt=json.loads((root/'reports'/(identity+'.json')).read_text())
            self.assertTrue(receipt['reviewed']);self.assertIn('verification',receipt)
            self.assertEqual(Path(receipt['output']).read_bytes(),b'verified-fixture')
            self.assertFalse(job.exists())

if __name__=='__main__':unittest.main()
