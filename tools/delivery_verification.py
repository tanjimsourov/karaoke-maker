"""Evidence-bound delivery review. ASR agreement is evidence, never proof of correctness."""
import difflib
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def tokens(text):
    return re.findall(r"[^\W_]+(?:['’][^\W_]+)?", text.casefold(), re.UNICODE)


def compare(transcript, aligned, reference, duration, quality):
    issues = []
    def flag(kind, detail, hard=False, **evidence):
        issues.append(dict(id=f'{kind}-{len(issues)+1}', kind=kind, detail=detail,
                           must_fix=hard, **evidence))
    draft = [t for row in transcript for t in tokens(row.get('text', ''))]
    aligned_text = [t for row in aligned for t in tokens(row.get('text', ''))]
    if not draft or aligned_text != draft:
        flag('alignment_text', 'Aligned lines do not match the current transcript.', True)
    timed = []
    previous = -1.0
    for line, row in enumerate(aligned):
        words = row.get('words', [])
        if [t for w in words for t in tokens(w.get('word', ''))] != tokens(row.get('text', '')):
            flag('missing_word_timing', 'Every lyric word must have a timing.', True, line=line)
        for w in words:
            a, b = w.get('start'), w.get('end')
            if (not isinstance(a, (int, float)) or not isinstance(b, (int, float))
                    or not math.isfinite(a) or not math.isfinite(b)
                    or a < 0 or b <= a or b > duration + .1 or a < previous - .05):
                flag('invalid_word_timing', 'Invalid, overlapping, or out-of-range word timing.', True,
                     line=line, word=w.get('word'), start=a, end=b)
                continue
            previous = b
            timed.append(w)
            if b-a < .06 or b-a > 3:
                flag('word_duration', 'Check this unusually short/long highlight.',
                     line=line, word=w.get('word'), start=a, end=b)
            score = w.get('score')
            if score is not None and (not isinstance(score, (int,float)) or not math.isfinite(score) or score < .5):
                flag('alignment_confidence', 'Low alignment confidence.', line=line,
                     word=w.get('word'), start=a, end=b)
    ref_rows = reference.get('segments', [])
    ref = [t for row in ref_rows for t in tokens(row.get('text', ''))]
    if not ref:
        flag('reference_empty', 'Original-audio transcription contains no words.', True)
    matcher = difflib.SequenceMatcher(None, draft, ref, autojunk=False)
    for op, a, b, c, d in matcher.get_opcodes():
        if op != 'equal':
            flag('lyric_disagreement', 'Check against the original singing; neither ASR pass is authoritative.',
                 transcript_words=draft[a:b], source_pass_words=ref[c:d], transcript_token_range=[a,b])
    flat = [(t,w) for w in timed for t in tokens(w.get('word',''))]
    ref_flat = [(t,w) for row in ref_rows for w in row.get('words',[]) for t in tokens(w.get('word',''))]
    for block in difflib.SequenceMatcher(None,[t for t,w in flat],[t for t,w in ref_flat],autojunk=False).get_matching_blocks():
        for offset in range(block.size):
            _, w = flat[block.a+offset]; _, r = ref_flat[block.b+offset]
            if isinstance(r.get('start'), (int,float)) and abs(w['start']-r['start']) > .4:
                flag('timing_disagreement', 'Word onset differs from the original-audio ASR pass by over 0.4s.',
                     word=w['word'], start=w['start'], reference_start=r['start'])
    for reason in quality.get('signal',{}).get('reject_reasons',[]):
        flag('audio_rejected', str(reason), True)
    for warning in quality.get('flags',[]) + quality.get('signal',{}).get('flags',[]):
        flag('audio_warning', 'Listen to original and instrumental at this interval.', evidence=warning)
    return issues


def inputs(cfg, folder):
    folder = Path(folder)
    preview = read(folder/'preview-validation.json')
    files = {'source':cfg['vocal_reference'], 'instrumental':cfg['zoom_video'],
             'transcript':folder/'transcript.json','alignment':folder/'aligned.json',
             'subtitles':folder/'lyrics.ass','audio_selection':folder/'audio-quality/selection.json',
             'preview_validation':folder/'preview-validation.json','video':preview['output'],
             'reference':folder/'verification-reference.json',
             'verifier':Path(__file__), 'reference_code':Path(__file__).with_name('transcribe_source_reference.py')}
    return {key:sha(path) for key,path in files.items()}


def build(cfg, folder):
    from project_runtime import ROOT, child_env
    from zoom_local_pipeline import audio
    import separation_guard
    folder=Path(folder)
    ref=folder/'verification-reference.json'
    ref_binding=folder/'verification-reference-binding.json'
    wanted={'source':sha(cfg['vocal_reference']), 'language':cfg['language'],
            'code':sha(ROOT/'tools/transcribe_source_reference.py')}
    cached=read(ref_binding) if ref_binding.exists() else {}
    if not (ref.exists() and all(cached.get(k)==v for k,v in wanted.items()) and cached.get('result')==sha(ref)):
        if ref.exists():
            history=folder/'history';history.mkdir(exist_ok=True)
            ref.replace(history/('reference-'+sha(ref)+'.json'))
        from model_queue import model_slot
        with model_slot(name='delivery-asr'):
            subprocess.run([sys.executable,str(ROOT/'tools/transcribe_source_reference.py'),
                            '--source',cfg['vocal_reference'],'--output',str(ref),
                            '--language',cfg['language'],'--threads',str(cfg.get('transcription_threads',2))],
                           check=True,env=child_env())
        write(ref_binding,{**wanted,'result':sha(ref)})
    reference=read(ref)
    if reference.get('source_sha256')!=wanted['source']:
        raise ValueError('Reference transcription is not bound to this source')
    _,quality=separation_guard.validate(cfg['vocal_reference'],folder/'audio-quality')
    issues=compare(read(folder/'transcript.json'),read(folder/'aligned.json'),reference,
                   len(audio(cfg['zoom_video']))/16000,quality)
    report={'schema':1,'status':'needs_review','bindings':inputs(cfg,folder),'issues':issues,
            'limitations':['ASR passes may agree on incorrect words.',
                'No clean reference instrumental: instrument preservation requires listening.',
                'Review the complete rendered video, not only sampled frames.']}
    write(folder/'delivery-verification.json',report)
    template=folder/'delivery-decisions.template.json'
    write(template,{'report_sha256':sha(folder/'delivery-verification.json'),'reviewer':'',
        'checked_full_lyrics':False,'checked_full_highlighting':False,'listened_full_instrumental':False,
        'compared_instrument_preservation':False,
        'issues':{i['id']:{'accepted_after_review':False,'reason':''} for i in issues}})
    return report


def require_current(cfg, folder):
    folder=Path(folder);report=read(folder/'delivery-verification.json')
    if report.get('bindings')!=inputs(cfg,folder):
        raise ValueError('Delivery evidence is stale; rerun verify after corrections')
    return report


def approve(cfg, folder, decisions):
    folder=Path(folder);report=require_current(cfg,folder);decision=read(decisions)
    if decision.get('report_sha256')!=sha(folder/'delivery-verification.json'):
        raise ValueError('Decisions belong to another verification report')
    if not isinstance(decision.get('reviewer'),str) or not decision['reviewer'].strip():
        raise ValueError('A named reviewer is required')
    for field in ['checked_full_lyrics','checked_full_highlighting','listened_full_instrumental','compared_instrument_preservation']:
        if decision.get(field) is not True:raise ValueError('Review missing: '+field)
    for issue in report['issues']:
        if issue['must_fix']:raise ValueError('Fix and rerun verification: '+issue['id'])
        entry=decision.get('issues',{}).get(issue['id'],{})
        if entry.get('accepted_after_review') is not True or not str(entry.get('reason','')).strip():
            raise ValueError('Unresolved issue: '+issue['id'])
    write(folder/'delivery-review.json',decision)


def require_approved(cfg, folder):
    folder=Path(folder)
    # Revalidate current media and every individual decision, not just an approval boolean.
    approve(cfg,folder,folder/'delivery-review.json')
