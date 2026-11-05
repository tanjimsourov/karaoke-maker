"""Regression checks for this recovered source, not listening approval."""
import json
import unittest
from compare_zoom_friends import WORK

class FriendsRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (WORK/'local/5/recovered.json').exists():
            raise unittest.SkipTest('Requires locally generated Friends recovery data')
        cls.cues=json.loads((WORK/'local/5/recovered.json').read_text())
    def test_all_screen_tracks(self):
        self.assertEqual(len(self.cues),80)
        self.assertEqual({c['track'] for c in self.cues},(set(range(3,82))-{23})|{85,86})
    def test_opening(self):
        self.assertAlmostEqual(self.cues[0]['start'],8.92)
        self.assertEqual(self.cues[0]['text'],'What would you think')
    def test_positive_ordered_timing(self):
        self.assertTrue(all(w['end']>w['start'] for c in self.cues for w in c['words']))
        self.assertTrue(all(a['end']<=b['start'] for a,b in zip(self.cues,self.cues[1:])))
    def test_no_incomplete_words(self):
        self.assertFalse(any('incomplete' in s or 'empty' in s for c in self.cues for s in c['issues']))

if __name__=='__main__':unittest.main()
