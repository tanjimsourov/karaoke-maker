"""Short, lower-resolution review clips; never replace the full delivery preview."""
import copy
import math
import shutil
from zoom_local_pipeline import read,save,digest,fingerprint,render
from workflow import identity


def preview_config(cfg,start,seconds,duration):
    if not all(math.isfinite(x) for x in (start,seconds)) or start<0 or not 1<=seconds<=60:
        raise ValueError('Preview start must be nonnegative; duration must be 1..60 seconds')
    end=min(start+seconds,duration+cfg['render']['intro_seconds'])
    if end<=start:raise ValueError('Preview starts beyond the song')
    result=copy.deepcopy(cfg)
    w,h=map(int,cfg['render']['canvas'].split('x'))
    scale=min(1,720/min(w,h))
    result['render']={**cfg['render'],'canvas':f'{int(w*scale)//2*2}x{int(h*scale)//2*2}',
                      'start':start,'end':end,'crf':23,'preset':'veryfast',
                      'guide_vocal_level':.65}
    result['slug']=cfg['slug']+'_quick'
    return result


def create(cfg,folder,start=0,seconds=20):
    import av
    with av.open(cfg['zoom_video']) as media:duration=media.duration/av.time_base
    trial=preview_config(cfg,start,seconds,duration)
    key=identity({'inputs':fingerprint(cfg,folder),'preview':trial['render']})[:16]
    work=folder/'quick-previews'/key
    receipt=work/'preview-validation.json'
    if receipt.is_file():
        old=read(receipt)
        if old['fingerprint']==fingerprint(trial,work) and digest(old['output'])==old['sha256']:
            return old['output']
        raise ValueError('Quick-preview cache changed; refusing stale reuse')
    work.mkdir(parents=True,exist_ok=True)
    for name in ('aligned.json','transcript.json','sync.json','alignment-inputs.json'):
        shutil.copy2(folder/name,work/name)
    render(trial,work,preview=True)
    save(work/'purpose.json',{'purpose':'short_lyric_timing_review','delivery_approved':False,
                             'guide_vocals_added_for_review':True,'source_job':str(folder)})
    return read(receipt)['output']
