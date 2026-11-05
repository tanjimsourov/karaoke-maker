"""Independent local transcription check; never rewrites approved captions."""
import json, subprocess
from pathlib import Path
import numpy as np
from faster_whisper import WhisperModel
root=Path(__file__).resolve().parents[1]
raw=subprocess.run([str(root/'tools/ffmpeg/ffmpeg.exe'),'-v','error','-i',str(root/'Bowlnfun Jakob For Visuals/Ærlig Freestyle.mp3'),'-t','65','-ar','16000','-ac','1','-f','f32le','-'],capture_output=True,check=True).stdout
audio=np.frombuffer(raw,dtype=np.float32)
model=WhisperModel('small',device='cpu',compute_type='int8')
segments,info=model.transcribe(audio,language='da',word_timestamps=True,vad_filter=False,beam_size=5,condition_on_previous_text=False)
results=[]
for seg in segments:
    item={'start':seg.start,'end':seg.end,'text':seg.text,'words':[{'start':w.start,'end':w.end,'word':w.word,'probability':w.probability} for w in seg.words or []]}
    results.append(item)
    print(json.dumps(item,ensure_ascii=True),flush=True)
out=root/'work/separation_review/aer_independent_timing.json'
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
