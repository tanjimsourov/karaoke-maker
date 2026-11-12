"""Real localhost FTP transport; fixture converter does not process media/models."""
import importlib.util
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import ftp_cloud_batch as batch


@unittest.skipUnless(importlib.util.find_spec('pyftpdlib'),'Optional pyftpdlib test dependency')
class TransportTests(unittest.TestCase):
    def test_iis_style_roundtrip_resume_and_changed_source(self):
        logging.getLogger('pyftpdlib').setLevel(logging.CRITICAL)
        # This is a plaintext fixture; do not load optional system PyOpenSSL.
        with patch.dict('sys.modules',{'OpenSSL':None}):
            from pyftpdlib.authorizers import DummyAuthorizer
            from pyftpdlib.handlers import FTPHandler
            from pyftpdlib.servers import FTPServer
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);remote_root=root/'remote';remote_root.mkdir()
            music=remote_root/'music';music.mkdir()
            source=music/'Artist - Danish æøå.mp3';source.write_bytes(b'source-one')
            class IIS(FTPHandler):
                def ftp_MLSD(self,path):self.respond('500 MLSD unsupported')
            auth=DummyAuthorizer();auth.add_user('test-only','test-only',str(remote_root),perm='elradfmwMT')
            IIS.authorizer=auth
            server=FTPServer(('127.0.0.1',0),IIS)
            thread=threading.Thread(target=server.serve_forever,kwargs={'timeout':.05,'handle_exit':False},daemon=True)
            thread.start()
            config={'host':'127.0.0.1','port':server.socket.getsockname()[1],'tls':False,
                    'input_folder':'/music','extensions':['.mp3'],'output_layout':'beside-source'}
            calls=[]
            def converter(local,config):
                calls.append(local.read_bytes())
                output=local.parent/'fixture.mp4';output.write_bytes(b'fixture-'+local.read_bytes());return output
            try:
                with patch.dict(os.environ,{'KARAOKE_FTP_USER':'test-only','KARAOKE_FTP_PASSWORD':'test-only'}),patch.object(batch,'ROOT',root/'project'):
                    remote=batch.Remote(config)
                    self.assertEqual(batch.run(config,remote,converter),0)
                    self.assertEqual(batch.run(config,remote,converter),0)
                    source.write_bytes(b'source-two')
                    self.assertEqual(batch.run(config,remote,converter),0)
                self.assertEqual(calls,[b'source-one',b'source-two'])
                outputs=list((music/'karaoke').glob('*.mp4'))
                self.assertEqual(len(outputs),2)
                self.assertEqual({p.read_bytes() for p in outputs},{b'fixture-source-one',b'fixture-source-two'})
                self.assertFalse(list(root.rglob('*.partial')))
                self.assertFalse(list((root/'project').rglob('*.mp3')))
                receipt=json.loads(next((music/'karaoke/.karaoke-status').glob('*.json')).read_text())
                self.assertEqual(receipt['source_sha256'],batch.file_sha(source))
            finally:
                server.close_all();thread.join(timeout=5)


if __name__=='__main__':unittest.main()
