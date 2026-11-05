"""Delete one completed song's generated data only after export verification."""
from pathlib import Path
import shutil

def remove_generated(target, allowed_root, protected=()):
    target=Path(target).absolute();allowed_root=Path(allowed_root).resolve()
    resolved=target.resolve()
    if resolved==allowed_root or not resolved.is_relative_to(allowed_root):
        raise ValueError('Cleanup target escapes its generated-data root: '+str(target))
    current=target
    while current.resolve()!=allowed_root:
        if current.is_symlink():raise ValueError('Cleanup refuses linked paths: '+str(current))
        if current==current.parent:raise ValueError('Cleanup ancestor check failed')
        current=current.parent
    for path in protected:
        p=Path(path).resolve()
        if p==resolved or p.is_relative_to(resolved):raise ValueError('Cleanup would delete protected media')
    if target.exists():shutil.rmtree(target)

def local_export(folder, output):
    from project_runtime import ROOT,WORK
    from zoom_local_pipeline import read,digest
    folder=Path(folder);output=Path(output)
    validation=read(folder/'preview-validation.json')
    if not output.is_file() or digest(output)!=validation['sha256']:
        raise ValueError('Export must match its verified preview before cleanup')
    cfg=validation['fingerprint']['config']
    protected=[output,Path(cfg['vocal_reference'])]
    scratch=ROOT/'work/bowlnfun'/folder.name
    remove_generated(scratch,ROOT/'work',protected)
    remove_generated(folder,WORK,protected)
    print('[CLEANUP] Completed song work removed; exported MP4 and models preserved.',flush=True)
