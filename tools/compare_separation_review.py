"""Measure the reported break without changing any delivery audio."""
import json, subprocess
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parents[1]
ff=root/'tools/ffmpeg/ffmpeg.exe'
review=root/'work/separation_review'
paths={
 'original':root/'Bowlnfun Jakob For Visuals/Ærlig Freestyle.mp3',
 'karadeo_instrumental':root/'work/bowlnfun/AEr_lig_Freestyle/instrumental.mp3',
 'demucs_ft_instrumental':review/'htdemucs_ft/aer_separation_test/no_vocals.wav',
 'demucs_ft_vocals':review/'htdemucs_ft/aer_separation_test/vocals.wav',
}
windows=[(0.1,1.1),(2,5),(30,35),(35.58,37.98),(38,42)]
report={'delivery_modified':False,'model':'htdemucs_ft','shifts':1,'overlap':0.5,'measurements_dbfs':{}}
for label,p in paths.items():
 raw=subprocess.run([str(ff),'-v','error','-i',str(p),'-t','45','-ar','8000','-ac','1','-f','f32le','-'],capture_output=True,check=True).stdout
 audio=np.frombuffer(raw,dtype=np.float32)
 rows=[]
 for start,end in windows:
  a=audio[round(start*8000):round(end*8000)]
  db=float(20*np.log10(max(1e-9,np.sqrt(np.mean(a*a)))))
  rows.append({'source_start':start,'source_end':end,'rms_dbfs':round(db,2)})
 report['measurements_dbfs'][label]=rows
 subprocess.run([str(ff),'-v','error','-y','-ss','33','-i',str(p),'-t','8','-c:a','pcm_s16le',str(review/f'{label}_33s_to_41s.wav')],check=True)
report['conclusion']='Alternative separator still produces near-silence in both reported sections. Not adopted. No original vocals mixed into final output. Vocal-only or nearly vocal-only source breaks are strongly indicated, not proven by energy measurements alone.'
(review/'comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
