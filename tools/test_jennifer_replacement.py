import unittest
from repair_jennifer_light import inside_replacement

class ReplacementBoundaryTests(unittest.TestCase):
    def test_following_phrase_survives_each_chorus(self):
        for start,end in ((51.4,56.42),(94.1,99.14),(130.7,135.72)):
            self.assertTrue(inside_replacement({'start':start+.02},start,end))
            self.assertFalse(inside_replacement({'start':end},start,end))
            self.assertFalse(inside_replacement({'start':end+1},start,end))

if __name__=='__main__':unittest.main()
