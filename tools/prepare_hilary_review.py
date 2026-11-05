"""Source-bound CATastrophe correction recipe; never claims listening approval."""
import json
import shutil
from project_runtime import ROOT
from zoom_local_pipeline import digest

folder=ROOT/'work/local_open_source/CATastrophe-663505cfa8b3'
source=ROOT/'inputs/Hilary Duff - CATastrophe (1080p).mp4'
assert digest(source)=='baee21ca43052b032228b8b01124582c923513e19546df685f4b9547782bf75c'
history=folder/'history';history.mkdir(exist_ok=True)
backup=history/'transcript-before-caption-review.json'
if not backup.exists():shutil.copy2(folder/'transcript.json',backup)
rows=json.loads(backup.read_text(encoding='utf-8'))
assert len(rows)==18 and 'little catty' in rows[0]['text']
for i in (4,13):rows[i]['text']='I put the cat in the catastrophe'
for i in (6,15):rows[i]['text']="Hey, I got nine lives, let's live one up tonight"
rows[9]['text']='You know I got some things hidden under my hat'
rows[9]['start']=73.1
rows[12]['text']='Just hold on to my whirlwind with whimsical force'
def cue(start,end,text):return {'start':start,'end':end,'text':text}
first=[cue(51.0,52.2,'Alright'),cue(52.2,54.7,'Hey, gi-gi-gi-gimme that'),
       cue(54.7,58.4,'Big ki-ki-ki kitty cat energy'),cue(58.5,59.8,'Alright'),
       cue(59.9,61.98,'Hey, let the cat out of the bag')]
second=[cue(108.6,110.3,'Alright'),cue(110.3,112.3,'Hey, gi-gi-gi-gimme that'),
        cue(112.3,116.2,'Big ki-ki-ki kitty cat energy'),cue(116.3,117.8,'Alright'),
        cue(117.9,120.0,'Let the cat out of the bag')]
rows[17]['start']=120.0;rows[17]['end']=123.5
result=rows[:8]+first+rows[8:17]+second+rows[17:]
(folder/'transcript.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
(folder/'lyric-review-notes.json').write_text(json.dumps({
    'basis':'Vocal-stem Whisper draft cross-checked against downloaded English captions from the same official video',
    'caption_file':str(ROOT/'tmp/hilary-caption/kutumaLYK18.en.json3'),
    'corroboration':'https://www.lahiguera.net/musicalia/artistas/varios/disco/0/tema/34829/',
    'corrections':'Cat/hat/whirlwind phrases corrected; missed rhythmic chant sections restored',
    'full_listening_completed':False,
    'limitations':['Stutter/chant phoneme timing needs review','Spoken end-of-video uh-oh is not included'],
},indent=2),encoding='utf-8')
print('Prepared source-bound lyric review candidate')
