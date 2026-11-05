"""Prepare source-derived lyric corrections; never invent lyric approval.

Accepts transcribe_source_reference.py JSON and optional reviewed lyric text.
Writes bounded line windows for the existing WhisperX alignment pipeline.
"""
import argparse
import json
import math
from pathlib import Path
import re
from lyrics_import import parse_lyrics, place_lines, segment_words


def flag_lines(rows):
    issues=[]
    for i,row in enumerate(rows):
        tokens=re.findall(r'\w+',row['text'].casefold())
        reasons=[]
        if sum(t.isdigit() for t in tokens)>=6:
            reasons.append('numeric_sequence_requires_source_review')
        for width in (1,2,3):
            if any(tokens[k:k+width]*4 == tokens[k:k+width*4]
                   for k in range(max(0,len(tokens)-width*4+1))):
                reasons.append('repeated_phrase_requires_source_review');break
        if i and row['start']-rows[i-1]['end']>12:
            reasons.append('long_gap_requires_source_review')
        if i>=2 and row['text'].casefold()==rows[i-1]['text'].casefold()==rows[i-2]['text'].casefold():
            reasons.append('three_identical_lines_require_source_review')
        if reasons:issues.append({'line':i+1,'start':row['start'],'end':row['end'],'reasons':reasons})
    return issues


def make_lines(segments,max_chars=46):
    rows=[]
    for segment in segments:
        words=segment_words([segment])
        group=[]
        for word in words:
            if group and (len(' '.join(w['word'].strip() for w in group+[word]))>max_chars
                          or word['start']-group[0]['start']>5.5):
                rows.append({'start':group[0]['start'],'end':group[-1]['end'],
                             'text':' '.join(w['word'].strip() for w in group)})
                group=[]
            group.append(word)
        if group:rows.append({'start':group[0]['start'],'end':group[-1]['end'],
                              'text':' '.join(w['word'].strip() for w in group)})
    for row in rows:
        if not all(math.isfinite(row[k]) for k in ('start','end')) or row['end']<=row['start']:
            raise ValueError('Invalid timing in original ASR; review required')
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--transcript',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--lyrics',type=Path,help='Reviewed text for this exact recording, one sung line per row')
    p.add_argument('--replacements',type=Path,help='Explicit JSON map of spelling corrections')
    a=p.parse_args()
    from zoom_local_pipeline import read,save,digest
    data=read(a.transcript)
    if digest(data['source'])!=data['source_sha256']:raise ValueError('Original source changed')
    if a.output.exists():raise FileExistsError('Use a new correction folder to preserve prior work')
    rows=make_lines(data['segments'])
    placement=None
    if a.lyrics:
        import av
        with av.open(data['source']) as media:duration=media.duration/av.time_base
        rows,placement=place_lines(parse_lyrics(a.lyrics.read_text(encoding='utf-8-sig')),
                                    segment_words(data['segments']),duration)
    changes=[]
    if a.replacements:
        replacements=read(a.replacements)
        for row in rows:
            for before,after in replacements.items():
                updated=re.sub(r'(?<!\w)'+re.escape(before)+r'(?!\w)',after,row['text'],flags=re.I)
                if updated!=row['text']:
                    changes.append({'start':row['start'],'before':row['text'],'after':updated})
                    row['text']=updated
    a.output.mkdir(parents=True)
    save(a.output/'transcript.json',rows)
    (a.output/'lyrics-to-review.txt').write_text('\n'.join(row['text'] for row in rows)+'\n',encoding='utf-8')
    report={'source':data['source'],'source_sha256':data['source_sha256'],
            'transcription_sha256':digest(a.transcript),'reference_lyrics_sha256':digest(a.lyrics) if a.lyrics else None,
            'placement':placement,'spelling_changes':changes,'flags':flag_lines(rows),
            'status':'needs_lyric_and_timing_review','accuracy_verified':False,
            'note':'No flags is not evidence of correct wording. Alignment and human lyric review remain separate.'}
    save(a.output/'correction-report.json',report)
    print(json.dumps({'output':str(a.output),'lines':len(rows),'flags':len(report['flags']),
                      'status':report['status']}))


if __name__=='__main__':main()
