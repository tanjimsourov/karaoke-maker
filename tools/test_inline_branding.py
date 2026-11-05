import tempfile
import unittest
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import patch
from inline_branding import masks_from_report, filters, prepare
from zoom_local_pipeline import save, digest


class InlineBrandingTests(unittest.TestCase):
    def test_real_render_cleans_source_before_intro_offset(self):
        from project_runtime import ROOT, FFMPEG, child_env
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp)
            def ff(*args):
                return subprocess.run([str(FFMPEG),'-v','error','-y',*map(str,args)],check=True,capture_output=True)
            ff('-f','lavfi','-i','color=gray:s=320x180:r=30:d=2',
               '-vf',"drawbox=x=20:y=20:w=40:h=20:color=red:t=fill:enable='between(t,0.5,1.2)'",
               '-c:v','libx264',d/'source.mp4')
            ff('-f','lavfi','-i','sine=frequency=440:duration=2','-c:a','pcm_s16le',d/'audio.wav')
            (d/'source.ass').write_text('Dialogue: 0,0:00:00.20,0:00:00.70,Default,,0,0,0,,{\\k50}Test\n')
            save(d/'plan.json',{'source_sha256':digest(d/'source.mp4'),'masks':[[18,18,44,24,.5,1.2]]})
            env=child_env();env['KARAOKE_FFMPEG_THREADS']='2'
            subprocess.run([sys.executable,str(ROOT/'tools/build_bowlnfun_karaoke.py'),
                '--slug','inline_test_'+uuid.uuid4().hex[:8],'--title','Test','--artist','Test',
                '--source-ass',str(d/'source.ass'),'--audio-file',str(d/'audio.wav'),
                '--background-file',str(d/'source.mp4'),'--branding-plan',str(d/'plan.json'),
                '--output-dir',str(d),'--output-name','rendered.mp4','--approved-intro',
                '--intro-seconds','.2','--sync-background','--canvas','320x180','--fps','30',
                '--preset','veryfast','--crf','14'],check=True,env=env,capture_output=True)
            raw=ff('-ss','0.9','-i',d/'rendered.mp4','-frames:v','1','-vf','crop=2:2:30:30',
                   '-f','rawvideo','-pix_fmt','rgb24','-').stdout
            self.assertEqual(len(raw),12)
            self.assertLess(abs(raw[0]-raw[2]),30,'Red source mark remains after inline cleanup')

    def test_unlocated_or_incomplete_scan_cannot_render(self):
        for report in ({'complete':False,'hits':[]},{'complete':True,'hits':[{'time':1}]}):
            with self.assertRaises(ValueError):masks_from_report(report)

    def test_source_coordinates_and_time_are_preserved(self):
        report={'complete':True,'hits':[{'time':35,'scan_size':[960,540],
            'frame_size':[1920,1080],'credit_box':[100,400,200,450]}]}
        self.assertEqual(masks_from_report(report),[[188,788,224,124,33.5,36.5]])

    def test_plan_checks_source_and_never_encodes(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);source=d/'source.mp4';source.write_bytes(b'original')
            def scan(src,report):save(report,{'complete':True,'hits':[]})
            with patch('branding_guard.scan',side_effect=scan),patch('subprocess.run',side_effect=AssertionError('Unexpected encode')):
                background,plan=prepare(source,d/'plan')
            self.assertEqual(background,str(source));self.assertEqual(filters(source,plan),'')
            source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'source changed'):filters(source,plan)

    def test_invalid_filter_input_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);source=d/'s';source.write_bytes(b's')
            for masks in ([[1,1,20,20,2,1]],[[1,1,20,20,0,float('nan')]]):
                save(d/'plan.json',{'source_sha256':digest(source),'masks':masks})
                with self.assertRaises(ValueError):filters(source,d/'plan.json')


if __name__=='__main__':unittest.main()
