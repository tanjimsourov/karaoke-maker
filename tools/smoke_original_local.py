"""Real Danish excerpt test; not a full-song final or quality approval."""
import os
import subprocess
from faster_whisper import WhisperModel
from zoom_local_pipeline import ROOT, FFMPEG, save, digest, audio, align, render
from local_audio_audit import compare

work=ROOT/'work/local_open_source/danish_excerpt_test'
work.mkdir(parents=True,exist_ok=True)
source=ROOT/'Bowlnfun Jakob For Visuals/done/Ærlig Freestyle.mp3'
clip=work/'original_30_to_42.wav'
if not clip.exists():
    subprocess.run([str(FFMPEG),'-v','error','-n','-ss','30','-i',str(source),
                    '-t','12','-c:a','pcm_f32le',str(clip)],check=True)
stems=ROOT/'work/local_open_source/separation_test'
cfg={'slug':'Local_Danish_Excerpt_Test','title':'EXCERPT TEST - 30 to 42 seconds',
     'artist':'Not a final delivery','language':'da','language_label':'DANSK KARAOKE',
     'vocal_reference':str(clip),'zoom_video':str(stems/'instrumental.wav'),
     'background':str(ROOT/'audio-bg-sample/14-10/jan-chatgpt/Dromerige neonbowling in Aalborg.png')}
save(work/'audio-audit.json',compare(clip,stems/'instrumental.wav',stems/'vocals.wav'))
save(work/'inputs.json',{key:digest(cfg[key]) for key in ('vocal_reference','zoom_video')})
save(work/'sync.json',{'anchors':[[0,0],[12,12]],'source_excerpt_start':30})
os.environ['PATH']=str(FFMPEG.parent)+os.pathsep+os.environ.get('PATH','')
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
if not (work/'transcript.json').exists():
    model=WhisperModel('small',device='cpu',compute_type='int8',local_files_only=True)
    segments,_=model.transcribe(audio(clip),language='da',beam_size=5,condition_on_previous_text=False)
    save(work/'transcript.json',[{'start':s.start,'end':s.end,'text':s.text} for s in segments])
    del model
align(cfg,work)
render(cfg,work,preview=True)
print('PASS: real Danish excerpt separated, transcribed, aligned, audited and preview-rendered. Not human-reviewed.')
