import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from unittest.mock import patch

import model_queue
import stage_metrics


class QueueTests(unittest.TestCase):
    def test_gpu_inference_stages_share_one_slot_across_five_jobs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);guard=threading.Lock();active=peak=0
            def inference():
                nonlocal active,peak
                with guard:active+=1;peak=max(peak,active)
                time.sleep(.025)
                with guard:active-=1
            slots=model_queue.resource_slots
            with patch.dict(os.environ,{'KARAOKE_CLOUD_GPU_SLOTS':'1','KARAOKE_DEVICE':'cuda'}), \
                 patch('model_queue.resource_slots',side_effect=partial(slots,root=root)):
                with ThreadPoolExecutor(max_workers=5) as pool:
                    list(pool.map(lambda i:stage_metrics.call(root/str(i),'transcription_or_import',inference),range(5)))
            self.assertEqual(peak,1)
            self.assertEqual(len(list(root.glob('*/stage-metrics.jsonl'))),5)


if __name__=='__main__':unittest.main()
