"""Reconcile obvious repeated-refrain ASR conflicts; keep uncertainty explicit."""
import copy
from zoom_local_pipeline import ROOT,read,save,digest

base=ROOT/'work/local_open_source/BUNT_TRIPPIN'
draft=copy.deepcopy(read(base/'vocals-medium-draft.json'))
changes=[]
for s in draft['segments']:
    old=s['text']
    s['text']=s['text'].replace("I've prepared","I'm trippin'").replace("drippin'","trippin'").replace("Drippin'","Trippin'").replace("Clippin'","Trippin'")
    if old!=s['text']:changes.append({'start':s['start'],'before':old,'after':s['text'],'basis':'Repeated refrain recognized as trippin in independent original-mix local draft; requires listening confirmation'})
    s.pop('words',None) # New word timings must come from forced alignment.
# Both original-mix and isolated-vocal small-model drafts detect this phrase,
# which medium omitted; wording follows the other medium-model repetitions.
draft['segments'].append({'start':52.62,'end':55.5,'text':"Trippin' on my own two"})
changes.append({'start':52.62,'after':"Trippin' on my own two",'basis':'Phrase detected in small original/vocal drafts, wording inferred from repeated medium-model refrain; unapproved'})
draft['segments'].sort(key=lambda s:s['start'])
draft['status']='provisional_reconciled_draft_not_listening_verified'
draft['changes']=changes
draft['review_required']=['Verse wording remains uncertain','Repeated anybody/everybody counts','Refrain wording and missing-phrase reconstruction','All word timings','Quiet backing section 48.16-49.20 original seconds']
draft['independent_original_draft_sha256']=digest(base/'original-draft.json')
save(base/'vocals-reconciled-draft.json',draft)
