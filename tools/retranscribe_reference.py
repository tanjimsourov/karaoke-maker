"""Keep an independent original-mix transcript for review after a stem ASR failure.

This does not replace/approve the working lyrics. The normal pipeline remains
unchanged; the candidate and its exact elapsed time are retained for comparison.
"""
import argparse
from pathlib import Path
import time
from project_runtime import ROOT, MODELS
from model_queue import model_slot
from workflow import normalize
from zoom_local_pipeline import read,save,audio,digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',type=Path,required=True)
    args=parser.parse_args()
    path=args.job.resolve();job,folder=normalize(read(path),path.parent)
    output=folder/'transcript.original-reference.json'
    if output.exists():raise FileExistsError('Reference exists; preserve it rather than overwriting')
    with model_slot():
        started=time.perf_counter()
        from faster_whisper import WhisperModel
        model=WhisperModel(job['transcription_model'],device='cpu',compute_type='int8',
            cpu_threads=job['audio_quality']['threads'],download_root=str(MODELS/'whisper'),local_files_only=True)
        segments,_=model.transcribe(audio(job['source']),language=job['language'],beam_size=5,
            word_timestamps=True,vad_filter=False,condition_on_previous_text=False,
            chunk_length=30,repetition_penalty=1.05,max_new_tokens=256)
        rows=[]
        for s in segments:
            rows.append({'start':s.start,'end':s.end,'text':s.text,
                'words':[{'word':w.word,'start':w.start,'end':w.end} for w in s.words or []]})
            print(f'{s.start:.2f}-{s.end:.2f} {s.text}',flush=True)
        save(output,rows)
        save(folder/'original-reference-report.json',{'source_sha256':job['source_sha256'],
            'transcript_sha256':digest(output),'elapsed_seconds':time.perf_counter()-started,
            'model':job['transcription_model'],'source_audio':'original mix','chunk_seconds':30,
            'vad_filter':False,'repetition_penalty':1.05,'approved':False})
    print('Saved review candidate:',output,flush=True)


if __name__=='__main__':main()
