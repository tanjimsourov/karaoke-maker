import unittest,math,tempfile
from pathlib import Path
from unittest.mock import patch
from output_size import video_budget,constrained_args,enforce,TARGET_BYTES
class SizeTests(unittest.TestCase):
 def test_budget_accounts_for_audio(self):
  for duration in (60,180,300,600):
   rate=video_budget(duration)
   self.assertLessEqual((rate+192000)*duration/8,TARGET_BYTES)
 def test_longer_video_gets_lower_rate(self):
  self.assertGreater(video_budget(180),video_budget(300))
 def test_invalid_duration(self):
  for d in (0,-1,float('nan'),float('inf')):
   with self.assertRaises(ValueError):video_budget(d)
 def test_small_files_are_unchanged(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'small.mp4';p.write_bytes(b'untouched')
   with patch('output_size.subprocess.run') as run:
    enforce(p);run.assert_not_called()
   self.assertEqual(p.read_bytes(),b'untouched')
if __name__=='__main__':unittest.main()
