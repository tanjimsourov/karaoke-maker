import unittest
from repair_lyric_draft import flag_lines,make_lines

class RepairTests(unittest.TestCase):
    def test_flags_audit_numeric_and_repetition(self):
        rows=[{'start':0,'end':5,'text':'3 4 3 4 4 4 5 5 6 6 7 8 9 10'},
              {'start':6,'end':10,'text':'er det er det er det er det'}]
        self.assertEqual(len(flag_lines(rows)),2)
    def test_real_refrain_not_deleted(self):
        rows=[{'start':0,'end':5,'text':'Come back home'}, {'start':6,'end':10,'text':'Come back home'}]
        self.assertEqual(flag_lines(rows),[])
    def test_long_segments_keep_all_words_in_order(self):
        words=[{'word':'word'+str(i),'start':i,'end':i+.8} for i in range(30)]
        rows=make_lines([{'start':0,'end':30,'text':'unused','words':words}])
        self.assertGreater(len(rows),4)
        self.assertEqual(' '.join(r['text'] for r in rows),' '.join(w['word'] for w in words))
        self.assertEqual(rows[-1]['end'],29.8)
    def test_long_gap_flagged_not_filled_with_guessed_words(self):
        rows=[{'start':0,'end':2,'text':'First line'}, {'start':30,'end':32,'text':'Next line'}]
        self.assertIn('long_gap',flag_lines(rows)[0]['reasons'][0])

if __name__=='__main__':unittest.main()
