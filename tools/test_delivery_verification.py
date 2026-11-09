import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import delivery_verification as v


class DeliveryTests(unittest.TestCase):
    def fixture(self):
        words=[{'word':'Hello','start':1.,'end':1.5,'score':.9},
               {'word':'world','start':1.6,'end':2.,'score':.9}]
        return ([{'text':'Hello world'}],[{'text':'Hello world','words':words}],
                {'segments':[{'text':'Hello world','words':[dict(w) for w in words]}]})

    def test_agreement_is_not_approval(self):
        self.assertEqual(v.compare(*self.fixture(),3,{}),[])
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):v.require_approved({},Path(d))

    def test_bad_lyrics_and_shifted_word_are_flagged(self):
        t,a,r=self.fixture();r['segments'][0]['text']='Hello friend'
        r['segments'][0]['words'][0]['start']=.2
        kinds={i['kind'] for i in v.compare(t,a,r,3,{})}
        self.assertIn('lyric_disagreement',kinds);self.assertIn('timing_disagreement',kinds)

    def test_missing_and_nonfinite_timing_are_hard_failures(self):
        t,a,r=self.fixture();a[0]['words'][0]['start']=float('nan');a[0]['words'].pop()
        issues=v.compare(t,a,r,3,{})
        self.assertTrue(any(i['kind']=='missing_word_timing' and i['must_fix'] for i in issues))
        self.assertTrue(any(i['kind']=='invalid_word_timing' and i['must_fix'] for i in issues))

    def test_audio_damage_is_not_approved_by_no_asr_words(self):
        issues=v.compare(*self.fixture(),3,{'signal':{'reject_reasons':['silent_output']},'flags':[]})
        self.assertTrue(any(i['kind']=='audio_rejected' and i['must_fix'] for i in issues))

    def test_changed_media_invalidates_report(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);v.write(p/'delivery-verification.json',{'bindings':{'video':'old'}})
            with patch.object(v,'inputs',return_value={'video':'new'}):
                with self.assertRaisesRegex(ValueError,'stale'):v.require_current({},p)

    def test_each_issue_needs_named_explanation_and_matching_report(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            report={'bindings':{},'issues':[{'id':'lyric-1','must_fix':False}]}
            v.write(p/'delivery-verification.json',report)
            decisions={'report_sha256':v.sha(p/'delivery-verification.json'),'reviewer':'Actual reviewer',
                       'checked_full_lyrics':True,'checked_full_highlighting':True,
                       'listened_full_instrumental':True,'compared_instrument_preservation':True,
                       'issues':{}}
            target=p/'decisions.json';v.write(target,decisions)
            with patch.object(v,'inputs',return_value={}):
                with self.assertRaisesRegex(ValueError,'Unresolved'):v.approve({},p,target)
                decisions['issues']={'lyric-1':{'accepted_after_review':True,'reason':'Compared exact phrase against source.'}}
                v.write(target,decisions);v.approve({},p,target);v.require_approved({},p)
                report['issues'][0]['must_fix']=True;v.write(p/'delivery-verification.json',report)
                with self.assertRaisesRegex(ValueError,'another verification'):v.require_approved({},p)

    def test_hard_errors_cannot_be_waived(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);report={'bindings':{},'issues':[{'id':'bad-1','must_fix':True}]}
            v.write(p/'delivery-verification.json',report)
            v.write(p/'decisions.json',{'report_sha256':v.sha(p/'delivery-verification.json'),'reviewer':'Reviewer',
                'checked_full_lyrics':True,'checked_full_highlighting':True,'listened_full_instrumental':True,
                'compared_instrument_preservation':True,'issues':{'bad-1':{'accepted_after_review':True,'reason':'ignore'}}})
            with patch.object(v,'inputs',return_value={}):
                with self.assertRaisesRegex(ValueError,'Fix and rerun'):v.approve({},p,p/'decisions.json')


if __name__=='__main__':unittest.main()
