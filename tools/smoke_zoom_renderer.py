"""Synthetic render check; never reads/writes a real delivery video."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from zoom_local_pipeline import ROOT, FFMPEG, save, digest, render

base = ROOT/'work/zoom_local'
base.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix='synthetic_smoke_', dir=base))
backing = work/'backing.wav'
reference = work/'reference.wav'
for target in (backing, reference):
    if not target.exists():
        subprocess.run([str(FFMPEG), '-v', 'error', '-n', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=4', str(target)], check=True)
cfg = {'slug': 'Zoom_Synthetic_Test', 'title': 'LOCAL PIPELINE TEST', 'artist': 'Synthetic audio',
       'zoom_video': str(backing), 'vocal_reference': str(reference),
       'background': str(ROOT/'audio-bg-sample/14-10/jan-chatgpt/Dromerige neonbowling in Aalborg.png')}
save(work/'transcript.json', [{'start': .5, 'end': 2, 'text': 'Timing test'}])
save(work/'alignment-inputs.json', {'transcript': digest(work/'transcript.json'),
                                   'vocal_reference': digest(reference)})
save(work/'aligned.json', [{'words':[{'start':.5,'end':1,'word':'Timing'},
                                   {'start':1.5,'end':2,'word':'test'}]}])
save(work/'sync.json', {'anchors':[[0,0],[4,4]]})
render(cfg, work, preview=True)
print('PASS: synthetic preview rendered, decoded and duration/resolution checked')
