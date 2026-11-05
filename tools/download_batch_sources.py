"""Download a manifest with two bounded workers and persistent source receipts."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
import time
from project_runtime import ROOT
from zoom_local_pipeline import read,save,digest
from parallel_song_benchmark import Measurement


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();folder=a.report.resolve();folder.mkdir(parents=True,exist_ok=True)
    if (folder/'measurement.json').exists():raise FileExistsError('Use a new report directory')
    jobs=read(a.manifest)['jobs']
    if len({j['id'] for j in jobs})!=len(jobs):raise ValueError('Duplicate job IDs')
    report={'status':'running','tasks':[],'items':{},'started_utc':datetime.now(timezone.utc).isoformat(),
        'working_set_note':'Summed sampled process-tree working sets.',
        'private_note':'Private committed bytes can include page-file-backed memory.'}
    m=Measurement(folder,report);m.thread.start();pending=list(jobs);active=[]
    try:
        while pending or active:
            while pending and len(active)<2:
                job=pending.pop(0)
                if Path(job['source_name']).name!=job['source_name']:raise ValueError('Invalid source filename')
                task=m.start(job['id'],[sys.executable,str(ROOT/'tools/download_youtube.py'),
                    job['url'],'--name',job['source_name']])
                active.append((job,task))
            for job,task in list(active):
                if task[0].poll() is None:continue
                try:
                    m.wait(task);source=ROOT/'inputs'/job['source_name']
                    receipt=read(source.with_suffix('.source.json'))
                    if receipt['url']!=job['url'] or receipt['sha256']!=digest(source):raise ValueError('Source binding mismatch')
                    report['items'][job['id']]={'status':'downloaded','source':str(source),
                        'sha256':receipt['sha256'],'duration_seconds':receipt['duration_seconds']}
                except Exception as exc:report['items'][job['id']]={'status':'failed','error':str(exc)}
                active.remove((job,task));save(folder/'downloads.json',report['items'])
            time.sleep(.5)
        report['status']='complete' if all(v['status']=='downloaded' for v in report['items'].values()) else 'partial_failure'
    finally:
        m.stop.set();m.thread.join();report['wall_seconds']=time.monotonic()-m.started
        save(folder/'measurement.json',report)
    return 0 if report['status']=='complete' else 1


if __name__=='__main__':raise SystemExit(main())
