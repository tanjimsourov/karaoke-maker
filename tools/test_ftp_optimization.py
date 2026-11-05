import tempfile
import time
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import convert_verified_ftp_raw as batch
from zoom_local_pipeline import read


class SchedulerTests(unittest.TestCase):
    def exercise(self,free_gib,fail=False):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp)
            commands=[('first',[sys.executable,'-c','import time; time.sleep(.3)']),
                      ('second',[sys.executable,'-c','import time; time.sleep(.4)'])]
            if fail:commands[0]=('first',[sys.executable,'-c','raise SystemExit(7)'])
            with patch.object(batch,'REPORT',d),patch.object(batch.psutil,'virtual_memory',return_value=SimpleNamespace(available=free_gib*1024**3)),patch.object(batch.os,'cpu_count',return_value=8):
                if fail:
                    with self.assertRaises(batch.subprocess.CalledProcessError):batch.independent(commands,d,8)
                else:batch.independent(commands,d,8)
            self.assertTrue((d/'second.done.json').exists())
            self.assertEqual(read(d/'schedule-first.json')['workers'],2 if free_gib>=8 else 1)
            if not fail:
                # Resume must consume checkpoints without executing subprocesses again.
                with patch.object(batch.subprocess,'run',side_effect=AssertionError('Repeated completed work')):
                    for stage,command in commands:batch.run(stage,command,d)

    def test_parallel_branches_checkpoint_and_resume(self):self.exercise(12)
    def test_low_memory_runs_sequentially(self):self.exercise(2)
    def test_failure_waits_for_sibling_checkpoint(self):self.exercise(12,True)


if __name__=='__main__':unittest.main()
