"""Bounded candidate retries with resumable, hash-bound review evidence."""
from pathlib import Path
import subprocess
import sys
from project_runtime import ROOT, DEMUCSPY, child_env
from zoom_local_pipeline import read, save, digest
from audio_quality import settings, choose, review_clips


def run(source, baseline, folder, config=None, language='auto'):
    source, baseline, folder = Path(source), Path(baseline), Path(folder)
    config = settings(config)
    folder.mkdir(parents=True, exist_ok=True)
    records, errors = [], []
    save(folder/'settings.json',config)
    def inspect(name, path):
        candidate_folder=folder/name; candidate_folder.mkdir(parents=True,exist_ok=True)
        command=[sys.executable,str(ROOT/'tools/audio_quality.py'),'--source',str(source),
            '--candidate',str(path),'--output',str(candidate_folder),'--config',str(folder/'settings.json'),
            '--language',language]
        # Release detector/ASR runtimes before the next model stage on low-RAM hosts.
        with (candidate_folder/'scan.log').open('a',encoding='utf-8') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,env=child_env())
        report=read(candidate_folder/'quality.json')
        item = {'name': name, 'path': str(path.resolve()), 'sha256': digest(path), 'report': report}
        records.append(item)
        return item
    first = inspect('demucs', baseline)
    problem = bool(first['report']['flags'] or first['report']['signal']['reject_reasons'])
    if problem:
        for strategy in config['alternatives']:
            attempt = folder/strategy/'stems'; attempt.mkdir(parents=True, exist_ok=True)
            command = ([sys.executable, str(ROOT/'tools/uvr_instrumental.py'), '--threads', str(config['threads'])]
                if strategy == 'uvr' else [str(DEMUCSPY), str(ROOT/'tools/separate_local_stems.py'), '--ensemble'])
            if strategy=='htdemucs_ft':
                command=[str(DEMUCSPY),str(ROOT/'tools/separate_local_stems.py'),
                         '--model','htdemucs_ft','--threads',str(config['threads'])]
            command += ['--source', str(source), '--output', str(attempt)]
            try:
                with (folder/strategy/'worker.log').open('a', encoding='utf-8') as log:
                    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=child_env())
                if result.returncode: raise ValueError(f'{strategy} exited {result.returncode}; see worker.log')
                inspect(strategy, attempt/'instrumental.wav')
            except Exception as exc:
                errors.append({'strategy': strategy, 'error': str(exc)})
            # Each alternative is attempted at most once; never feed residuals back.
    selected = choose(records)
    if selected:
        clips = review_clips(source, selected['path'], selected['report'],
                             folder/'review', config['max_review_clips'])
        selected = {k:v for k,v in selected.items() if k != 'report'}
    else:
        clips = review_clips(source, baseline, first['report'], folder/'review', config['max_review_clips'])
    report = {'source_sha256': digest(source), 'baseline_sha256': digest(baseline),
              'code_sha256': digest(__file__), 'settings': config, 'candidates': records,
              'selected': selected, 'errors': errors, 'clips': clips,
              'status': 'needs_human_listening' if selected else 'no_usable_candidate'}
    save(folder/'selection.json', report)
    return report


def validate(source, folder):
    report = read(Path(folder)/'selection.json')
    if digest(source) != report['source_sha256'] or digest(__file__) != report['code_sha256']:
        raise ValueError('Audio quality evidence is stale; rerun audio-qc')
    selected = report.get('selected')
    if not selected or digest(selected['path']) != selected['sha256']:
        raise ValueError('No valid selected instrumental; rerun audio-qc')
    for c in report['candidates']:
        if c['name'] == selected['name']:
            from audio_quality import MODEL, REVISION
            binding=c['report']['binding']
            if binding.get('candidate')!=selected['sha256'] or binding.get('source')!=report['source_sha256']:
                raise ValueError('Selected quality report belongs to another audio file')
            if binding.get('detector')!=MODEL or binding.get('revision')!=REVISION:
                raise ValueError('Detector revision changed; rerun audio-qc')
            if c['report']['binding']['code'] != digest(ROOT/'tools/audio_quality.py'):
                raise ValueError('Audio screening code changed; rerun audio-qc')
            for clip in report.get('clips',[]):
                if digest(clip['path'])!=clip['sha256']: raise ValueError('Review clip changed; rerun audio-qc')
            return report, c['report']
    raise ValueError('Selected candidate missing from report')
