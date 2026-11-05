import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import project_runtime as runtime

class InterpreterTests(unittest.TestCase):
    def test_interpreter_setting_does_not_resolve_symlink(self):
        expected=runtime.ROOT/'.venv-demucs/bin/python'
        with patch.dict(os.environ,{'TEST_INTERPRETER':str(expected)}), \
                patch.object(Path,'resolve',side_effect=AssertionError('Must not resolve venv Python')):
            self.assertEqual(runtime.python_setting('TEST_INTERPRETER','unused'),expected)

    def test_relative_interpreter_is_project_relative(self):
        with patch.dict(os.environ,{'TEST_INTERPRETER':'.venv-demucs/bin/python'}):
            self.assertEqual(runtime.python_setting('TEST_INTERPRETER','unused'),runtime.ROOT/'.venv-demucs/bin/python')

if __name__=='__main__':unittest.main()
