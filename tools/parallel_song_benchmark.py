"""Measure a single song with bounded overlap; never fabricate human approval.

Independent source checks overlap separation. After separation, instrumental QC
and vocal-only ASR run in separate processes/directories. Dependent alignment and
rendering follow. --draft explicitly creates an unapproved benchmark preview.
Reports survive work cleanup. Run with the project's zoom Python environment.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from project_runtime import ROOT, child_env
from zoom_local_pipeline import read, save, digest


def process_metrics(process):
    """Private bytes exclude shared DLL/model pages counted by working sets."""
    import psutil
    members=[]
    try: members=[process,*process.children(recursive=True)]
    except psutil.Error: pass
    result={'rss':0,'private':0,'cpu':{},'io':{},'processes':len(members)}
    for p in members:
        try:
            with p.oneshot():
                key=f'{p.pid}:{p.create_time()}'
                m=p.memory_info(); c=p.cpu_times(); io=p.io_counters()
                result['rss']+=m.rss
                result['private']+=getattr(m,'private',m.rss)
                result['cpu'][key]=c.user+c.system
                result['io'][key]=[io.read_bytes,io.write_bytes]
        except psutil.Error: pass
    return result


class Measurement:
    def __init__(self,folder,report):
        import psutil
        self.psutil=psutil;self.folder=folder;self.report=report
        self.stop=threading.Event();self.started=time.monotonic()
        self.active={};self.watchers={};self.mutex=threading.Lock();self.cpu={};self.io={}
        self.root=psutil.Process();self.previous_cpu=0.;self.previous_time=0.
        self.thread=threading.Thread(target=self.monitor,daemon=True)

    def monitor(self):
        ps=self.psutil;ps.cpu_percent()
        fields=['elapsed_seconds','active_stages','project_working_set_bytes',
            'project_private_bytes','project_cpu_percent_of_pc','system_used_bytes',
            'system_available_bytes','system_cpu_percent','project_processes']
        with (self.folder/'resources.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
            while not self.stop.is_set():
                elapsed=time.monotonic()-self.started
                m=process_metrics(self.root);vm=ps.virtual_memory()
                self.cpu.update(m['cpu']);self.io.update(m['io'])
                cpu=sum(self.cpu.values())
                # The root already spent CPU importing modules before t=0;
                # bootstrap the first sample rather than reporting that as a spike.
                percent=(max(0,(cpu-self.previous_cpu)/max(.01,elapsed-self.previous_time)/(os.cpu_count() or 1)*100)
                    if self.previous_time else 0.)
                self.previous_cpu=cpu;self.previous_time=elapsed
                with self.mutex:
                    stages=list(self.active)
                    for name,task in self.active.items():
                        try:tm=process_metrics(ps.Process(task['pid']))
                        except ps.Error:continue
                        task['peak_working_set_bytes']=max(task['peak_working_set_bytes'],tm['rss'])
                        task['peak_private_bytes']=max(task['peak_private_bytes'],tm['private'])
                    self.report['peak_project_working_set_bytes']=max(self.report.get('peak_project_working_set_bytes',0),m['rss'])
                    self.report['peak_project_private_bytes']=max(self.report.get('peak_project_private_bytes',0),m['private'])
                    self.report['peak_total_system_used_bytes']=max(self.report.get('peak_total_system_used_bytes',0),vm.total-vm.available)
                    self.report['min_available_system_bytes']=min(self.report.get('min_available_system_bytes',vm.available),vm.available)
                    self.report['peak_project_cpu_percent_of_pc']=max(self.report.get('peak_project_cpu_percent_of_pc',0),percent)
                    self.report['project_cpu_seconds_observed']=cpu
                    self.report['project_io_read_bytes_observed']=sum(v[0] for v in self.io.values())
                    self.report['project_io_write_bytes_observed']=sum(v[1] for v in self.io.values())
                    self.report['wall_seconds']=elapsed
                    try:
                        save(self.folder/'measurement.json',self.report)
                    except PermissionError:
                        # Windows readers can briefly deny atomic replacement.
                        # Preserve monitoring and retry on the next sampling tick.
                        self.report['report_write_contention_count']=self.report.get('report_write_contention_count',0)+1
                writer.writerow(dict(zip(fields,[round(elapsed,3),'|'.join(stages),m['rss'],m['private'],round(percent,2),vm.total-vm.available,vm.available,ps.cpu_percent(),m['processes']])))
                f.flush();self.stop.wait(.5)

    def start(self,name,command):
        log=(self.folder/(name+'.log')).open('w',encoding='utf-8')
        env=child_env()
        env.update({'KARAOKE_THREADS':'3','KARAOKE_SEPARATION_THREADS':'4',
            'OMP_NUM_THREADS':'3','MKL_NUM_THREADS':'3','OPENBLAS_NUM_THREADS':'3',
            'PYTHONUNBUFFERED':'1'})
        p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,cwd=ROOT)
        row={'name':name,'pid':p.pid,'start_seconds':time.monotonic()-self.started,
            'command':command,'log':str(self.folder/(name+'.log')),
            'peak_working_set_bytes':0,'peak_private_bytes':0}
        with self.mutex:self.active[name]=row;self.report['tasks'].append(row)
        def finished():
            code=p.wait()
            with self.mutex:
                row['exit_code']=code;row['end_seconds']=time.monotonic()-self.started
                row['elapsed_seconds']=row['end_seconds']-row['start_seconds']
                self.active.pop(name,None)
        watcher=threading.Thread(target=finished,daemon=True)
        self.watchers[p.pid]=watcher;watcher.start()
        print('START',name,p.pid,flush=True)
        return p,row,log

    def wait(self,task):
        p,row,log=task;self.watchers[p.pid].join();code=row['exit_code'];log.close()
        print('END',row['name'],code,round(row['elapsed_seconds'],2),flush=True)
        if code:raise RuntimeError(f"{row['name']} failed ({code}); see {row['log']}")

    def group(self,tasks):
        # Wait for all siblings even when one fails; never abandon live workers.
        failures=[]
        for task in tasks:
            try:self.wait(task)
            except RuntimeError as e:failures.append(str(e))
        if failures:raise RuntimeError('; '.join(failures))


def worker(kind,job_path):
    if kind=='alignment-setup':
        from huggingface_hub import snapshot_download
        from project_runtime import MODELS
        print(snapshot_download('saattrupdan/wav2vec2-xls-r-300m-ftspeech',
            cache_dir=str(MODELS/'huggingface/hub'),max_workers=2,
            allow_patterns=['config.json','preprocessor_config.json','special_tokens_map.json',
                'tokenizer_config.json','vocab.json','model.safetensors']))
        return
    from workflow import normalize,context
    import local_karaoke as local
    job,folder=normalize(read(job_path),job_path.parent)
    if kind=='background':
        if job.get('profile')=='optimized':
            from inline_branding import prepare
            print(prepare(job['source'],folder/'branding-background'))
        else:
            from branding_guard import prepare_background
            print(prepare_background(job['source'],folder/'branding-background'))
    elif kind=='vocal-asr':
        cfg=context(job,folder,strict_quality=False)
        draft=folder/'parallel-asr';draft.mkdir(parents=True,exist_ok=True)
        local.transcribe(cfg,draft)
        save(draft/'vocal-binding.json',{'source':digest(job['source']),
            'vocals':digest(cfg['align_audio'])})
    elif kind=='draft-render':
        # Exit the Torch/WhisperX process before starting FFmpeg. Deleting model
        # objects does not reliably release the CPU runtime's committed memory.
        subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker','draft-align',
                        '--job',str(job_path)],check=True)
        from zoom_local_pipeline import render
        cfg=context(job,folder)
        phases=read(folder/'benchmark-phases.json')
        started=time.perf_counter();render(cfg,folder,preview=True)
        phases['render_and_backing_verification_seconds']=time.perf_counter()-started
        save(folder/'benchmark-phases.json',phases)
    elif kind=='draft-align':
        from asr_draft_quality import validate_asr_draft
        from zoom_local_pipeline import align,render
        import torch
        alignment_threads=int(os.environ.get('KARAOKE_ALIGNMENT_THREADS','6'))
        if not 1<=alignment_threads<=64:raise ValueError('KARAOKE_ALIGNMENT_THREADS must be 1..64')
        torch.set_num_threads(alignment_threads)
        cfg=context(job,folder)
        validate_asr_draft({'segments':read(folder/'transcript.json')})
        local.verify_stems(cfg,folder)
        save(folder/'review-status.json',{'status':'unapproved_benchmark_draft',
            'lyrics_reviewed':False,'full_listening_completed':False})
        # Existing preview backend explicitly permits unapproved drafts. Never
        # create transcript-review/full-review/approval files in this path.
        phases={};started=time.perf_counter()
        align(cfg,folder)
        phases['alignment_seconds']=time.perf_counter()-started
        started=time.perf_counter();local.check_timing(cfg,folder)
        phases['timing_check_seconds']=time.perf_counter()-started
        save(folder/'benchmark-phases.json',phases)
    else:raise ValueError(kind)


def merge_vocal_draft(job_path):
    from workflow import normalize,context
    job,folder=normalize(read(job_path),job_path.parent);cfg=context(job,folder)
    draft=folder/'parallel-asr'
    if read(draft/'vocal-binding.json')!={'source':digest(job['source']),'vocals':digest(cfg['align_audio'])}:
        raise ValueError('Source/vocals changed during parallel ASR')
    names=['transcript.json','transcript.whisper.json','sync.json']
    if (draft/'language.json').exists():names.append('language.json')
    for name in names:
        target=folder/name
        if target.exists() and digest(target)!=digest(draft/name):
            raise ValueError('Existing corrected transcript/history must not be overwritten')
        if not target.exists():shutil.copy2(draft/name,target)
    # Selection changes backing only, not the source/vocals used to transcribe.
    save(folder/'inputs.json',{key:digest(cfg[key]) for key in ['vocal_reference','zoom_video']})
    save(folder/'parallel-asr-import.json',{'vocal_binding':read(draft/'vocal-binding.json'),
        'draft_sha256':digest(draft/'transcript.json'),'selected_backing_sha256':digest(cfg['zoom_video']),
        'lyrics_reviewed':False})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',type=Path,required=True)
    parser.add_argument('--url');parser.add_argument('--source-name')
    parser.add_argument('--report',type=Path)
    parser.add_argument('--draft',action='store_true',help='Render an unapproved benchmark draft; never approve it')
    parser.add_argument('--worker',choices=['background','vocal-asr','draft-align','draft-render','alignment-setup'])
    a=parser.parse_args();a.job=a.job.resolve()
    if a.worker:worker(a.worker,a.job);return
    if not a.report:parser.error('--report is required')
    import psutil
    folder=a.report.resolve();folder.mkdir(parents=True,exist_ok=True)
    if (folder/'measurement.json').exists():raise FileExistsError('Choose a new report directory per attempt')
    report={'started_utc':datetime.now(timezone.utc).isoformat(),'job':str(a.job),
        'job_sha256':digest(a.job),'sample_interval_seconds':.5,'tasks':[],
        'logical_cpus':psutil.cpu_count(),'physical_cpus':psutil.cpu_count(logical=False),
        'system_total_bytes':psutil.virtual_memory().total,'psutil_version':psutil.__version__,
        'initial_available_bytes':psutil.virtual_memory().available,
        'human_content_approved':False,'full_listening_completed':False,
        'working_set_note':'Sum of sampled process-tree working sets; shared pages can be counted multiple times.',
        'private_note':'Sum of sampled private committed bytes; not identical to physical RAM usage.',
        'sampling_note':'Short-lived processes and peaks between 0.5-second samples may be missed.',
        'status':'running'}
    m=Measurement(folder,report);m.thread.start()
    script=str(Path(__file__).resolve());py=sys.executable
    try:
        if a.url:
            if not a.source_name:parser.error('--source-name required with --url')
            setup=[m.start('download',[py,str(ROOT/'tools/download_youtube.py'),a.url,'--name',a.source_name])]
            if read(a.job).get('language')=='da':
                setup.append(m.start('danish-alignment-setup',[py,script,'--worker','alignment-setup','--job',str(a.job)]))
            m.group(setup)
        from workflow import normalize
        job,work=normalize(read(a.job),a.job.parent)
        report.update({'work':str(work),'source_sha256':job['source_sha256']})
        import av
        with av.open(job['source']) as media:report['source_duration_seconds']=media.duration/av.time_base
        processing=time.monotonic()
        m.group([m.start('source-branding',[py,script,'--worker','background','--job',str(a.job)]),
            m.start('separate',[py,str(ROOT/'karaoke.py'),'separate','--job',str(a.job)])])
        # Reserve RAM for the OS. Post-separation ASR and QC have independent
        # artifacts and three CPU threads each on this benchmark configuration.
        if psutil.virtual_memory().available >= 4*1024**3:
            report['asr_qc_overlap']=True
            m.group([m.start('audio-qc',[py,str(ROOT/'karaoke.py'),'audio-qc','--job',str(a.job)]),
                m.start('vocal-asr',[py,script,'--worker','vocal-asr','--job',str(a.job)])])
        else:
            report['asr_qc_overlap']=False;report['overlap_fallback']='Less than 4 GiB available after separation'
            for name,command in [('audio-qc',[py,str(ROOT/'karaoke.py'),'audio-qc','--job',str(a.job)]),
                ('vocal-asr',[py,script,'--worker','vocal-asr','--job',str(a.job)])]:m.wait(m.start(name,command))
        merge_vocal_draft(a.job)
        if a.draft:
            m.wait(m.start('align-render-draft',[py,script,'--worker','draft-render','--job',str(a.job)]))
            m.wait(m.start('checked-draft-export',[py,str(ROOT/'tools/export_checked_sample.py'),
                '--job',str(a.job),'--name',job['artist']+' - '+job['title']+' - BENCHMARK.mp4','--unreviewed-benchmark']))
            report['status']='benchmark_draft_exported_not_human_approved'
        else:report['status']='needs_lyric_review'
        report['processing_wall_seconds']=time.monotonic()-processing
    except Exception as e:
        report['status']='failed';report['error']=str(e);raise
    finally:
        m.stop.set();m.thread.join()
        report['wall_seconds']=time.monotonic()-m.started
        report['completed_utc']=datetime.now(timezone.utc).isoformat()
        save(folder/'measurement.json',report)


if __name__=='__main__':main()
