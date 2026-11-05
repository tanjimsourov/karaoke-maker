"""Build an explicitly unapproved local preview from separated original audio.

Never reads Karadeo outputs or creates a listening/lyric approval record.
"""
import argparse
import os
from pathlib import Path
import torch
from zoom_local_pipeline import ROOT,FFMPEG,read,save,digest,audio,align,render
from local_audio_audit import compare
from asr_draft_quality import validate_asr_draft

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--song',required=True);p.add_argument('--draft',type=Path,required=True)
    a=p.parse_args();job=next(j for j in read(ROOT/'local_karaoke_jobs.json') if j['slug']==a.song)
    base=ROOT/'work/local_open_source'/a.song;work=base/'vocal_aligned_preview'
    source=ROOT/job['source'];stems=base/'stems';separation=read(stems/'separation.json')
    assert not separation['is_excerpt'] and separation['settings']['source_sha256']==digest(source)
    assert all(digest(stems/name)==sha for name,sha in separation['files'].items())
    draft=read(a.draft)
    assert draft['source_sha256']==digest(stems/'vocals.wav')
    validate_asr_draft(draft)
    if any("I've prepared" in s['text'] for s in draft['segments']):
        raise ValueError('Conflicting chorus transcription: compare independent local drafts before alignment')
    cfg={'slug':'Local_'+a.song,'title':job['title'],'artist':job['artist'],
         'vocal_reference':str(stems/'vocals.wav'),'zoom_video':str(stems/'instrumental.wav'),
         'background':str(ROOT/job['background']),'language':job['language'],
         'language_label':job.get('language_label','KARAOKE')}
    work.mkdir(parents=True,exist_ok=True)
    if (work/'transcript.json').exists():raise FileExistsError('Preserve existing draft corrections')
    save(work/'config.json',cfg)
    save(work/'inputs.json',{key:digest(cfg[key]) for key in ('vocal_reference','zoom_video')})
    save(work/'transcript.json',[{'start':s['start'],'end':s['end'],'text':s['text']} for s in draft['segments']])
    duration=len(audio(source))/16000
    save(work/'sync.json',{'anchors':[[0,0],[duration,duration]],'basis':'sample-preserving separation of same original'})
    save(work/'audio-audit.json',compare(source,stems/'instrumental.wav',stems/'vocals.wav'))
    save(work/'review-status.json',{'status':'unapproved_preview','lyrics':'automatic local ASR draft, not listening-verified',
         'paid_operations':0,'original_sha256':digest(source),'draft_sha256':digest(a.draft),
         'requires':'Check all lyrics, singing synchronization, and separated audio before final approval.'})
    os.environ['PATH']=str(FFMPEG.parent)+os.pathsep+os.environ.get('PATH','')
    torch.set_num_threads(2)
    align(cfg,work)
    render(cfg,work,preview=True)
    print('UNAPPROVED REVIEW COPY:',work/'preview'/(cfg['slug']+'_Karaoke.mp4'),flush=True)
