import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from project_runtime import FFMPEG
from zoom_local_pipeline import digest
from cleanup_job import plan_cleanup, cleanup


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.job = self.root/'work/local_open_source/Test-1234'
        self.job.mkdir(parents=True)
        self.output = self.root/'out/song.mp4'
        self.output.parent.mkdir()
        subprocess.run([str(FFMPEG),'-v','error','-f','lavfi','-i',
            'color=c=blue:s=160x120:r=25:d=0.2','-f','lavfi','-i',
            'sine=frequency=440:duration=0.2','-c:v','libx264','-c:a','aac',
            '-shortest',str(self.output)],check=True)
        self.source = self.root/'source.mp4'
        self.source.write_bytes(self.output.read_bytes())
        self.fingerprint = {'config': {'slug':self.job.name,
            'vocal_reference':str(self.source),'background':str(self.source)}}
        self.validation = {'output':str(self.output),'sha256':digest(self.output),
            'preview':False,'fingerprint':self.fingerprint}
        self.save('validation.json',self.validation)
        self.save('full-review.json',{'fingerprint':self.fingerprint,'listened':True,
            'checked_lyrics':True,'reviewed_audio_flags':True,'reviewed_timing':True})
        self.save('state.json',{'status':'delivered'})

    def save(self, name, value):
        (self.job/name).write_text(json.dumps(value))

    def test_removes_only_verified_job_data(self):
        for p in [self.root/'tools/app.py',self.root/'models/weight.bin',
                  self.root/'config/job.json',self.root/'out/another.mp4']:
            p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'preserve')
        scratch=self.root/'work/bowlnfun'/self.job.name
        scratch.mkdir(parents=True);(scratch/'karaoke.ass').write_text('scratch')
        (self.job/'stems').mkdir();(self.job/'stems/audio.wav').write_bytes(b'temp')
        before=self.output.read_bytes()
        plan=plan_cleanup(self.job,root=self.root)
        self.assertTrue(self.job.exists())
        cleanup(plan,root=self.root)
        self.assertFalse(self.job.exists());self.assertFalse(scratch.exists())
        self.assertEqual(self.output.read_bytes(),before)
        self.assertEqual(self.source.read_bytes(),before)
        self.assertEqual((self.root/'models/weight.bin').read_bytes(),b'preserve')
        self.assertEqual((self.root/'tools/app.py').read_bytes(),b'preserve')

    def test_changed_output_blocks_deletion(self):
        self.output.write_bytes(b'broken')
        with self.assertRaises(ValueError):plan_cleanup(self.job,root=self.root)
        self.assertTrue(self.job.exists())

    def test_checked_sample_cleanup_retains_honest_receipt_and_other_jobs(self):
        self.save('preview-validation.json',self.validation)
        self.save('sample-export.json',{'output':str(self.output),'sha256':digest(self.output),
            'status':'review_sample_technical_checks_passed','strict_decode':'passed',
            'human_content_approved':False})
        (self.job/'full-review.json').unlink()
        other=self.job.parent/'Other-5678';other.mkdir()
        (other/'data.wav').write_bytes(b'keep')
        cleanup(plan_cleanup(self.job,root=self.root,sample=True),root=self.root)
        self.assertFalse(self.job.exists())
        self.assertTrue((other/'data.wav').exists())
        receipts=list((self.root/'reports/completed').rglob('sample-export.json'))
        self.assertEqual(len(receipts),1)
        self.assertFalse(json.loads(receipts[0].read_text())['human_content_approved'])

    def test_unchecked_sample_blocks_cleanup(self):
        self.save('preview-validation.json',self.validation)
        self.save('sample-export.json',{'status':'pending'})
        with self.assertRaises(ValueError):plan_cleanup(self.job,root=self.root,sample=True)
        self.assertTrue(self.job.exists())

    def test_generated_background_removed_but_original_source_preserved(self):
        background=self.job/'branding-background/clean.mp4'
        background.parent.mkdir();background.write_bytes(self.source.read_bytes())
        self.fingerprint['config']['background']=str(background)
        self.save('branding-background/cleaned.json',{'output':str(background),
            'sha256':digest(background),'source_sha256':digest(self.source)})
        self.save('branding-background/cleanup-plan.json',{'source':str(self.source)})
        self.save('validation.json',self.validation)
        self.save('full-review.json',{'fingerprint':self.fingerprint,'listened':True,
            'checked_lyrics':True,'reviewed_audio_flags':True,'reviewed_timing':True})
        cleanup(plan_cleanup(self.job,root=self.root),root=self.root)
        self.assertFalse(background.exists());self.assertTrue(self.source.exists())

    def test_preview_and_missing_review_block_deletion(self):
        self.validation['preview']=True;self.save('validation.json',self.validation)
        with self.assertRaises(ValueError):plan_cleanup(self.job,root=self.root)
        self.validation['preview']=False;self.save('validation.json',self.validation)
        (self.job/'full-review.json').unlink()
        with self.assertRaises((ValueError,FileNotFoundError)):plan_cleanup(self.job,root=self.root)

    def test_code_or_models_in_work_are_never_deleted(self):
        for name in ['script.py','weights.onnx']:
            p=self.job/name;p.write_bytes(b'important')
            with self.assertRaises(ValueError):plan_cleanup(self.job,root=self.root)
            self.assertTrue(p.exists());p.unlink()

    def test_running_job_blocks_deletion(self):
        (self.job/'running.lock').write_text('123')
        with self.assertRaises(ValueError):plan_cleanup(self.job,root=self.root)

    def test_outside_work_path_blocks_deletion(self):
        with self.assertRaises(ValueError):plan_cleanup(self.root/'models',root=self.root)

    def test_corrupt_mp4_with_updated_hash_still_blocks_deletion(self):
        self.output.write_bytes(b'invalid MP4')
        self.validation['sha256']=digest(self.output);self.save('validation.json',self.validation)
        with self.assertRaises((ValueError,subprocess.CalledProcessError)):
            plan_cleanup(self.job,root=self.root)

    def test_modified_plan_cannot_expand_deletion(self):
        plan=plan_cleanup(self.job,root=self.root)
        plan['targets'].append(str(self.root/'tools'))
        with self.assertRaises(ValueError):cleanup(plan,root=self.root)
        self.assertTrue(self.job.exists())

    def test_new_data_after_dry_run_requires_new_plan(self):
        plan=plan_cleanup(self.job,root=self.root)
        (self.job/'new.wav').write_bytes(b'new data')
        with self.assertRaises(ValueError):cleanup(plan,root=self.root)
        self.assertTrue(self.job.exists())

    def test_links_are_rejected(self):
        link=self.job/'linked-model.bin'
        try:link.symlink_to(self.source)
        except OSError:self.skipTest('Symlink creation not permitted on this host')
        with self.assertRaises(ValueError):plan_cleanup(self.job,root=self.root)
        self.assertTrue(self.source.exists())


if __name__ == '__main__': unittest.main()
