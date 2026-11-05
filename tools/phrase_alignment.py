"""Reuse unchanged aligned phrases; changed text/windows get fresh forced alignment."""
import hashlib
import json
from pathlib import Path

def incremental(transcript,binding,folder,align_one):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    output=[];reused=0;computed=0
    for segment in transcript:
        key=hashlib.sha256(json.dumps({'binding':binding,'segment':segment},sort_keys=True).encode()).hexdigest()
        path=folder/(key+'.json')
        if path.exists():
            item=json.loads(path.read_text(encoding='utf-8'))
            payload=json.dumps(item['segments'],sort_keys=True).encode()
            if hashlib.sha256(payload).hexdigest()!=item['sha256']:raise ValueError('Phrase cache corrupted')
            rows=item['segments'];reused+=1
        else:
            rows=align_one(segment)
            if not rows:raise ValueError('Alignment returned no words for a phrase')
            payload=json.dumps(rows,sort_keys=True).encode()
            temp=path.with_suffix('.tmp')
            temp.write_text(json.dumps({'segments':rows,'sha256':hashlib.sha256(payload).hexdigest()},ensure_ascii=False),encoding='utf-8')
            temp.replace(path);computed+=1
        output.extend(rows)
    return output,{'reused_phrases':reused,'aligned_phrases':computed,'binding':binding}
