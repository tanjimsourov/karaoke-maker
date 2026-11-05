"""Rebuild this verified Babylon job's picture once; retain each model's AAC audio."""
from pathlib import Path
import shutil
import time
from project_runtime import ROOT
from workflow import normalize,context
from zoom_local_pipeline import read,save,render,digest
from replace_backing import replace,video_hash

def main():
    started=time.perf_counter()
    recipe=ROOT/'config/babylon-youtube-optimized.json'
    job,original=normalize(read(recipe),recipe.parent)
    root=ROOT/'work/babylon-text-cleanup';folder=root/'render';folder.mkdir(parents=True,exist_ok=True)
    cfg=context(job,original)
    cfg['background']=str(root/'background-v2.mp4')
    cfg['slug']+='-text-clean'
    for name in ['aligned.json','transcript.json','sync.json','alignment-inputs.json','inputs.json']:
        target=folder/name
        if target.exists() and digest(target)!=digest(original/name):raise ValueError('Existing repair inputs changed')
        if not target.exists():shutil.copy2(original/name,target)
    save(folder/'config.json',cfg)
    render(cfg,folder,preview=True)
    picture=Path(read(folder/'preview-validation.json')['output'])
    out=ROOT/'out'
    originals={'heavy':out/'Taylor Swift - Babylon - BENCHMARK.mp4',
               'light':out/'Taylor Swift - Babylon - htdemucs - BENCHMARK.mp4'}
    results={}
    for model,source in originals.items():
        destination=root/('final-'+model+'.mp4')
        results[model]=replace(picture,source,destination,copy_audio=True)
    if video_hash(root/'final-heavy.mp4')!=video_hash(root/'final-light.mp4'):
        raise ValueError('Comparison versions must have identical picture')
    save(root/'ready.json',{'variants':results,'elapsed_seconds':time.perf_counter()-started,
         'lyrics_changed':False,'approval':'draft; prior lyric/timing/audio warnings remain',
         'background_change':'timed regional interpolation of source text; patch softness remains'})

if __name__=='__main__':main()
