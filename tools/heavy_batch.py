"""Resource-aware, resumable full-song heavy-model batch, producing review drafts.

All four original fine-tuned components run per song with a saved RNG chain.
Independent jobs/stages overlap. A 95% memory ceiling is an admission threshold,
not a guarantee against unrelated OS/app allocations after a worker starts.
"""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import os
import sys
import time
import psutil
from project_runtime import ROOT,DEMUCSPY,OUT
from zoom_local_pipeline import read,save,digest
from parallel_song_benchmark import Measurement,process_metrics
from isolated_ft import component_folder,verified_component,SIGNATURES

GIB=1024**3
DEPS={'background':[], 'component-0':[], 'component-1':['component-0'],
    'component-2':['component-1'],'component-3':['component-2'],
    'merge':['component-3'],'audio-qc':['merge'],'vocal-asr':['merge'],
    'render':['background','audio-qc','vocal-asr'],'export':['render']}
PRIORITY={'export':0,'render':1,'audio-qc':2,'vocal-asr':2,'merge':3,'background':4}


def ready_stages(stages):
    return [name for name,deps in DEPS.items() if stages[name]['status']=='pending' and
        all(stages[d]['status']=='completed' for d in deps)]


def admitted(available,total,active,candidate,ceiling=.95,max_heavy=2,cpu_budget=7):
    if len(active)>=3:return False
    if candidate['heavy'] and sum(t['heavy'] for t in active)>=max_heavy:return False
    if not candidate['heavy'] and any(not t['heavy'] for t in active):return False
    if sum(t['cpu'] for t in active)+candidate['cpu']>cpu_budget:return False
    reserved=sum(max(0,t['memory']-t.get('rss',0)) for t in active)
    floor=max(512*1024**2,total*(1-ceiling))
    return available-reserved-candidate['memory']>=floor


def resource_profile(stage,duration):
    if stage.startswith('component-'):memory=2.3+duration/600;cpu=3
    else:memory,cpu={'background':(.6,1),'merge':(1.2,1),'audio-qc':(3.4,3),
        'vocal-asr':(2.,3),'render':(3.7,3),'export':(1.,2)}[stage]
    return {'memory':int(memory*GIB),'cpu':cpu,'heavy':stage!='background'}


def command(job,stage,retry=False):
    py=sys.executable;path=str(job['job_path']);folder=job['folder'];source=job['job']['source']
    if stage=='background':return [py,str(ROOT/'tools/parallel_song_benchmark.py'),'--worker','background','--job',path]
    if stage.startswith('component-'):
        index=int(stage[-1]);stems=folder/'stems';dest=component_folder(stems,index)
        cmd=[str(DEMUCSPY),str(ROOT/'tools/separate_local_stems.py'),'--source',source,
            '--output',str(dest),'--model','htdemucs_ft','--submodel-index',str(index),
            '--threads','2' if retry else '3']
        return cmd+(['--seed','0'] if index==0 else ['--random-state-in',str(component_folder(stems,index-1)/'random-state-after.json')])
    if stage=='merge':return [py,str(ROOT/'tools/isolated_ft.py'),'--source',source,'--output',str(folder/'stems')]
    if stage=='audio-qc':return [py,str(ROOT/'karaoke.py'),'audio-qc','--job',path]
    if stage=='vocal-asr':return [py,str(ROOT/'tools/parallel_song_benchmark.py'),'--worker','vocal-asr','--job',path]
    if stage=='render':return [py,str(Path(__file__).resolve()),'--worker','render','--job',path]
    if stage=='export':return [py,str(ROOT/'tools/export_checked_sample.py'),'--job',path,
        '--name',job['output_name'],'--unreviewed-benchmark','--resume-existing']
    raise ValueError(stage)


def artifact(job,stage):
    folder=job['folder'];source=job['job']['source']
    if stage.startswith('component-'):
        return verified_component(source,folder/'stems',int(stage[-1]))['files']
    if stage=='merge':
        from local_karaoke import verify_stems
        r=verify_stems({'vocal_reference':source,'stems_dir':str(folder/'stems')},folder)
        if r['settings']['model']!='htdemucs_ft':raise ValueError('Batch requires heavy model')
        return r['files']
    if stage=='background':
        from branding_guard import resolved_background
        path=Path(resolved_background(source,folder/'branding-background'))
        scan=read(folder/'branding-background'/('source-scan.json' if path==Path(source) else 'clean-scan.json'))
        if not scan.get('complete') or scan['hits'] or scan['binding']['video_sha256']!=digest(path):
            raise ValueError('Background scan incomplete/failed')
        return {'background':str(path),'sha256':digest(path)}
    if stage=='audio-qc':
        from separation_guard import validate
        r,_=validate(source,folder/'audio-quality');return r['selected']
    if stage=='vocal-asr':
        draft=folder/'parallel-asr';binding=read(draft/'vocal-binding.json')
        if binding!={'source':digest(source),'vocals':digest(folder/'stems/vocals.wav')}:
            raise ValueError('ASR binding changed')
        return {name:digest(draft/name) for name in ['transcript.json','transcript.whisper.json','sync.json']}
    if stage=='render':
        from workflow import context,verify_preview
        r=verify_preview(context(job['job'],folder),folder,branding=False)
        return {'output':r['output'],'sha256':r['sha256']}
    if stage=='export':
        path=OUT/job['output_name']
        receipts=list((ROOT/'reports/completed'/folder.name).glob('*/sample-export.json'))
        if (folder/'sample-export.json').is_file():receipts.append(folder/'sample-export.json')
        for receipt in sorted(receipts,key=lambda p:p.stat().st_mtime,reverse=True):
            r=read(receipt)
            if Path(r['output'])==path and path.is_file() and digest(path)==r['sha256']:
                if r['strict_decode']!='passed' or not r.get('unreviewed_benchmark'):raise ValueError('Wrong export basis')
                return r
        raise ValueError('Missing verified batch draft export')
    raise ValueError(stage)


def render_worker(job_path):
    from workflow import normalize,context,verify_preview,ReviewRequired
    from parallel_song_benchmark import merge_vocal_draft,worker
    job,folder=normalize(read(job_path),job_path.parent)
    merge_vocal_draft(job_path)
    if (folder/'preview-validation.json').exists():
        try:
            verify_preview(context(job,folder),folder,branding=False)
            print('Reusing checksum-bound benchmark draft',flush=True);return
        except (ReviewRequired,FileNotFoundError,ValueError):pass
    worker('draft-render',job_path)


def run(manifest,report_dir,ceiling=.95):
    from workflow import normalize
    report_dir.mkdir(parents=True,exist_ok=True);state_path=report_dir/'state.json'
    binding={'manifest_sha256':digest(manifest),'jobs':{}}
    jobs=[]
    for item in read(manifest)['jobs']:
        path=ROOT/item['job'];job,folder=normalize(read(path),path.parent)
        source=Path(job['source']);receipt=read(source.with_suffix('.source.json'))
        if receipt['url']!=item['url'] or receipt['sha256']!=job['source_sha256'] or not receipt['strict_decode_passed']:
            raise ValueError('Unverified/mismatched download: '+item['id'])
        binding['jobs'][item['id']]={'job_sha256':digest(path),'source_sha256':job['source_sha256']}
        jobs.append({'id':item['id'],'job_path':path,'job':job,'folder':folder,
            'duration':receipt['duration_seconds'],
            'output_name':job['artist']+' - '+job['title']+' - 2026-10-31 BATCH - BENCHMARK.mp4'})
    if state_path.exists():
        state=read(state_path)
        if state['binding']!=binding:raise ValueError('Batch inputs/config changed; use a new report')
    else:state={'binding':binding,'status':'running','jobs':{},'human_content_approved':False,
        'memory_ceiling':ceiling,'memory_policy':'Admission threshold; unrelated OS/app allocations can fluctuate.',
        'known_quality_limitations':'Automatic voice-screen sensitivity is not certified. No full listening or lyric approval.'}
    for job in jobs:
        saved=state['jobs'].setdefault(job['id'],{'status':'pending','last_scheduled':0,
            'stages':{name:{'status':'pending','attempts':[]} for name in DEPS}})
        if saved['status']=='completed':
            if digest(saved['output']['output'])!=saved['output']['sha256']:raise ValueError('Completed output changed')
            continue
        for stage,row in saved['stages'].items():
            if row['status']=='running':
                try:
                    p=psutil.Process(row['pid'])
                    if abs(p.create_time()-row['process_created'])<.01:raise RuntimeError('Batch worker still active; refusing duplicate coordinator')
                except psutil.NoSuchProcess:pass
                row['status']='pending'
            if row['status']=='completed':
                try:
                    if artifact(job,stage)!=row['artifact']:raise ValueError('Artifact changed')
                except Exception as exc:raise ValueError('Resume artifact changed: '+job['id']+'/'+stage+': '+str(exc)) from exc
        # Failed/review-blocked jobs stay terminal on a resume. Do not reset
        # their retry budgets or silently bypass a review requirement.
    state['status']='running'
    attempt=report_dir/f'attempt-{len(list(report_dir.glob("attempt-*")))+1:03d}'
    attempt.mkdir()
    measurements={'status':'running','tasks':[],'started_utc':datetime.now(timezone.utc).isoformat(),
        'working_set_note':'Summed sampled working sets; shared pages can be counted more than once.',
        'private_note':'Private committed bytes include possible page-file backing.',
        'memory_ceiling':ceiling,'max_heavy_workers':2,'max_active_workers':3,
        'model':'htdemucs_ft; all original components and weights, isolated process lifetimes'}
    m=Measurement(attempt,measurements);m.thread.start();active=[];sequence=0;last_wait=0.
    os.environ.update({'KARAOKE_ALIGNMENT_THREADS':'3','KARAOKE_FFMPEG_THREADS':'3'})
    try:
        while True:
            for running in list(active):
                if running['task'][0].poll() is None:continue
                job,stage=running['job'],running['stage'];saved=state['jobs'][job['id']];row=saved['stages'][stage]
                try:
                    m.wait(running['task']);proof=artifact(job,stage)
                    row.update(status='completed',artifact=proof)
                    if stage=='export':saved.update(status='completed',output=proof)
                except Exception as exc:
                    row['error']=str(exc)
                    if running['task'][0].returncode==2:
                        row['status']='needs_review';saved['status']='needs_review'
                    elif len(row['attempts'])<2:row['status']='pending'
                    else:row['status']='failed';saved['status']='failed'
                active.remove(running);save(state_path,state)
            candidates=[]
            for job in jobs:
                saved=state['jobs'][job['id']]
                if saved['status'] in ['completed','failed','needs_review']:continue
                for stage in ready_stages(saved['stages']):
                    candidates.append((PRIORITY.get(stage,5),saved['last_scheduled'],job,stage))
            for _,_,job,stage in sorted(candidates,key=lambda x:(x[0],x[1],x[2]['id'])):
                vm=psutil.virtual_memory();profile=resource_profile(stage,job['duration'])
                live=[]
                for running in active:
                    try:rss=process_metrics(psutil.Process(running['task'][0].pid))['rss']
                    except psutil.Error:rss=0
                    live.append({**running['profile'],'rss':rss})
                if not admitted(vm.available,vm.total,live,profile,ceiling):continue
                saved=state['jobs'][job['id']];row=saved['stages'][stage]
                if len(row['attempts'])>=2:
                    row['status']='failed';saved['status']='failed';continue
                sequence+=1;saved['last_scheduled']=sequence;saved['status']='processing'
                label=job['id']+'-'+stage+'-'+str(len(row['attempts'])+1)
                task=m.start(label,command(job,stage,retry=bool(row['attempts'])))
                row.update(status='running',pid=task[0].pid,process_created=psutil.Process(task[0].pid).create_time())
                row['attempts'].append({'log':task[1]['log'],'started_utc':datetime.now(timezone.utc).isoformat()})
                active.append({'job':job,'stage':stage,'profile':profile,'task':task});save(state_path,state)
            terminal=all(v['status'] in ['completed','failed','needs_review'] for v in state['jobs'].values())
            if terminal and not active:break
            if not active and time.monotonic()-last_wait>30:
                print('WAIT: memory admission; available GiB',round(psutil.virtual_memory().available/GIB,2),flush=True);last_wait=time.monotonic()
            time.sleep(.5)
        state['status']='complete_unapproved_drafts' if all(v['status']=='completed' for v in state['jobs'].values()) else 'partial_failure'
    finally:
        m.stop.set();m.thread.join();measurements['wall_seconds']=time.monotonic()-m.started
        measurements['status']=state['status'];save(attempt/'measurement.json',measurements)
        state['last_measurements']=str(attempt/'measurement.json');save(state_path,state)
    return 0 if state['status']=='complete_unapproved_drafts' else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path);p.add_argument('--report',type=Path)
    p.add_argument('--worker',choices=['render']);p.add_argument('--job',type=Path)
    p.add_argument('--memory-ceiling',type=float,default=.95)
    a=p.parse_args()
    if a.worker:
        if not a.job:p.error('--job required')
        render_worker(a.job.resolve());return 0
    if not a.manifest or not a.report:p.error('--manifest and --report required')
    if not .5<=a.memory_ceiling<=.95:p.error('Memory ceiling must be 0.5..0.95')
    from model_queue import model_slot
    with model_slot(name='heavy-batch',timeout=1):return run(a.manifest.resolve(),a.report.resolve(),a.memory_ceiling)


if __name__=='__main__':raise SystemExit(main())
