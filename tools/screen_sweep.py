"""Measured screen sweep geometry reused from zoom_converter, without its renderer."""
from bisect import bisect_right
import math
import re
import numpy as np


def text(value):
    return str(value).replace('\\','/').replace('{','(').replace('}',')').replace('\n',' ')


def tokens(value):
    return re.sub(r'\W','',value,flags=re.UNICODE).casefold()

def validate_cues(cues,duration,require_sweep=False):
    if not cues:raise ValueError('No recovered lyrics; review this layout')
    previous=0
    for cue in cues:
        words=cue.get('words',[])
        if not words or tokens(cue['text'])!=tokens(''.join(w['word'] for w in words)):
            raise ValueError('Missing or mismatched lyric words: '+cue.get('text',''))
        if any('incomplete' in issue or 'empty' in issue for issue in cue.get('issues',[])):
            raise ValueError('Incomplete recovered words must be corrected')
        for w in words:
            if not all(math.isfinite(w[key]) for key in ('start','end')):
                raise ValueError('Nonfinite timestamp')
            if not previous<=w['start']<w['end']<=duration+.04:
                raise ValueError('Overlapping, zero-length or out-of-range word: '+str(w))
            if round(w['end']*100)<=round(w['start']*100):
                raise ValueError('Word is shorter than subtitle resolution')
            if require_sweep and not w.get('sweep'):
                raise ValueError('Missing measured source sweep')
            if 'sweep' in w:
                last_time=-1.0;last_fraction=-1.0
                for sample in w['sweep']:
                    if len(sample)!=2 or not all(math.isfinite(x) for x in sample):
                        raise ValueError('Invalid source-frame sweep sample')
                    at,fraction=sample
                    if not last_time<at or not 0<=fraction<=1 or fraction<last_fraction:
                        raise ValueError('Source sweep timestamps/progress must increase')
                    last_time,last_fraction=at,fraction
                if not w['sweep']:raise ValueError('Empty source-frame sweep')
            previous=w['end']
        if abs(cue['start']-words[0]['start'])>.02 or abs(cue['end']-words[-1]['end'])>.02:
            raise ValueError('Cue boundaries must match its words')
    return cues

def glyph_front(columns,fraction):
    """Map painted glyph area to a horizontal clip, including inter-letter gaps."""
    values=np.asarray(columns,dtype=float)
    if fraction<=0:return 0.0
    if fraction>=1:return float(len(values))
    cumulative=np.cumsum(values)
    if not len(cumulative) or cumulative[-1]<=0:return 0.0
    target=fraction*cumulative[-1]
    index=min(len(values)-1,int(np.searchsorted(cumulative,target)))
    before=cumulative[index-1] if index else 0
    return index+(target-before)/max(values[index],1e-9)

def eased_progress(value,at,start,end,ease=1.0):
    """Optional visual slowdown bounded by the existing word interval."""
    if ease==1:return value
    phase=max(0.0,min(1.0,(at-start)/(end-start)))
    return min(value,phase**ease)



def sweep_intervals(words,font,offset=0.,ease=1.):
    """Yield output start/end and painted width from actual source-frame samples.

    Offset shifts audio and all source samples together; zero progress is a hold.
    No interpolation turns a measured hold into a straight word-duration sweep.
    """
    a,b=words[0]['start'],words[-1]['end']
    times=sorted({a,b,*[w[key] for w in words for key in ('start','end')],
                  *[at for w in words for at,_ in w['sweep'] if a<=at<=b]})
    prefixes=[font.getlength(' '.join(text(w['word']).strip() for w in words[:j])+(' ' if j else '')) for j in range(len(words))]
    glyphs=[]
    for w in words:
        mask=font.getmask(text(w['word']).strip())
        glyphs.append(np.asarray(mask,dtype=float).reshape(mask.size[1],mask.size[0]).sum(axis=0))
    for t,until in zip(times,times[1:]):
        front=0.
        for j,w in enumerate(words):
            samples=w['sweep']; index=bisect_right([s[0] for s in samples],t+.0001)-1
            value=samples[index][1] if index>=0 else 0.
            if t<w['start']:value=0.
            if t>=w['end']:value=1.
            value=eased_progress(value,t,w['start'],w['end'],ease)
            if value>0:front=max(front,prefixes[j]+glyph_front(glyphs[j],value))
        yield t+offset,until+offset,front
