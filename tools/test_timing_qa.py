import unittest
from timing_qa import timing_report


class TimingBoundaryTests(unittest.TestCase):
    def test_exact_sixty_milliseconds_is_not_short(self):
        report = timing_report([{'text': 'I', 'words': [
            {'word': 'I', 'start': 21.202, 'end': 21.262}]}])
        self.assertEqual(report['issues'], [])

    def test_forty_milliseconds_still_requires_review(self):
        report = timing_report([{'text': 'I', 'words': [
            {'word': 'I', 'start': 21.202, 'end': 21.242}]}])
        self.assertEqual(len(report['issues']), 1)
        self.assertIn('too short', report['issues'][0]['problem'])


if __name__ == '__main__':
    unittest.main()
