"""Create an explicitly unreviewed transcription from a supplied original recording."""
import argparse
from pathlib import Path
from project_runtime import MODELS
from zoom_local_pipeline import audio, digest, save
from faster_whisper import WhisperModel

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--language',required=True)
    p.add_argument('--prompt',default='')
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    model=WhisperModel('large-v3-turbo',device='cpu',compute_type='int8',cpu_threads=6,
                       download_root=str(MODELS/'whisper'),local_files_only=True)
    segments,info=model.transcribe(audio(a.source),language=a.language,beam_size=5,
        vad_filter=False,condition_on_previous_text=False,word_timestamps=True,
        initial_prompt=a.prompt,chunk_length=30,temperature=0)
    rows=[]
    for s in segments:
        row={'start':s.start,'end':s.end,'text':s.text,
             'words':[{'word':w.word,'start':w.start,'end':w.end,'probability':w.probability} for w in s.words or []],
             'avg_logprob':s.avg_logprob,'no_speech_prob':s.no_speech_prob}
        rows.append(row)
        print(f'{s.start:.2f} {s.end:.2f} {s.text}',flush=True)
        save(a.output.with_suffix('.partial.json'),rows)
    save(a.output,{'source':str(a.source.resolve()),'source_sha256':digest(a.source),
                   'language':info.language,'human_reviewed':False,'segments':rows})

if __name__=='__main__':main()
