import unittest
from prepare_zoom_local import make_ass


class TimingTests(unittest.TestCase):
    def test_preserves_gap_and_offset(self):
        result = make_ass([{'words': [
            {'start': 1, 'end': 1.5, 'word': 'Hello'},
            {'start': 2, 'end': 3, 'word': 'world'}]}], 2, 10)
        self.assertIn('0:00:03.00,0:00:05.00', result)
        self.assertIn(r'{\kf50}Hello {\kf50} {\kf100}world', result)

    def test_bad_timings_rejected(self):
        for a, b in [(2, 2), (3, 2), (-1, 1), (9, 11)]:
            with self.assertRaises(ValueError):
                make_ass([{'words': [{'start': a, 'end': b, 'word': 'test'}]}], 0, 10)

    def test_markup_rejected(self):
        with self.assertRaises(ValueError):
            make_ass([{'words': [{'start': 1, 'end': 2, 'word': '{bad}'}]}], 0, 10)

    def test_no_words_rejected(self):
        with self.assertRaises(ValueError):
            make_ass([], 0, 10)


if __name__ == '__main__':
    unittest.main()
