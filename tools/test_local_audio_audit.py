import unittest
import json
from unittest.mock import patch
import numpy as np
from local_audio_audit import quiet_intervals,level,compare


class AuditTests(unittest.TestCase):
    def test_antiphase_is_not_silence(self):
        x=np.full((8000,2),.2); x[:,1]*=-1
        self.assertEqual(quiet_intervals(x),[])
        self.assertGreater(level(x),-20)

    def test_known_gap(self):
        x=np.full((24000,2),.2)
        x[8000:16000]=0
        self.assertEqual(quiet_intervals(x),[(1.,2.)])

    def test_short_gap_ignored(self):
        x=np.full((8000,2),.2); x[200:1000]=0
        self.assertEqual(quiet_intervals(x),[])

    def test_silent_source(self):
        self.assertEqual(quiet_intervals(np.zeros((8000,2))),[(0.,1.)])

    def test_report_json(self):
        with patch('local_audio_audit.stereo_audio',return_value=np.zeros((8000,2))):
            result=compare('original','backing','vocals')
            json.dumps(result)
            self.assertEqual(result['quiet_sections'][0]['classification'],'quiet_in_original_source')

if __name__=='__main__': unittest.main()
