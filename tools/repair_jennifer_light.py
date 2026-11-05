"""Source-reference repair using the existing htdemucs backing, with honest review state."""
import argparse,shutil,subprocess,sys
from pathlib import Path
from project_runtime import ROOT,FFMPEG
from zoom_local_pipeline import read,save,digest,audio

WORK=ROOT/'work/jennifer-light-repair'
REPORT=ROOT/'reports/jennifer-repair'
OLD=ROOT/'work/local_open_source/Jennifer-6a1030d28ad2'

def inside_replacement(row,start,end):
    # The next phrase starts exactly at the replacement end: keep it.
    return start<=row['start']<end-.001

def prepare():
    from workflow import normalize,context
    recipe=ROOT/'reports/ftp-raw-two-models/Jennifer/job.json'
    job,folder=normalize(read(recipe),recipe.parent);cfg=context(job,folder)
    cfg['slug']='Jennifer-light-repaired';cfg['background']=job['source']
    cfg['align_audio']=job['source']
    cfg.pop('branding_plan',None)
    WORK.mkdir(parents=True,exist_ok=True)
    patch=REPORT/'credit-patch.mp4';receipt=read(patch.with_suffix('.json'))
    if digest(patch)!=receipt['sha256']:raise ValueError('Patch changed')
    x,y,w,h=receipt['box']
    layers={'media':[{'file':str(patch),'start':receipt['start'],'end':receipt['end'],
        'x':x+w/2,'y':y+h/2,'width':w,'height':h}]}
    save(WORK/'layers.json',layers)
    cfg['layers']={'file':str(WORK/'layers.json'),'sha256':digest(WORK/'layers.json'),
                   'media':{str(patch):digest(patch)},'changes_audio':False}
    save(WORK/'config.json',cfg)
    for name in ('inputs.json','sync.json'):shutil.copy2(OLD/name,WORK/name)
    data=read(REPORT/'source-transcript.json')
    rows=[{'start':s['start'],'end':s['end'],'text':s['text'].strip()} for s in data['segments']]
    changes=[]
    replacements={"Oh, Jimmy, what did you do?":"Oh, Jenny, what did you do?",
        "Money don't fit the same":"Money don't feel the same",
        "Make a city go, go insane":"Make a city girl go insane",
        'You stole your inhibition':'Used all your inhibition',
        'Can I feel magical?':"Jennifer, where'd you go?"}
    # Corrections are candidates supported by repeated phrases/source-reference
    # comparisons and published wording, not a claim of human listening approval.
    for row in rows:
        before=row['text'];row['text']=replacements.get(before,before)
        if before!=row['text']:changes.append({'start':row['start'],'before':before,'after':row['text']})
    # Recognition repeatedly joins the short question to the following phrase.
    for lo,hi,question_end,next_start,next_end in [(51.4,56.43,52.56,52.56,56.42),
           (94.1,99.15,95.60,95.60,99.14),(130.7,135.73,131.84,131.84,135.72)]:
        removed=[r for r in rows if inside_replacement(r,lo,next_end)]
        rows=[r for r in rows if not inside_replacement(r,lo,next_end)]
        rows.extend([{'start':lo,'end':question_end,'text':'But what for?'},
          {'start':next_start,'end':next_end,'text':"Now every night, I'm wondering why, why I didn't do nothing"}])
        changes.append({'start':lo,'replaced_segments':removed,'basis':'Repeated chorus + source reference; needs listening confirmation'})
    rows.sort(key=lambda r:r['start'])
    save(WORK/'transcript.json',rows)
    save(WORK/'review-status.json',{'status':'unapproved_repair_candidate','lyrics_reviewed':False,'full_listening_completed':False})
    save(REPORT/'corrections.json',{'changes':changes,'source_transcript':str(REPORT/'source-transcript.json'),
        'reference':'https://paroles2chansons.lemonde.fr/paroles-charlie-jeer/paroles-jennifer.html',
        'unresolved':['Published wording and ASR disagree on inhibition phrase; needs listening.',
                      'Opening repeats and outro need source listening confirmation.'],
        'separation_model':'htdemucs','backing_sha256':digest(cfg['zoom_video'])})

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','align','restore','refine','render','verify'])
    p.add_argument('--output',type=Path,help='New delivery path; existing files are preserved')
    a=p.parse_args()
    if a.stage=='prepare':prepare();return
    cfg=read(WORK/'config.json')
    if a.stage=='restore':
        import torch,whisperx
        from low_memory_models import mapped_checkpoint_load
        from timing_qa import timing_report
        torch.set_num_threads(5)
        transcript=read(WORK/'transcript.json');rows=read(WORK/'aligned.json')
        candidates=[s for s in read(REPORT/'source-transcript.json')['segments']
                    if any(abs(s['start']-t)<.01 for t in (56.42,99.14,135.72))]
        missing=[s for s in candidates if not any(abs(r['start']-s['start'])<.01 for r in transcript)]
        if missing:
            checkpoint=Path(torch.hub.get_dir())/'checkpoints/wav2vec2_fairseq_large_lv60k_asr_ls960.pth'
            with mapped_checkpoint_load(torch,checkpoint):
                model,metadata=whisperx.load_align_model(language_code='en',device='cpu',model_name=cfg['alignment_model'])
            source=audio(cfg['align_audio'])
            for s in missing:
                segment={k:s[k] for k in ('start','end','text')}
                aligned=whisperx.align([segment],model,metadata,source,'cpu',return_char_alignments=False)['segments']
                if not aligned or not all(r.get('words') for r in aligned):
                    raise ValueError('Restored phrase failed alignment')
                transcript.append(segment);rows.extend(aligned)
            transcript.sort(key=lambda s:s['start']);rows.sort(key=lambda s:s['start'])
            save(WORK/'transcript.json',transcript);save(WORK/'aligned.json',rows)
            save(REPORT/'restored-phrases.json',missing)
            save(WORK/'timing-report.json',timing_report(rows,audio(OLD/'stems/vocals.wav')))
        save(WORK/'alignment-inputs.json',{'transcript':digest(WORK/'transcript.json'),
                                         'vocal_reference':digest(cfg['vocal_reference'])})
    elif a.stage=='align':
        import torch
        torch.set_num_threads(5)
        from zoom_local_pipeline import align
        from timing_qa import timing_report
        align(cfg,WORK)
        save(WORK/'timing-report.json',timing_report(read(WORK/'aligned.json'),audio(OLD/'stems/vocals.wav')))
    elif a.stage=='refine':
        import torch,whisperx
        from low_memory_models import mapped_checkpoint_load
        from timing_qa import timing_report
        torch.set_num_threads(5)
        rows=read(WORK/'aligned.json');vocal=audio(OLD/'stems/vocals.wav')
        report=timing_report(rows,vocal)
        targets=sorted({i['line']-1 for i in report['issues']})
        checkpoint=Path(torch.hub.get_dir())/'checkpoints/wav2vec2_fairseq_large_lv60k_asr_ls960.pth'
        with mapped_checkpoint_load(torch,checkpoint):
            model,metadata=whisperx.load_align_model(language_code='en',device='cpu',model_name=cfg['alignment_model'])
        edits=[];attempts=[]
        for index in targets:
            original=rows[index]
            candidates=[s for s in read(WORK/'transcript.json') if s['text']==original['text']]
            segment=dict(min(candidates,key=lambda s:abs(s['start']-original['start'])))
            if segment['text']=='Forgive my hesitation':segment['start']=68.8
            proposed=whisperx.align([segment],model,metadata,vocal,'cpu',return_char_alignments=False)['segments']
            old_flags=timing_report([original],vocal)['issues'];new_flags=timing_report(proposed,vocal)['issues']
            severity=lambda flags:(sum('silent' in f['problem'] for f in flags),len(flags))
            words=lambda parts:[w['word'].casefold() for row in parts for w in row.get('words',[])]
            valid=(len(proposed)==1 and words(proposed)==words([original]) and
                   proposed[0]['start']>=segment['start']-.02 and proposed[0]['end']<=segment['end']+.02)
            accepted=valid and severity(new_flags)<severity(old_flags)
            attempts.append({'index':index,'old_flags':old_flags,'new_flags':new_flags,'accepted':accepted,
                             'proposed':proposed})
            if accepted:
                rows[index]=proposed[0];edits.append({'index':index,'before':original,'after':proposed[0]})
        previous=read(REPORT/'timing-refinements.json') if (REPORT/'timing-refinements.json').exists() else []
        save(REPORT/'timing-refinements.json',previous+edits)
        save(REPORT/'timing-retry-evidence.json',attempts)
        save(WORK/'aligned.json',rows);save(WORK/'timing-report.json',timing_report(rows,vocal))
    elif a.stage=='render':
        from zoom_local_pipeline import render
        render(cfg,WORK,preview=True)
    else:
        from branding_guard import scan
        result=read(WORK/'preview-validation.json');path=Path(result['output'])
        if digest(path)!=result['sha256']:raise ValueError('Render changed')
        for name in ('aligned.json','transcript.json','sync.json'):
            item=WORK/name
            if result.get('fingerprint',{}).get('files',{}).get(str(item))!=digest(item):
                raise ValueError(f'Render is stale: {name} changed; render before verifying')
        subprocess.run([str(FFMPEG),'-v','error','-xerror','-threads','2','-i',str(path),'-f','null','-'],check=True)
        scan(path,REPORT/'output-branding.json')
        dest=a.output or ROOT/'out/comparison/ftp-raw-light-heavy/repaired/Charlie Jeer - Jennifer - Light - Repaired.mp4'
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():raise FileExistsError(dest)
        shutil.copy2(path,dest)
        receipt={'output':str(dest),'sha256':digest(dest),'model':'htdemucs',
            'strict_decode':True,'timing':read(WORK/'timing-report.json'),
            'full_listening_approved':False,'lyrics_human_verified':False}
        save(dest.with_suffix('.verification.json'),receipt)
        save(REPORT/'delivery.json',receipt)
        print(dest,flush=True)

if __name__=='__main__':main()
