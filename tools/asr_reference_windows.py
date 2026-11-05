"""Transcribe short original-audio windows as review evidence, never approval."""
import argparse
from pathlib import Path
import time
from project_runtime import MODELS
from workflow import normalize
from zoom_local_pipeline import read,save,audio
from model_queue import model_slot


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--job',type=Path,required=True)
    p.add_argument('--window',action='append',required=True,help='START:END seconds, at most 30 seconds')
    args=p.parse_args();path=args.job.resolve()
    job,folder=normalize(read(path),path.parent)
    output=folder/'reference-windows.json'
    if output.exists():raise FileExistsError(output)
    windows=[tuple(map(float,w.split(':'))) for w in args.window]
    if any(len(w)!=2 or w[0]<0 or not 0<w[1]-w[0]<=30 for w in windows):p.error('Invalid window')
    with model_slot():
        started=time.perf_counter()
        from faster_whisper import WhisperModel
        model=WhisperModel('base',device='cpu',compute_type='int8',cpu_threads=4,
            download_root=str(MODELS/'whisper'),local_files_only=True)
        samples=audio(job['source']);rows=[]
        for start,end in windows:
            segments,_=model.transcribe(samples[round(start*16000):round(end*16000)],language='en',
                beam_size=5,word_timestamps=True,vad_filter=False,condition_on_previous_text=False,
                repetition_penalty=1.05,max_new_tokens=64)
            result=[]
            for s in segments:
                result.append({'start':start+s.start,'end':start+s.end,'text':s.text,
                    'words':[{'word':w.word,'start':start+w.start,'end':start+w.end} for w in s.words or []]})
            rows.append({'window':[start,end],'segments':result})
            print(start,end,' / '.join(s['text'] for s in result),flush=True)
        save(output,{'source_sha256':job['source_sha256'],'model':'base','windows':rows,
            'elapsed_seconds':time.perf_counter()-started,'approved':False})


if __name__=='__main__':main()
