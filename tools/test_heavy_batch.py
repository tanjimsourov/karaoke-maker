from pathlib import Path
import tempfile
import unittest
from unittest import mock
import numpy as np
from scipy.io import wavfile
from heavy_batch import DEPS,ready_stages,admitted,GIB
from isolated_ft import combine_components,SOURCES,SIGNATURES,component_folder,merge
from zoom_local_pipeline import save,digest,read
from project_runtime import ffmpeg_thread_args


class BatchTests(unittest.TestCase):
    def test_component_chain_and_independent_post_stages(self):
        stages={name:{'status':'pending'} for name in DEPS}
        self.assertEqual(set(ready_stages(stages)),{'background','component-0'})
        stages['component-0']['status']='completed'
        self.assertIn('component-1',ready_stages(stages))
        self.assertNotIn('component-2',ready_stages(stages))
        for name in ['component-1','component-2','component-3','merge']:stages[name]['status']='completed'
        self.assertTrue({'audio-qc','vocal-asr'}.issubset(ready_stages(stages)))
        self.assertNotIn('render',ready_stages(stages))

    def test_memory_admission_reserves_not_yet_allocated_memory(self):
        active=[{'memory':3*GIB,'rss':GIB,'cpu':3,'heavy':True}]
        candidate={'memory':3*GIB,'cpu':3,'heavy':True}
        self.assertTrue(admitted(8*GIB,16*GIB,active,candidate))
        self.assertFalse(admitted(5*GIB,16*GIB,active,candidate))
        active*=2
        self.assertFalse(admitted(12*GIB,16*GIB,active,candidate))

    def test_diagonal_bag_reuses_each_source_from_its_original_component(self):
        components=[{name:np.full((8,2),10*i+k,dtype=np.float32) for k,name in enumerate(SOURCES)} for i in range(4)]
        combined=combine_components(components,np.eye(4))
        for k,name in enumerate(SOURCES):np.testing.assert_array_equal(combined[name],components[k][name])
        np.testing.assert_array_equal(combined['instrumental'],sum(combined[n] for n in SOURCES[:3]))
        with self.assertRaises(ValueError):combine_components(components,np.zeros((4,4)))

    def test_encoder_thread_override_is_optional_and_validated(self):
        with mock.patch.dict('os.environ',{},clear=True):self.assertEqual(ffmpeg_thread_args(),[])
        with mock.patch.dict('os.environ',{'KARAOKE_FFMPEG_THREADS':'3'}):self.assertEqual(ffmpeg_thread_args(),['-threads:v','3'])
        with mock.patch.dict('os.environ',{'KARAOKE_FFMPEG_THREADS':'0'}):
            with self.assertRaises(ValueError):ffmpeg_thread_args()

    def test_real_wav_merge_undoes_component_gain_and_checks_rng_chain(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.wav';out=root/'stems'
            wavfile.write(source,44100,np.zeros((64,2),np.float32))
            bag=root/'bag.yaml';bag.write_text('fixture')
            checkpoints={}
            previous=None
            for i,sig in enumerate(SIGNATURES):
                checkpoint=root/(sig+'.safetensors');checkpoint.write_bytes(sig.encode());checkpoints[sig]=checkpoint
                folder=component_folder(out,i);folder.mkdir(parents=True)
                files={}
                for k,name in enumerate((*SOURCES,'instrumental')):
                    path=folder/(name+'.wav');wavfile.write(path,44100,np.full((64,2),(.01*(i+1)+.001*k)*.5,np.float32));files[path.name]=digest(path)
                rng=folder/'random-state-after.json';save(rng,{'state':i})
                settings={'source_sha256':digest(source),'model':'htdemucs_ft','start':0,'seconds':None,
                    'shifts':1,'overlap':.5,'ensemble':None,'keep_backing':None,
                    'component':{'index':i,'signature':sig,'bag_sha256':digest(bag),'checkpoint_sha256':digest(checkpoint)}}
                settings.update({'shift_seed':0} if i==0 else {'random_state_in_sha256':digest(previous)})
                save(folder/'separation.json',{'settings':settings,'files':files,'common_gain':.5,
                    'is_intermediate':True,'is_excerpt':False,'model_sources':list(SOURCES),'elapsed_seconds':1.,
                    'runtime':{'random_state_after_sha256':digest(rng)}})
                previous=rng
            fixture={'models':SIGNATURES,'weights':np.eye(4).tolist()}
            with mock.patch('isolated_ft.bag_definition',return_value=(bag,fixture)),mock.patch('isolated_ft.hf_hub_download',side_effect=lambda repo,name,**kw:checkpoints[name.split('.')[0]]):
                merge(source,out)
            report=read(out/'separation.json');self.assertFalse(report['is_intermediate'])
            sr,samples=wavfile.read(out/'instrumental.wav')
            self.assertEqual(sr,44100);np.testing.assert_allclose(samples,.063,atol=1e-7)
            self.assertEqual(report['settings']['model'],'htdemucs_ft')


if __name__=='__main__':unittest.main()
