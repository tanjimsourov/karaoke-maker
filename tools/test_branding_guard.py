import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
import numpy as np
from unittest.mock import MagicMock
from branding_guard import matches,scan,BrandingDetected,credit_box
from workflow import check_branding,ReviewRequired


class BrandingTests(unittest.TestCase):
    def test_identical_samples_reuse_inference_but_preserve_every_hit_time(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'v.mp4';p.write_bytes(b'fixture');report=Path(temp)/'r.json'
            frames=[]
            for t in range(30):
                frame=Mock();frame.time=float(t)
                frame.to_ndarray.return_value=np.zeros((600,800,3),dtype=np.uint8);frames.append(frame)
            container=MagicMock();container.__enter__.return_value=container
            container.decode.return_value=iter(frames)
            engine=Mock(return_value=([([[0,0],[100,0],[100,20],[0,20]],'Xtendamix',.9)],None))
            with patch('branding_guard.av.open',return_value=container):
                with self.assertRaises(BrandingDetected):scan(p,report,engine=engine)
            import json
            result=json.loads(report.read_text())
            self.assertEqual(engine.call_count,1)
            self.assertEqual(result['sampled_frames'],30)
            self.assertEqual(result['reused_identical_samples'],29)
            self.assertEqual([h['time'] for h in result['hits']],list(range(30)))

    def test_interrupted_scan_resumes_saved_frame_without_claiming_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'v.mp4';p.write_bytes(b'fixture');report=Path(temp)/'r.json'
            frames=[]
            for t in (0.,1.):
                frame=Mock();frame.time=t;frame.to_ndarray.return_value=np.full((600,800,3),int(t),dtype=np.uint8);frames.append(frame)
            container=MagicMock();container.__enter__.return_value=container
            container.decode.side_effect=lambda **kw:iter(frames)
            with patch('branding_guard.av.open',return_value=container):
                with self.assertRaises(MemoryError):
                    scan(p,report,engine=Mock(side_effect=[([],None),MemoryError('test allocation failure')]))
                import json
                self.assertFalse(json.loads(report.read_text())['complete'])
                engine=Mock(return_value=([],None));result=scan(p,report,engine=engine)
                self.assertTrue(result['complete']);self.assertEqual(result['sampled_frames'],2)
                self.assertEqual(engine.call_count,1)

    def test_known_source_marks_and_ordinary_karaoke(self):
        for text in ['XtendaMix','XTENDA MIX','Universal Music','Independent','© 2026','All rights reserved']:
            self.assertTrue(matches(text),text)
        self.assertEqual(matches('KARAOKE REI AMI 2Loud'),[])

    def test_known_mark_blocks_and_cannot_reuse_stale_clean_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'frame.png';report=Path(temp)/'scan.json'
            Image.new('RGB',(800,600),'black').save(p)
            engine=Mock(return_value=([],None))
            self.assertTrue(scan(p,report,engine=engine)['complete'])
            scan(p,report,engine=Mock(side_effect=AssertionError('Cached result not reused')))
            Image.new('RGB',(800,600),'red').save(p)
            engine.return_value=([([[0,0],[100,0],[100,20],[0,20]],'Xtendamix',.95)],None)
            with self.assertRaises(BrandingDetected):scan(p,report,engine=engine)
            with self.assertRaises(BrandingDetected):scan(p,report,engine=engine)

    def test_gate_does_not_treat_missing_scanner_as_clean(self):
        with patch('branding_guard.scan',side_effect=ImportError('Missing OCR')):
            with self.assertRaises(ImportError):check_branding('video','report')
        with patch('branding_guard.scan',side_effect=BrandingDetected('Xtendamix remains')):
            with self.assertRaises(ReviewRequired):check_branding('video','report')

    def test_separate_ocr_words_are_combined(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'f.png';Image.new('RGB',(800,600)).save(p)
            rows=[([[0,0],[10,0],[10,10],[0,10]],word,.9) for word in ['Xtenda','Mix']]
            with self.assertRaises(BrandingDetected):
                scan(p,Path(temp)/'r.json',engine=Mock(return_value=(rows,None)))

    def test_caption_cleanup_includes_artist_title_and_label(self):
        def row(y,text):return ([[145,y],[400,y],[400,y+35],[145,y+35]],text,.9)
        rows=[row(730,'Bad Times'),row(778,'Imael Angel'),row(826,'Independent'),row(874,'Xtendamix')]
        box=credit_box(rows,rows[-1][0],1920,1080)
        self.assertEqual(box,[145.,730.,400.,909.])

    def test_delivery_verification_invokes_branding_gate(self):
        from workflow import verify_preview
        with patch('workflow.read',return_value={'fingerprint':'same','output':'video','sha256':'hash'}), \
             patch('workflow.fingerprint',return_value='same'),patch('workflow.digest',return_value='hash'), \
             patch('workflow.check_branding',side_effect=ReviewRequired('Mark remains')) as gate, \
             patch('pathlib.Path.stat',return_value=type('Stat',(),{'st_size':1})()):
            with self.assertRaisesRegex(ReviewRequired,'Mark remains'):
                verify_preview({},Path('job'))
            gate.assert_called_once()

if __name__=='__main__':unittest.main()
