import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from workflow import normalize
from local_karaoke import separate_command
from quick_preview import preview_config


class OptimizedTests(unittest.TestCase):
    def test_new_profile_is_explicit_and_preserves_legacy_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'song').write_bytes(b'source')
            base={'source':'song','title':'T','artist':'A'}
            old,oldpath=normalize(base,root)
            new,newpath=normalize({**base,'profile':'optimized'},root)
            self.assertNotIn('model',old.get('separation',{}))
            self.assertNotEqual(oldpath,newpath)
            self.assertEqual(new['separation'],{'model':'htdemucs','overlap':.25})
            self.assertEqual(new['render']['crf'],14)
            self.assertEqual(new['render']['preset'],'veryfast')
            override,_=normalize({**base,'profile':'optimized','separation':{'model':'htdemucs_ft'}},root)
            self.assertEqual(override['separation']['model'],'htdemucs_ft')
            with patch('local_karaoke.DEMUCSPY') as py:
                py.is_file.return_value=True
                cmd=separate_command({'vocal_reference':'song','separation':new['separation']},root)
                self.assertEqual(cmd[cmd.index('--model')+1],'htdemucs')
                self.assertEqual(cmd[cmd.index('--overlap')+1],'0.25')

    def test_quick_preview_does_not_change_delivery_settings(self):
        cfg={'slug':'song','render':{'canvas':'1920x1080','intro_seconds':10,'fps':30,'crf':14}}
        p=preview_config(cfg,190,30,195)
        self.assertEqual(p['render']['end'],205)
        self.assertEqual(p['render']['canvas'],'1280x720')
        self.assertGreater(p['render']['guide_vocal_level'],0)
        self.assertEqual(cfg['render']['crf'],14)
        self.assertNotIn('guide_vocal_level',cfg['render'])
        for start,seconds in [(210,20),(0,61),(-1,10),(float('nan'),10)]:
            with self.assertRaises(ValueError):preview_config(cfg,start,seconds,195)

if __name__=='__main__':unittest.main()
