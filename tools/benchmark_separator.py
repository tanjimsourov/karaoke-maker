"""Benchmark one separator without changing the normal karaoke pipeline.

Download/setup are timed separately. The existing separation worker performs
full-song inference; verified instrumental audio and measurements are retained.
This is not transcription, alignment, a karaoke render, or listening approval.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys
import time

from project_runtime import ROOT, MODELS, DEMUCSPY, FFMPEG
from zoom_local_pipeline import read,save,digest
from parallel_song_benchmark import Measurement


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url')
    p.add_argument('--source-name')
    p.add_argument('--source',type=Path)
    p.add_argument('--report',type=Path)
    p.add_argument('--model',choices=['htdemucs','htdemucs_ft'],default='htdemucs')
    p.add_argument('--threads',type=int,default=4)
    p.add_argument('--worker',choices=['model-setup','verify'])
    p.add_argument('--stems',type=Path)
    a=p.parse_args()
    if not 1<=a.threads<=8:p.error('--threads must be 1..8')
    if a.worker=='model-setup':
        from huggingface_hub import snapshot_download
        repo='adefossez/HTDemucs' if a.model=='htdemucs' else 'adefossez/HTDemucs-ft'
        result=snapshot_download(repo,cache_dir=str(MODELS/'huggingface/hub'),
            allow_patterns=[a.model+'.yaml','*.safetensors'],max_workers=2)
        print(result,flush=True);return
    if not a.report:p.error('--report required')
    folder=a.report.resolve()
    if a.worker=='verify':
        import av
        from local_karaoke import verify_stems
        manifest=verify_stems({'vocal_reference':str(a.source),'stems_dir':str(a.stems)},a.stems.parent)
        if manifest['settings']['model']!=a.model:raise ValueError('Wrong model result')
        audio=folder/'instrumental.m4a'
        if audio.exists():raise FileExistsError(audio)
        subprocess.run([str(FFMPEG),'-v','error','-nostdin','-n','-i',str(a.stems/'instrumental.wav'),
            '-c:a','aac','-b:a','320k',str(audio)],check=True)
        subprocess.run([str(FFMPEG),'-v','error','-xerror','-nostdin','-i',str(audio),'-f','null','-'],check=True)
        with av.open(str(audio)) as media:
            duration=media.duration/av.time_base
            if abs(duration-manifest['duration'])>.1:raise ValueError('Instrumental duration mismatch')
        shutil.copy2(a.stems/'separation.json',folder/'separation.json')
        save(folder/'instrumental-verification.json',{'output':str(audio),'sha256':digest(audio),
            'source_sha256':digest(a.source),'model':a.model,'duration_seconds':duration,
            'strict_decode':'passed','stem_hashes_verified':True,
            'full_listening_completed':False,'residual_vocals_certified_absent':False})
        return
    if bool(a.url)==bool(a.source):p.error('Specify --url with --source-name, or --source')
    if a.url and (not a.source_name or Path(a.source_name).name!=a.source_name):p.error('Need an inputs filename')
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'measurement.json').exists():raise FileExistsError('Use a new report directory')
    import psutil
    source=(ROOT/'inputs'/a.source_name).resolve() if a.url else a.source.resolve()
    work=ROOT/'work/separator-benchmarks'/folder.name
    report={'status':'running','started_utc':datetime.now(timezone.utc).isoformat(),
        'tasks':[],'model':a.model,'cpu_threads':a.threads,'source':str(source),'work':str(work),
        'sample_interval_seconds':.5,'logical_cpus':psutil.cpu_count(),
        'physical_cpus':psutil.cpu_count(logical=False),'system_total_bytes':psutil.virtual_memory().total,
        'psutil_version':psutil.__version__,'human_content_approved':False,
        'working_set_note':'Sum of sampled process-tree working sets; shared pages can be counted multiple times.',
        'private_note':'Private committed bytes include page-file-backed memory, not only physical RAM.'}
    m=Measurement(folder,report);m.thread.start();script=str(Path(__file__).resolve())
    try:
        setup=[]
        if a.url:setup.append(m.start('download',[sys.executable,str(ROOT/'tools/download_youtube.py'),a.url,'--name',a.source_name]))
        setup.append(m.start('model-setup',[sys.executable,script,'--worker','model-setup','--model',a.model]))
        m.group(setup)
        import av
        with av.open(str(source)) as media:report['source_duration_seconds']=media.duration/av.time_base
        report['source_sha256']=digest(source)
        m.wait(m.start('separation',[str(DEMUCSPY),str(ROOT/'tools/separate_local_stems.py'),
            '--source',str(source),'--output',str(work/'stems'),'--model',a.model,
            '--threads',str(a.threads),'--seed','0']))
        report['separation_wall_seconds']=next(t['elapsed_seconds'] for t in report['tasks'] if t['name']=='separation')
        report['separation_to_track_ratio']=report['separation_wall_seconds']/report['source_duration_seconds']
        m.wait(m.start('stem-verification-and-audio',[sys.executable,script,'--worker','verify',
            '--source',str(source),'--stems',str(work/'stems'),'--report',str(folder),'--model',a.model]))
        report['status']='separation_benchmark_completed_not_listening_approved'
    except Exception as exc:
        report['status']='failed';report['error']=str(exc);raise
    finally:
        m.stop.set();m.thread.join()
        report['wall_seconds']=time.monotonic()-m.started
        report['completed_utc']=datetime.now(timezone.utc).isoformat()
        save(folder/'measurement.json',report)
    print('MEASUREMENTS:',folder/'measurement.json',flush=True)


if __name__=='__main__':main()
