"""Small deterministic checks. No model downloads or song processing."""
from pathlib import Path
import copy
import os
import tempfile
import unittest
from unittest.mock import patch
from argparse import Namespace
import numpy as np
from audio_quality import signal_checks, choose, settings, evaluate
from workflow import normalize, lock, execute, ReviewRequired
import workflow
import separation_guard
from project_runtime import load_env, python_in
from zoom_local_pipeline import save, read
from exports import enhanced_lrc
import lyric_editor
import layers
import local_karaoke


class PortableTests(unittest.TestCase):
    def test_media_output_timeline_can_cover_intro_without_negative_song_times(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'poster.png').write_bytes(b'image fixture')
            item={'file':'poster.png','start':0,'end':10,'x':960,'y':540,'timeline':'output'}
            layers.validate({'media':[item]},root)
            _,graph=layers.media_graph([item],3,root,10,1,1,30)
            self.assertIn('between(t,0.000,10.000)',graph)
            self.assertIn('trim=end=10.000',graph)
            item.pop('timeline')
            _,graph=layers.media_graph([item],3,root,10,1,1,30)
            self.assertIn('between(t,10.000,20.000)',graph)
    def test_cpu_retry_changes_threads_without_changing_model_or_job(self):
        cfg={'vocal_reference':'source.mp4','separation_threads':4,'separation':{}}
        with patch.object(local_karaoke,'DEMUCSPY') as py,patch.dict(os.environ,{'KARAOKE_SEPARATION_THREADS':'2'}):
            py.is_file.return_value=True
            command=local_karaoke.separate_command(cfg,Path('job'))
            self.assertEqual(command[command.index('--threads')+1],'2')
            self.assertNotIn('--model',command)
            self.assertEqual(cfg['separation_threads'],4)
        with patch.object(local_karaoke,'DEMUCSPY') as py,patch.dict(os.environ,{'KARAOKE_SEPARATION_THREADS':'0'}):
            py.is_file.return_value=True
            with self.assertRaises(ValueError):local_karaoke.separate_command(cfg,Path('job'))

    def test_highlight_colour_is_forwarded_without_reprocessing(self):
        from zoom_local_pipeline import render_options
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'s').write_bytes(b'x')
            base={'source':'s','title':'T','artist':'A'}
            _,first=normalize(base,root)
            job,second=normalize({**base,'render':{'highlight_colour':'#00FF00'}},root)
            self.assertEqual(first,second)
            options,args=render_options({'render':job['render']})
            self.assertEqual(options['highlight_colour'],'#00FF00')
            self.assertEqual(args[args.index('--highlight-colour')+1],'#00FF00')

    def test_highlight_colour_preserves_template_default_and_rejects_bad_values(self):
        from zoom_local_pipeline import render_options
        _,args=render_options({})
        self.assertNotIn('--highlight-colour',args)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'s').write_bytes(b'x')
            for colour in ['red','#12345','#GG0000',7]:
                with self.assertRaisesRegex(ValueError,'highlight_colour'):
                    normalize({'source':'s','title':'T','artist':'A',
                               'render':{'highlight_colour':colour}},root)

    def test_both_style_options_are_distinct(self):
        parser = local_karaoke.build_parser()
        a = parser.parse_args(['translate','--translation-style','singable'])
        self.assertEqual(a.translation_style, 'singable'); self.assertIsNone(a.style)
        a = parser.parse_args(['edit','--style','size=90'])
        self.assertEqual(a.style,['size=90'])

    def test_env_never_executes_or_overrides_values(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'QC_TEST':'existing'}):
            path = Path(temp)/'.env'; path.write_text('QC_TEST=other\nQC_TEST_LITERAL="$(unsafe)"\n')
            load_env(path)
            self.assertEqual(os.environ['QC_TEST'],'existing')
            self.assertEqual(os.environ['QC_TEST_LITERAL'],'$(unsafe)')

    def test_env_rejects_broken_lines(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'.env'; p.write_text('not a setting')
            with self.assertRaisesRegex(ValueError,'Invalid environment'): load_env(p)

    def test_environment_python_layout(self):
        self.assertEqual(python_in(Path('env')).name, 'python.exe' if os.name=='nt' else 'python')

    def test_job_paths_relative_to_job_not_cwd(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'song.mp4').write_bytes(b'input')
            j, f = normalize({'source':'song.mp4','title':'Test','artist':'A'},root)
            self.assertEqual(j['source'],str((root/'song.mp4').resolve()))
            self.assertEqual(j['render']['intro_seconds'],10)
            self.assertEqual(j['render']['crf'],14)
            self.assertEqual(j['audio_quality']['alternatives'],['uvr'])

    def test_invalid_job_options_do_not_silently_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'s').write_bytes(b'x')
            base={'source':'s','title':'Test','artist':'A'}
            for addition in [{'typo':1},{'mode':'unknown'},{'background':'missing'},
                             {'separation':{'keep_backing_vocals':True}}]:
                with self.assertRaises(ValueError): normalize({**base,**addition},root)

    def test_render_setting_changes_reuse_processing_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'s').write_bytes(b'x')
            base={'source':'s','title':'T','artist':'A'}
            _,first=normalize(base,root)
            _,second=normalize({**base,'render':{'crf':18,'fps':30}},root)
            self.assertEqual(first,second)

    def test_concurrent_job_is_rejected_and_lock_is_released(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            with lock(folder):
                with self.assertRaises(ValueError):
                    with lock(folder): pass
            self.assertFalse((folder/'running.lock').exists())

    def test_clipping_duration_and_missing_music_are_flags(self):
        source=np.full((16000*3,2),.2,np.float32)
        silence=signal_checks(source,source*0)
        self.assertIn('silent_output',silence['reject_reasons'])
        self.assertIn('severe_energy_loss',silence['reject_reasons'])
        self.assertIn('severe_energy_loss',signal_checks(source,source*.015)['reject_reasons'])
        self.assertTrue(silence['flags'])
        self.assertIn('clipping',signal_checks(source,source*6)['reject_reasons'])
        self.assertIn('duration_mismatch',signal_checks(source,source[:-3200])['reject_reasons'])

    def test_antiphase_stereo_is_not_silence(self):
        t=np.arange(16000*2)/16000
        x=.2*np.sin(2*np.pi*440*t)
        stereo=np.column_stack([x,-x])
        checks=signal_checks(stereo,stereo)
        self.assertEqual(checks['reject_reasons'],[])
        self.assertAlmostEqual(checks['energy_ratio'],1)

    def test_nonfinite_candidate_is_rejected(self):
        x=np.ones((16000,2),np.float32)
        y=x.copy();y[0,0]=np.nan
        with self.assertRaises(ValueError):signal_checks(x,y)

    def test_quiet_gap_is_located(self):
        x=np.full((16000*4,2),.2,np.float32);y=x.copy();y[16000:32000]=0
        flags=signal_checks(x,y)['flags']
        gap=next(f for f in flags if f['kind']=='new_quiet_gap')
        self.assertAlmostEqual(gap['start'],1);self.assertAlmostEqual(gap['end'],2)

    def test_rejecting_destroyed_music_precedes_lower_voice_score(self):
        def item(name, rejected, score):
            return {'name':name,'report':{'signal':{'reject_reasons':rejected,'flags':[]},
                'screening_complete':True,'asr':[],'detector':{'windows':[{'voice_score':score,'flagged':score>.25}]}}}
        good=item('music',[],.3);bad=item('silent',['severe_energy_loss'],0)
        self.assertEqual(choose([bad,good])['name'],'music')
        self.assertIsNone(choose([bad]))

    def test_unavailable_classifier_is_not_treated_as_clean(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);a=root/'a';b=root/'b';a.write_bytes(b'a');b.write_bytes(b'b')
            x=np.full((16000,2),.2,np.float32)
            with patch('audio_quality.decode',return_value=x), \
                 patch('audio_quality.VoiceDetector',side_effect=RuntimeError('not available')):
                result=evaluate(a,b,root/'scan',{'asr':False})
            self.assertFalse(result['screening_complete'])
            self.assertEqual(result['status'],'needs_human_listening')

    def test_clear_classifier_still_requires_listening(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);a=root/'a';b=root/'b';a.write_bytes(b'a');b.write_bytes(b'b')
            x=np.full((16000,2),.2,np.float32)
            with patch('audio_quality.decode',return_value=x),patch('audio_quality.VoiceDetector') as detector:
                detector.return_value.scan.return_value=[]
                result=evaluate(a,b,root/'scan',{'asr':False})
            self.assertTrue(result['screening_complete'])
            self.assertEqual(result['status'],'needs_human_listening')

    def test_incomplete_screening_is_retried_after_models_become_available(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);a=root/'a';b=root/'b';a.write_bytes(b'a');b.write_bytes(b'b')
            x=np.full((16000,2),.2,np.float32)
            with patch('audio_quality.decode',return_value=x), \
                 patch('audio_quality.VoiceDetector',side_effect=RuntimeError('not cached')) as detector:
                evaluate(a,b,root/'scan',{'asr':False})
                evaluate(a,b,root/'scan',{'asr':False})
                self.assertEqual(detector.call_count,2)

    def test_retries_always_read_original_and_are_bounded(self):
        from types import SimpleNamespace
        from audio_quality import MODEL,REVISION
        from zoom_local_pipeline import digest
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';base=root/'baseline'
            source.write_bytes(b'original');base.write_bytes(b'baseline')
            commands=[]
            def worker(command,**kwargs):
                commands.append(command)
                self.assertEqual(command[command.index('--source')+1],str(source))
                out=Path(command[command.index('--output')+1]);out.mkdir(parents=True,exist_ok=True)
                if command[1].endswith('audio_quality.py'):
                    candidate=Path(command[command.index('--candidate')+1])
                    score=.8 if candidate==base else .1
                    save(out/'quality.json',{'binding':{'source':digest(source),'candidate':digest(candidate),
                        'code':digest(workflow.ROOT/'tools/audio_quality.py'),'detector':MODEL,'revision':REVISION},
                        'signal':{'reject_reasons':[],'flags':[]},'asr':[], 'screening_complete':True,
                        'detector':{'windows':[{'flagged':score>.25,'voice_score':score}]},
                        'flags':[{'start':0,'end':1}] if score>.25 else []})
                else:(out/'instrumental.wav').write_bytes(b'alternative')
                return SimpleNamespace(returncode=0)
            with patch('separation_guard.subprocess.run',side_effect=worker), \
                 patch('separation_guard.review_clips',return_value=[]):
                result=separation_guard.run(source,base,root/'quality',{'alternatives':['uvr','roformer'],'asr':False})
            self.assertEqual(len(commands),5) # baseline scan + 2 separate/scan pairs
            self.assertIn(result['selected']['name'],['uvr','roformer'])
            separation_guard.validate(source,root/'quality')

    def test_final_delivery_copies_exact_reviewed_bytes_and_refuses_collision(self):
        from zoom_local_pipeline import digest
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'work';folder.mkdir();video=root/'preview.mp4';video.write_bytes(b'reviewed bytes')
            cfg={'slug':'Test','title':'T','artist':'A'};job={'source':'fixture'}
            validation={'output':str(video),'sha256':digest(video)}
            save(folder/'full-review.json',{'fingerprint':{'fixture':True}})
            with patch('workflow.preflight'),patch('workflow.context',return_value=cfg), \
                 patch('workflow.require_lyrics'),patch('workflow.separation_guard.validate'), \
                 patch('workflow.fingerprint',return_value={'fixture':True}), \
                 patch('workflow.verify_preview',return_value=validation),patch.object(workflow,'OUT',root/'out'):
                execute('render',job,folder,Namespace())
                final=root/'out/Test_Karaoke.mp4'
                self.assertEqual(final.read_bytes(),video.read_bytes())
                final.write_bytes(b'existing user file')
                with self.assertRaises(FileExistsError):execute('render',job,folder,Namespace())
                self.assertEqual(final.read_bytes(),b'existing user file')

    def test_quality_rejects_unbounded_or_invalid_settings(self):
        for cfg in [{'threads':True},{'threads':100},{'step_seconds':11},
                    {'max_asr_windows':99},{'alternatives':['uvr','uvr']},{'typo':1}]:
            with self.assertRaises(ValueError):settings(cfg)

    def test_no_automatic_human_signoff(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);job={'source':'not processed'}
            flags=Namespace(listened=False,checked_lyrics=False,reviewed_audio=False,reviewed_timing=False)
            with patch('workflow.preflight'),patch('workflow.context',return_value={}),patch('workflow.require_lyrics'):
                with self.assertRaises(ReviewRequired):execute('approve',job,folder,flags)
            self.assertFalse((folder/'full-review.json').exists())

    def test_lrc_applies_intro_and_export_trim(self):
        rows=[{'words':[{'word':'before','start':0,'end':1},
                        {'word':'hello','start':5,'end':6},{'word':'after','start':20,'end':21}]}]
        result=enhanced_lrc(rows,'T','A',offset=10,start=14,end=18)
        self.assertIn('<00:01.00>hello',result)
        self.assertNotIn('before',result);self.assertNotIn('after',result)

    def test_nonfinite_editor_and_layer_values_are_rejected(self):
        with self.assertRaises(ValueError):
            lyric_editor.validate([{'words':[{'word':'x','start':float('nan'),'end':1}]}])
        with self.assertRaises(ValueError):
            layers.validate({'texts':[{'text':'x','start':0,'x':float('inf')}]},Path('.'))

    def test_media_rotation_keyframes_reach_filter_graph(self):
        _,graph=layers.media_graph([{'file':'image.png','start':0,'width':100,
            'keyframes':[{'t':0,'rotation':0},{'t':1,'rotation':90}]}],3,Path('.'),10,1,1,25)
        self.assertIn('rotate=angle=',graph)
        self.assertIn('90.000',graph)


if __name__=='__main__':unittest.main()
