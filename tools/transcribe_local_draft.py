"""Independent local draft transcription; never implies lyric approval."""
import argparse
from pathlib import Path
from faster_whisper import WhisperModel
from zoom_local_pipeline import audio,save,digest

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--model',default='small')
    p.add_argument('--allow-download',action='store_true',help='Download public model weights; inference remains local')
    p.add_argument('--language',default='en');a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    model=WhisperModel(a.model,device='cpu',compute_type='int8',cpu_threads=2,local_files_only=not a.allow_download)
    segments,_=model.transcribe(audio(a.source),language=a.language,beam_size=5,
                               vad_filter=False,condition_on_previous_text=False,word_timestamps=True)
    result=[]
    for s in segments:
        result.append({'start':s.start,'end':s.end,'text':s.text,'words':[
            {'word':w.word,'start':w.start,'end':w.end,'probability':w.probability} for w in s.words or []]})
        print(s.start,s.end,s.text,flush=True)
    save(a.output,{'source_sha256':digest(a.source),'model':a.model,'status':'unreviewed_draft','segments':result})
