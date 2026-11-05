"""Correct this source's ASR candidate; preserve drafts and review limitations."""
import json
import shutil
from pathlib import Path
from project_runtime import ROOT

folder = ROOT / 'work/local_open_source/2Loud-27ce6177a39d'
rows = json.loads((folder/'transcript.original-reference.json').read_text(encoding='utf-8'))
corrections = {
6: 'To keep the peace and suffocate',
9: "Spent my life tryna fit your frame",
10: 'Smaller to keep you close',
11: "Filtering every word I say",
20: "Not safe for your work, cry about it. Zero to a hundred, real quick, supersonic",
21: "Middle fingers up, I could give a what, start a riot. Pop Crave, front page, need a headline? I provide it",
22: "Why would I be living life on the sidelines? Let me be or get caught in the crossfire",
23: "Got that rage in my heart and it's beating. Why I gotta be shh? Put you in a mausoleum",
24: "Spent my life tryna fit your frame. Smaller to keep you close",
25: "Filtering every word I say",
}
# Indexes below are checked against recognizable original text to avoid silently
# editing another recording or a differently segmented transcript.
assert len(rows) == 41, len(rows)
assert 'What you mean' in rows[1]['text']
for index, text in corrections.items():
    rows[index]['text'] = text
for index in (18, 19):
    rows[index]['text'] = "Ha, ha, said what I said. Blah, blah, I'm getting paid. Talk about me, talk, talk about me, baby"
for index in (34, 37):
    rows[index]['text'] = 'Ha, ha, said what I said'
for index in (35, 38):
    rows[index]['text'] = "Blah, blah, I'm getting paid"
for index in (36,):
    rows[index]['text'] = 'Talk about me, talk, talk about me'
for index in (39, 40):
    rows[index]['text'] = 'Talk about me' if index == 39 else 'Talk, talk about me, baby'
history = folder/'history'
history.mkdir(exist_ok=True)
backup = history/'transcript-before-reference-correction.json'
if not backup.exists():
    shutil.copy2(folder/'transcript.json', backup)
candidate = [{'start':r['start'], 'end':r['end'], 'text':r['text'].strip()} for r in rows]
(folder/'transcript.json').write_text(json.dumps(candidate, indent=2), encoding='utf-8')
(folder/'lyric-review-notes.json').write_text(json.dumps({
    'basis':'Two independent transcriptions of user-supplied recording; spelling/phrase cross-check',
    'reference':'https://music.bugs.co.kr/track/133969513',
    'full_listening_completed':False,
    'limitations':['Opening background ad-libs may be missing', 'Word timings require alignment and review'],
}, indent=2), encoding='utf-8')
print('Saved corrected candidate with original draft preserved')
