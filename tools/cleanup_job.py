"""Remove one delivered job's temporary data, preserving source, app and models.

Default is a dry run. --apply validates the final MP4 again before deleting.
After cleanup, editing/re-rendering requires processing the source again.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
from project_runtime import ROOT, WORK, OUT, FFMPEG
from zoom_local_pipeline import read, digest

PROTECTED = {'.py','.pyc','.ps1','.bat','.cmd','.exe','.dll','.onnx',
             '.safetensors','.pt','.pth','.ckpt','.env'}


def no_links(path):
    info = path.lstat()
    if path.is_symlink() or getattr(info,'st_file_attributes',0) & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024):
        raise ValueError('Cleanup refuses links/junctions: '+str(path))


def plan_cleanup(folder, root=None, sample=False):
    root = Path(root or ROOT).resolve()
    work = WORK.resolve() if root == ROOT.resolve() else root/'work/local_open_source'
    out = OUT.resolve() if root == ROOT.resolve() else root/'out'
    if not work.is_relative_to(root/'work') or not out.is_relative_to(root/'out'):
        raise ValueError('Cleanup requires work and output inside this project')
    supplied = Path(folder).absolute()
    if supplied.parent != work:
        raise ValueError('Only a direct song folder inside work/local_open_source can be cleaned')
    no_links(supplied)
    folder = supplied.resolve()
    if folder.parent != work or not re.fullmatch(r'[A-Za-z0-9_-]+',folder.name):
        raise ValueError('Only a direct song folder inside work/local_open_source can be cleaned')
    for ancestor in [root/'work', work, folder]:
        no_links(ancestor)
    if any((folder/name).exists() for name in ['running.lock','.cleanup.lock']):
        raise ValueError('Job is running or cleanup is already active')
    validation = read(folder/('preview-validation.json' if sample else 'validation.json'))
    receipt = read(folder/'sample-export.json') if sample else validation
    if sample:
        if receipt.get('status') != 'review_sample_technical_checks_passed' or receipt.get('strict_decode') != 'passed':
            raise ValueError('A technically verified exported sample is required')
        if receipt.get('sha256') != validation.get('sha256'):
            raise ValueError('Sample does not match its verified preview')
    elif validation.get('preview') is not False or read(folder/'state.json').get('status') != 'delivered':
        raise ValueError('A delivered final output is required')
    fingerprint = validation['fingerprint']
    if not sample:
        review = read(folder/'full-review.json')
        if review.get('fingerprint') != fingerprint or not all(review.get(k) is True for k in [
            'listened','checked_lyrics','reviewed_audio_flags','reviewed_timing']):
            raise ValueError('The delivered output must have complete matching review evidence')
    cfg = fingerprint['config']
    if cfg.get('slug') != folder.name:
        raise ValueError('Job identity does not match the work folder')
    output = Path(receipt['output']).resolve()
    if not output.is_relative_to(out) or output.suffix.lower() != '.mp4':
        raise ValueError('The final MP4 must be inside this project output directory')
    if not output.is_file() or digest(output) != validation['sha256']:
        raise ValueError('Final output is missing or changed')
    targets = [folder]
    scratch = root/'work/bowlnfun'/folder.name
    if scratch.exists():
        no_links(root/'work/bowlnfun');no_links(scratch)
        targets.append(scratch)
    protected = [output] + [Path(cfg[k]).resolve() for k in ['vocal_reference','background'] if cfg.get(k)]
    # A verified, generated branding-cleaned background is work data. Protect
    # the original input from its recipe instead of retaining the derived MP4.
    derived = folder/'branding-background/cleaned.json'
    recipe = folder/'branding-background/cleanup-plan.json'
    if derived.is_file() and recipe.is_file():
        marker, original = read(derived), Path(read(recipe)['source']).resolve()
        background = Path(cfg['background']).resolve()
        if (background.is_relative_to(folder/'branding-background') and
                Path(marker['output']).resolve() == background and
                marker.get('sha256') == digest(background) and
                marker.get('source_sha256') == digest(original)):
            protected.remove(background)
            protected.append(original)
    size = 0
    for target in targets:
        if any(p == target or p.is_relative_to(target) for p in protected):
            raise ValueError('Source or final output lies inside the proposed cleanup target')
        for entry in [target,*target.rglob('*')]:
            no_links(entry)
            if entry.is_file():
                if (entry.suffix.lower() in PROTECTED or entry.name in {'pyvenv.cfg','.env'}
                        or entry.name.startswith('.env.')):
                    raise ValueError('Code, environment or model file found in work; nothing deleted: '+str(entry))
                size += entry.stat().st_size
    # Decode both streams; matching a hash alone does not establish a valid MP4.
    result = subprocess.run([str(FFMPEG),'-v','error','-xerror','-nostdin','-i',str(output),
        '-map','0:v:0','-map','0:a:0','-f','null','-'],capture_output=True)
    if result.returncode:
        raise ValueError('Final MP4 decode failed: '+result.stderr.decode(errors='replace')[-1000:])
    if digest(output) != validation['sha256']:
        raise ValueError('Final output changed during validation')
    return {'work':str(folder),'output':str(output),'sha256':validation['sha256'],'sample':sample,
            'targets':[str(p) for p in targets],'bytes_to_remove':size}


def cleanup(plan, root=None):
    # Never trust a previously printed/edited plan; recompute all safety checks.
    fresh = plan_cleanup(Path(plan['work']),root=root,sample=plan.get('sample',False))
    if fresh != plan:
        raise ValueError('Cleanup plan changed; inspect a fresh dry run')
    folder = Path(fresh['work'])
    # Retain small audit evidence outside generated data; never invent approval.
    archive = Path(root or ROOT)/'reports/completed'/folder.name/fresh['sha256'][:16]
    archive.mkdir(parents=True,exist_ok=True)
    for name in ['validation.json','preview-validation.json','sample-export.json',
                 'full-review.json','timing-report.json','state.json','layers.json','stage-metrics.jsonl',
                 'delivery-verification.json','delivery-review.json','verification-reference-binding.json']:
        source = folder/name
        if source.is_file(): shutil.copy2(source,archive/name)
    (archive/'cleanup.json').write_text(json.dumps(fresh,indent=2),encoding='utf-8')
    # Share the workflow's exclusive lock so processing cannot start mid-cleanup.
    with (folder/'running.lock').open('x') as lock:
        lock.write('cleanup')
    try:
        # Keep delivery evidence until renderer scratch has been removed.
        for target in reversed(fresh['targets']):
            shutil.rmtree(target)
    finally:
        (folder/'running.lock').unlink(missing_ok=True)
    if digest(fresh['output']) != fresh['sha256']:
        raise ValueError('Final output changed unexpectedly')
    return fresh


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    args = parser.parse_args()
    plan = plan_cleanup(args.work)
    if args.apply: cleanup(plan)
    print(json.dumps({**plan,'deleted':args.apply},indent=2))


if __name__ == '__main__': main()
