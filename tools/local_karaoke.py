"""Open-source original-song workflow. No API keys, cloud inference or paid calls.

All generated stems and drafts are isolated under work/local_open_source.
Existing files in out are never replaced. Final exports require listened review.
"""
import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata
from uuid import uuid4
from zoom_local_pipeline import (ROOT, FFMPEG, read, save, digest, audio, align,
                                 render, fingerprint, reviewed_ass, render_options)
from local_audio_audit import compare
from lyrics_import import parse_lyrics, place_lines, segment_words, split_parts
from timing_qa import timing_report
import lyric_editor
import layers as layer_tools
import exports
from device import best_device, whisper_compute_type
from translate_lyrics import (MODES, ENGINES, LLM_MODEL, LLM_URL, lines_from_aligned, model_chain,
                              hub_model_exists, translate, translate_llm, load_memory, add_to_memory)

from project_runtime import WORK, MANIFEST, DEMUCSPY, MODELS, python_in
LABELS = {'da': 'DANSK KARAOKE'}
# large-v3-turbo (0.8B) hears sung lyrics far better than small; override per job.
WHISPER_MODEL = 'large-v3-turbo'
# Finishing for song jobs: streaming loudness, soft edges, cue dots after breaks.
# A job's own "render" block overrides any of these.
PRO_RENDER = {'loudness_lufs':-14.0,'fade_in':0.3,'fade_out':2.0,'gap_countdown':True}
RUNNING = {}  # slug -> background Demucs process started ahead of time


def job_context(job):
    slug = job['slug']
    if not slug.replace('_','').isalnum():
        raise ValueError('Invalid slug')
    folder = WORK/slug
    folder.mkdir(parents=True,exist_ok=True)
    language = job.get('language','auto')
    if language == 'auto' and (folder/'language.json').exists():
        language = read(folder/'language.json')['language']
    separation = job.get('separation',{})
    unknown = set(separation) - {'ensemble','keep_backing_vocals'}
    if unknown:
        raise ValueError(f'Unknown separation option(s): {sorted(unknown)}')
    keep_backing = bool(separation.get('keep_backing_vocals'))
    cfg = {'slug':'Local_'+slug, 'title':job['title'],'artist':job['artist'],
           'vocal_reference':str((ROOT/job['source']).resolve()),
           'zoom_video':str(folder/('stems/instrumental_with_backing.wav' if keep_backing else 'stems/instrumental.wav')),
           # Whisper and WhisperX listen to the isolated (lead) vocal, not the full mix.
           'align_audio':str(folder/('stems/lead_vocals.wav' if keep_backing else 'stems/vocals.wav')),
           'separation':separation,
           'render_defaults':PRO_RENDER,
           'background':str((ROOT/job['background']).resolve()),
           'language':language,
           'language_label':job.get('language_label', LABELS.get(language,'KARAOKE')),
           'transcription_model':job.get('transcription_model',WHISPER_MODEL)}
    if job.get('translation'):
        mode = job['translation'].get('mode','below')
        if mode not in MODES or not job['translation'].get('to'):
            raise ValueError(f'translation needs "to" and a mode in {MODES}')
        cfg['translation'] = {'to':job['translation']['to'],'mode':mode,'file':str(folder/'translation.json')}
        for key in ('engine','style','glossary','quality','instructions'):
            if key in job['translation']:
                cfg['translation'][key] = job['translation'][key]
        if (folder/'translation.json').exists():
            # Bound into the approval fingerprint: edited translations need a new review.
            cfg['translation']['sha256'] = digest(folder/'translation.json')
    if (folder/'layers.json').exists():
        data = layer_tools.validate({**layer_tools.empty(),**read(folder/'layers.json')},ROOT)
        backing = data.get('backing',{})
        # Digests bind layers and their media into the approval fingerprint.
        cfg['layers'] = {'file':str(folder/'layers.json'),'sha256':digest(folder/'layers.json'),
                         'media':{i['file']:digest(layer_tools.resolve(i['file'],ROOT)) for i in data['media']+data['audio']},
                         'changes_audio':bool([a for a in data['audio'] if not a.get('mute')]
                                              or backing.get('mute') or backing.get('volume_db'))}
    if job.get('render'):
        cfg['render'] = job['render']
        cfg['guide_vocal'] = str(folder/'stems/vocals.wav')
        render_options(cfg)
    if not Path(cfg['vocal_reference']).is_file():
        raise ValueError('Original song missing: '+cfg['vocal_reference'])
    return cfg,folder


def separate_command(cfg,folder):
    if not DEMUCSPY.is_file():
        raise ValueError(f'Demucs environment missing: create {DEMUCSPY.parent.parent} from requirements-demucs.txt')
    threads=int(os.environ.get('KARAOKE_SEPARATION_THREADS',cfg.get('separation_threads',int(os.environ.get('KARAOKE_THREADS','2')))))
    if not 1<=threads<=8:raise ValueError('KARAOKE_SEPARATION_THREADS must be 1..8')
    command = [str(DEMUCSPY),str(ROOT/'tools/separate_local_stems.py'),
               '--source',cfg['vocal_reference'],'--output',str(folder/'stems'),
               '--threads',str(threads)]
    if 'model' in cfg['separation']:
        command += ['--model',cfg['separation']['model']]
    if 'overlap' in cfg['separation']:
        command += ['--overlap',str(cfg['separation']['overlap'])]
    if cfg['separation'].get('ensemble'):
        command.append('--ensemble')
    if cfg['separation'].get('keep_backing_vocals'):
        command.append('--keep-backing')
    return command


def separate(cfg,folder):
    if os.environ.get('KARAOKE_KEEP_MODELS')=='1':
        from separation_service import run
        run(separate_command(cfg,folder)[2:]);return
    process = RUNNING.pop(cfg['slug'],None)
    if process:
        print('Waiting for separation started in the background...',flush=True)
        if process.wait():
            raise ValueError(f'Background separation failed; see {folder/"separate.log"}')
        return
    subprocess.run(separate_command(cfg,folder),check=True)


def prefetch_separation(job):
    """Start Demucs for the next song while the current one transcribes (parallel queue)."""
    try:
        cfg,folder = job_context(job)
    except ValueError:
        return
    if cfg['slug'] in RUNNING or (folder/'stems/separation.json').exists():
        return
    try:
        log = (folder/'separate.log').open('w',encoding='utf-8')
        RUNNING[cfg['slug']] = subprocess.Popen(separate_command(cfg,folder),stdout=log,stderr=subprocess.STDOUT)
        print(f"{job['slug']}: separation started in the background",flush=True)
    except ValueError:
        pass


def verify_stems(cfg,folder):
    # A file-based bridge can reuse verified stems without copying large WAVs.
    stems = Path(cfg.get('stems_dir',folder/'stems'))
    report = read(stems/'separation.json')
    if report.get('is_intermediate'):raise ValueError('Isolated model component is not a complete separation')
    if report['is_excerpt'] or report['settings']['source_sha256'] != digest(cfg['vocal_reference']):
        raise ValueError('Stems are an excerpt or belong to a different original')
    if not all(digest(stems/name)==sha for name,sha in report['files'].items()):
        raise ValueError('Separated audio changed since generation')
    return report


def transcribe(cfg,folder):
    from faster_whisper import WhisperModel
    verify_stems(cfg,folder)
    inputs = {key:digest(cfg[key]) for key in ('vocal_reference','zoom_video')}
    if (folder/'inputs.json').exists() and read(folder/'inputs.json') != inputs:
        raise ValueError('Input changed: use another job slug to preserve corrections')
    if (folder/'transcript.json').exists() and not (folder/'inputs.json').exists():
        raise ValueError('Untracked transcript; use a new job folder')
    save(folder/'inputs.json',inputs)
    if not (folder/'transcript.json').exists():
        device = best_device()
        from model_reuse import get
        model = get('asr',(cfg['transcription_model'],device,cfg.get('transcription_threads',0)),lambda:WhisperModel(cfg['transcription_model'],device=device,compute_type=whisper_compute_type(device),
                             cpu_threads=cfg.get('transcription_threads',0),
                             download_root=str(MODELS/'whisper'),
                             local_files_only=os.environ.get('KARAOKE_ALLOW_MODEL_DOWNLOAD','1')!='1'))
        language = None if cfg['language'] == 'auto' else cfg['language']
        # The isolated vocal stem has no instrumental for Whisper to "hear" words in,
        # so voice-activity filtering can safely skip the silent stretches.
        chunk_options={}
        if 'transcription_chunk_length' in cfg:
            length=cfg['transcription_chunk_length']
            if type(length) is not int or length<1:raise ValueError('transcription_chunk_length must be positive')
            chunk_options['chunk_length']=length
        recognizer=model
        if cfg.get('transcription_batch_size',1)>1:
            from faster_whisper import BatchedInferencePipeline
            recognizer=BatchedInferencePipeline(model=model)
            chunk_options['batch_size']=cfg['transcription_batch_size']
        segments,info = recognizer.transcribe(audio(cfg['align_audio']),language=language,
                                        beam_size=5,vad_filter=True,condition_on_previous_text=False,
                                        word_timestamps=True,**chunk_options)
        records = []
        for segment in segments:
            records.append({'start':segment.start,'end':segment.end,'text':segment.text,
                            'words':[{'word':w.word,'start':w.start,'end':w.end} for w in segment.words or []]})
            print(segment.text,flush=True)
        if not records:
            raise ValueError('No transcript detected')
        if language is None:
            save(folder/'language.json',{'language':info.language,'probability':info.language_probability})
            print(f'Detected language: {info.language} ({info.language_probability:.0%})',flush=True)
            cfg['language'] = info.language
            cfg['language_label'] = LABELS.get(info.language, cfg['language_label'])
        # Whisper's own words stay available as timing anchors for imported lyrics.
        save(folder/'transcript.whisper.json',records)
        save(folder/'transcript.json',[{k:r[k] for k in ('start','end','text')} for r in records])
    if not (folder/'sync.json').exists():
        # Demucs preserves sample count/timeline; unlike Zoom covers, no musical
        # matching assumption is needed. Final decoded-audio check still applies.
        seconds = len(audio(cfg['vocal_reference']))/16000
        save(folder/'sync.json',{'anchors':[[0,0],[seconds,seconds]],
                                'basis':'same source timeline; separation length checked'})


def transcript_identity(cfg,folder):
    return {'transcript':digest(folder/'transcript.json'),
            'source':digest(cfg['vocal_reference'])}


def require_transcript_review(cfg,folder):
    if not (folder/'transcript-review.json').exists():
        raise ValueError('Review/correct transcript.json, then run accept-transcript --confirm-lyrics')
    if read(folder/'transcript-review.json') != transcript_identity(cfg,folder):
        raise ValueError('Transcript changed since lyric review; review again')


def backup_transcript(folder):
    """Keep every replaced transcript so lyric edits can be undone with `restore`."""
    if (folder/'transcript.json').exists():
        history = folder/'history'
        history.mkdir(exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        # Windows clock ticks can repeat even with %f. Never overwrite history.
        destination = history/f'transcript-{stamp}-{uuid4().hex[:12]}.json'
        with (folder/'transcript.json').open('rb') as source, destination.open('xb') as target:
            shutil.copyfileobj(source,target)


def import_lyrics(cfg,folder,path,confirmed):
    """Replace the transcript text with the user's lyrics, keeping Whisper's timing."""
    path = Path(path)
    if not path.is_absolute():
        path = ROOT/path
    lines,parts = split_parts(parse_lyrics(path.read_text(encoding='utf-8-sig')))
    heard = folder/'transcript.whisper.json'
    if not heard.exists():
        heard = folder/'transcript.json'
    if not heard.exists():
        raise ValueError('Run transcribe first: its word timings anchor the lyrics')
    duration = verify_stems(cfg,folder)['duration']
    segments,report = place_lines(lines, segment_words(read(heard)), duration)
    for segment,part in zip(segments,parts):
        if part:
            segment['part'] = part
    backup_transcript(folder)
    save(folder/'transcript.json',segments)
    save(folder/'lyrics-import.json',{**report,'lyrics_file':str(path),'lyrics_sha256':digest(path)})
    print(f"{report['anchored_lines']}/{report['lines']} lines anchored, "
          f"{report['matched_word_ratio']:.0%} of words matched Whisper",flush=True)
    if report['matched_word_ratio'] < .4:
        print('Warning: weak match; check the song/lyrics pairing and line timings in transcript.json',flush=True)
    if confirmed:
        save(folder/'transcript-review.json',transcript_identity(cfg,folder))


def history(folder):
    versions = sorted((folder/'history').glob('transcript-*.json')) if (folder/'history').exists() else []
    for version in versions:
        print(version.stem.removeprefix('transcript-'), len(read(version)), 'lines')
    return versions


def restore(cfg,folder,version):
    source = folder/'history'/f'transcript-{version}.json'
    if not version or not source.is_file():
        raise ValueError('Unknown --version; run the history stage to list versions')
    backup_transcript(folder)
    shutil.copy2(source, folder/'transcript.json')
    print('Restored',version,'- review it, then accept-transcript --confirm-lyrics',flush=True)


PROMPT_FILE = ROOT/'config/translation_prompt.txt'


def translate_song(cfg,folder,target,engine='llm',style='natural',glossary=None,quality='best',instructions=''):
    """Translate each aligned lyric line; the result is a draft to correct and accept."""
    require_language(cfg)
    if not target:
        raise ValueError('translate needs --to LANG or a "translation" block in the manifest')
    if engine not in ENGINES:
        raise ValueError(f'engine must be one of {ENGINES}')
    if not (folder/'aligned.json').exists():
        raise ValueError('Run align first: translations reuse the aligned line timing')
    lines = lines_from_aligned(read(folder/'aligned.json'))
    source_texts = [l['text'] for l in lines]
    memory = load_memory(ROOT,cfg['language'],target)
    notes, brief = ['']*len(lines), ''
    if engine == 'llm':
        # Project-wide house style first, then this song's own instructions.
        house = PROMPT_FILE.read_text(encoding='utf-8').strip() if PROMPT_FILE.exists() else ''
        texts,notes,brief = translate_llm(source_texts,cfg['language'],target,style,glossary,
                                          quality=quality,instructions=' '.join(filter(None,[house,instructions])),
                                          memory=memory,progress=lambda m: print(m,flush=True))
        models = [os.environ.get('LLM_MODEL',LLM_MODEL)+' @ '+os.environ.get('LLM_URL',LLM_URL)]
    else:
        models = model_chain(cfg['language'],target,hub_model_exists)
        texts = translate(source_texts,models,best_device())
        texts = [memory.get(s,t) for s,t in zip(source_texts,texts)]
    if (folder/'translation.json').exists():
        history_dir = folder/'history'; history_dir.mkdir(exist_ok=True)
        shutil.copy2(folder/'translation.json',history_dir/f"translation-{datetime.now():%Y%m%d-%H%M%S-%f}.json")
    entries = []
    for l,t,n in zip(lines,texts,notes):
        entry = {**l,'translation':t}
        if l['text'] in memory:
            entry['from_memory'] = True
        if n:
            entry['check'] = n  # reviewer hint; remove once the line is fixed
        entries.append(entry)
    save(folder/'translation.json',{'from':cfg['language'],'to':target,'engine':engine,'style':style,
        'quality':quality if engine=='llm' else 'line-by-line','models':models,'glossary':glossary or {},
        'instructions':instructions,'brief':brief,'lines':entries})
    for e in entries:
        print(f"{e['text']}  ->  {e['translation']}"+(f"   [check: {e['check']}]" if 'check' in e else ''),flush=True)
    flagged = sum('check' in e for e in entries)
    print(f"{flagged} of {len(entries)} lines flagged for checking; {sum('from_memory' in e for e in entries)} "
          'reused from translation memory.',flush=True)
    print('Correct "translation" values in translation.json, then accept-translation --confirm-translation',flush=True)


def accept_translation(folder):
    """Lock the reviewed translation and teach the translation memory."""
    data = read(folder/'translation.json')
    save(folder/'translation-review.json',translation_identity(folder))
    add_to_memory(ROOT,data['from'],data['to'],[(l['text'],l['translation']) for l in data['lines']])


def translation_identity(folder):
    return {'translation':digest(folder/'translation.json'),'aligned':digest(folder/'aligned.json')}


def require_translation_review(cfg,folder):
    if not cfg.get('translation'):
        return
    if not (folder/'translation.json').exists():
        raise ValueError('Song has a translation block: run translate first')
    data = read(folder/'translation.json')
    if data['to'] != cfg['translation']['to']:
        raise ValueError(f"translation.json is {data['to']}, manifest wants {cfg['translation']['to']}; translate again")
    if not (folder/'translation-review.json').exists() or \
            read(folder/'translation-review.json') != translation_identity(folder):
        raise ValueError('Review translation.json, then accept-translation --confirm-translation')


def audit(cfg,folder):
    verify_stems(cfg,folder)
    result = compare(cfg['vocal_reference'],cfg['zoom_video'],folder/'stems/vocals.wav')
    result['input_hashes'] = {key:digest(cfg[key]) for key in ('vocal_reference','zoom_video')}
    save(folder/'audio-audit.json',result)
    return result


def approve(cfg,folder,confirmed):
    if not confirmed:
        raise ValueError('Full listening/lyric review required: --confirm-listened')
    reviewed_ass(cfg,folder)
    result = read(folder/'preview-validation.json')
    if result['fingerprint'] != fingerprint(cfg,folder) or digest(result['output']) != result['sha256']:
        raise ValueError('Preview is stale or changed')
    report = audit(cfg,folder)
    save(folder/'approval.json',{'fingerprint':fingerprint(cfg,folder),
        'review':'user_confirmed_entire_preview_including_flagged_quiet_sections',
        'audio_audit_sha256':digest(folder/'audio-audit.json')})


def check_timing(cfg,folder):
    """Flag suspicious word timings right after alignment (saved to timing-report.json)."""
    report = timing_report(read(folder/'aligned.json'), audio(cfg['align_audio']))
    save(folder/'timing-report.json',report)
    print(f"Timing check: {len(report['issues'])} issue(s) in {report['words']} words (score {report['score']:.0%})",flush=True)
    for issue in report['issues'][:15]:
        print(f"  line {issue['line']} '{issue['word']}' at {issue.get('time','?')}s: {issue['problem']}",flush=True)
    if len(report['issues']) > 15:
        print(f"  ... see {folder/'timing-report.json'}",flush=True)


def make_extras(cfg,folder):
    """LRC, thumbnail and teaser next to the approved final video."""
    if not (folder/'validation.json').exists():
        raise ValueError('Render the approved final first')
    validation = read(folder/'validation.json')
    if digest(validation['output']) != validation['sha256']:
        raise ValueError('Final video changed since rendering')
    segments = read(folder/'aligned.json')
    options = validation.get('render_options', {})
    outputs = exports.write_extras(FFMPEG,validation['output'],segments,cfg['title'],cfg['artist'],
        offset=options.get('intro_seconds',3), start=options.get('start') or 0, end=options.get('end'))
    save(folder/'extras.json',outputs)
    for kind,path in outputs.items():
        print(kind,path,flush=True)


def edit_timing(cfg,folder,args):
    """Backend lyric/timing editor on aligned.json, with history, validation and re-check."""
    path = folder/'aligned.json'
    if not path.exists():
        raise ValueError('Run align first')
    if args.show:
        print(lyric_editor.show(read(path),args.line),flush=True)
        return
    history_dir = folder/'history'
    if args.undo:
        versions = sorted(history_dir.glob('aligned-*.json')) if history_dir.exists() else []
        if not versions:
            raise ValueError('No earlier aligned.json version to undo to')
        shutil.copy2(versions[-1],path)
        versions[-1].unlink()  # undo is a stack: repeat to step further back
        print('Undone: restored',versions[-1].stem.removeprefix('aligned-'),flush=True)
        check_timing(cfg,folder)
        return
    segments = read(path)
    if args.insert_after is not None:
        if args.text is None or args.start is None or args.end is None:
            raise ValueError('--insert-after needs --text, --start and --end')
        segments = lyric_editor.insert(segments,args.insert_after,args.text,args.start,args.end)
    elif args.style or args.style_clear:
        # No --line: the style applies to every line (Karadeo's "all lines" scope).
        segments = lyric_editor.set_style(segments,lyric_editor.parse_style(args.style or []),
                                          args.line,args.until,clear=args.style_clear)
    elif args.snap_beats:
        from beats import detect_beats
        bpm,beat_times = detect_beats(audio(cfg['zoom_video']),subdivision=args.subdivision)
        save(folder/'beats.json',{'bpm':bpm,'subdivision':args.subdivision,'beats':beat_times})
        segments,moved = lyric_editor.snap_to_beats(segments,beat_times,args.line,args.until,args.tolerance)
        print(f'Tempo {bpm:.1f} BPM; {moved} line(s) moved onto the beat',flush=True)
    elif args.text is not None:
        segments = lyric_editor.set_text(segments,args.line,args.text)
    elif args.split_at:
        segments = lyric_editor.split(segments,args.line,args.split_at)
    elif args.merge:
        segments = lyric_editor.merge(segments,args.line)
    elif args.delete:
        segments = lyric_editor.delete(segments,args.line)
    elif args.part is not None:
        segments = lyric_editor.set_part(segments,args.line,args.part,args.until)
    elif args.word and (args.start is not None or args.end is not None):
        segments = lyric_editor.set_word(segments,args.line,args.word,args.start,args.end)
    elif args.line and args.start is not None and args.end is not None:
        segments = lyric_editor.stretch(segments,args.line,args.start,args.end)
    elif args.shift is not None:
        segments = lyric_editor.shift(segments,args.shift,args.line,args.until)
    else:
        raise ValueError('edit needs --show, --undo, --text, --shift, --start/--end, --split-at, --merge, '
                         '--delete, --part, --insert-after, --style, --style-clear or --snap-beats')
    needs_line = (args.text is not None and args.insert_after is None) or args.split_at or args.merge or args.delete or args.part is not None or args.word
    if needs_line and not args.line:
        raise ValueError('This edit needs --line N (see edit --show)')
    lyric_editor.validate(segments,verify_stems(cfg,folder)['duration'])
    history_dir.mkdir(exist_ok=True)
    shutil.copy2(path,history_dir/f"aligned-{datetime.now():%Y%m%d-%H%M%S-%f}.json")
    save(path,segments)
    print(lyric_editor.show(segments,args.line) if args.line else f'{len(segments)} lines updated',flush=True)
    check_timing(cfg,folder)
    print('Edited timing makes earlier previews/approvals stale: run clip, then preview again.',flush=True)


def layer_values(pairs):
    """['x=960','bold=true','crop=0,0,10,0','text=Hi there'] -> typed dict."""
    values = {}
    for pair in pairs or []:
        key,sep,raw = pair.partition('=')
        if not sep:
            raise ValueError(f'Expected key=value, got "{pair}"')
        key = key.strip().replace('color','colour')
        if raw.lower() in ('true','false'):
            values[key] = raw.lower()=='true'
        elif ',' in raw and key=='crop':
            values[key] = [float(v) for v in raw.split(',')]
        else:
            try:
                values[key] = float(raw)
            except ValueError:
                values[key] = raw
    return values


def layer_command(cfg,folder,args):
    """Edit layers.json: text overlays, media layers, audio tracks, backing level, keyframes."""
    path = folder/'layers.json'
    data = {**layer_tools.empty(),**read(path)} if path.exists() else layer_tools.empty()
    if args.list:
        print(layer_tools.describe(data),flush=True)
        return
    values = layer_values(args.values)
    for key in ('start','end'):
        if getattr(args,key) is not None:
            values[key] = getattr(args,key)
    if args.add_text:
        data = layer_tools.add(data,'texts',{'text':args.add_text,'start':0,**values})
    elif args.add_media:
        data = layer_tools.add(data,'media',{'file':relative(args.add_media),'start':0,**values})
    elif args.add_audio:
        data = layer_tools.add(data,'audio',{'file':relative(args.add_audio),'start':0,**values})
    elif args.backing_db is not None or args.mute_backing:
        backing = dict(data.get('backing',{}))
        if args.backing_db is not None:
            backing['volume_db'] = args.backing_db
        if args.mute_backing:
            backing['mute'] = args.mute_backing=='on'
        data['backing'] = backing
    elif args.item:
        kind,_,number = args.item.partition(':')
        if kind not in ('texts','media','audio') or not number.isdigit():
            raise ValueError('--item must look like texts:1, media:2 or audio:1')
        if args.remove:
            data = layer_tools.remove(data,kind,int(number))
        elif args.keyframe is not None:
            data = layer_tools.add_keyframe(data,kind,int(number),{'t':args.keyframe,**values})
        elif values:
            data = layer_tools.update(data,kind,int(number),values)
        else:
            raise ValueError('With --item use --remove, --keyframe T --values ..., or --values to change it')
    else:
        raise ValueError('layer needs --list, --add-text, --add-media, --add-audio, --item, --backing-db or --mute-backing')
    layer_tools.validate(data,ROOT)
    if path.exists():
        history_dir = folder/'history'; history_dir.mkdir(exist_ok=True)
        shutil.copy2(path,history_dir/f"layers-{datetime.now():%Y%m%d-%H%M%S-%f}.json")
    save(path,data)
    print(layer_tools.describe(data),flush=True)
    print('Layers changed: run clip or preview again (earlier approvals are stale).',flush=True)


def render_clip(cfg,folder,line,seconds):
    """A few seconds around one line, for checking an edit without a full preview."""
    from zoom_local_pipeline import run_renderer
    segments = read(folder/'aligned.json')
    segment = segments[(line or 1)-1]
    intro = 3.0
    start = max(0.0,segment['words'][0]['start']+intro-seconds)
    end = segment['words'][-1]['end']+intro+seconds
    (folder/'lyrics.ass').write_text(reviewed_ass(cfg,folder),encoding='utf-8')
    clip_cfg = {**cfg,'render':{**cfg.get('render',{}),'start':round(start,2),'end':round(end,2),
                                 'preset':'veryfast'}}
    destination = folder/'clips'
    name = f"line{line or 1}-{datetime.now():%H%M%S}.mp4"
    run_renderer(clip_cfg,folder,destination,name)
    print(destination/name,flush=True)


def require_language(cfg):
    if cfg['language'] == 'auto':
        raise ValueError('Language not detected yet; run transcribe first')


def run_stage(stage,cfg,folder,args):
    if stage=='separate':
        separate(cfg,folder)
    elif stage=='audit':
        audit(cfg,folder)
    elif stage=='transcribe':
        transcribe(cfg,folder)
    elif stage=='lyrics':
        if not args.file:
            raise ValueError('lyrics needs --file path/to/lyrics.txt (one sung line per row)')
        import_lyrics(cfg,folder,args.file,args.confirm_lyrics)
    elif stage=='align':
        require_language(cfg); verify_stems(cfg,folder); require_transcript_review(cfg,folder); align(cfg,folder)
        check_timing(cfg,folder)
    elif stage=='check-timing':
        check_timing(cfg,folder)
    elif stage=='edit':
        edit_timing(cfg,folder,args)
    elif stage=='clip':
        render_clip(cfg,folder,args.line,args.window)
    elif stage=='layer':
        layer_command(cfg,folder,args)
    elif stage=='extras':
        make_extras(cfg,folder)
    elif stage=='accept-transcript':
        if not args.confirm_lyrics:
            raise ValueError('Correct and review lyrics before --confirm-lyrics')
        save(folder/'transcript-review.json',transcript_identity(cfg,folder))
    elif stage=='history':
        history(folder)
    elif stage=='restore':
        restore(cfg,folder,args.version)
    elif stage=='translate':
        settings = cfg.get('translation',{})
        translate_song(cfg,folder,args.to or settings.get('to'),
                       args.engine or settings.get('engine','llm'),
                       args.translation_style or settings.get('style','natural'),
                       settings.get('glossary'),
                       args.quality or settings.get('quality','best'),
                       settings.get('instructions',''))
    elif stage=='accept-translation':
        if not args.confirm_translation:
            raise ValueError('Correct and review translation.json before --confirm-translation')
        accept_translation(folder)
    elif stage=='preview':
        require_language(cfg); require_translation_review(cfg,folder); audit(cfg,folder); render(cfg,folder,preview=True)
    elif stage=='approve':
        require_translation_review(cfg,folder); approve(cfg,folder,args.confirm_listened)
    elif stage=='render':
        verify_stems(cfg,folder); require_translation_review(cfg,folder); render(cfg,folder)


def draft_stages(job,folder):
    """Automatic part of a song: stops for lyric review unless lyrics are already confirmed."""
    stages = ['separate','audit','transcribe']
    if job.get('lyrics') and not (folder/'transcript-review.json').exists():
        stages.append('lyrics')
    return stages


def slugify(text):
    text = text.translate(str.maketrans({'æ':'ae','Æ':'AE','ø':'oe','Ø':'OE','å':'aa','Å':'AA'}))
    text = unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode()
    return re.sub(r'_+','_',re.sub(r'[^A-Za-z0-9]+','_',text)).strip('_')


def relative(path):
    """Project-relative manifest path; relative input is read from the project root."""
    path = Path(path)
    path = (path if path.is_absolute() else ROOT/path).resolve()
    if not path.is_file():
        raise ValueError(f'File not found: {path}')
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        raise ValueError(f'Copy the file into the project first: {path}')


def add_job(args):
    jobs = read(MANIFEST) if MANIFEST.exists() else []
    if not (args.source and args.title and args.artist):
        raise ValueError('add needs --source, --title and --artist')
    slug = args.slug or slugify(args.title)
    if not slug or not slug.replace('_','').isalnum():
        raise ValueError('Give a --slug using letters, digits and underscores')
    if any(j['slug']==slug for j in jobs):
        raise ValueError(f'Song slug already exists: {slug}')
    background = args.background or (jobs[0]['background'] if jobs else None)
    if not background:
        raise ValueError('add needs --background for the first song')
    job = {'slug':slug,'title':args.title,'artist':args.artist,'source':relative(args.source),
           'language':args.language,'background':relative(background)}
    if args.language_label:
        job['language_label'] = args.language_label
    if args.file:
        job['lyrics'] = relative(args.file)
    render_block = {k:v for k,v in (('template',args.template),('canvas',args.canvas),
                    ('guide_vocal_level',args.guide_vocal),('pitch_semitones',args.pitch)) if v is not None}
    if render_block:
        job['render'] = render_block
        render_options({'render':render_block,'guide_vocal':'stems/vocals.wav'})
    jobs.append(job)
    save(MANIFEST,jobs)
    print('Added',slug)


def doctor():
    """Check everything a run needs without loading any model. Returns problem count."""
    from zoom_local_pipeline import LOGO
    problems = []
    def check(ok, label, fix=''):
        print(('OK      ' if ok else 'MISSING ')+label+('' if ok or not fix else f'  ->  {fix}'))
        if not ok: problems.append(label)
    check(FFMPEG.is_file(), f'FFmpeg {FFMPEG}')
    check(LOGO.is_file(), f'Logo {LOGO}')
    check(DEMUCSPY.is_file(), 'Demucs environment .venv-demucs', 'run setup.ps1')
    check(python_in(ROOT/'.venv-zoom').is_file(), 'Whisper environment .venv-zoom', 'run setup.py')
    for template in sorted((ROOT/'config/templates').glob('*.json')):
        try:
            read(template)['lines_per_page']; check(True, f'Template {template.stem}')
        except (KeyError, ValueError) as exc:
            check(False, f'Template {template.stem}: {exc}')
    jobs = read(MANIFEST) if MANIFEST.exists() else []
    check(bool(jobs), f'Songs in {MANIFEST.name}', 'use the add stage')
    for job in jobs:
        try:
            job_context(job)
            for key in ('background','lyrics'):
                if job.get(key) and not (ROOT/job[key]).is_file():
                    raise ValueError(f'{key} missing: {job[key]}')
            check(True, f"Song {job['slug']}")
        except (KeyError, ValueError) as exc:
            check(False, f"Song {job.get('slug','?')}: {exc}")
    if any((j.get('translation') or {}).get('engine','llm')=='llm' for j in jobs if j.get('translation')):
        import urllib.request
        url = os.environ.get('LLM_URL',LLM_URL)
        try:
            urllib.request.urlopen(url.split('/v1/')[0],timeout=3); reachable = True
        except OSError:
            reachable = False
        check(reachable, f'LLM translation server {url}',
              f"install Ollama, run: ollama pull {os.environ.get('LLM_MODEL',LLM_MODEL)}")
    print(f"Device: {best_device()} (set KARAOKE_DEVICE=cpu|cuda to override)")
    return len(problems)


def build_parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['doctor','status','add','separate','audit','transcribe','lyrics','accept-transcript',
                                    'history','restore','align','check-timing','edit','clip','layer',
                                    'translate','accept-translation',
                                    'preview','approve','render','extras','draft'])
    p.add_argument('--song',help='Manifest slug; omitted means all jobs in order (a queue)')
    p.add_argument('--confirm-listened',action='store_true')
    p.add_argument('--confirm-lyrics',action='store_true')
    p.add_argument('--file',help='Lyrics .txt for the lyrics/add stages')
    p.add_argument('--version',help='History version for restore')
    p.add_argument('--to',help='Target language for translate, e.g. da or en')
    p.add_argument('--confirm-translation',action='store_true')
    p.add_argument('--engine',choices=['llm','opus'],help='llm: whole-song AI translation (default); opus: fast MarianMT')
    p.add_argument('--translation-style',choices=['natural','singable','literal'],help='Translation style; --style is for lyric formatting')
    p.add_argument('--quality',choices=['best','fast'],help='best: 5-pass brief/draft/edit/shorten/check (default); fast: one pass')
    e=p.add_argument_group('edit / clip (line and word numbers from edit --show)')
    e.add_argument('--show',action='store_true'); e.add_argument('--undo',action='store_true')
    e.add_argument('--line',type=int); e.add_argument('--until',type=int,help='Last line of a range')
    e.add_argument('--word',type=int); e.add_argument('--text')
    e.add_argument('--shift',type=float,help='Seconds; whole song when --line is omitted')
    e.add_argument('--start',type=float); e.add_argument('--end',type=float)
    e.add_argument('--split-at',type=int,help='Word where the new line starts')
    e.add_argument('--merge',action='store_true',help='Join --line with the next line')
    e.add_argument('--delete',action='store_true'); e.add_argument('--part',help='M/F/D, or "" to clear')
    e.add_argument('--window',type=float,default=3.0,help='clip: seconds before/after the line')
    e.add_argument('--insert-after',type=int,help='New line after this line (0 = first); needs --text --start --end')
    e.add_argument('--style',nargs='+',metavar='KEY=VALUE',
                   help='Per-line style, e.g. size=90 colour=#FFFFFF highlight_colour=#FF0000 x=960 y=300; '
                        'no --line = all lines')
    e.add_argument('--style-clear',action='store_true')
    e.add_argument('--snap-beats',action='store_true',help='Move line starts onto the nearest beat')
    e.add_argument('--subdivision',type=int,default=2,help='Beats per beat for snapping (2 = half-beats)')
    e.add_argument('--tolerance',type=float,default=0.12,help='Max seconds a line may move when snapping')
    l=p.add_argument_group('layer (text overlays, media, audio tracks; see tools/layers.py)')
    l.add_argument('--list',action='store_true')
    l.add_argument('--add-text'); l.add_argument('--add-media'); l.add_argument('--add-audio')
    l.add_argument('--item',help='kind:number, e.g. texts:1, media:2, audio:1')
    l.add_argument('--remove',action='store_true'); l.add_argument('--keyframe',type=float,metavar='T',
                   help='Keyframe at T seconds from the item start (with --values x= y= scale= ...)')
    l.add_argument('--values',nargs='+',metavar='KEY=VALUE',help='Layer properties, e.g. x=960 y=200 size=80')
    l.add_argument('--backing-db',type=float); l.add_argument('--mute-backing',choices=['on','off'])
    a=p.add_argument_group('add')
    a.add_argument('--source'); a.add_argument('--title'); a.add_argument('--artist')
    a.add_argument('--slug'); a.add_argument('--background')
    a.add_argument('--language',default='auto',help="ISO code such as da/en, or auto")
    a.add_argument('--language-label')
    a.add_argument('--template'); a.add_argument('--canvas')
    a.add_argument('--guide-vocal',type=float); a.add_argument('--pitch',type=float)
    return p


def main():
    args=build_parser().parse_args()
    os.environ['PATH']=str(FFMPEG.parent)+os.pathsep+os.environ.get('PATH','')
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    if args.stage=='doctor':
        sys.exit(1 if doctor() else 0)
    if args.stage=='add':
        try:
            add_job(args)
        except ValueError as exc:
            sys.exit(str(exc))
        return
    jobs=read(MANIFEST)
    if args.song:
        jobs=[j for j in jobs if j['slug']==args.song]
        if not jobs: p.error('Unknown song slug')
    failed=False
    for index,job in enumerate(jobs):
        if args.stage=='draft' and index+1 < len(jobs):
            # Parallel queue: Demucs for the next song runs while this one transcribes.
            prefetch_separation(jobs[index+1])
        try:
            cfg,folder=job_context(job)
        except ValueError as exc:
            print(job['slug'],'skipped:',exc,flush=True)
            failed=True
            continue
        if args.stage=='status':
            print(job['slug'],{name:(folder/name).exists() for name in
                  ['stems/separation.json','audio-audit.json','transcript.json','transcript-review.json','aligned.json','preview-validation.json','approval.json','validation.json']})
            continue
        stages=draft_stages(job,folder) if args.stage=='draft' else [args.stage]
        while stages:
            stage=stages.pop(0)
            print(job['slug'],stage,flush=True)
            try:
                if stage=='lyrics' and args.stage=='draft':
                    # Lyrics named in the manifest are the user's reviewed text.
                    import_lyrics(cfg,folder,job['lyrics'],True)
                else:
                    run_stage(stage,cfg,folder,args)
                save(folder/'last-status.json',{'stage':stage,'status':'completed_not_quality_approved'})
            except Exception as exc:
                save(folder/'last-status.json',{'stage':stage,'status':'blocked','error':str(exc)})
                print(f'{stage} stopped: {exc}',flush=True)
                failed=True
                break
            if args.stage=='draft' and not stages and stage not in ('align','preview'):
                if (folder/'transcript-review.json').exists():
                    stages=['align','preview']
                else:
                    print(job['slug'],'draft ready: correct transcript.json (or run lyrics --file), '
                          'then accept-transcript --confirm-lyrics',flush=True)
    for process in RUNNING.values():
        process.wait()  # never leave a half-written separation behind
    if failed: sys.exit(1)


if __name__=='__main__': main()
