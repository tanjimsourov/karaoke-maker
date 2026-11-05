"""Summarize observed process-tree measurements; never infer content approval."""
import argparse
import csv
from pathlib import Path
from zoom_local_pipeline import read,save,digest


def summarize(folder):
    report=read(folder/'measurement.json')
    if report['status']=='running':raise ValueError('Benchmark is still running')
    samples=list(csv.DictReader((folder/'resources.csv').open(encoding='utf-8')))
    # First interval includes pre-monitor imports in the earliest runner revision.
    valid=[s for s in samples if float(s['elapsed_seconds'])>=.5]
    tasks=[dict(t) for t in report['tasks']]; intervals=[]
    markers=read(folder/'completion-markers.json') if (folder/'completion-markers.json').exists() else {}
    for task in tasks:
        if task['name'] in markers:
            marker=markers[task['name']]
            task['end_seconds']=marker['artifact_ready_seconds']
            task['elapsed_seconds']=marker['elapsed_to_artifact_ready_seconds']
            task['timing_basis']=marker['basis']
    for t in tasks:
        if 'end_seconds' in t:intervals.append((t['start_seconds'],t['end_seconds']))
    changes=sorted([(a,1) for a,b in intervals]+[(b,-1) for a,b in intervals])
    active=0;previous=0.;parallel=0.
    for when,delta in changes:
        if active>=2:parallel+=when-previous
        active+=delta;previous=when
    result={'status':report['status'],'source_duration_seconds':report.get('source_duration_seconds'),
        'total_wall_seconds':report['wall_seconds'],'processing_wall_seconds':report.get('processing_wall_seconds'),
        'observed_parallel_seconds':parallel,
        'peak_project_working_set_gib':max((int(s['project_working_set_bytes']) for s in samples),default=0)/1024**3,
        'peak_project_private_commit_gib':max((int(s['project_private_bytes']) for s in samples),default=0)/1024**3,
        'peak_total_pc_used_gib':max((int(s['system_used_bytes']) for s in samples),default=0)/1024**3,
        'peak_project_cpu_percent_of_pc':max((float(s['project_cpu_percent_of_pc']) for s in valid),default=0),
        'cpu_bootstrap_note':'Excluded the initial CPU interval; RAM samples are all retained.',
        'memory_note':report['working_set_note']+' '+report['private_note'],
        'human_content_approved':False,'full_listening_completed':False,
        'stages':[{k:v for k,v in t.items() if k in ['name','elapsed_seconds','exit_code',
            'start_seconds','end_seconds','peak_working_set_bytes','peak_private_bytes','timing_basis']} for t in tasks]}
    root=Path(report['job']).parent.parent
    receipts=list((root/'reports/completed'/Path(report.get('work','')).name).glob('*/sample-export.json'))
    if receipts:
        receipt=read(max(receipts,key=lambda p:p.stat().st_mtime))
        output=Path(receipt['output'])
        result['export']=receipt
        result['saved_output_hash_matches']=output.is_file() and digest(output)==receipt['sha256']
    import importlib.metadata
    result['dependency_versions']={}
    for package in ['psutil','torch','whisperx','faster-whisper','transformers','yt-dlp','onnxruntime']:
        try:result['dependency_versions'][package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:pass
    save(folder/'summary.json',result)
    return result


def main():
    import json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path)
    a=p.parse_args();print(json.dumps(summarize(a.folder.resolve()),indent=2))


if __name__=='__main__':main()
