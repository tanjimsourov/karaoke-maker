import unittest
from unittest.mock import patch
from pathlib import Path
import numpy as np
from zoom_local_pipeline import map_time, mapped_segments, suggest_sync, check_audio, render, delivery_folder, ROOT


class SyncTests(unittest.TestCase):
    def test_zoom_delivery_folder(self):
        self.assertEqual(delivery_folder({'output_dir':'out/zoom'}), (ROOT/'out/zoom').resolve())
        with self.assertRaises(ValueError):
            delivery_folder({'output_dir':'out/../../elsewhere'})

    def test_piecewise_drift(self):
        self.assertAlmostEqual(map_time(15, [[0,3],[10,13],[20,24]]), 18.5)

    def test_no_extrapolation(self):
        with self.assertRaises(ValueError):
            map_time(21, [[0,0],[20,20]])

    def test_invalid_anchors(self):
        for anchors in ([[0,0]], [[1,0],[0,1]], [[0,1],[1,0]], [[0,0],[1,float('nan')]]):
            with self.assertRaises(ValueError):
                map_time(.5, anchors)

    def test_missing_word_timing(self):
        with self.assertRaises(ValueError):
            mapped_segments([{'words':[{'word':'unmatched'}]}], [[0,0],[10,10]])

    def test_known_shift(self):
        rng = np.random.default_rng(2)
        x = rng.normal(size=(12,1000))
        x /= np.linalg.norm(x, axis=0)
        y = np.pad(x, ((0,0),(35,0)))
        result = suggest_sync(x,y,max_shift=10)
        self.assertAlmostEqual(result['proposed_offset'],3.5)
        self.assertEqual(result['status'],'proposal_needs_listening')

    def test_silence_not_accepted(self):
        result = suggest_sync(np.zeros((12,1000)),np.zeros((12,1000)),max_shift=10)
        self.assertEqual(result['status'],'manual_sync_required')

    def test_audio_delay(self):
        x = np.random.default_rng(1).normal(size=16000)
        report = check_audio(x, np.pad(x,(48000,0)))
        self.assertAlmostEqual(report['correlation'],1)

    def test_audio_gap_rejected(self):
        x = np.random.default_rng(1).normal(size=16000)
        y = np.pad(x,(48000,0))
        y[50000:55000] = 0
        with self.assertRaises(ValueError):
            check_audio(x,y)

    def test_final_requires_approval(self):
        with patch('zoom_local_pipeline.read', side_effect=FileNotFoundError('approval')):
            with self.assertRaises(FileNotFoundError):
                render({'slug':'Test_Approval_Gate_Not_A_Song'}, Path('unused'))

    def test_stale_approval_rejected(self):
        with patch('zoom_local_pipeline.read', return_value={'fingerprint': 'old'}), \
             patch('zoom_local_pipeline.fingerprint', return_value='new'):
            with self.assertRaisesRegex(ValueError, 'changed since review'):
                render({'slug':'Test_Approval_Gate_Not_A_Song'}, Path('unused'))


if __name__ == '__main__':
    unittest.main()
