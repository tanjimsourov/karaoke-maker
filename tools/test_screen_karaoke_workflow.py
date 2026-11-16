"""Screen sources must retain their audio and measured source colour progression."""
import copy
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch
import workflow
from zoom_local_pipeline import save, read, run_renderer


def cue():
    return {'start':1.,'end':3.,'text':'Hello', 'words':[
        {'word':'Hello','start':1.,'end':3.,'sweep':[[1.,0.],[2.5,0.],[2.8,.7],[3.,1.]]}]}


class ScreenWorkflowTests(unittest.TestCase):
    def test_screen_transcribe_does_not_run_music_models_or_checks(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=root/'source.mp4';source.write_bytes(b'source')
            bg=root/'bg.jpg';bg.write_bytes(b'background')
            job,folder=workflow.normalize({'source':str(source),'title':'Test','artist':'Artist',
                'mode':'zoom','language':'en','background':str(bg)},root)
            folder=root/'job'
            args=Namespace(parallel_stages=False)
            with patch.object(workflow,'preflight'),patch.object(workflow,'transcripts') as imported, \
                 patch.object(workflow.local,'separate') as separate, \
                 patch.object(workflow.local,'verify_stems') as stems, \
                 patch.object(workflow.separation_guard,'validate') as quality:
                workflow.execute('transcribe',job,folder,args)
            imported.assert_called_once();separate.assert_not_called();stems.assert_not_called();quality.assert_not_called()
            cfg=imported.call_args.args[2]
            self.assertEqual(cfg['zoom_video'],str(source))
            self.assertTrue(cfg['source_sweeps'])
            self.assertTrue(cfg['source_backing'])
            self.assertEqual(cfg['render_defaults'],{})

    def test_full_run_routes_skip_all_music_only_work_for_both_types(self):
        from server_batch import make_job
        for kind in ('zoom','singking'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                root=Path(d);source=root/'source.mp4';source.write_bytes(b'source')
                bg=root/'bg.jpg';bg.write_bytes(b'image');folder=root/'job'
                with patch.dict('os.environ',{'KARAOKE_BACKGROUND':str(bg),'KARAOKE_SCREEN_PROFILE':'auto'}):
                    raw=make_job(source,'en','htdemucs',2,kind)
                raw['render']['fps']=25  # Encoded-media boundary is covered by the real render test.
                job,_=workflow.normalize(raw,root)
                def imported(job,folder,cfg):
                    save(folder/'aligned.json',[cue()]);save(folder/'transcript.json',[cue()])
                    save(folder/'sync.json',{'anchors':[[0,0],[5,5]]})
                def rendered(cfg,folder,preview=False):
                    self.assertTrue(cfg['source_sweeps']);self.assertEqual(cfg['zoom_video'],str(source))
                    video=folder/'test.mp4';video.write_bytes(b'encoded fixture')
                    save(folder/'preview-validation.json',{'output':str(video)})
                flags=Namespace(parallel_stages=False,draft_export=True,automatic_export=True,verify_output=False)
                with patch.object(workflow,'preflight'),patch.object(workflow,'transcripts',side_effect=imported), \
                     patch.object(workflow,'render',side_effect=rendered),patch.object(workflow,'check_branding'), \
                     patch.object(workflow,'OUT',root/'out'),patch('screen_source.timing'), \
                     patch('inline_branding.prepare',return_value=(str(bg),None)), \
                     patch.object(workflow.local,'separate') as separate, \
                     patch.object(workflow.local,'transcribe') as asr, \
                     patch.object(workflow.local,'align') as align, \
                     patch.object(workflow.local,'audit') as audit, \
                     patch.object(workflow.local,'check_timing') as vocal_timing, \
                     patch.object(workflow.separation_guard,'validate') as quality:
                    workflow.execute('run',job,folder,flags)
                for music_only in (separate,asr,align,audit,vocal_timing,quality):music_only.assert_not_called()
                self.assertTrue((root/'out'/ (folder.name+'_Karaoke.mp4')).is_file())

    def test_old_screen_export_is_repaired_once_then_new_export_is_skipped(self):
        import server_batch as server
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'tools').mkdir();media=root/'media';media.mkdir()
            source=media/'Artist - Song.mp4';source.write_bytes(b'source')
            output=media/'karaoke';output.mkdir();old=output/'old.mp4';old.write_bytes(b'old export')
            reports=root/'reports';reports.mkdir()
            identity=hashlib.sha256(source.name.encode()).hexdigest()[:20]
            receipt=reports/(identity+'.json')
            save(receipt,{'status':'exported','source_sha256':server.sha(source),
                'output':str(old),'output_sha256':server.sha(old),'recipe_sha256':'legacy'})
            (root/'karaoke.py').write_text("import os,pathlib\np=pathlib.Path(os.environ['KARAOKE_OUTPUT_DIR']);p.mkdir(parents=True,exist_ok=True);(p/'test-job_Karaoke.mp4').write_bytes(b'new export')\n")
            args=Namespace(language='en',model='htdemucs',threads=2,source_type='zoom',retry_failed=True,
                parallel=False,cleanup_song=True,delivery_mode='automatic')
            with patch.object(server,'ROOT',root),patch('workflow.normalize',return_value=({},root/'work/test-job')), \
                 patch.dict('os.environ',{'KARAOKE_BACKGROUND':'original','KARAOKE_SCREEN_PROFILE':'auto'}):
                self.assertEqual(server.run_one(source,media,output,reports,args),'exported')
                self.assertEqual(read(receipt)['screen_pipeline'],'measured-source-v1')
                self.assertEqual(server.run_one(source,media,output,reports,args),'skipped')
            self.assertEqual(old.read_bytes(),b'old export')

    def test_optional_verification_does_not_retranscribe_karaoke_backing(self):
        import delivery_verification as verification
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);save(root/'transcript.json',[cue()]);save(root/'aligned.json',[cue()])
            save(root/'zoom-import/aligned.json',[cue()])
            cfg={'source_backing':True,'zoom_video':'source.mp4'}
            with patch('screen_source.audit'),patch('screen_source.timing'), \
                 patch('av.open') as media,patch.object(verification,'inputs',return_value={}), \
                 patch.object(verification.subprocess,'run') as model:
                media.return_value.__enter__.return_value.duration=5000000
                result=verification.build(cfg,root)
            model.assert_not_called()
            self.assertIn('Original source backing retained; any vocals already in it remain.',result['limitations'])

    def test_renderer_receives_measured_samples_for_screen_only(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name,data in [('aligned.json',[cue()]),('transcript.json',[cue()]),('sync.json',{'anchors':[[0,0],[5,5]]})]:save(root/name,data)
            cfg={'slug':'test','title':'T','artist':'A','zoom_video':'source.mp4','background':'bg.jpg',
                 'source_sweeps':True,'render':{}}
            with patch('zoom_local_pipeline.subprocess.run') as run:
                run_renderer(cfg,root,root/'out','output.mp4',ass_only=True)
            cmd=run.call_args.args[0]
            self.assertIn('--source-sweep-file',cmd)
            samples=read(cmd[cmd.index('--source-sweep-file')+1])
            self.assertEqual(samples[0]['words'][0]['sweep'],cue()['words'][0]['sweep'])
            cfg.pop('source_sweeps')
            with patch('zoom_local_pipeline.subprocess.run') as run:
                run_renderer(cfg,root,root/'out','output.mp4',ass_only=True)
            self.assertNotIn('--source-sweep-file',run.call_args.args[0])

    def test_missing_measured_sweep_rejected_instead_of_linear_fallback(self):
        from screen_sweep import validate_cues
        bad=cue();bad['words'][0].pop('sweep')
        with self.assertRaisesRegex(ValueError,'sweep'):validate_cues([bad],5,require_sweep=True)

    def test_holds_different_curves_and_offset_are_preserved(self):
        from screen_sweep import sweep_intervals
        from PIL import ImageFont
        from project_runtime import font_file
        font=ImageFont.truetype(str(font_file()),50)
        words=cue()['words'];slow=list(sweep_intervals(words,font,10))
        fast=copy.deepcopy(words);fast[0]['sweep']=[[1.,0.],[1.5,.7],[3.,1.]]
        self.assertNotEqual(slow,list(sweep_intervals(fast,font,10)))
        self.assertEqual(slow[0][:2],(11.,12.5))
        self.assertEqual(slow[0][2],0.)
        self.assertGreater(slow[-1][2],0.)

class ScreenRenderIntegrationTests(unittest.TestCase):
    def test_real_render_keeps_hold_then_colours_and_preserves_audio(self):
        import subprocess
        import os
        import numpy as np
        import av
        from PIL import Image
        from project_runtime import FFMPEG
        from prepare_zoom_local import make_ass
        from zoom_local_pipeline import audio,check_audio
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.wav';bg=root/'bg.png'
            Image.new('RGB',(1920,1080),(20,20,20)).save(bg)
            subprocess.run([str(FFMPEG),'-v','error','-f','lavfi','-i','sine=frequency=440:duration=4',
                '-ac','2',str(source)],check=True,capture_output=True)
            save(root/'aligned.json',[cue()]);save(root/'sync.json',{'anchors':[[0,0],[4,4]]})
            (root/'lyrics.ass').write_text(make_ass([cue()],0,4),encoding='utf-8')
            cfg={'slug':'screen-test','title':'Title','artist':'Artist','zoom_video':str(source),
                 'background':str(bg),'source_sweeps':True,
                 'render':{'intro_seconds':1.,'intro_countdown':True,'fps':10,'video_bitrate':500000,'preset':'veryfast'}}
            with patch.dict(os.environ,{'KARAOKE_RENDER_WORK_DIR':str(root/'render'),'KARAOKE_FFMPEG_THREADS':'2'}):
                run_renderer(cfg,root,root/'out','screen.mp4')
            output=root/'out/screen.mp4'
            with av.open(str(output)) as media:
                self.assertEqual((media.streams.video[0].width,media.streams.video[0].height),(1920,1080))
                self.assertAlmostEqual(media.duration/av.time_base,5,delta=.15)
                frames={}
                for frame in media.decode(video=0):
                    t=round(float(frame.time),1)
                    if t in (2.7,3.9):frames[t]=frame.to_ndarray(format='rgb24')[220:350,700:1200]
            def orange(frame):
                r,g,b=frame[:,:,0].astype(float),frame[:,:,1].astype(float),frame[:,:,2].astype(float)
                return int(((r>180)&(g>60)&(g<210)&(b<80)&(r>g+25)).sum())
            self.assertEqual(orange(frames[2.7]),0,'Source hold must stay white')
            self.assertGreater(orange(frames[3.9]),50,'Measured source progress must paint the lyric')
            result=check_audio(audio(source),audio(output),delay=16000)
            self.assertGreater(result.get('correlation',result.get('corr',0)),.98)

if __name__=='__main__':unittest.main()
