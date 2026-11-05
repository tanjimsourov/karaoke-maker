"""Reuse verified same-source model stems to create two unapproved karaoke drafts."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
from project_runtime import ROOT, OUT, child_env
from zoom_local_pipeline import read, save, digest
from workflow import normalize


def main():
    report = ROOT/'reports/comparisons/2026-10-31-mucki-bar-htdemucs-vs-ft'
    data = read(report/'comparison-inputs.json')
    if digest(data['source']) != data['source_sha256']:
        raise ValueError('Comparison source changed')
    configs = ROOT/'config/mucki-model-karaoke'
    configs.mkdir(exist_ok=True)
    env = child_env()
    env.update(KARAOKE_ALIGNMENT_THREADS='3', KARAOKE_FFMPEG_THREADS='3')
    state = {'status':'running', 'outputs':[], 'human_content_approved':False}
    save(report/'karaoke-status.json', state)
    for record in data['records']:
        model = record['name']
        path = configs/(model+'.json')
        job = {'source':data['source'], 'title':'Mucki Bar', 'artist':'Tobias Rahim',
               'language':'da', 'mode':'music', 'background':'original',
               'alignment_model':'saattrupdan/wav2vec2-xls-r-300m-ftspeech',
               'audio_quality':{'threads':3,'alternatives':[]},
               'render':{'fps':30,'crf':14}}
        # Separate data identities without altering the displayed song metadata.
        if model == 'htdemucs_ft':
            job['audio_quality']['threads'] = 2
        save(path, job)
        normalized, folder = normalize(job, path.parent)
        dest = folder/'stems'
        dest.mkdir(parents=True, exist_ok=True)
        source = Path(record['stems'])
        manifest = read(source/'separation.json')
        if manifest['settings']['model'] != model or manifest['settings']['source_sha256'] != data['source_sha256']:
            raise ValueError('Wrong saved model/source')
        for name, sha in manifest['files'].items():
            if digest(source/name) != sha:
                raise ValueError('Changed model stem: '+name)
            target = dest/name
            if target.exists():
                if digest(target) != sha: raise ValueError('Conflicting target stem')
            else: shutil.copy2(source/name,target)
        save(dest/'separation.json',manifest)
        commands = [
            ['tools/parallel_song_benchmark.py','--worker','background','--job',str(path)],
            ['karaoke.py','audio-qc','--job',str(path)],
            ['tools/parallel_song_benchmark.py','--worker','vocal-asr','--job',str(path)],
            ['tools/heavy_batch.py','--worker','render','--job',str(path)],
        ]
        for index,args in enumerate(commands):
            print('START',model,index,flush=True)
            with (report/(model+'-karaoke-'+str(index)+'.log')).open('a',encoding='utf-8') as log:
                subprocess.run([sys.executable,*args],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
            print('END',model,index,flush=True)
        name = 'Tobias Rahim - Mucki Bar - '+model+' - BENCHMARK.mp4'
        subprocess.run([sys.executable,'tools/export_checked_sample.py','--job',str(path),
                        '--name',name,'--unreviewed-benchmark','--resume-existing'],
                       cwd=ROOT,env=env,check=True)
        target = report/'htdemucs'/name
        if target.exists() and digest(target) != digest(OUT/name):
            raise ValueError('Existing comparison output differs')
        if not target.exists(): shutil.copy2(OUT/name,target)
        if digest(target) != digest(OUT/name): raise ValueError('Copy integrity failed')
        state['outputs'].append({'model':model,'path':str(target),'sha256':digest(target)})
        save(report/'karaoke-status.json',state)
    state['status']='complete_unapproved_drafts'
    save(report/'karaoke-status.json',state)


if __name__ == '__main__':
    main()
