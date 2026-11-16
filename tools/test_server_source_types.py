"""Routing checks without AI downloads or full-song conversion."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import server_batch as server


class SourceTypeTests(unittest.TestCase):
    def test_mp3_discovery_recurses_and_excludes_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'karaoke';out.mkdir();(root/'nested').mkdir()
            song=root/'nested/song.MP3';song.write_bytes(b'audio')
            (root/'song.mp4').write_bytes(b'video');(out/'song.mp3').write_bytes(b'output')
            self.assertEqual(list(server.discover(root,out,0,'mp3')),[song])

    def test_four_routes_and_backgrounds(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'KARAOKE_BACKGROUND':'auto','KARAOKE_SCREEN_PROFILE':'auto'}):
            root=Path(d);image=root/'background.jpg';image.write_bytes(b'image')
            with patch.dict(os.environ,{'KARAOKE_AUDIO_BACKGROUND':str(image)}):
                for kind,extension,mode in [('mp4','.mp4','music'),('mp3','.mp3','music'),('zoom','.mp4','zoom'),('singking','.mp4','zoom')]:
                    source=root/('Artist - Song'+extension);source.write_bytes(b'media')
                    job=server.make_job(source,'en','htdemucs',2,kind)
                    self.assertEqual(job['mode'],mode)
                    self.assertEqual(job['background'],'original' if kind=='mp4' else str(image))
                    self.assertEqual(job['render']['fps'],30 if kind=='mp3' else 'source')
                    if kind=='singking':self.assertEqual(job['screen_profile'],'white-magenta')

    def test_zoom_and_singking_require_fixed_language(self):
        for kind in ['zoom','singking']:
            with self.assertRaisesRegex(ValueError,'language'):
                server.make_job(Path('Song.mp4'),'auto','htdemucs',2,kind)

    def test_invalid_type_and_missing_mp3_background_rejected(self):
        with self.assertRaises(ValueError):server.make_job(Path('Song.mp4'),'en','htdemucs',2,'other')
        with patch.dict(os.environ,{'KARAOKE_BACKGROUND':'missing-background.jpg'}):
            with self.assertRaisesRegex(ValueError,'background'):
                server.make_job(Path('Song.mp3'),'en','htdemucs',2,'mp3')

    def test_env_drives_cli_mp3_selection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'song.mp3').write_bytes(b'audio');(root/'song.mp4').write_bytes(b'video')
            env={'KARAOKE_SOURCE_TYPE':'mp3','KARAOKE_EXTRA_INPUT_DIRS':'[]','KARAOKE_SERVER_OUTPUT_DIR':str(root/'karaoke')}
            output=io.StringIO()
            with patch.dict(os.environ,env),patch('sys.argv',['server_batch.py','--input-dir',str(root),'--settle-seconds','0','--dry-run']),contextlib.redirect_stdout(output):
                self.assertEqual(server.main(),0)
            report=json.loads(output.getvalue())
            self.assertEqual(report['files'],[str(root/'song.mp3')])
            self.assertEqual(report['source_type'],'mp3')


if __name__=='__main__':unittest.main()
