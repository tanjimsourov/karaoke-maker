"""Use a feathered clean source-frame patch instead of blurring lyric artwork.

This is a source-specific, visually checked recipe, not arbitrary video inpaint.
The rest of the original moving video remains unchanged behind the karaoke.
"""
import json
from pathlib import Path
import av
import numpy as np
from PIL import Image
from project_runtime import ROOT
from workflow import normalize
from zoom_local_pipeline import read,save,digest

p=ROOT/'config/kygo-ava-max-before-you-know-it-final.json'
job,folder=normalize(read(p),p.parent)
assert job['source_sha256']=='fed9959cfcd710e641149e1993a826b35a9c1dc9260712c60006da57587d3d12'
with av.open(job['source']) as c:
    c.seek(160000000)
    for frame in c.decode(video=0):
        if frame.time>=160:break
    clean=frame.to_image()
patch=clean.crop((300,500,1620,585)).convert('RGBA')
y,x=np.indices((85,1320))
alpha=np.clip(np.minimum.reduce([x/16,(1319-x)/16,y/12,(84-y)/12]),0,1)
patch.putalpha(Image.fromarray(np.uint8(alpha*255)))
asset=ROOT/'assets/source-patches/kygo-before-you-know-it.png';asset.parent.mkdir(parents=True,exist_ok=True)
patch.save(asset)
poster=asset.with_name('kygo-before-you-know-it-intro.png');clean.save(poster)
layers={'backing':{'volume_db':0,'mute':False},'texts':[],'audio':[],
        'media':[{'file':poster.relative_to(ROOT).as_posix(),'start':0,
                  'end':job['render']['intro_seconds'],'timeline':'output',
                  'x':960,'y':540,'width':1920,'height':1080,'opacity':1},
                 {'file':asset.relative_to(ROOT).as_posix(),'start':3,
                  'end':174,'x':960,'y':542.5,'width':1320,'height':85,'opacity':1}]}
target=folder/'layers.json'
if target.exists() and read(target)!=layers:
    prior=read(target)
    # Only migrate this recipe's own single-patch draft; refuse other edits.
    known_files={asset.relative_to(ROOT).as_posix(),poster.relative_to(ROOT).as_posix()}
    if len(prior.get('media',[])) not in (1,2) or any(m.get('file') not in known_files for m in prior['media']) or prior.get('texts') or prior.get('audio'):
        raise ValueError('Different existing layers; preserve user edits')
    backup=folder/'layers-before-clean-intro.json'
    if not backup.exists():save(backup,prior)
save(target,layers)
save(folder/'source-patch.json',{'source_sha256':job['source_sha256'],'clean_frame_seconds':160,
    'patch':str(asset),'sha256':digest(asset),'box':[300,500,1320,85],
    'basis':'Clean pixels from this supplied source, feathered only across the embedded lyric band',
    'patch_start_source_seconds':3,
    'limitation':'Small local lighting/grain differences can remain; original motion elsewhere is retained'})
print('Prepared original-video patch:',target)
