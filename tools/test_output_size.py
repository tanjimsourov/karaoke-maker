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
 def test_compact_budget_and_strict_ceiling(self):
  from output_size import bitrate_args,MAX_BYTES
  self.assertLess(MAX_BYTES,100_000_000)
  self.assertEqual(bitrate_args(240,2_000_000)[1],'2000000')
  rate=int(bitrate_args(600,2_000_000)[1])
  self.assertLess(rate,2_000_000)
  self.assertLessEqual((rate+192000)*600/8,TARGET_BYTES)
 def test_source_fps_preserved_and_capped(self):
  from output_size import resolve_fps
  from fractions import Fraction
  from types import SimpleNamespace
  for rate,expected in [(Fraction(25),25),(Fraction(24000,1001),24000/1001),(Fraction(60),30)]:
   with patch('output_size.av.open') as opened:
    opened.return_value.__enter__.return_value.streams.video=[SimpleNamespace(average_rate=rate)]
    self.assertEqual(resolve_fps('source','fixture.mp4'),expected)
if __name__=='__main__':unittest.main()
