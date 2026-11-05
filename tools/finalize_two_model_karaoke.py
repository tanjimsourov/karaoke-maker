"""Build two actual Demucs model versions per song from verified source caches.

Uses existing renderer and corrected timing files. Does not invent listening or
lyric approval. Existing comparison exports are preserved.
"""
import argparse,subprocess,sys,shutil,re
from pathlib import Path
import av
from project_runtime import ROOT,FFMPEG
from zoom_local_pipeline import read,save,digest,align,render,audio,check_audio,loudness_gain
from workflow import normalize,context
from repair_lyric_draft import make_lines
from replace_backing import replace,video_hash
from timing_qa import timing_report

WORK=ROOT/'work/two-model-delivery'
OUT=ROOT/'out/comparison/final-karaoke'


def preflight():
    evidence=read(ROOT/'reports/reference-repair/source-preflight-final.json')
    for r in evidence['youtube']:
        if not r['strict_decode'] or digest(r['source'])!=r['sha256']:
            raise ValueError('Preflight is stale or source changed')
    return evidence


def american_lines(segments):
    rows=[]
    for segment in segments:
        group=[]
        for word in segment.get('words',[]):
            text=word['word'].strip()
            if not text:continue
            if group and (len(' '.join(x['word'].strip() for x in group+[word]))>46
                          or word['end']-group[0]['start']>6):
                rows.append({'start':group[0]['start'],'end':group[-1]['end'],
                             'text':' '.join(x['word'].strip() for x in group)})
                group=[]
            group.append(word)
            if len(group)>=3 and text.endswith(('?', '.', '!', ',')):
                rows.append({'start':group[0]['start'],'end':group[-1]['end'],
                             'text':' '.join(x['word'].strip() for x in group)})
                group=[]
        if group:rows.append({'start':group[0]['start'],'end':group[-1]['end'],
                             'text':' '.join(x['word'].strip() for x in group)})
    return rows


def prepare(only=None):
    preflight()
    for title in ('Babylon','American'):
        if only and title!=only:continue
        dest=WORK/title;dest.mkdir(parents=True,exist_ok=True)
        if title=='Babylon':
            original=ROOT/'work/babylon-reference-repair'
            cfg=read(original/'config.json');cfg['background']=str(original/'background-final.mp4')
            for name in ['transcript.json','aligned.json','sync.json','alignment-inputs.json']:
                shutil.copy2(original/name,dest/name)
        else:
            recipe=ROOT/'config/american-youtube-optimized.json'
            job,original=normalize(read(recipe),recipe.parent)
            cfg=context(job,original,strict_quality=False)
            # Original-mix ASR retains phrases missed by the prior stem ASR.
            # Wording remains explicitly unapproved; alternative ASR is retained.
            reference=read(ROOT/'reports/reference-repair/american-original-transcript.json')
            if digest(reference['source'])!=reference['source_sha256']:raise ValueError('ASR source changed')
            save(dest/'transcript.json',american_lines(reference['segments']))
            shutil.copy2(original/'sync.json',dest/'sync.json')
            save(dest/'lyric-provenance.json',{'reference':'american-original-transcript.json',
                'alternative':'american-uvr-transcript.json','accuracy_verified':False,
                'note':'Two automatic passes disagree; final media export is not lyric certification.'})
        cfg['slug']=title+'TwoModels20261102'
        cfg['render'].update(fps=30,crf=14,preset='veryfast')
        save(dest/'config.json',cfg)
        save(dest/'inputs.json',{k:digest(cfg[k]) for k in ('vocal_reference','zoom_video')})


def align_american():
    dest=WORK/'American';cfg=read(dest/'config.json')
    align(cfg,dest)
    save(dest/'timing-qa.json',timing_report(read(dest/'aligned.json'),audio(cfg['align_audio'])))


def picture(title):
    dest=WORK/title;cfg=read(dest/'config.json')
    if (dest/'preview-validation.json').exists():
        r=read(dest/'preview-validation.json')
        if digest(r['output'])!=r['sha256']:raise ValueError('Cached picture changed')
        return
    render(cfg,dest,preview=True)


def stem(folder,model,source):
    receipt=read(folder/'separation.json')
    if receipt['settings']['model']!=model or receipt['settings']['source_sha256']!=digest(source):
        raise ValueError('Wrong separation model or source')
    path=folder/'instrumental.wav'
    if receipt['files']['instrumental.wav']!=digest(path):raise ValueError('Backing changed')
    return path


def mux_new_backing(picture,backing,target):
    with av.open(str(backing)) as c:duration=c.duration/av.time_base
    gain=loudness_gain(backing,-14)
    filters=f'volume={gain:.2f}dB,afade=t=in:st=0:d=0.3,afade=t=out:st={duration-2:.6f}:d=2,adelay=10000:all=1'
    subprocess.run([str(FFMPEG),'-v','error','-n','-i',str(picture),'-i',str(backing),
        '-map','0:v:0','-map','1:a:0','-c:v','copy','-af',filters,'-c:a','aac','-b:a','320k',
        '-map_metadata','-1','-movflags','+faststart',str(target)],check=True)
    result=check_audio(audio(backing),audio(target),delay=160000,gain_invariant=True,
                       skip_start=4800,skip_end=32000)
    return {'audio_check':result,'gain_db':gain,'intro_seconds':10,'fades_seconds':[.3,2]}


def publish():
    preflight();OUT.mkdir(parents=True,exist_ok=True);results=[]
    for title,artist,slug in [('Babylon','Taylor Swift','Babylon-1039d7a138bd'),
                              ('American','Geordie Kieffer','American-ecc60d27df03')]:
        work=WORK/title;cfg=read(work/'config.json');pic=Path(read(work/'preview-validation.json')['output'])
        source=Path(cfg['vocal_reference']);base=ROOT/'work/local_open_source'/slug
        models={'Light':('htdemucs',base/'stems'),
                'Heavy':('htdemucs_ft',base/'audio-quality/htdemucs_ft/stems' if title=='Babylon'
                          else ROOT/'work/american-reference-repair/htdemucs-ft')}
        video_signature=video_hash(pic)
        for label,(model,folder) in models.items():
            backing=stem(folder,model,source)
            target=OUT/f'{artist} - {title} - {label}.mp4';receipt_path=target.with_suffix('.delivery.json')
            binding={'picture':digest(pic),'backing':digest(backing),'model':model,'source':digest(source)}
            if receipt_path.exists():
                r=read(receipt_path)
                if r['binding']!=binding or digest(target)!=r['sha256']:raise ValueError('Delivery cache changed')
                results.append(r);continue
            if target.exists():raise FileExistsError('Unverified partial export retained: '+str(target))
            # Prior AAC already contains the same intro, linear gain and fades.
            old=(ROOT/f'out/Taylor Swift - Babylon - {"htdemucs - " if label=="Light" else ""}BENCHMARK.mp4'
                 if title=='Babylon' else ROOT/'out/Geordie Kieffer - American - BENCHMARK.mp4')
            if title=='American' and label=='Heavy':audio_result=mux_new_backing(pic,backing,target)
            else:audio_result=replace(pic,old,target,copy_audio=True)
            subprocess.run([str(FFMPEG),'-v','error','-xerror','-threads','2','-i',str(target),'-f','null','-'],check=True)
            with av.open(str(target)) as c:
                v=c.streams.video[0];duration=c.duration/av.time_base
                if (v.width,v.height)!=(1920,1080) or float(v.average_rate)!=30:raise ValueError('Export format mismatch')
            if video_hash(target)!=video_signature:raise ValueError('Picture differs between models')
            model_audio_check=check_audio(audio(backing),audio(target),delay=160000,
                                         gain_invariant=True,skip_start=4800,skip_end=32000)
            r={'output':str(target),'sha256':digest(target),'binding':binding,'strict_decode':True,
               'resolution':[1920,1080],'fps':30,'duration':duration,'audio':audio_result,
               'named_model_backing_check':model_audio_check,
               'lyric_and_listening_approval':False}
            save(receipt_path,r);results.append(r)
            print('EXPORTED',target,flush=True)
    save(OUT/'delivery-manifest.json',{'status':'four_full_karaoke_media_exports_complete',
        'source_preflight':str(ROOT/'reports/reference-repair/source-preflight-final.json'),
        'outputs':results,'limitations':['Automatic lyrics need accuracy review, especially American.',
        'No human listening approval was inferred.','AI-repaired source text regions contain reconstructed scenery.']})


def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','prepare-american','align-american','render-babylon','render-american','publish']);a=p.parse_args()
    {'prepare':prepare,'prepare-american':lambda:prepare('American'),'align-american':align_american,'render-babylon':lambda:picture('Babylon'),
     'render-american':lambda:picture('American'),'publish':publish}[a.stage]()


if __name__=='__main__':main()
