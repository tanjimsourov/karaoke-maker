import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from parallel_song_benchmark import Measurement


class MeasurementTests(unittest.TestCase):
    def test_parallel_children_measured_and_reports_survive(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);report={'tasks':[]}
            m=Measurement(folder,report);m.thread.start()
            try:
                commands=[m.start(name,[sys.executable,'-c',
                    'import time; data=bytearray(25*1024*1024); time.sleep(1.2)'])
                    for name in ['first','second']]
                m.group(commands)
            finally:m.stop.set();m.thread.join()
            first,second=report['tasks']
            self.assertLess(second['start_seconds'],first['end_seconds'])
            self.assertGreater(first['peak_private_bytes'],20*1024**2)
            self.assertGreater(second['peak_private_bytes'],20*1024**2)
            self.assertGreater(report['peak_project_working_set_bytes'],50*1024**2)
            self.assertIn('first|second',(folder/'resources.csv').read_text())
            self.assertTrue((folder/'measurement.json').is_file())

    def test_failure_still_waits_for_parallel_sibling(self):
        with tempfile.TemporaryDirectory() as d:
            m=Measurement(Path(d),{'tasks':[]})
            bad=m.start('bad',[sys.executable,'-c','raise SystemExit(7)'])
            good=m.start('good',[sys.executable,'-c','import time; time.sleep(.3)'])
            with self.assertRaises(RuntimeError):m.group([bad,good])
            self.assertEqual(good[0].poll(),0)
            self.assertEqual(bad[1]['exit_code'],7)
            self.assertFalse(m.active)

    def test_short_sibling_completion_is_not_inflated_by_wait_order(self):
        with tempfile.TemporaryDirectory() as d:
            m=Measurement(Path(d),{'tasks':[]})
            slow=m.start('slow',[sys.executable,'-c','import time; time.sleep(.7)'])
            fast=m.start('fast',[sys.executable,'-c','import time; time.sleep(.1)'])
            m.group([slow,fast])
            self.assertLess(fast[1]['end_seconds'],slow[1]['end_seconds']-.3)


if __name__=='__main__':unittest.main()
