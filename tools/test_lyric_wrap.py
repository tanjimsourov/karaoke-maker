import unittest
from lyric_wrap import balanced_groups

class WrapTests(unittest.TestCase):
    def test_no_orphan_and_tokens_unchanged(self):
        words=[(str(i),w+' ') for i,w in enumerate('I was gonna say it Jenny I was gonna let you know'.split())]
        groups=balanced_groups(words,len,44)
        self.assertEqual([w for group in groups for w in group],words)
        self.assertEqual(len(groups),2)
        self.assertTrue(all(len(g)>1 for g in groups))
        self.assertTrue(all(len(''.join(w for _,w in g))<=44 for g in groups))
    def test_short_line_unchanged(self):
        words=[('40','Hello '),('50','there')]
        self.assertEqual(balanced_groups(words,len,40),[words])
    def test_oversized_word_terminates(self):
        self.assertEqual(balanced_groups([('1','longword')],len,2),[[('1','longword')]])

if __name__=='__main__':unittest.main()
