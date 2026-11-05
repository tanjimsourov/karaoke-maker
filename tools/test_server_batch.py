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

    def test_child_failure_not_published(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'tools').mkdir();media=root/'media';media.mkdir()
            source=media/'Artist - Song.mp4';source.write_bytes(b'input')
            (root/'karaoke.py').write_text('raise SystemExit(2)\n')
            args=argparse.Namespace(language='da',model='htdemucs',threads=2,retry_failed=False,parallel=False,cleanup_song=False)
            with patch.object(server,'ROOT',root),patch('workflow.normalize',return_value=({},root/'work/test-job')):
                self.assertEqual(server.run_one(source,media,media/'karaoke',root/'reports',args),'needs_review')
                self.assertFalse((media/'karaoke').exists())

if __name__=='__main__':unittest.main()
