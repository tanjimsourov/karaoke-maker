"""Job-scoped decoded masters and rate/channel views, with checked content identities."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid
import numpy as np
from project_runtime import FFMPEG
from model_queue import model_slot

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

@contextmanager
def scope(folder):
    previous=os.environ.get('KARAOKE_AUDIO_CACHE')
    os.environ['KARAOKE_AUDIO_CACHE']=str(Path(folder).resolve())
    try:yield
    finally:
        if previous is None:os.environ.pop('KARAOKE_AUDIO_CACHE',None)
        else:os.environ['KARAOKE_AUDIO_CACHE']=previous

def decode(path,rate=16000,channels=1):
    root=os.environ.get('KARAOKE_AUDIO_CACHE')
    def raw(source):
        b=subprocess.run([str(FFMPEG),'-v','error','-i',str(source),'-map','0:a:0',
            '-ac',str(channels),'-ar',str(rate),'-f','f32le','-'],capture_output=True,check=True).stdout
        a=np.frombuffer(b,'<f4').reshape(-1,channels).copy()
        if not a.size or not np.isfinite(a).all():raise ValueError('Empty/nonfinite decoded audio')
        return a[:,0] if channels==1 else a
    if not root:return raw(path)
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    binding={'source':sha(path),'decoder':sha(FFMPEG),'version':1}
    key=hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()
    folder=root/key;folder.mkdir(exist_ok=True)
    with model_slot(root=root,name='decode-'+key[:16],timeout=120):
        master=folder/'master.wav';receipt=folder/'master.json'
        if receipt.exists():
            r=json.loads(receipt.read_text())
            if r['binding']!=binding or sha(master)!=r['sha256']:raise ValueError('Decoded master cache corrupted')
        else:
            temp=folder/(uuid.uuid4().hex+'.wav')
            subprocess.run([str(FFMPEG),'-v','error','-i',str(path),'-map','0:a:0',
                '-c:a','pcm_f32le',str(temp)],check=True)
            temp.replace(master)
            receipt.write_text(json.dumps({'binding':binding,'sha256':sha(master)}))
        view=folder/f'{rate}-{channels}.npy';check=view.with_suffix('.json')
        if check.exists():
            if sha(view)!=json.loads(check.read_text())['sha256']:raise ValueError('Decoded view cache corrupted')
            return np.load(view,allow_pickle=False)
        values=raw(master);temp=folder/(uuid.uuid4().hex+'.npy')
        np.save(temp,values,allow_pickle=False);temp.replace(view)
        check.write_text(json.dumps({'sha256':sha(view)}))
        return values
