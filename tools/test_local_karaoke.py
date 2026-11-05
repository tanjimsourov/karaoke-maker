from pathlib import Path
import tempfile
import unittest
from unittest import mock
from zoom_local_pipeline import save, read, render_options
import local_karaoke
from local_karaoke import (require_transcript_review, transcript_identity, verify_stems,
                           slugify, draft_stages, backup_transcript, restore)


class WorkflowTests(unittest.TestCase):
    def test_transcript_review_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            source=folder/'source.txt'; source.write_text('test source')
            cfg={'vocal_reference':str(source)}
            save(folder/'transcript.json',[{'text':'test'}])
            with self.assertRaises(ValueError):
                require_transcript_review(cfg,folder)
            save(folder/'transcript-review.json',transcript_identity(cfg,folder))
            require_transcript_review(cfg,folder)
            save(folder/'transcript.json',[{'text':'changed'}])
            with self.assertRaises(ValueError):
                require_transcript_review(cfg,folder)

    def test_excerpt_cannot_be_full_song(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            save(folder/'stems/separation.json',{'is_excerpt':True})
            with self.assertRaisesRegex(ValueError,'excerpt'):
                verify_stems({},folder)

    def test_slug_folds_danish_letters(self):
        self.assertEqual(slugify('Ærlig Freestyle'),'AErlig_Freestyle')
        self.assertEqual(slugify("Tænker Ik' På Andre!"),'Taenker_Ik_Paa_Andre')

    def test_draft_imports_manifest_lyrics_only_before_review(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            self.assertEqual(draft_stages({},folder),['separate','audit','transcribe'])
            self.assertEqual(draft_stages({'lyrics':'x.txt'},folder)[-1],'lyrics')
            save(folder/'transcript-review.json',{})
            self.assertNotIn('lyrics',draft_stages({'lyrics':'x.txt'},folder))

    def test_restore_keeps_current_transcript_in_history(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            save(folder/'transcript.json',[{'text':'first'}])
            backup_transcript(folder)
            version=next((folder/'history').glob('*.json')).stem.removeprefix('transcript-')
            save(folder/'transcript.json',[{'text':'second'}])
            restore({},folder,version)
            self.assertEqual(read(folder/'transcript.json'),[{'text':'first'}])
            self.assertEqual(len(list((folder/'history').glob('*.json'))),2)
            with self.assertRaises(ValueError):
                restore({},folder,'missing')

    def test_render_options_defaults_and_validation(self):
        options,args=render_options({})
        self.assertEqual(args,['--template','four_line','--canvas','1920x1080','--crf','19','--preset','veryfast'])
        _,args=render_options({'render':{'canvas':'1080x1920','pitch_semitones':-3,'guide_vocal_level':.2},
                               'guide_vocal':'v.wav'})
        self.assertIn('--pitch',args); self.assertIn('v.wav',args)
        with self.assertRaises(ValueError):
            render_options({'render':{'colour':'red'}})
        with self.assertRaises(ValueError):
            render_options({'render':{'guide_vocal_level':.2}})

    def test_backups_do_not_overwrite_when_clock_has_same_tick(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(local_karaoke,'datetime') as clock:
            clock.now.return_value.strftime.return_value='fixed-timestamp'
            folder=Path(directory)
            save(folder/'transcript.json',[{'text':'first'}]);backup_transcript(folder)
            version=next((folder/'history').glob('*.json')).stem.removeprefix('transcript-')
            save(folder/'transcript.json',[{'text':'second'}]);restore({},folder,version)
            self.assertEqual(read(folder/'transcript.json'),[{'text':'first'}])
            self.assertEqual(len(list((folder/'history').glob('*.json'))),2)

    def test_add_writes_project_relative_job(self):
        work=local_karaoke.ROOT/'work'
        if not work.exists():
            work.mkdir()
            self.addCleanup(work.rmdir)
        with tempfile.TemporaryDirectory(dir=local_karaoke.ROOT/'work') as directory:
            folder=Path(directory)
            song=folder/'Første dag.mp3'; song.write_bytes(b'x')
            background=folder/'bg.png'; background.write_bytes(b'x')
            manifest=folder/'jobs.json'
            args=mock.Mock(source=str(song),title='Første dag',artist='A',slug=None,background=str(background),
                           language='auto',language_label=None,file=None,template='single_line',
                           canvas=None,guide_vocal=None,pitch=None)
            with mock.patch.object(local_karaoke,'MANIFEST',manifest):
                local_karaoke.add_job(args)
                with self.assertRaises(ValueError):
                    local_karaoke.add_job(args)
            job=read(manifest)[0]
            self.assertEqual(job['slug'],'Foerste_dag')
            self.assertFalse(Path(job['source']).is_absolute())
            self.assertEqual(job['render'],{'template':'single_line'})

if __name__=='__main__': unittest.main()
