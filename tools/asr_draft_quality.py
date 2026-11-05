"""Minimal reject-only sanity checks, not a lyric accuracy certification."""
import re
import math

def validate_asr_draft(draft):
    segments=draft.get('segments',[])
    isolated=sum(len(re.sub(r'\W','',s['text'],flags=re.UNICODE))<=1 for s in segments)
    if not segments or (len(segments)>=10 and isolated/len(segments)>.2):
        raise ValueError(f'Unusable ASR draft: {isolated}/{len(segments)} isolated-letter/empty cues; lyric review required before rendering')
    for number,segment in enumerate(segments,1):
        if 'start' not in segment or 'end' not in segment:continue
        duration=segment['end']-segment['start']
        if not math.isfinite(duration) or duration<=0:
            raise ValueError(f'Unusable ASR draft: invalid duration in segment {number}')
        tokens=[re.sub(r'\W+','',w).casefold() for w in segment['text'].split()]
        longest=run=0;previous=None
        for token in tokens:
            run=run+1 if token and token==previous else 1
            longest=max(longest,run);previous=token
        rate=len(tokens)/duration
        if (longest>=30 and rate>6) or (len(tokens)>30 and rate>12):
            raise ValueError(f'Unusable ASR draft: implausible repetition/word rate in segment {number}; correct the lyrics before review')
    return {'segments':len(segments),'isolated_letter_cues':isolated,'accuracy_verified':False}
