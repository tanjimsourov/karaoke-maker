import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from parallel_background import BackgroundJob
class Tests(unittest.TestCase):
 def test_nonblocking_entry_and_result(self):
  with tempfile.TemporaryDirectory() as d:
   p=MagicMock();p.wait.return_value=0;p.poll.return_value=0
   with patch('parallel_background.subprocess.Popen',return_value=p):
    with BackgroundJob('source',d,True) as job:
     p.wait.assert_not_called()
     Path(d,'result.json').write_text(json.dumps({'background':'ready','plan':None}))
     self.assertEqual(job.result()['background'],'ready')
    p.wait.assert_called()
 def test_failure_not_success(self):
  with tempfile.TemporaryDirectory() as d:
   p=MagicMock();p.wait.return_value=1;p.poll.return_value=1
   with patch('parallel_background.subprocess.Popen',return_value=p):
    with BackgroundJob('source',d,True) as job:
     with self.assertRaises(ValueError):job.result()
 def test_exception_stops_worker(self):
  with tempfile.TemporaryDirectory() as d:
   p=MagicMock();p.poll.return_value=None
   with patch('parallel_background.subprocess.Popen',return_value=p):
    with self.assertRaises(RuntimeError):
     with BackgroundJob('source',d,True):raise RuntimeError('foreground failed')
    p.terminate.assert_called_once();p.wait.assert_called_once()
if __name__=='__main__':unittest.main()
