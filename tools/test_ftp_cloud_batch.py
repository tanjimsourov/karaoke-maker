import ftplib
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ftp_cloud_batch as batch


class Remote:
    def __init__(self):
        self.files = {'/music/song.mp4': b'source'}
        self.fail_upload = False

    def list(self, folder):
        if folder == '/music':
            return [('song.mp4', {'type': 'file', 'size': '6', 'modify': '1'}),
                    ('karaoke', {'type': 'dir'})]
        raise AssertionError('Output folder must not be scanned')

    def json(self, path):
        if path not in self.files:
            raise ftplib.error_perm('550 Missing')
        return json.loads(self.files[path])

    def digest(self, path):
        if path not in self.files:
            raise ftplib.error_perm('550 Missing')
        return hashlib.sha256(self.files[path]).hexdigest()

    def download(self, remote, local, size):
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(self.files[remote])

    def upload(self, local, remote):
        if self.fail_upload:
            raise OSError('Transfer interrupted')
        self.files[remote] = local.read_bytes()


class BatchTests(unittest.TestCase):
    def test_iis_without_mlsd_lists_files_and_directories(self):
        class IIS:
            current='/'
            def mlsd(self,*args,**kwargs):raise ftplib.error_perm('500 MLSD unsupported')
            def pwd(self):return self.current
            def voidcmd(self,command):return '200 OK'
            def cwd(self,path):
                if path not in ('/','/music','/music/artist'):raise ftplib.error_perm('550 Not a directory')
                self.current=path
            def nlst(self):return ['song.mp3','artist']
            def size(self,path):
                if path=='/music/song.mp3':return 123
                raise ftplib.error_perm('550 Not a file')
            def sendcmd(self,command):return '213 20261112000000'
        remote=batch.Remote({})
        with patch.object(remote,'retry',side_effect=lambda operation:operation(IIS())):
            rows=dict(remote.list('/music'))
        self.assertEqual(rows['song.mp3'],{'type':'file','size':'123','modify':'20261112000000'})
        self.assertEqual(rows['artist']['type'],'dir')

    def test_same_size_source_change_is_not_skipped(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(batch,'ROOT',Path(temp)):
            remote=Remote();calls=[]
            def convert(source,config):
                calls.append(source.read_bytes());result=source.parent/'karaoke.mp4'
                result.write_bytes(b'video');return result
            cfg={'input_folder':'/music','output_folder':'/music/karaoke'}
            self.assertEqual(batch.run(cfg,remote,convert),0)
            remote.files['/music/song.mp4']=b'newone'
            self.assertEqual(batch.run(cfg,remote,convert),0)
            self.assertEqual(calls,[b'source',b'newone'])

    def test_cleanup_failed_setting_removes_spool_without_publishing_receipt(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(batch,'ROOT',Path(temp)):
            remote=Remote();remote.fail_upload=True
            cfg={'input_folder':'/music','output_folder':'/music/karaoke','cleanup_failed':True}
            self.assertEqual(batch.run(cfg,remote,lambda source,config:source),2)
            self.assertFalse(list(Path(temp).rglob('song.mp4')))
            self.assertFalse(list(Path(temp).rglob('error.txt')))
            self.assertFalse(any(name.endswith('.json') for name in remote.files))

    def test_mp3_discovery_excludes_every_nested_karaoke_folder(self):
        class Tree:
            def list(self, folder):
                return {'/music':[('artist',{'type':'dir'})],
                        '/music/artist':[('song.mp3',{'type':'file','size':'6','modify':'1'}),
                                         ('karaoke',{'type':'dir'})]}[folder]
        result=list(batch.discover(Tree(),'/music','/music/karaoke',True,extensions=['.mp3']))
        self.assertEqual(result,[('/music/artist/song.mp3',{'size':6,'modify':'1'})])

    def test_output_beside_nested_mp3_and_cleanup(self):
        class MP3Remote(Remote):
            def __init__(self):
                super().__init__();self.files={'/music/artist/song.mp3':b'source'}
            def list(self, folder):
                if folder=='/music':return [('artist',{'type':'dir'})]
                if folder=='/music/artist':return [('song.mp3',{'type':'file','size':'6','modify':'1'})]
                raise AssertionError(folder)
        with tempfile.TemporaryDirectory() as temp,patch.object(batch,'ROOT',Path(temp)):
            remote=MP3Remote()
            def converter(source, config):
                result=source.parent/'Song - Karaoke.mp4';result.write_bytes(b'video');return result
            config={'input_folder':'/music','output_layout':'beside-source','extensions':['.mp3']}
            self.assertEqual(batch.run(config,remote,converter),0)
            self.assertTrue(any(p.startswith('/music/artist/karaoke/song - Karaoke - ') and p.endswith('.mp4') for p in remote.files))
            self.assertFalse(list(Path(temp).rglob('song.mp3')))
            self.assertEqual(batch.run(config,remote,converter),0)

    def test_mp3_job_uses_configured_image_and_complete_automatic_pipeline(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(batch,'ROOT',Path(temp)):
            root=Path(temp);source=root/'Artist - Title.mp3';source.write_bytes(b'audio')
            image=root/'image.jpg';image.write_bytes(b'image')
            commands=[]
            def worker(command,**kwargs):
                commands.append(command)
                job=json.loads(Path(command[command.index('--job')+1]).read_text())
                self.assertEqual(job['background'],str(image))
                self.assertEqual(job['language'],'da')
                self.assertEqual(job['source'],str(source))
                output=Path(kwargs['env']['KARAOKE_OUTPUT_DIR']);output.mkdir()
                (output/'result_Karaoke.mp4').write_bytes(b'video')
            with patch('ftp_cloud_batch.subprocess.run',side_effect=worker),patch('server_batch.verify_existing'):
                result=batch.convert(source,{'background':str(image),'language':'da'})
            self.assertEqual(result.read_bytes(),b'video')
            self.assertIn('--automatic-export',commands[0])
            self.assertNotIn('--draft-export',commands[0])

    def test_upload_cleanup_resume_and_missing_output(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(batch, 'ROOT', Path(temp)):
            remote = Remote()
            calls = []
            def convert(source, config):
                calls.append(source)
                out = source.parent / 'karaoke.mp4'
                out.write_bytes(b'finished video')
                return out
            config = {'input_folder': '/music', 'output_folder': '/music/karaoke'}
            self.assertEqual(batch.run(config, remote, convert), 0)
            self.assertFalse(calls[0].parent.exists())
            self.assertEqual(batch.run(config, remote, convert), 0)
            self.assertEqual(len(calls), 1)
            del remote.files['/music/karaoke/karaoke.mp4']
            self.assertEqual(batch.run(config, remote, convert), 0)
            self.assertEqual(len(calls), 2)

    def test_failed_upload_keeps_local_data_and_does_not_mark_complete(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(batch, 'ROOT', Path(temp)):
            remote = Remote()
            remote.fail_upload = True
            self.assertEqual(batch.run({'input_folder': '/music', 'output_folder': '/music/karaoke'},
                                       remote, lambda source, config: source), 2)
            self.assertTrue(list(Path(temp).rglob('song.mp4')))
            self.assertTrue(list(Path(temp).rglob('error.txt')))
            self.assertFalse(any(p.endswith('.json') for p in remote.files))

    def test_reject_unsafe_remote_paths(self):
        for path in ('relative', '/music/../other', '/music\nDELE x', '/music\\other'):
            with self.assertRaises(ValueError):
                batch.remote_path(path)


if __name__ == '__main__':
    unittest.main()
