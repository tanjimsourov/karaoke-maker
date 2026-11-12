"""Sequential FTP/explicit-FTPS -> existing converter -> FTP batch for GPU hosts."""
import argparse
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import ftplib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import ssl
import subprocess
import sys
import time
import threading
import random

ROOT = Path(__file__).resolve().parents[1]


def remote_path(value):
    if not value.startswith('/') or any(c in value for c in '\r\n\\') or '..' in value.split('/'):
        raise ValueError('FTP folders must be absolute POSIX paths without traversal')
    return str(PurePosixPath(value))


class Remote:
    def __init__(self, config):
        self.config = config

    @contextmanager
    def connection(self):
        c = self.config
        ftp = ftplib.FTP_TLS(context=ssl.create_default_context()) if c.get('tls', True) else ftplib.FTP()
        try:
            ftp.connect(c['host'], int(c.get('port', 21)), timeout=120)
            ftp.login(os.environ[c.get('user_env', 'KARAOKE_FTP_USER')],
                      os.environ[c.get('password_env', 'KARAOKE_FTP_PASSWORD')])
            if c.get('tls', True):
                ftp.prot_p()
            ftp.set_pasv(True)
            ftp.voidcmd('TYPE I')
            yield ftp
        finally:
            ftp.close()

    def retry(self, operation):
        for attempt in range(3):
            try:
                with self.connection() as ftp:
                    return operation(ftp)
            except ftplib.error_perm:
                raise  # Permanent missing-file/permission responses are not transient.
            except (OSError, EOFError, ftplib.Error):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    def list(self, folder):
        def listing(f):
            try:return list(f.mlsd(folder,facts=['type','size','modify']))
            except ftplib.error_perm as exc:
                if not str(exc).startswith(('500','501','502','504')):raise
            # IIS does not advertise MLSD. Classify NLST entries via SIZE/CWD,
            # rather than parsing locale-dependent LIST dates or file names.
            original=f.pwd();rows=[]
            try:
                f.cwd(folder)
                try:names=f.nlst()
                except ftplib.error_perm as exc:
                    if str(exc).startswith('550'):return []
                    raise
                f.voidcmd('TYPE I')  # NLST switches the connection back to ASCII.
                for value in names:
                    name=PurePosixPath(value).name
                    if name in ('','.','..') or any(c in name for c in '\r\n\\'):continue
                    path=folder.rstrip('/')+'/'+name
                    try:
                        size=f.size(path)
                        if size is None:raise ValueError('FTP did not provide file size: '+path)
                    except ftplib.error_perm:
                        f.cwd(path);f.cwd(folder)
                        rows.append((name,{'type':'dir'}));continue
                    try:modified=f.sendcmd('MDTM '+path).split(' ',1)[1]
                    except ftplib.error_perm:modified=''
                    rows.append((name,{'type':'file','size':str(size),'modify':modified}))
                return rows
            finally:f.cwd(original)
        return self.retry(listing)

    def digest(self, path):
        def read(f):
            digest = hashlib.sha256()
            f.retrbinary('RETR ' + path, digest.update)
            return digest.hexdigest()
        return self.retry(read)

    def json(self, path):
        def read(f):
            data = io.BytesIO()
            f.retrbinary('RETR ' + path, data.write)
            return json.loads(data.getvalue())
        return self.retry(read)

    def download(self, remote, local, size):
        local.parent.mkdir(parents=True, exist_ok=True)
        def read(f):
            with local.with_suffix('.part').open('wb') as output:
                f.retrbinary('RETR ' + remote, output.write)
        self.retry(read)
        part = local.with_suffix('.part')
        if part.stat().st_size != size:
            raise ValueError('Source changed or incomplete download: ' + remote)
        part.replace(local)

    def upload(self, local, remote):
        replace_checkpoint=False
        try:
            existing=self.digest(remote)
        except ftplib.error_perm as exc:
            if not str(exc).startswith('550'):raise
        else:
            if existing==file_sha(local):return
            if '/.karaoke-status/' not in remote or not remote.endswith('.json'):
                raise FileExistsError('Refusing to replace a different FTP file: '+remote)
            replace_checkpoint=True
        def write(f):
            parent = PurePosixPath(remote).parent
            current = ''
            for component in parent.parts[1:]:
                current += '/' + component
                try:
                    f.mkd(current)
                except ftplib.error_perm:
                    f.cwd(current)  # Confirm existing directory, not an ignored permission error.
            with local.open('rb') as source:
                f.storbinary('STOR ' + remote + '.partial', source)
        self.retry(write)
        if self.digest(remote + '.partial') != file_sha(local):
            raise ValueError('Uploaded checksum mismatch')
        # IIS/Windows cannot rename over an existing file. Only replace our
        # bookkeeping JSON; published media is never deleted or overwritten.
        # A disconnect here loses a skip receipt, never a source/final video.
        if replace_checkpoint:self.retry(lambda f:f.delete(remote))
        self.retry(lambda f: f.rename(remote + '.partial', remote))


def file_sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def select_background(config):
    folder=config.get('background_folder')
    if not folder:return config.get('background','assets/audio-bg/6.jpeg')
    from PIL import Image
    directory=Path(folder)
    if not directory.is_absolute():directory=ROOT/directory
    candidates=[]
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in ('.jpg','.jpeg','.png'):continue
        try:
            with Image.open(path) as image:
                w,h=image.size
                if w>=1280 and h>=720 and abs(w/h-16/9)<=.025:
                    candidates.append(path)
        except OSError:continue
    if not candidates:raise ValueError('No uncropped HD 16:9 backgrounds in '+str(directory))
    return str(random.SystemRandom().choice(candidates).resolve())


def discover(remote, folder, output, recursive, extensions=None):
    extensions=extensions or ['.mp4']
    for name, facts in sorted(remote.list(folder)):
        if name in ('.', '..') or '/' in name or '\\' in name or any(c in name for c in '\r\n'):
            continue
        path = folder.rstrip('/') + '/' + name
        if name.casefold() in ('karaoke','.karaoke-status') or path == output or path.startswith(output.rstrip('/') + '/'):
            continue
        if facts.get('type') == 'dir' and recursive:
            yield from discover(remote, path, output, recursive, extensions)
        elif facts.get('type') == 'file' and PurePosixPath(name).suffix.lower() in extensions:
            yield path, {'size': int(facts['size']), 'modify': facts.get('modify', '')}


def convert(source, config):
    output = source.parent / 'exports'
    artist, separator, title=source.stem.partition(' - ')
    if not separator:artist,title='Unknown Artist',source.stem
    background=select_background(config) if source.suffix.lower()=='.mp3' else config.get('video_background','original')
    if background!='original':
        image=Path(background)
        background=str((image if image.is_absolute() else ROOT/image).resolve())
        if not Path(background).is_file():raise FileNotFoundError('Background image not found: '+background)
    job={'source':str(source.resolve()),'title':title,'artist':artist,
         'language':config.get('language','da'),'mode':'music','background':background,'profile':'optimized',
         'separation':{'model':config.get('model','htdemucs'),'overlap':.25},
         'audio_quality':{'threads':int(config.get('threads',2)),'alternatives':[]},
         'render':{'canvas':'1920x1080','fps':config.get('fps',30),'intro_seconds':10,'intro_countdown':True,
                   'preset':'veryfast',
                   'highlight_colour':config.get('highlight_colour','#FFA500'),
                   'countdown_style':config.get('countdown_style','arc'),
                   'countdown_colour':config.get('countdown_colour','#BB3794')}}
    spec=source.parent/'job.json';spec.write_text(json.dumps(job),encoding='utf-8')
    scratch=source.parent/'generated';scratch.mkdir(exist_ok=True)
    (scratch/'tmp').mkdir(exist_ok=True)
    env={**os.environ,'KARAOKE_OUTPUT_DIR':str(output),'KARAOKE_WORK_DIR':str(scratch/'jobs'),
         'KARAOKE_RENDER_WORK_DIR':str(scratch/'render'),'TMPDIR':str(scratch/'tmp'),
         'TMP':str(scratch/'tmp'),'TEMP':str(scratch/'tmp'),
         'KARAOKE_EXTRA_INPUT_DIRS':'[]','KARAOKE_CLEANUP_AFTER_SONG':'0',
         'KARAOKE_SERVER_CONCURRENT':'1','KARAOKE_STILL_FIT':'contain',
         'KARAOKE_CLOUD_GPU_SLOTS':str(config.get('gpu_slots',1))}
    command=[sys.executable,'-u',str(ROOT/'karaoke.py'),'run','--job',str(spec),
             '--automatic-export','--keep-work','--parallel-stages']
    subprocess.run(command,cwd=ROOT,env=env,check=True)
    files = list(output.glob('*.mp4'))
    if len(files) != 1:
        raise RuntimeError('Expected exactly one completed MP4')
    from server_batch import verify_existing
    verify_existing(files[0])
    return files[0]


def _run_items(config, remote, items, converter=convert, claim=None):
    source_root = remote_path(config['input_folder'])
    beside=config.get('output_layout')=='beside-source'
    output_root = remote_path(config.get('output_folder',source_root.rstrip('/')+'/karaoke'))
    if source_root == output_root:
        raise ValueError('Use a separate output folder')
    spool = ROOT / 'work/ftp-cloud'
    if spool.is_symlink() or not spool.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('Unsafe spool folder')
    failed = 0
    found=0
    extensions=config.get('extensions',['.mp4'])
    if not isinstance(extensions,list) or not extensions or set(extensions)-{'.mp3','.mp4'}:
        raise ValueError('extensions must contain .mp3 and/or .mp4')
    count=0
    for source, fingerprint in items:
        found+=1
        song_output=str(PurePosixPath(source).parent/'karaoke') if beside else output_root
        identity = hashlib.sha256(source.encode()).hexdigest()[:24]
        receipt_path = song_output + '/.karaoke-status/' + identity + '.json'
        job = spool / identity
        try:
            if job.is_symlink():
                raise ValueError('Unsafe song folder')
            try:
                receipt = remote.json(receipt_path)
            except ftplib.error_perm as exc:
                if not str(exc).startswith('550'):
                    raise
                receipt = {}
            valid = False
            if (receipt.get('source') == source and receipt.get('fingerprint') == fingerprint
                    and receipt.get('output', '').startswith(song_output.rstrip('/') + '/')):
                try:
                    valid = remote.digest(remote_path(receipt['output'])) == receipt.get('sha256')
                    if valid and receipt.get('source_sha256'):
                        valid=remote.digest(source)==receipt['source_sha256']
                except ftplib.error_perm as exc:
                    if not str(exc).startswith('550'):
                        raise
            if valid:
                print('[SKIP UPLOADED]', source, flush=True)
                if job.exists():
                    shutil.rmtree(job)
                continue
            if config.get('limit',0) and count>=int(config['limit']):break
            if claim is not None and not claim():continue
            count+=1
            local = job / PurePosixPath(source).name
            print('[DOWNLOAD]', source, flush=True)
            remote.download(source, local, fingerprint['size'])
            source_sha=file_sha(local)
            print('[CONVERT]', source, flush=True)
            result = converter(local, config)
            current = dict(remote.list(str(PurePosixPath(source).parent)))[PurePosixPath(source).name]
            if {'size': int(current['size']), 'modify': current.get('modify', '')} != fingerprint:
                raise ValueError('FTP source changed during conversion')
            if remote.digest(source)!=source_sha:
                raise ValueError('FTP source content changed during conversion')
            relative = PurePosixPath(source).relative_to(PurePosixPath(source_root))
            filename=PurePosixPath(source).stem+' - Karaoke - '+source_sha[:8]+'.mp4'
            destination = str(PurePosixPath(song_output)/filename) if beside else str(PurePosixPath(output_root) / relative.parent / result.name)
            print('[UPLOAD]', destination, flush=True)
            remote.upload(result, destination)
            receipt = {'source': source, 'fingerprint': fingerprint, 'output': destination,
                       'source_sha256':source_sha,
                       'sha256': file_sha(result), 'bytes': result.stat().st_size,
                       'completed': time.time(), 'mode': 'automatic'}
            checkpoint = job / 'uploaded.json'
            checkpoint.write_text(json.dumps(receipt), encoding='utf-8')
            remote.upload(checkpoint, receipt_path)
            shutil.rmtree(job)
            print('[COMPLETE + CLEANED]', destination, flush=True)
        except Exception as exc:
            failed += 1
            if not job.is_symlink() and job.resolve().is_relative_to(spool.resolve()):
                if config.get('cleanup_failed',False):
                    if job.exists():shutil.rmtree(job)
                else:
                    job.mkdir(parents=True, exist_ok=True)
                    (job / 'error.txt').write_text(str(exc), encoding='utf-8')
            print('[FAILED]', source, str(exc), flush=True)
    if not found:
        print('[NO SOURCES] No matching files in '+source_root,flush=True)
        return 2
    return 2 if failed else 0


def run(config,remote,converter=convert):
    workers=config.get('workers',1)
    if type(workers) is not int or not 1<=workers<=5:raise ValueError('workers must be 1 to 5')
    limit=config.get('limit',0)
    if type(limit) is not int or limit<0:raise ValueError('limit must be a non-negative integer')
    source=remote_path(config['input_folder'])
    output=remote_path(config.get('output_folder',source.rstrip('/')+'/karaoke'))
    extensions=config.get('extensions',['.mp4'])
    if not isinstance(extensions,list) or not extensions or set(extensions)-{'.mp3','.mp4'}:
        raise ValueError('extensions must contain .mp3 and/or .mp4')
    items=list(discover(remote,source,output,config.get('recursive',True),extensions))
    if workers==1 or not items:return _run_items(config,remote,items,converter)
    count=0;guard=threading.Lock()
    def claim():
        nonlocal count
        with guard:
            if limit and count>=limit:return False
            count+=1;return True
    def one(item):return _run_items({**config,'limit':0},remote,[item],converter,claim)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results=list(pool.map(one,items))
    return 2 if any(results) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--list-only',action='store_true',help='Read FTP sources without loading models or converting')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if args.list_only:
        source=remote_path(config['input_folder'])
        output=remote_path(config.get('output_folder',source.rstrip('/')+'/karaoke'))
        rows=list(discover(Remote(config),source,output,config.get('recursive',True),config.get('extensions',['.mp3'])))
        print(json.dumps({'input':source,'count':len(rows),'first_files':rows[:10]},ensure_ascii=False,indent=2))
        return 0 if rows else 2
    if config.get('require_gpu', True):
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError('No CUDA GPU available; select a GPU runtime before starting')
        print('[GPU]', torch.cuda.get_device_name(0), flush=True)
        os.environ['KARAOKE_DEVICE'] = 'cuda'
    from model_queue import model_slot
    with model_slot(ROOT, timeout=0, name='ftp-cloud-batch'):
        return run(config, Remote(config))


if __name__ == '__main__':
    raise SystemExit(main())
