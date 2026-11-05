"""Measure existing job stages or real render presets, with hardware/version evidence."""
import argparse
import importlib.metadata as metadata
from pathlib import Path
import subprocess
import sys
import time
from project_runtime import FFMPEG,ROOT
from zoom_local_pipeline import save

def hardware():
    import torch
    import psutil
    import inspect
    import whisperx
    return {'cpu_logical':psutil.cpu_count(),'ram_bytes':psutil.virtual_memory().total,
        'cuda_available':torch.cuda.is_available(),
        'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        'versions':{k:metadata.version(k) for k in ['torch','whisperx','faster-whisper']},
        'fast_extra_in_pinned_release':'fast' in (metadata.metadata('whisperx').get_all('Provides-Extra') or []),
        'alignment_parameters':list(inspect.signature(whisperx.align).parameters)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path)
    p.add_argument('--job',type=Path)
    p.add_argument('--stage',choices=['separate','transcribe','align','quick-preview','preview'])
    p.add_argument('--seconds',type=float,default=10)
    p.add_argument('--start',type=float,default=0)
    p.add_argument('--report-dir',type=Path,required=True)
    p.add_argument('--nvenc',action='store_true',help='Optional separate CQ profile; not CRF equivalent')
    a=p.parse_args()
    import math
    if not 0<a.seconds<=60:p.error('Excerpt must be 0..60 seconds')
    if not math.isfinite(a.start) or a.start<0:p.error('Start must be finite and nonnegative')
    a.report_dir.mkdir(parents=True,exist_ok=True)
    report={'hardware':hardware(),'measurements':[],'source':str(a.source) if a.source else None,
            'start_seconds':a.start,'duration_seconds':a.seconds}
    def run(label,cmd):
        start=time.perf_counter()
        with (a.report_dir/(label+'.log')).open('w',encoding='utf-8') as f:
            result=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
        report['measurements'].append({'label':label,'wall_seconds':time.perf_counter()-start,'exit_code':result.returncode})
        save(a.report_dir/'benchmark.json',report)
        if result.returncode:raise RuntimeError('Benchmark failed: '+label)
    if a.job:
        if not a.stage:p.error('--stage required with --job')
        # Each result reports whether the actual workflow reused artifacts.
        for attempt in ('first','repeat'):
            run(a.stage+'-'+attempt,[sys.executable,str(ROOT/'karaoke.py'),a.stage,'--job',str(a.job.resolve())])
        report['note']='Repeat may reuse validated artifacts; not necessarily warm-model inference.'
    elif a.source:
        for preset in ('veryfast','fast'):
            target=a.report_dir/(preset+'.mp4')
            run(preset,[str(FFMPEG),'-v','error','-n','-ss',str(a.start),'-i',str(a.source),'-t',str(a.seconds),
                '-vf','scale=1920:1080,fps=30','-c:v','libx264','-preset',preset,'-crf','14',
                '-an',str(target)])
        if a.nvenc:
            if not report['hardware']['cuda_available']:raise ValueError('No CUDA GPU available for NVENC test')
            run('nvenc-cq',[str(FFMPEG),'-v','error','-n','-ss',str(a.start),'-i',str(a.source),'-t',str(a.seconds),
                '-vf','scale=1920:1080,fps=30','-c:v','h264_nvenc','-rc','vbr','-cq','19','-b:v','0',
                '-an',str(a.report_dir/'nvenc-cq.mp4')])
        report['note']='Encoder microbenchmark only. Use --job --stage preview for complete composition measurements.'
    save(a.report_dir/'benchmark.json',report)
    print(a.report_dir/'benchmark.json')

if __name__=='__main__':main()
