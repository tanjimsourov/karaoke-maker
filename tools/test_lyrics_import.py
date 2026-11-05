import unittest
from lyrics_import import parse_lyrics, place_lines, segment_words


def words(*timed):
    return [{'word': w, 'start': s, 'end': e} for w, s, e in timed]


class LyricsImportTests(unittest.TestCase):
    def test_parse_skips_labels_blank_rows_and_markup(self):
        text = '[Chorus]\n\nHej  {med} dig\n(Verse 2)\nFarvel\\n\n'
        self.assertEqual(parse_lyrics(text), ['Hej med dig', 'Farveln'])
        with self.assertRaises(ValueError):
            parse_lyrics('[Intro]\n\n')

    def test_user_words_take_whisper_timing_despite_mishearing(self):
        heard = words(('jeg', 1, 1.4), ('elsker', 1.5, 2), ('dig', 2.1, 2.5),
                      ('hvor', 5, 5.3), ('er', 5.4, 5.6), ('du', 5.7, 6))
        segments, report = place_lines(['Jeg elsker dig', 'Hvor er du nu'], heard, 30)
        self.assertEqual(report['anchored_lines'], 2)
        self.assertAlmostEqual(segments[0]['start'], 0.7)
        self.assertAlmostEqual(segments[1]['end'], 6.3)
        self.assertEqual(segments[1]['text'], 'Hvor er du nu')

    def test_unmatched_lines_fill_gap_in_order_without_overlap(self):
        heard = words(('one', 1, 2), ('three', 10, 11))
        segments, report = place_lines(['one', 'la la la', 'three'], heard, 20)
        self.assertEqual(report['interpolated_lines'], [1])
        for a, b in zip(segments, segments[1:]):
            self.assertLessEqual(a['end'], b['start'])
        self.assertGreater(segments[1]['start'], 1.9)
        self.assertLess(segments[1]['end'], 10.1)

    def test_out_of_order_repeat_is_not_used_as_anchor(self):
        heard = words(('chorus', 20, 21), ('verse', 30, 31))
        segments, _ = place_lines(['verse', 'chorus'], heard, 40)
        self.assertLessEqual(segments[0]['end'], segments[1]['start'])

    def test_segments_without_words_are_split_by_length(self):
        result = segment_words([{'start': 0, 'end': 4, 'text': 'ab abcdef'}])
        self.assertEqual([w['word'] for w in result], ['ab', 'abcdef'])
        self.assertAlmostEqual(result[0]['end'], 1.0)


if __name__ == '__main__':
    unittest.main()
