"""Correct/recover this source's lyrics from its own on-screen words plus ASR."""
import shutil
from project_runtime import ROOT
from zoom_local_pipeline import read,save,digest
from read_visible_lyrics import norm

folder=ROOT/'work/local_open_source/Before_You_Know_It-30464422ee10'
reference=read(folder/'screen-reference.json')
assert reference['complete'] and reference['binding']['source_sha256']=='fed9959cfcd710e641149e1993a826b35a9c1dc9260712c60006da57587d3d12'
pairs=[
('FRIDAYNIGHT','Friday night'),('LASTCALLAGAIN','Last call again'),
('ONEFINALROUND OFDRINKS','One final round of drinks'),('MYFRIENDS','My friends'),
("WE'REGOING","We're going, we're going"),('TAKEAGLASS','Take a glass'),
('ANDFILLITUP','And fill it up'),("DON'TWANTTOSEE","Don't wanna see"),
('NO EMPTY CUP','No empty cup'),("WE'RETOASTING","We're toasting"),('THISMOMENT','This moment'),
('AND EVENTHOUGH','And even though'),('THEYSAYTHE','They say the'),
('BARSARECLOSING','Bars are closing'),('NIGHTIS DONE','Night is done'),
("WE'LLBE","We'll be"),('BACKBEFOREYOUKNOWIT','Back before you know it'),
('TOTHEPLACE','To the place'),('WEALLKNOW','We all know'),('ANDLOVE','And love'),
('WITHTHOSEREDWINE','With those red wine'),('STAINS ON THERUGS','Stains on the rugs'),
('THOUGHOURHEADS','Though our heads'),('MIGHTHURTINTHEMORNING','Might hurt in the morning'),
("WE'LLBEBACKBEFOREYOU","We'll be back before you"),
("WE'LLBERIGHTBACK","We'll be right back"),('ATITAGAIN','At it again'),
('TURNING RANDOM','Turning random'),('STRANGERS TOFRIENDS','Strangers to friends'),
('WEMIGHTWAKEUP','We might wake up'),('WISHING ANDHOPING','Wishing and hoping'),
("BUTWE'LLBEBACKBEFOREYOU","But we'll be back before you"),
('STARTTOWALKTO','Start to walk too'),('STRAIGHTOFLINE','Straight a line'),
("WE'LLCIRCLEBACK","We'll circle back"),('TOTHISOLDDIVELIKEALWAYS','To this old dive, like always'),
('LIKEALWAYS','Like always'),("WE'LLBEPICKING UP","We'll be picking up"),
('WHEREWELEFTOF','Where we left off'),('WE TAKETHEHEARTBREAKS','We take our heartbreaks'),
('ON THE ROCKS','On the rocks'),('ATOURPLACE','At our place, at our place'),
("OH,WE'LLBEBACKBEFOREYOU","Oh, we'll be back before you"),
("OH,WE'LLBEBAK","Oh, we'll be back"),
("OH,WELLBEBACKBEFOREOU","Oh, we'll be back before you"),
]
corrections={norm(a):b for a,b in pairs}
patterns=[('FRIDAYNIGHT','LASTCALLAGAIN'),('ONEFINALROUND OFDRINKS','MYFRIENDS'),
    ('TAKEAGLASS','ANDFILLITUP'),("DON'TWANTTOSEE",'NO EMPTY CUP'),("WE'RETOASTING",'THISMOMENT'),
    ('AND EVENTHOUGH','THEYSAYTHE','BARSARECLOSING'),('AND EVENTHOUGH','THEYSAYTHE','NIGHTIS DONE'),
    ("WE'LLBE",'BACKBEFOREYOUKNOWIT'),('TOTHEPLACE','WEALLKNOW','ANDLOVE'),
    ('WITHTHOSEREDWINE','STAINS ON THERUGS'),('THOUGHOURHEADS','MIGHTHURTINTHEMORNING'),
    ("WE'LLBERIGHTBACK",'ATITAGAIN'),('TURNING RANDOM','STRANGERS TOFRIENDS'),
    ('WEMIGHTWAKEUP','WISHING ANDHOPING'),('STARTTOWALKTO','STRAIGHTOFLINE'),
    ("WE'LLCIRCLEBACK",'TOTHISOLDDIVELIKEALWAYS'),("WE'LLBEPICKING UP",'WHEREWELEFTOF'),
    ('WE TAKETHEHEARTBREAKS','ON THE ROCKS')]
patterns=[tuple(map(norm,p)) for p in patterns]
cues=reference['cues'];keys=[norm(c['text']) for c in cues]
unknown=[c['text'] for c in cues if norm(c['text']) not in corrections]
if unknown:raise ValueError('Unreviewed source text: '+repr(unknown))
rows=[];i=0
while i<len(cues):
    count=next((len(p) for p in patterns if tuple(keys[i:i+len(p)])==p),1)
    selected=cues[i:i+count]
    texts=[corrections[keys[j]] for j in range(i,i+count)]
    text=texts[0]+''.join(' '+part[0].lower()+part[1:] for part in texts[1:])
    rows.append({'start':max(0,selected[0]['start']-.75),
                 'end':min(173.5,selected[-1]['end']+.25),'text':text})
    i+=count
assert len(rows)==45 and rows[-1]['text']=='Back before you know it'
# Source line change is at 165.5s; the first loose window caught the prior line.
rows[-1]['start']=165.32
history=folder/'history';history.mkdir(exist_ok=True)
backup=history/'transcript-before-screen-review.json'
if not backup.exists():shutil.copy2(folder/'transcript.json',backup)
save(folder/'transcript.json',rows)
save(folder/'lyric-review-notes.json',{
    'basis':'On-screen lyric words from the exact downloaded source cross-checked against its vocal-stem ASR',
    'reference_sha256':digest(folder/'screen-reference.json'),
    'outro_boundary_seconds':165.32,
    'corrections':'Spacing/OCR errors, rug/rocks, know it/know me and missing chorus/outro phrases corrected',
    'full_listening_completed':False,'timing_status':'Source appearance windows are guides; forced word alignment follows',
    'limitations':['Ad-lib completeness and singing alignment still require listening review']})
print('Prepared',len(rows),'source-checked lyric lines')
