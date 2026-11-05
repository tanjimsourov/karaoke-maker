from pathlib import Path
import tempfile
import unittest
import json
from translate_lyrics import clean, lines_from_aligned, model_chain, parse_llm_reply
from zoom_local_pipeline import save
from local_karaoke import require_translation_review, translation_identity


class TranslateTests(unittest.TestCase):
    def test_direct_model_preferred(self):
        self.assertEqual(model_chain('en', 'da', lambda m: True), ['Helsinki-NLP/opus-mt-en-da'])

    def test_pivot_through_english(self):
        available = {'Helsinki-NLP/opus-mt-es-en', 'Helsinki-NLP/opus-mt-en-da'}
        self.assertEqual(model_chain('es', 'da', available.__contains__),
                         ['Helsinki-NLP/opus-mt-es-en', 'Helsinki-NLP/opus-mt-en-da'])

    def test_missing_pair_and_same_language_rejected(self):
        with self.assertRaisesRegex(ValueError, 'No Opus-MT'):
            model_chain('xx', 'da', lambda m: False)
        with self.assertRaises(ValueError):
            model_chain('da', 'da', lambda m: True)

    def test_lines_use_word_times_and_skip_untimed(self):
        lines = lines_from_aligned([
            {'start': 0, 'end': 9, 'text': ' Hej {x} med dig ',
             'words': [{'word': 'Hej', 'start': 1.2, 'end': 1.5}, {'word': 'dig', 'start': 2, 'end': 2.6}]},
            {'start': 9, 'end': 10, 'text': 'untimed', 'words': [{'word': 'untimed'}]}])
        self.assertEqual(lines, [{'start': 1.2, 'end': 2.6, 'text': 'Hej x med dig'}])
        self.assertEqual(clean('a\\N {b}'), 'aN b')

    def test_llm_reply_parsing_tolerates_fences_and_numbering(self):
        self.assertEqual(parse_llm_reply('```json\n["1. Hej", "Farvel"]\n```', 2), ['Hej', 'Farvel'])
        with self.assertRaisesRegex(ValueError, 'expected 3'):
            parse_llm_reply('["a", "b"]', 3)

    def test_translation_review_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            cfg = {'translation': {'to': 'da'}}
            with self.assertRaisesRegex(ValueError, 'translate first'):
                require_translation_review(cfg, folder)
            save(folder/'aligned.json', [])
            save(folder/'translation.json', {'to': 'da', 'lines': [{'translation': 'a'}]})
            with self.assertRaisesRegex(ValueError, 'accept-translation'):
                require_translation_review(cfg, folder)
            save(folder/'translation-review.json', translation_identity(folder))
            require_translation_review(cfg, folder)
            save(folder/'translation.json', {'to': 'da', 'lines': [{'translation': 'edited'}]})
            with self.assertRaises(ValueError):
                require_translation_review(cfg, folder)
            require_translation_review({}, folder)  # no translation block: nothing required


if __name__ == '__main__':
    unittest.main()
