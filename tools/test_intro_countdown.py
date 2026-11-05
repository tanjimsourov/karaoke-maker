import tempfile
import unittest
from pathlib import Path
from PIL import Image,ImageDraw
from intro_countdown import events,logo_without_outer_ring,reference_logo_filter
from zoom_local_pipeline import render_options
from workflow import normalize
from unittest.mock import patch
from intro_countdown import settings


def timestamp(t):
    return f'{t:.2f}'


class IntroTests(unittest.TestCase):
    def test_settings_env_config_precedence_and_validation(self):
        with patch.dict('os.environ',{'KARAOKE_COUNTDOWN_STYLE':'circle','KARAOKE_COUNTDOWN_COLOUR':'#00aaff'}):
            self.assertEqual(settings(),{'countdown_style':'circle','countdown_colour':'#00AAFF'})
            options,args=render_options({'render':{'intro_countdown':True,'countdown_style':'arc','countdown_colour':'#FF8800'}})
            self.assertEqual(options['countdown_style'],'arc')
            self.assertIn('#FF8800',args)
            for style,colour in [('bad','#FFFFFF'),('arc','white'),('circle','#ZZZZZZ')]:
                with self.assertRaises(ValueError):settings(style,colour)

    def test_environment_style_changes_render_fingerprint(self):
        from zoom_local_pipeline import fingerprint
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.write_bytes(b'source')
            for name in ('aligned.json','sync.json','transcript.json'):(root/name).write_text('[]')
            cfg={'vocal_reference':str(source),'zoom_video':str(source),'background':str(source),'render':{}}
            with patch.dict('os.environ',{'KARAOKE_COUNTDOWN_STYLE':'arc','KARAOKE_COUNTDOWN_COLOUR':'#FFFFFF'}):
                first=fingerprint(cfg,root)
            with patch.dict('os.environ',{'KARAOKE_COUNTDOWN_STYLE':'circle','KARAOKE_COUNTDOWN_COLOUR':'#00FF00'}):
                second=fingerprint(cfg,root)
                job,_=normalize({'source':str(source),'title':'Test','artist':'Test'},root)
                self.assertEqual(job['render']['countdown_style'],'circle')
                self.assertEqual(job['render']['countdown_colour'],'#00FF00')
            self.assertNotEqual(first,second)

    def test_white_arc_and_numbers_cover_added_intro(self):
        rows=events(10,30,1920,1080,timestamp)
        numbers=[r for r in rows if r.startswith('Dialogue: 4')]
        self.assertEqual(len(numbers),10)
        self.assertTrue(numbers[0].endswith('}10'))
        self.assertTrue(numbers[-1].endswith('}1'))
        self.assertIn(',0.00,1.00,',numbers[0])
        self.assertIn(',9.00,10.00,',numbers[-1])
        self.assertTrue(all('\\1c&HFFFFFF&' in r for r in rows))
        self.assertFalse(any('\\p1' in r for r in rows))
        graph=reference_logo_filter(10)
        self.assertIn('pad=500:500:40:40',graph)
        self.assertIn('2*PI*T/10.000',graph)
        self.assertIn('between(hypot(X-W/2,Y-H/2),231,239)',graph)
        self.assertIn('if(',graph)
        self.assertEqual(events(0,30,1920,1080,timestamp),[])

    def test_real_render_is_round_closes_and_preserves_custom_logo(self):
        import subprocess,math
        import numpy as np
        from project_runtime import FFMPEG
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'custom.png'
            im=Image.new('RGBA',(100,100));ImageDraw.Draw(im).rectangle((35,35,65,65),fill=(255,0,0,255));im.save(source)
            raw=subprocess.run([str(FFMPEG),'-v','error','-loop','1','-framerate','2','-i',str(source),
                '-vf',reference_logo_filter(2,.4),'-frames:v','5','-f','rawvideo','-pix_fmt','rgba','-'],
                capture_output=True,check=True).stdout
            frames=np.frombuffer(raw,dtype=np.uint8).reshape(5,200,200,4)
            for angle in np.linspace(0,2*math.pi,72,endpoint=False):
                y=round(100+94*math.sin(angle));x=round(100+94*math.cos(angle))
                self.assertGreater(int(frames[0,y,x,3]),240,'Initial ring is not complete and round')
                self.assertEqual(int(frames[4,y,x,3]),0,'Residual ring remains after countdown')
            self.assertEqual(int(frames[2,100,194,3]),0,'Right half should be cleared at halfway')
            self.assertGreater(int(frames[2,100,6,3]),240,'Left half should remain at halfway')
            for frame in frames:
                self.assertEqual(tuple(frame[100,100]),(255,0,0,255),'Logo was changed by the countdown')
            for scale in (1/6,2/3):
                subprocess.run([str(FFMPEG),'-v','error','-i',str(source),
                    '-vf',reference_logo_filter(2,scale),'-frames:v','1','-f','null','-'],
                    capture_output=True,check=True)
            raw=subprocess.run([str(FFMPEG),'-v','error','-loop','1','-framerate','2','-i',str(source),
                '-vf',reference_logo_filter(2,.4,'circle','#00FF00'),'-frames:v','5','-f','rawvideo','-pix_fmt','rgba','-'],
                capture_output=True,check=True).stdout
            frames=np.frombuffer(raw,dtype=np.uint8).reshape(5,200,200,4)
            for index in (0,2,3):
                self.assertEqual(tuple(frames[index,100,194]),(0,255,0,255))
            self.assertEqual(int(frames[4,100,194,3]),0)

    def test_ring_mask_preserves_central_and_original_logo(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'logo.png';out=Path(temp)/'intro.png'
            im=Image.new('RGBA',(100,100));d=ImageDraw.Draw(im)
            d.ellipse((4,4,95,95),outline='white',width=3)
            d.rectangle((30,30,70,70),fill='white');im.save(source)
            before=source.read_bytes();logo_without_outer_ring(source,out)
            self.assertEqual(source.read_bytes(),before)
            result=Image.open(out)
            self.assertEqual(result.getpixel((50,4))[3],0)
            self.assertEqual(result.getpixel((50,50))[3],255)

    def test_shared_renderer_uses_custom_logo_for_intro_and_corner(self):
        import subprocess,sys,uuid,io
        from project_runtime import ROOT,FFMPEG,child_env
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);logo=d/'custom.png'
            Image.new('RGBA',(100,100),(255,0,0,255)).save(logo)
            def ff(*args):
                return subprocess.run([str(FFMPEG),'-v','error','-y',*map(str,args)],capture_output=True,check=True)
            ff('-f','lavfi','-i','color=blue:s=320x180:r=30:d=2','-c:v','libx264',d/'source.mp4')
            ff('-f','lavfi','-i','sine=frequency=440:duration=2','-c:a','pcm_s16le',d/'audio.wav')
            (d/'lyrics.ass').write_text('Dialogue: 0,0:00:00.20,0:00:00.70,Default,,0,0,0,,{\\k50}Test\n')
            env=child_env();env['KARAOKE_LOGO']=str(logo);env['KARAOKE_FFMPEG_THREADS']='2'
            subprocess.run([sys.executable,str(ROOT/'tools/build_bowlnfun_karaoke.py'),
                '--slug','circle_regression_'+uuid.uuid4().hex[:10],'--title','Test','--artist','Test',
                '--source-ass',str(d/'lyrics.ass'),'--audio-file',str(d/'audio.wav'),
                '--background-file',str(d/'source.mp4'),'--output-dir',str(d),'--output-name','render.mp4',
                '--approved-intro','--intro-countdown','--intro-seconds','1','--sync-background',
                '--countdown-style','circle','--countdown-colour','#00FFFF',
                '--canvas','320x180','--fps','30','--preset','veryfast'],env=env,capture_output=True,check=True)
            for when,point in ((.1,(160,55)),(1.5,(297,22))):
                raw=ff('-ss',when,'-i',d/'render.mp4','-frames:v','1','-f','image2pipe','-vcodec','png','-').stdout
                pixel=Image.open(io.BytesIO(raw)).convert('RGB').getpixel(point)
                self.assertTrue(pixel[0]>200 and pixel[1]<50 and pixel[2]<50,(when,pixel))
            raw=ff('-ss','0.1','-i',d/'render.mp4','-frames:v','1','-f','image2pipe','-vcodec','png','-').stdout
            im=Image.open(io.BytesIO(raw)).convert('RGB')
            ring_pixels=[im.getpixel((160,y)) for y in range(14,18)]
            self.assertTrue(any(p[0]<70 and p[1]>180 and p[2]>180 for p in ring_pixels),ring_pixels)

    def test_canonical_jobs_enable_intro_and_allow_opt_out(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'s').write_bytes(b'input')
            base={'source':'s','title':'T','artist':'A'}
            job,folder=normalize(base,root)
            self.assertTrue(job['render']['intro_countdown'])
            _,args=render_options({'render':job['render']})
            self.assertIn('--intro-countdown',args)
            other,other_folder=normalize({**base,'render':{'intro_countdown':False}},root)
            self.assertEqual(folder,other_folder)
            self.assertNotIn('--intro-countdown',render_options({'render':other['render']})[1])
            with self.assertRaisesRegex(ValueError,'intro_countdown'):
                normalize({**base,'render':{'intro_countdown':'yes'}},root)

if __name__=='__main__':unittest.main()
