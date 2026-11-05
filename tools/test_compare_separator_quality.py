import unittest
from compare_separator_quality import common_factors,fixed_asr_windows,source_matching_phrases,control_summary


class ComparisonTests(unittest.TestCase):
    def test_undo_protective_gains_without_per_track_loudness_matching(self):
        factors=common_factors([.8,.4,.2],[1.,.5,.25])
        self.assertEqual(factors,[1.,2.,4.])
        self.assertAlmostEqual(.4*factors[1],.2*factors[2])

    def test_shared_gain_keeps_every_track_below_full_scale(self):
        peaks=[.9,.8,.4];gains=[1.,.4,.5]
        factors=common_factors(peaks,gains)
        self.assertLessEqual(max(p*f for p,f in zip(peaks,factors)),.9900001)
        self.assertAlmostEqual(factors[1]*gains[1],factors[2]*gains[2])

    def test_invalid_gain_rejected(self):
        with self.assertRaises(ValueError):common_factors([1.],[0.])

    def test_shared_asr_windows_cover_both_models_and_track_bounds(self):
        reports=[{'detector':{'windows':[{'start':30.,'voice_score':.8}]}},
                 {'detector':{'windows':[{'start':150.,'voice_score':.9}]}}]
        windows=fixed_asr_windows(reports,195.)
        starts=[w['start'] for w in windows]
        self.assertEqual(len(starts),6)
        self.assertIn(30.,starts);self.assertIn(150.,starts)
        self.assertIn(0.,starts);self.assertIn(185.,starts)
        self.assertTrue(all(0<=w['start']<w['end']<=195. for w in windows))

    def test_source_matches_require_shared_phrase_and_time(self):
        row={'start':20.,'end':25.,'text':'The same test phrase.'}
        self.assertEqual(len(source_matching_phrases([row],[{**row,'text':'the SAME test phrase'}])),1)
        self.assertEqual(source_matching_phrases([row],[{**row,'start':100.,'end':105.}]),[])
        self.assertEqual(source_matching_phrases([row],[{**row,'text':'a different unrelated sentence'}]),[])

    def test_empty_original_asr_cannot_be_used_as_positive_control(self):
        q={'screening_complete':True,'detector':{'windows':[{'flagged':True,'voice_score':.8}]*4}}
        result=control_summary(q,{'complete':True,'evidence':[]})
        self.assertTrue(result['voice_control_responded'])
        self.assertFalse(result['asr_control_responded'])

    def test_insensitive_classifier_cannot_pass_positive_control(self):
        q={'screening_complete':True,'detector':{'windows':[{'flagged':False,'voice_score':.1}]*4}}
        result=control_summary(q,{'complete':True,'evidence':[]})
        self.assertFalse(result['voice_control_responded'])


if __name__=='__main__':unittest.main()
