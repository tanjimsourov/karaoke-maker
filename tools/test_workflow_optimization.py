import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from project_runtime import FFMPEG
from audio_cache import decode,scope
from phrase_alignment import incremental
from replace_backing import replace,video_hash
from model_reuse import get,clear

class OptimizationTests(unittest.TestCase):
    def test_failed_stage_still_records_measurement(self):
        from stage_metrics import measure
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'test failure'):
                with measure(Path(temp),'alignment'):raise ValueError('test failure')
            row=json.loads((Path(temp)/'stage-metrics.jsonl').read_text())
            self.assertEqual(row['outcome'],'interrupted_or_failed')
            self.assertGreaterEqual(row['wall_seconds'],0)

    def test_gpu_export_is_explicit_and_does_not_change_x264_default(self):
        from zoom_local_pipeline import render_options
        _,default=render_options({})
        self.assertNotIn('--encoder',default)
        _,gpu=render_options({'render':{'encoder':'h264_nvenc','nvenc_cq':22}})
        self.assertEqual(gpu[gpu.index('--encoder')+1],'h264_nvenc')
        self.assertEqual(gpu[gpu.index('--nvenc-cq')+1],'22')

    def test_decoded_audio_reused_and_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);source=d/'s.wav'
            subprocess.run([str(FFMPEG),'-v','error','-f','lavfi','-i','sine=frequency=391:duration=1',str(source)],check=True)
            direct=decode(source)
            with scope(d/'cache'):
                first=decode(source)
                self.assertTrue(np.allclose(first,direct,atol=1e-6))
                with patch('audio_cache.subprocess.run',side_effect=AssertionError('decode repeated')):
                    self.assertTrue(np.array_equal(first,decode(source)))
                master=next((d/'cache').glob('*/master.wav'));master.write_bytes(b'corrupt')
                with self.assertRaisesRegex(ValueError,'corrupted'):decode(source)

    def test_only_changed_phrase_is_realigned(self):
        with tempfile.TemporaryDirectory() as temp:
            calls=[]
            def align(s):calls.append(s['text']);return [{**s,'words':[{'word':s['text'],'start':s['start'],'end':s['end']}]}]
            rows=[{'start':0,'end':1,'text':'first'},{'start':2,'end':3,'text':'second'}]
            incremental(rows,{'audio':'a'},temp,align)
            rows[1]['text']='corrected'
            output,report=incremental(rows,{'audio':'a'},temp,align)
            self.assertEqual(calls,['first','second','corrected'])
            self.assertEqual(report['reused_phrases'],1)
            self.assertEqual(output[0]['text'],'first')
            _,report=incremental(rows,{'audio':'changed'},temp,align)
            self.assertEqual(report['aligned_phrases'],2)

    def test_warm_models_are_reused_and_family_is_bounded(self):
        clear()
        with patch.dict(os.environ,{'KARAOKE_KEEP_MODELS':'1'}):
            first=get('asr','a',object)
            self.assertIs(get('asr','a',object),first)
            get('alignment','b',object)
            self.assertIsNot(get('asr','a',object),first)
        clear()

    def test_audio_only_replacement_preserves_encoded_picture(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp)
            subprocess.run([str(FFMPEG),'-v','error','-f','lavfi','-i','testsrc2=s=320x180:r=30:d=3',
                '-f','lavfi','-i','sine=frequency=440:duration=3','-c:v','libx264','-preset','veryfast',
                '-c:a','aac',str(d/'video.mp4')],check=True)
            subprocess.run([str(FFMPEG),'-v','error','-f','lavfi','-i','sine=frequency=220:duration=3',str(d/'backing.wav')],check=True)
            r=replace(d/'video.mp4',d/'backing.wav',d/'result.mp4')
            self.assertTrue(r['video_stream_unchanged'])
            self.assertEqual(video_hash(d/'video.mp4'),video_hash(d/'result.mp4'))
            self.assertGreater(r['audio_check']['correlation'],.98)
            with self.assertRaises(FileExistsError):replace(d/'video.mp4',d/'backing.wav',d/'result.mp4')

if __name__=='__main__':unittest.main()
