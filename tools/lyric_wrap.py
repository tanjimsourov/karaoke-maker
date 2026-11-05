"""Measured, balanced lyric rows that preserve every timed token."""
from functools import lru_cache


def balanced_groups(words, measure, maximum):
    if not words:return []
    @lru_cache(None)
    def solve(i):
        if i==len(words):return (0,0,0),[]
        best=None
        for end in range(i+1,len(words)+1):
            width=measure(''.join(w for _,w in words[i:end]))
            if width>maximum and end>i+1:break
            score,rest=solve(end)
            actual=sum(bool(w.strip()) for _,w in words[i:end])
            value=(score[0]+1,score[1]+int(actual==1),score[2]+(maximum-width)**2)
            candidate=value,[words[i:end],*rest]
            if best is None or value<best[0]:best=candidate
        return best
    return solve(0)[1]
