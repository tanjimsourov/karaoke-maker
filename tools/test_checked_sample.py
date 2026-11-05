import tempfile
import unittest
from pathlib import Path
from export_checked_sample import verify_inputs
from zoom_local_pipeline import digest


class SampleTests(unittest.TestCase):
    def test_unrelated_helper_change_is_recorded_but_media_and_renderer_changes_block(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);helper=root/'local_karaoke.py';renderer=root/'build_bowlnfun_karaoke.py';media=root/'aligned.json'
            for p in [helper,renderer,media]:p.write_text('original')
            cfg={'render':{}}
            v={'fingerprint':{'config':cfg,'files':{str(p):digest(p) for p in [helper,renderer,media]}}}
            helper.write_text('separation thread settings changed')
            self.assertEqual(verify_inputs(v,cfg),[str(helper)])
            renderer.write_text('render changed')
            with self.assertRaisesRegex(ValueError,'dependency changed'):verify_inputs(v,cfg)
            renderer.write_text('original');media.write_text('lyrics changed')
            with self.assertRaisesRegex(ValueError,'dependency changed'):verify_inputs(v,cfg)
            with self.assertRaisesRegex(ValueError,'configuration changed'):verify_inputs(v,{'render':{'crf':20}})

if __name__=='__main__':unittest.main()
