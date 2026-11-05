"""Convert verified local Xtendamix raw sources into two real model versions.

Reuses the existing preparation, transcription, alignment, render and export
checks. Heavy stages run serially to avoid the observed memory contention.
"""
from pathlib import Path
import subprocess,sys,os,time,shutil
import av
import psutil
from concurrent.futures import ThreadPoolExecutor
from project_runtime import ROOT,DEMUCSPY,FFMPEG,child_env
from zoom_local_pipeline import read,save,digest,audio,check_audio
from workflow import normalize
from replace_backing import video_hash
from finalize_two_model_karaoke import mux_new_backing

REPORT=ROOT/'reports/ftp-raw-two-models'
OUT=ROOT/'out/comparison/ftp-raw-light-heavy'


def run(stage,command,folder,publish_status=True):
    stamp=folder/(stage+'.done.json')
    binding={'command':command}
    if stamp.exists():
        if read(stamp)['binding']!=binding:raise ValueError('Stage settings changed: '+stage)
        return
    if publish_status:
        save(REPORT/'status.json',{'song':folder.name,'stage':stage,'status':'running','output_directory':str(OUT)})
    env=child_env();env.update(OMP_NUM_THREADS='3',MKL_NUM_THREADS='3',OPENBLAS_NUM_THREADS='3',
                              KARAOKE_FFMPEG_THREADS='3',KARAOKE_ALIGNMENT_THREADS='3',PYTHONUNBUFFERED='1')
    started=time.perf_counter()
    with (folder/(stage+'.log')).open('a',encoding='utf-8') as log:
        subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    save(stamp,{'binding':binding,'elapsed_seconds':time.perf_counter()-started})


def independent(stages,folder,minimum_free_gib):
    """Overlap independent branches only when RAM permits both model footprints."""
    available=psutil.virtual_memory().available
    parallel=available >= minimum_free_gib*1024**3 and (os.cpu_count() or 1)>=6
    save(folder/('schedule-'+stages[0][0]+'.json'),{'available_bytes':available,
        'minimum_free_gib':minimum_free_gib,'workers':2 if parallel else 1,
        'stages':[stage for stage,_ in stages]})
    if not parallel:
        for stage,command in stages:run(stage,command,folder)
        return
    save(REPORT/'status.json',{'song':folder.name,'stage':[stage for stage,_ in stages],
        'status':'running','output_directory':str(OUT)})
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending=[pool.submit(run,stage,command,folder,False) for stage,command in stages]
        # The context waits for siblings even if one branch fails; checkpoints survive.
        for task in pending:task.result()


def verify(path,backing,source_sha,model):
    subprocess.run([str(FFMPEG),'-v','error','-xerror','-threads','2','-i',str(path),'-f','null','-'],check=True)
    with av.open(str(path)) as c:
        v=c.streams.video[0]
        if (v.width,v.height)!=(1920,1080) or float(v.average_rate)!=30:raise ValueError('Export format mismatch')
        duration=c.duration/av.time_base
    check=check_audio(audio(backing),audio(path),delay=160000,gain_invariant=True,skip_start=4800,skip_end=32000)
    return {'file':str(path),'sha256':digest(path),'model':model,'source_sha256':source_sha,
            'strict_decode':True,'duration':duration,'resolution':[1920,1080],'fps':30,
            'backing_match':check,'full_listening_approved':False,'lyrics_human_verified':False}


def main():
    REPORT.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    inventory=read(ROOT/'reports/ftp-raw-preflight/inventory.json')['raw_files']
    chosen=[('Charlie Jeer','Jennifer','Charlie Jeer - Jennifer (1080).mp4'),
            ('REI AMI','2Loud','REI AMI - 2Loud (1080).mp4')]
    results=[]
    # Release both light deliveries before starting either heavyweight pass.
    for phase,artist,title,filename in [(phase,*song) for phase in ('Light','Heavy') for song in chosen]:
        source=ROOT/filename
        row=next(r for r in inventory if Path(r['path'])==source)
        if not row['strict_decode'] or digest(source)!=row['sha256']:raise ValueError('Incomplete/changed FTP raw source')
        if not any('xtendamix' in str(v).lower() for v in row['metadata'].values()):raise ValueError('Unidentified source')
        folder=REPORT/title;folder.mkdir(exist_ok=True);recipe=folder/'job.json'
        config={'source':str(source),'title':title,'artist':artist,'language':'en','mode':'music',
            'profile':'optimized','background':'original','alignment_model':'WAV2VEC2_ASR_LARGE_LV60K_960H',
            'separation':{'model':'htdemucs','overlap':.25},
            'audio_quality':{'threads':3,'alternatives':[]},
            'render':{'fps':30,'crf':14,'preset':'veryfast','intro_seconds':10,'intro_countdown':True,
                      'highlight_colour':'#FF8C00'}}
        if recipe.exists() and read(recipe)!=config:raise ValueError('Existing FTP job changed')
        save(recipe,config);job,work=normalize(config,recipe.parent)
        worker=str(ROOT/'tools/parallel_song_benchmark.py');py=sys.executable
        independent([
            ('source-branding',[py,worker,'--worker','background','--job',str(recipe)]),
            ('light-separation',[py,str(ROOT/'karaoke.py'),'separate','--job',str(recipe)])],folder,6)
        independent([
            ('light-audio-check',[py,str(ROOT/'karaoke.py'),'audio-qc','--job',str(recipe)]),
            ('vocal-transcription',[py,worker,'--worker','vocal-asr','--job',str(recipe)])],folder,8)
        from parallel_song_benchmark import merge_vocal_draft
        merge_vocal_draft(recipe)
        run('alignment-and-render',[py,worker,'--worker','draft-render','--job',str(recipe)],folder)
        benchname=artist+' - '+title+' - FTP RAW - BENCHMARK.mp4'
        run('checked-export',[py,str(ROOT/'tools/export_checked_sample.py'),'--job',str(recipe),
                            '--name',benchname,'--unreviewed-benchmark'],folder)
        picture=ROOT/'out'/benchname
        heavy=work/'explicit-heavy'
        if phase=='Heavy':
            run('heavy-separation',[str(DEMUCSPY),str(ROOT/'tools/separate_local_stems.py'),'--source',str(source),
                 '--output',str(heavy),'--model','htdemucs_ft','--overlap','0.25','--threads','3'],folder)
        source_video_hash=video_hash(picture)
        for label,model,stems in [('Light','htdemucs',work/'stems'),('Heavy','htdemucs_ft',heavy)]:
            if label!=phase:continue
            backing=stems/'instrumental.wav';r=read(stems/'separation.json')
            if r['settings']['model']!=model or r['settings']['source_sha256']!=row['sha256'] or r['files']['instrumental.wav']!=digest(backing):raise ValueError('Model/source provenance mismatch')
            target=OUT/f'{artist} - {title} - {label}.mp4';receipt=target.with_suffix('.delivery.json')
            if receipt.exists():
                verified=read(receipt)
                if digest(target)!=verified['sha256']:raise ValueError('Delivered file changed')
            else:
                if target.exists():raise FileExistsError('Unverified output retained: '+str(target))
                if label=='Light':shutil.copy2(picture,target)
                else:mux_new_backing(picture,backing,target)
                verified=verify(target,backing,row['sha256'],model)
                if video_hash(target)!=source_video_hash:raise ValueError('Comparison picture differs')
                save(receipt,verified)
            results.append(verified)
            save(OUT/'delivery-manifest.json',{'status':'processing','outputs':results,
                'source_inventory':str(ROOT/'reports/ftp-raw-preflight/inventory.json')})
            print('EXPORTED',target,flush=True)
    save(OUT/'delivery-manifest.json',{'status':'four_full_karaoke_media_exports_complete','outputs':results,
        'source_inventory':str(ROOT/'reports/ftp-raw-preflight/inventory.json'),
        'limitations':['Automatic transcription and screening do not constitute human lyric/listening approval.']})
    save(REPORT/'status.json',{'status':'exports_complete','outputs':[r['file'] for r in results]})


if __name__=='__main__':
    try:main()
    except Exception as exc:
        save(REPORT/'error.json',{'error':repr(exc)})
        previous=read(REPORT/'status.json') if (REPORT/'status.json').exists() else {}
        save(REPORT/'status.json',{**previous,'status':'failed','error':repr(exc)})
        raise
