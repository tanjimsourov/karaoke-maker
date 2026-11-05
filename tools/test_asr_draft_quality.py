import unittest
from asr_draft_quality import validate_asr_draft

class DraftQualityTests(unittest.TestCase):
    def test_empty_rejected(self):
        with self.assertRaises(ValueError):validate_asr_draft({'segments':[]})
    def test_isolated_letters_rejected(self):
        with self.assertRaises(ValueError):
            validate_asr_draft({'segments':[{'text':'i'}]*8+[{'text':'Ay mama'}]*5})
    def test_normal_draft_not_certified(self):
        r=validate_asr_draft({'segments':[{'text':'Bliv her lidt endnu'}]*12})
        self.assertFalse(r['accuracy_verified'])
    def test_unicode_words_preserved(self):
        self.assertEqual(validate_asr_draft({'segments':[{'text':'følelser'}]*12})['isolated_letter_cues'],0)

    def test_fast_repeated_word_hallucination_rejected(self):
        with self.assertRaisesRegex(ValueError,'repetition'):
            validate_asr_draft({'segments':[{'start':120.,'end':140.,'text':'shake '*223}]})

    def test_real_chorus_repetition_allowed(self):
        result=validate_asr_draft({'segments':[{'start':0.,'end':3.,'text':'play play play play play'}]})
        self.assertFalse(result['accuracy_verified'])

if __name__=='__main__':unittest.main()
