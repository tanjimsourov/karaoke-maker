import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml
from container_init import initialize

ROOT=Path(__file__).resolve().parents[1]

class DeploymentTests(unittest.TestCase):
    def test_init_preserves_source_and_creates_only_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);media=root/'media';media.mkdir();app=root/'app';app.mkdir()
            source=media/'song.mp4';source.write_bytes(b'unchanged')
            with patch('container_init.os.chown',create=True) as chown:
                initialize(media,app,10001,10001)
                self.assertEqual(chown.call_count,6)
            self.assertEqual(source.read_bytes(),b'unchanged')
            self.assertTrue((media/'karaoke').is_dir())
            self.assertEqual(set(p.name for p in media.iterdir()),{'song.mp4','karaoke'})

    def test_compose_layout_and_permissions(self):
        data=yaml.safe_load((ROOT/'docker-compose.yml').read_text())
        runner=data['services']['karaoke'];init=data['services']['karaoke-init']
        self.assertTrue(runner['volumes'][0]['read_only'])
        self.assertFalse(runner['volumes'][0]['bind']['create_host_path'])
        self.assertEqual(runner['volumes'][1]['target'],'/media/karaoke')
        self.assertEqual(runner['depends_on']['karaoke-init']['condition'],'service_completed_successfully')
        self.assertEqual(init['user'],'0:0')
        self.assertEqual(runner['logging']['driver'],'none')

    def test_runtime_storage_is_project_bind_mounts(self):
        data=yaml.safe_load((ROOT/'docker-compose.yml').read_text())
        self.assertNotIn('volumes',data)
        for name in ('karaoke','karaoke-init'):
            mounts={v['target']:v for v in data['services'][name]['volumes']}
            for target in ('models','work','out','reports','tmp'):
                mount=mounts['/app/'+target]
                self.assertEqual(mount['type'],'bind')
                self.assertTrue(mount['source'].startswith('${KARAOKE_DATA_HOST_DIR:-./docker-data}/'))
        self.assertIn('/docker-data/',(ROOT/'.gitignore').read_text())

    def test_initial_source_and_branding(self):
        values={}
        for line in (ROOT/'.env').read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k,v=line.split('=',1);values[k]=v.strip('"')
        self.assertEqual(values['KARAOKE_MEDIA_HOST_DIR'],'D:/Application/Website/ftpPrivate/Danish New')
        self.assertEqual(values['KARAOKE_COUNTDOWN_COLOUR'],'#BB3794')
        self.assertEqual(values['KARAOKE_CLEANUP_AFTER_RUN'],'1')
        self.assertTrue((ROOT/values['KARAOKE_LOGO']).is_file())

    def test_shared_server_isolation(self):
        service=yaml.safe_load((ROOT/'docker-compose.yml').read_text())['services']['karaoke']
        self.assertTrue(service['read_only'])
        self.assertEqual(service['cap_drop'],['ALL'])
        self.assertIn('no-new-privileges:true',service['security_opt'])
        self.assertNotIn('ports',service)
        self.assertNotIn('privileged',service)
        self.assertNotIn('network_mode',service)
        self.assertNotIn('docker.sock',str(service))
        self.assertEqual(service['pids_limit'],512)
        values=dict(line.split('=',1) for line in (ROOT/'.env').read_text().splitlines()
                    if '=' in line and not line.lstrip().startswith('#'))
        self.assertEqual(values['KARAOKE_SERVER_WORKERS'],'3')
        self.assertEqual(values['KARAOKE_DOCKER_CPUS'],'8')
        self.assertEqual(values['KARAOKE_DOCKER_MEMORY'],'12g')

if __name__=='__main__':unittest.main()
