"""Real render regression: a short source must end on blue, never wrap to red."""
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from project_runtime import ROOT,FFMPEG,child_env

class BackgroundEndTests(unittest.TestCase):
    def test_synced_background_holds_final_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory)
            def ff(*args):
                return subprocess.run([str(FFMPEG),'-v','error','-y',*map(str,args)],check=True,capture_output=True)
            ff('-f','lavfi','-i','color=red:s=320x180:r=24:d=1',
               '-f','lavfi','-i','color=blue:s=320x180:r=24:d=1',
               '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]',
               '-map','[v]','-c:v','libx264',d/'source.mp4')
            ff('-f','lavfi','-i','sine=frequency=440:duration=2.05','-c:a','pcm_s16le',d/'audio.wav')
            (d/'source.ass').write_text('Dialogue: 0,0:00:00.20,0:00:00.70,Default,,0,0,0,,{\\k50}Test\n')
            env=child_env();env['KARAOKE_FFMPEG_THREADS']='2'
            subprocess.run([sys.executable,str(ROOT/'tools/build_bowlnfun_karaoke.py'),
                '--slug','end_regression_'+uuid.uuid4().hex[:10],'--title','Test','--artist','Test',
                '--source-ass',str(d/'source.ass'),'--audio-file',str(d/'audio.wav'),
                '--background-file',str(d/'source.mp4'),'--output-dir',str(d),
                '--output-name','rendered.mp4','--approved-intro','--intro-seconds','0.2',
                '--sync-background','--canvas','320x180','--fps','30','--preset','veryfast'],
                check=True,env=env,capture_output=True)
            # Unobscured corner, decoded through the entire export.
            raw=ff('-i',d/'rendered.mp4','-vf','crop=2:2:0:0','-f','rawvideo','-pix_fmt','rgb24','-').stdout
            self.assertGreater(len(raw),12*60)
            last=raw[-12:]
            self.assertGreater(last[2],last[0]+50,'Final blue background wrapped to red')

            from quick_preview import create
            from zoom_local_pipeline import save,digest,read
            work=d/'job';work.mkdir()
            cfg={'slug':'quick_regression_'+uuid.uuid4().hex[:10],'title':'Test','artist':'Test',
                 'vocal_reference':str(d/'source.mp4'),'background':str(d/'source.mp4'),
                 'zoom_video':str(d/'audio.wav'),'guide_vocal':str(d/'audio.wav'),
                 'preview_versions':True,
                 'render':{'canvas':'320x180','intro_seconds':.2,'fps':30,'crf':14,
                           'sync_background':True,'intro_countdown':False}}
            save(work/'transcript.json',[{'start':.2,'end':.7,'text':'Test'}])
            save(work/'aligned.json',[{'start':.2,'end':.7,'text':'Test',
                                      'words':[{'word':'Test','start':.2,'end':.7}]}])
            save(work/'sync.json',{'anchors':[[0,0],[2.05,2.05]]})
            save(work/'alignment-inputs.json',{'transcript':digest(work/'transcript.json'),
                                               'vocal_reference':digest(d/'source.mp4')})
            save(work/'preview-validation.json',{'sentinel':'full quality preview'})
            before=digest(work/'preview-validation.json')
            first=create(cfg,work,0,1)
            self.assertTrue(Path(first).is_file())
            self.assertEqual(create(cfg,work,0,1),first)
            self.assertEqual(digest(work/'preview-validation.json'),before)
            self.assertFalse((work/'approval.json').exists())

if __name__=='__main__':unittest.main()
