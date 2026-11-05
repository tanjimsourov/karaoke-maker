"""Measure real workflow stages, retaining logs and resume history.

Does not approve lyrics or listening. Review gates remain in the workflow.
"""
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
from project_runtime import ROOT, child_env
from model_queue import model_slot
from workflow import normalize
from zoom_local_pipeline import read, save, digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--job',type=Path,required=True)
    p.add_argument('--stages',nargs='+',default=['separate','audio-qc','transcribe'],
        choices=['separate','audio-qc','transcribe','align','preview'])
    p.add_argument('--allow-overlap',action='store_true',
        help='Measured-RAM diagnostic only: allow align/preview alongside another job; timings are marked contended')
    args=p.parse_args()
    if args.allow_overlap and any(s not in ['align','preview'] for s in args.stages):
        p.error('Overlap diagnostics are limited to align/preview')
    job=args.job.resolve();data,work=normalize(read(job),job.parent)
    import av
    with av.open(data['source']) as media:duration=media.duration/av.time_base
    folder=ROOT/'tmp/benchmarks'/job.stem;folder.mkdir(parents=True,exist_ok=True)
    report_path=folder/'timings.json'
    binding={'job_sha256':digest(job),'source_sha256':data['source_sha256']}
    report=read(report_path) if report_path.exists() else {
        'binding':binding,'source_duration_seconds':duration,'models_preloaded':True,
        'host':platform.platform(),'processor':platform.processor(),
        'work':str(work),'stages':[],'complete_conversion_verified':False}
    if report['binding']!=binding:raise ValueError('Benchmark input changed; preserve the old report and choose another job filename')
    queued=time.perf_counter()
    with (nullcontext() if args.allow_overlap else model_slot()):
        report['queue_wait_seconds']=time.perf_counter()-queued
        for stage in args.stages:
            marker={'separate':'stems/separation.json','audio-qc':'audio-quality/selection.json',
                'transcribe':'transcript.json','align':'aligned.json','preview':'preview-validation.json'}[stage]
            cached=(work/marker).exists()
            command=[sys.executable,str(ROOT/'karaoke.py'),stage,'--job',str(job)]
            name=f'{len(report["stages"])+1:02d}-{stage}.log'
            print('START',stage,flush=True);started=time.perf_counter()
            with (folder/name).open('w',encoding='utf-8') as log:
                result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,env=child_env())
            row={'stage':stage,'elapsed_seconds':time.perf_counter()-started,
                 'exit_code':result.returncode,'artifact_existed_before':cached,'log':str(folder/name),
                 'concurrent_model_job':args.allow_overlap}
            report['stages'].append(row)
            report['successful_stage_seconds']=sum(s['elapsed_seconds'] for s in report['stages'] if s['exit_code']==0)
            report['total_measured_stage_seconds']=sum(s['elapsed_seconds'] for s in report['stages'])
            report['measured_processing_to_track_ratio']=report['total_measured_stage_seconds']/duration
            save(report_path,report)
            print('END',stage,json.dumps(row),flush=True)
            if result.returncode:return result.returncode
    print('Measurements:',report_path,flush=True)
    print('Lyric/listening review and any remaining stages are not included yet.',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
