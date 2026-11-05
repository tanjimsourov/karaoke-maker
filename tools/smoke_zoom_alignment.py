"""Actual WhisperX alignment test on locally synthesized speech, not a song test."""
import os
import subprocess
import sys
from zoom_local_pipeline import ROOT, FFMPEG, save, audio

work = ROOT/'work/zoom_local/alignment_smoke'
work.mkdir(parents=True, exist_ok=True)
wav = work/'speech.wav'
if not wav.exists():
    command = "Add-Type -AssemblyName System.Speech; $speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; $speaker.SetOutputToWaveFile('" + str(wav).replace("'", "''") + "'); $speaker.Speak('This is a local timing test.'); $speaker.Dispose()"
    subprocess.run(['powershell','-NoProfile','-Command', command], check=True)
os.environ['PATH'] = str(FFMPEG.parent)+os.pathsep+os.environ.get('PATH','')
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
import whisperx
samples = audio(wav)
model, metadata = whisperx.load_align_model(language_code='en',device='cpu')
result = whisperx.align([{'start':0, 'end':len(samples)/16000,
                         'text':'This is a local timing test.'}],model,metadata,samples,
                         'cpu',return_char_alignments=False)
save(work/'result.json',result)
words = result['word_segments']
assert len(words) == 6, words
assert all('start' in w and 'end' in w and w['end'] > w['start'] for w in words), words
assert all(a['end'] <= b['start'] for a,b in zip(words,words[1:])), words
print('PASS: real WhisperX model aligned six locally synthesized words')
