"""Portable version of the existing bridge's full fine-tuned component merger.

Every original model and bag weight is retained. Child RNG checkpoints preserve
component order. Intermediate stems are never accepted as complete separation.
"""
import argparse
from pathlib import Path
import subprocess
import time
import numpy as np
import yaml
from scipy.io import wavfile
from huggingface_hub import hf_hub_download
from project_runtime import FFMPEG
from zoom_local_pipeline import read,save,digest

SOURCES=('drums','bass','other','vocals')
SIGNATURES=['f7e0c4bc','d12395a8','92cfc3b6','04573f0d']


def bag_definition():
    path=Path(hf_hub_download('adefossez/HTDemucs-ft','htdemucs_ft.yaml',local_files_only=True))
    bag=yaml.safe_load(path.read_text())
    if bag['models']!=SIGNATURES or bag.get('segment') is not None:
        raise ValueError('Cached fine-tuned bag changed; review required')
    return path,bag


def component_folder(output,index):return Path(output)/'_isolated_ft'/f'{index}-{SIGNATURES[index]}'


def combine_components(components,weights):
    # Reused from bridge/separate_isolated_ft.py: weighted per-source averaging.
    weights=np.asarray(weights,dtype=float)
    if weights.shape!=(len(components),4) or not np.isfinite(weights).all() or np.any(weights<0) or np.any(weights.sum(axis=0)<=0):
        raise ValueError('Invalid fine-tuned bag weights')
    result={}
    for k,name in enumerate(SOURCES):
        value=None
        for i,component in enumerate(components):
            if not weights[i,k]:continue
            part=np.asarray(component[name],dtype=np.float32)*weights[i,k]
            value=part.copy() if value is None else value+part
        result[name]=value/weights[:,k].sum()
    result['instrumental']=sum(result[k] for k in SOURCES[:3])
    return result


def verified_component(source,output,index,bag_path=None):
    path,bag=bag_definition() if bag_path is None else (bag_path,None)
    folder=component_folder(output,index);report=read(folder/'separation.json')
    settings=report['settings'];component=settings.get('component',{})
    if (settings['source_sha256']!=digest(source) or settings['model']!='htdemucs_ft' or
        settings.get('start')!=0 or settings.get('shifts')!=1 or settings.get('overlap')!=.5 or
        settings.get('ensemble') is not None or settings.get('keep_backing') is not None or
        settings['seconds'] is not None or not report['is_intermediate'] or report['is_excerpt'] or
        component.get('index')!=index or component.get('signature')!=SIGNATURES[index] or
        component.get('bag_sha256')!=digest(path) or report['model_sources']!=list(SOURCES)):
        raise ValueError('Component binding mismatch')
    checkpoint=hf_hub_download('adefossez/HTDemucs-ft',SIGNATURES[index]+'.safetensors',local_files_only=True)
    if component.get('checkpoint_sha256')!=digest(checkpoint):raise ValueError('Component model weights changed')
    if index==0:
        if settings.get('shift_seed')!=0:raise ValueError('Missing initial RNG seed')
    elif settings.get('random_state_in_sha256')!=digest(component_folder(output,index-1)/'random-state-after.json'):
        raise ValueError('Component RNG chain mismatch')
    if not all(digest(folder/name)==sha for name,sha in report['files'].items()):raise ValueError('Component WAV changed')
    if digest(folder/'random-state-after.json')!=report['runtime']['random_state_after_sha256']:
        raise ValueError('Component RNG result changed')
    return report


def merge(source,output):
    source=source.resolve();output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    source_sha=digest(source);path,bag=bag_definition();started=time.monotonic()
    if (output/'separation.json').exists():
        r=read(output/'separation.json')
        if r['settings']['source_sha256']!=source_sha or r['is_intermediate'] or r['is_excerpt']:
            raise ValueError('Different separation exists')
        if all(digest(output/name)==sha for name,sha in r['files'].items()):return
        raise ValueError('Existing complete stems changed')
    if list(output.glob('*.wav')):raise ValueError('Untracked final stems; refusing overwrite')
    components=[];records=[]
    for index,signature in enumerate(SIGNATURES):
        report=verified_component(source,output,index,path);folder=component_folder(output,index)
        gain=report['common_gain']
        if not np.isfinite(gain) or gain<=0:raise ValueError('Invalid component gain')
        selected={}
        for k,name in enumerate(SOURCES):
            if bag['weights'][index][k]:
                sr,x=wavfile.read(folder/(name+'.wav'),mmap=True)
                if sr!=44100 or x.ndim!=2 or x.shape[1]!=2:raise ValueError('Invalid component canvas')
                selected[name]=np.asarray(x,dtype=np.float32)/gain
        components.append(selected)
        records.append({'signature':signature,'manifest_sha256':digest(folder/'separation.json'),
            'elapsed_seconds':report['elapsed_seconds']})
    values=combine_components(components,bag['weights'])
    if len({x.shape for x in values.values()})!=1 or any(not np.isfinite(x).all() for x in values.values()):
        raise ValueError('Invalid merged samples')
    gain=min(1.,.99/max(float(np.max(np.abs(x))) for x in values.values()))
    files={}
    for name,x in values.items():
        dest=output/(name+'.wav')
        subprocess.run([str(FFMPEG),'-v','error','-nostdin','-n','-f','f32le','-ar','44100','-ac','2',
            '-i','-','-c:a','pcm_f32le',str(dest)],input=(x*gain).astype('<f4').tobytes(),check=True)
        files[dest.name]=digest(dest)
    if digest(source)!=source_sha:raise ValueError('Source changed during merge')
    save(output/'separation.json',{'settings':{'source_sha256':source_sha,'model':'htdemucs_ft',
        'start':0,'seconds':None,'shifts':1,'overlap':.5,'ensemble':None,'keep_backing':None},
        'files':files,'duration':next(iter(values.values())).shape[0]/44100,'sample_rate':44100,
        'channels':2,'common_gain':gain,'is_excerpt':False,'is_intermediate':False,
        'model_sources':list(SOURCES),'elapsed_seconds':sum(r['elapsed_seconds'] for r in records)+time.monotonic()-started,
        'instrumental':'All four original fine-tuned components combined with the cached bag weights; drums+bass+other',
        'runtime':{'process_isolated_components':records,'bag_sha256':digest(path),'shift_seed':0,
            'elapsed_basis':'Sum of component compute times plus merge. Batch report retains wall/queue times.'}})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();merge(a.source,a.output)
