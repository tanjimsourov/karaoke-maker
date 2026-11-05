import json
import re
import unittest
from pathlib import Path
from recover_zoom_screen import word_ranges

ROOT=Path(__file__).resolve().parents[1]

class ScreenRecoveryTests(unittest.TestCase):
    def test_restored_spaces_keep_character_positions(self):
        best={'letters':list('AndIsay'),'chars':[[[i*10,0],[i*10+9,0],[i*10+9,30],[i*10,30]] for i in range(7)]}
        self.assertEqual(word_ranges(best,0,70,'And I say'),[('And',0,29),('I',30,39),('say',40,69)])

    def test_hyphens_have_separate_sweep_intervals(self):
        best={'letters':list('heyyeah'),'chars':[[[i*10,0],[i*10+9,0],[i*10+9,30],[i*10,30]] for i in range(7)]}
        self.assertEqual([v[0] for v in word_ranges(best,0,70,'hey-yeah')],['hey-','yeah'])

    @unittest.skipUnless(all((ROOT/f'work/zoom_screen/{k}/recovered.json').exists() for k in (0,1)),
                         'Historical song-specific fixtures are not bundled with the portable project')
    def test_expected_lines_and_no_dropped_words(self):
        for k,count in [(0,79),(1,82)]:
            cues=json.loads((ROOT/f'work/zoom_screen/{k}/recovered.json').read_text(encoding='utf-8'))
            self.assertEqual(len(cues),count)
            for c in cues:
                self.assertFalse(any('incomplete' in x or 'empty' in x for x in c['issues']))
                self.assertEqual(re.sub(r'[^\w]','',c['text']),re.sub(r'[^\w]','',''.join(w['word'] for w in c['words'])))

    @unittest.skipUnless(all((ROOT/f'work/zoom_screen/{k}/reviewed.ass').exists() for k in (0,1)),
                         'Historical song-specific fixtures are not bundled with the portable project')
    def test_ass_positive_and_exact_timing_totals(self):
        def time(s):
            h,m,s=s.split(':');return round((int(h)*3600+int(m)*60+float(s))*100)
        for k in (0,1):
            previous=0
            for row in (ROOT/f'work/zoom_screen/{k}/reviewed.ass').read_text(encoding='utf-8').splitlines():
                if not row.startswith('Dialogue:'):continue
                f=row.split(',',9);start,end=time(f[1]),time(f[2]);durations=list(map(int,re.findall(r'\\kf(\d+)',f[9])))
                self.assertGreaterEqual(start,previous);self.assertGreater(end,start)
                self.assertTrue(all(d>0 for d in durations));self.assertEqual(sum(durations),end-start)
                previous=end

if __name__=='__main__':unittest.main()
