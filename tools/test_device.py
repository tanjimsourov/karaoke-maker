import unittest
from unittest.mock import patch
import builtins
import device


class CpuDeviceTests(unittest.TestCase):
    def test_cpu_wheel_does_not_load_torch_to_select_cpu(self):
        original_import=builtins.__import__
        def guarded(name,*args,**kwargs):
            if name=='torch':raise AssertionError('CPU device selection loaded PyTorch unnecessarily')
            return original_import(name,*args,**kwargs)
        with patch.dict('os.environ',{'KARAOKE_DEVICE':''}), \
             patch('importlib.metadata.version',return_value='2.8.0+cpu'), \
             patch('builtins.__import__',side_effect=guarded):
            self.assertEqual(device.best_device(),'cpu')

    def test_explicit_invalid_device_is_rejected(self):
        with patch.dict('os.environ',{'KARAOKE_DEVICE':'invalid'}):
            with self.assertRaises(ValueError):device.best_device()


if __name__=='__main__':unittest.main()
