"""Ten-stage project workflow using the existing processing and rendering code.

New automated checks augment separation and final review; they never sign off lyrics.
"""
import argparse
from contextlib import contextmanager, ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from project_runtime import ROOT, FFMPEG, LOGO, WORK, OUT, MODELS, DEMUCSPY, child_env, font_file
from zoom_local_pipeline import read, save, digest, fingerprint, render, render_options
import local_karaoke as local
from audio_quality import settings as quality_settings
import separation_guard

STAGES = ['run', 'doctor', 'status', 'separate', 'audio-qc', 'transcribe', 'lyrics-review', 'quick-preview',
          'align', 'preview', 'approve', 'render', 'extras', 'edit', 'clip', 'layer',
          'translate', 'accept-translation', 'lyrics', 'history', 'restore', 'check-timing', 'cleanup']
ADVANCED = {'edit','clip','layer','translate','accept-translation','lyrics','history','restore','check-timing'}


class ReviewRequired(ValueError): pass


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalize(job, base=ROOT):
    if not isinstance(job,dict): raise ValueError('Each job must be a JSON object')
    allowed = {'source','title','artist','language','mode','background','lyrics','transcription_model','alignment_model',
               'transcription_chunk_length','transcription_batch_size',
               'render','audio_quality','separation','screen_profile','aligned','layers','translation','profile'}
    if set(job)-allowed: raise ValueError('Unknown job fields: '+str(sorted(set(job)-allowed)))
    j = {'language':'auto','mode':'music','background':'original','transcription_model':'large-v3-turbo',**job}
    if j.get('profile') not in (None,'optimized'):
        raise ValueError('Unknown processing profile')
    if j.get('profile')=='optimized':
        j['separation']={'model':'htdemucs','overlap':.25,**j.get('separation',{})}
        j['render']={'preset':'veryfast',**j.get('render',{})}
        j['audio_quality']={'alternatives':['htdemucs_ft'],**j.get('audio_quality',{})}
    j.setdefault('transcription_chunk_length',15)
    j.setdefault('alignment_model',None)
    if type(j.get('transcription_batch_size',1)) is not int or not 1<=j.get('transcription_batch_size',1)<=32:
        raise ValueError('transcription_batch_size must be 1..32')
    for key in ['source','title','artist']:
        if not isinstance(j.get(key), str) or not j[key].strip(): raise ValueError(key+' is required')
    if any(c in j[k] for k in ['title','artist'] for c in '{}\\\r\n'):
        raise ValueError('Title/artist must not contain ASS markup or newlines')
    if type(j['transcription_chunk_length']) is not int or not 1<=j['transcription_chunk_length']<=30:
        raise ValueError('transcription_chunk_length must be 1..30')
    if j.get('screen_profile','white-blue') not in ['white-blue','blue-yellow']:
        raise ValueError('Unsupported Zoom screen profile')
    if j['mode'] not in ['music','zoom']: raise ValueError('mode must be music or zoom')
    if not re.fullmatch(r'auto|[a-z]{2,3}', j['language']): raise ValueError('Invalid language code')
    for key in ['source','lyrics','aligned','layers']:
        if j.get(key): j[key] = str((Path(base)/j[key]).resolve())
    if j['background'] != 'original': j['background'] = str((Path(base)/j['background']).resolve())
    if not Path(j['source']).is_file(): raise ValueError('Source not found: '+j['source'])
    for key in ['lyrics','aligned','layers']:
        if j.get(key) and not Path(j[key]).is_file(): raise ValueError('Missing '+key)
    if j['background'] != 'original' and not Path(j['background']).is_file():
        raise ValueError('Background not found')
    separation=j.get('separation',{})
    if not isinstance(separation,dict) or set(separation)-{'ensemble','keep_backing_vocals','model','overlap'}:
        raise ValueError('Unknown separation settings')
    if any(not isinstance(v,bool) for k,v in separation.items() if k in ('ensemble','keep_backing_vocals')):
        raise ValueError('Separation flags must be true/false')
    if separation.get('model','htdemucs_ft') not in ('htdemucs','htdemucs_ft'):
        raise ValueError('Unsupported separation model')
    overlap=separation.get('overlap',.5)
    import math
    if isinstance(overlap,bool) or not isinstance(overlap,(int,float)) or not math.isfinite(overlap) or not 0<overlap<1:
        raise ValueError('Separation overlap must be between zero and one')
    if separation.get('keep_backing_vocals'):
        raise ValueError('The clean-karaoke workflow removes all vocals. Use the legacy lead/backing workflow explicitly if required.')
    if j.get('translation'):
        tr=j['translation']
        if not isinstance(tr,dict) or tr.get('mode','below') not in ['below','only'] or not tr.get('to'):
            raise ValueError('Translation requires a target language and below/only mode')
        j['translation']={'mode':'below',**tr}
    if not isinstance(j.get('render',{}),dict): raise ValueError('render must be a JSON object')
    j['audio_quality'] = quality_settings(j.get('audio_quality'))
    j['render'] = {'intro_seconds':10.,'intro_countdown':True,'canvas':'1920x1080','fps':30,'crf':14,'preset':'fast',
                   'sync_background':j['background']=='original', **j.get('render',{})}
    r = j['render']
    allowed_render={'template','canvas','start','end','crf','preset','guide_vocal_level','pitch_semitones',
        'loudness_lufs','fade_in','fade_out','gap_countdown','motion','fps','intro_seconds','sync_background',
        'highlight_colour','intro_countdown','encoder','nvenc_cq','countdown_style','countdown_colour'}
    if set(r)-allowed_render: raise ValueError('Unknown render options: '+str(sorted(set(r)-allowed_render)))
    from intro_countdown import settings
    r.update(settings(r.get('countdown_style'),r.get('countdown_colour')))
    if r.get('highlight_colour') is not None and (
            not isinstance(r['highlight_colour'],str) or
            not re.fullmatch(r'#[0-9A-Fa-f]{6}',r['highlight_colour'])):
        raise ValueError('highlight_colour must be #RRGGBB')
    if r['fps'] not in [24,25,30,50,60] or isinstance(r['fps'],bool): raise ValueError('Unsupported fps')
    canvas = re.fullmatch(r'(\d{3,4})x(\d{3,4})', str(r['canvas']))
    if not canvas or any(int(x)%2 for x in canvas.groups()): raise ValueError('Canvas needs even WIDTHxHEIGHT')
    import math
    if not isinstance(r['intro_seconds'],(float,int)) or not math.isfinite(r['intro_seconds']) or not 0 <= r['intro_seconds'] <= 60:
        raise ValueError('Intro duration must be 0..60 seconds')
    if type(r['crf']) is not int or not 0 <= r['crf'] <= 51: raise ValueError('CRF must be 0..51')
    if r['preset'] not in ['veryfast','faster','fast','medium','slow']: raise ValueError('Unsupported encoder preset')
    if r.get('encoder','libx264') not in ['libx264','h264_nvenc']: raise ValueError('Unsupported encoder')
    if type(r.get('nvenc_cq',19)) is not int or not 0 <= r.get('nvenc_cq',19) <= 51: raise ValueError('NVENC CQ must be 0..51')
    if not isinstance(r['sync_background'],bool): raise ValueError('sync_background must be true/false')
    if not isinstance(r['intro_countdown'],bool): raise ValueError('intro_countdown must be true/false')
    j['source_sha256'] = digest(j['source'])
    j['imports'] = {k:digest(j[k]) for k in ['lyrics','aligned','layers'] if j.get(k)}
    name = local.slugify(j['title'])[:60] or 'Song'
    data_identity={k:j[k] for k in ['source','source_sha256','title','artist','language','mode',
                   'transcription_model','alignment_model','transcription_chunk_length','audio_quality','imports']}
    data_identity['separation']=j.get('separation',{})
    if 'transcription_batch_size' in j:data_identity['transcription_batch_size']=j['transcription_batch_size']
    data_identity['screen_profile']=j.get('screen_profile','white-blue')
    return j, WORK/(name+'-'+identity(data_identity)[:12])


@contextmanager
def lock(folder):
    folder.mkdir(parents=True, exist_ok=True); path = folder/'running.lock'
    try:
        with path.open('x') as f: f.write(str(os.getpid()))
    except FileExistsError:
        raise ValueError('Job is locked. Check the recorded PID before removing a stale lock: '+str(path))
    try: yield
    finally: path.unlink()


def context(job, folder, strict_quality=True):
    # Existing local functions receive the same contract as before.
    cfg = {'slug':folder.name, 'title':job['title'], 'artist':job['artist'],
        'vocal_reference':job['source'], 'zoom_video':str(folder/'stems/instrumental.wav'),
        'align_audio':str(folder/'stems/vocals.wav'), 'stems_dir':str(folder/'stems'),
        'language':job['language'], 'language_label':'KARAOKE',
        'background':job['source'] if job['background']=='original' else job['background'],
        'transcription_model':job['transcription_model'], 'transcription_threads':job['audio_quality']['threads'],
        'separation_threads':job['audio_quality']['threads'],
        'transcription_chunk_length':job['transcription_chunk_length'],
        'transcription_batch_size':job.get('transcription_batch_size',1),
        'alignment_model':job.get('alignment_model'),
        'separation':job.get('separation',{}), 'render':job['render'],
        'preview_versions':True,
        'render_defaults':local.PRO_RENDER, 'guide_vocal':str(folder/'stems/vocals.wav'),
        'output_dir':str(OUT)}
    if (folder/'language.json').exists() and cfg['language']=='auto':
        cfg['language'] = read(folder/'language.json')['language']
    cfg['language_label']=local.LABELS.get(cfg['language'],'KARAOKE')
    if cfg['language']=='en' and not cfg['alignment_model']:
        cfg['alignment_model']='WAV2VEC2_ASR_LARGE_LV60K_960H'
    if job.get('translation'):
        cfg['translation'] = {**job['translation'], 'file':str(folder/'translation.json')}
        if (folder/'translation.json').exists(): cfg['translation']['sha256']=digest(folder/'translation.json')
    layer_file = folder/'layers.json'
    if job.get('layers') and not layer_file.exists(): save(layer_file,read(job['layers']))
    if layer_file.exists():
        import layers
        data = layers.validate(read(layer_file), ROOT)
        cfg['layers'] = {'file':str(layer_file), 'sha256':digest(layer_file),
            'media':{x['file']:digest(layers.resolve(x['file'],ROOT)) for x in data.get('media',[])+data.get('audio',[])},
            'changes_audio':bool(data.get('audio') or data.get('backing',{}).get('mute') or data.get('backing',{}).get('volume_db'))}
    if strict_quality and (folder/'audio-quality/selection.json').exists():
        report, _ = separation_guard.validate(job['source'], folder/'audio-quality')
        cfg['zoom_video'] = report['selected']['path']
        cfg['audio_quality_sha256'] = digest(folder/'audio-quality/selection.json')
    from branding_guard import resolved_background
    cfg['background']=resolved_background(cfg['background'],folder/'branding-background')
    plan=folder/'branding-background/inline-plan.json'
    if job.get('profile')=='optimized' and plan.exists() and read(plan)['source_sha256']==digest(cfg['background']):
        cfg['branding_plan']={'file':str(plan),'sha256':digest(plan)}
    parallel_result = folder/'parallel-background/result.json'
    if parallel_result.exists():
        prepared = read(parallel_result)
        original = job['source'] if job['background']=='original' else job['background']
        if prepared.get('source_sha256') == digest(original):
            cfg['background'] = prepared['background']
            if prepared.get('plan'):
                cfg['branding_plan']={'file':prepared['plan'],'sha256':digest(prepared['plan'])}
    return cfg


def preflight(job, folder):
    if digest(job['source']) != job['source_sha256']: raise ValueError('Source changed')
    import av
    with av.open(job['source']) as media:
        if not media.streams.audio: raise ValueError('Source needs an audio track')
        if not media.streams.video and (job['mode']=='zoom' or job['background']=='original'):
            raise ValueError('Audio-only inputs need music mode and a custom image/video background')
    marker = folder/'source-health.json'
    if marker.exists() and read(marker).get('source') == job['source_sha256']: return
    subprocess.run([str(FFMPEG), '-v','error','-xerror','-nostdin','-i',job['source'],
        '-map','0:v:0?','-map','0:a:0','-f','null','-'], check=True)
    save(marker, {'source':job['source_sha256'],'strict_decode':True})


def screen(job, folder):
    report = separation_guard.run(job['source'], folder/'stems/instrumental.wav',
        folder/'audio-quality', job['audio_quality'], job['language'])
    if not report['selected']:
        raise ReviewRequired('No usable instrumental candidate. Inspect audio-quality/review before continuing.')
    print('Audio selected:', report['selected']['name'], '; full listening review remains required.', flush=True)


def transcripts(job, folder, cfg):
    if job.get('aligned'):
        import lyric_editor
        segments=read(job['aligned']); lyric_editor.validate(segments)
        if cfg['language']=='auto': raise ReviewRequired('Specify language for imported word timings')
        if not (folder/'aligned.json').exists(): save(folder/'aligned.json',segments)
        if not (folder/'transcript.json').exists():
            save(folder/'transcript.json',[{'start':s['words'][0]['start'],'end':s['words'][-1]['end'],
                'text':' '.join(w['word'].strip() for w in s['words'])} for s in segments])
        from audio_quality import decode, RATE
        duration=len(decode(job['source']))/RATE
        save(folder/'sync.json',{'anchors':[[0,0],[duration,duration]]})
        save(folder/'inputs.json',{k:digest(cfg[k]) for k in ['vocal_reference','zoom_video']})
        return
    if job['mode']=='zoom':
        imported = folder/'zoom-import'
        subprocess.run([sys.executable, str(ROOT/'tools/zoom_import_job.py'), '--source',job['source'],
            '--output',str(imported),'--profile',job.get('screen_profile','white-blue')], check=True, env=child_env())
        segments = read(imported/'aligned.json')
        if not (folder/'transcript.json').exists():
            save(folder/'transcript.json', [{k:s[k] for k in ['start','end','text']} for s in segments])
        if not (folder/'aligned.json').exists(): save(folder/'aligned.json', segments)
        save(folder/'inputs.json', {k:digest(cfg[k]) for k in ['vocal_reference','zoom_video']})
        from audio_quality import decode, RATE
        duration = len(decode(job['source']))/RATE
        save(folder/'sync.json', {'anchors':[[0,0],[duration,duration]]})
        if cfg['language']=='auto':
            raise ReviewRequired('Zoom OCR does not detect spoken language. Set language in the job file.')
    else:
        local.transcribe(cfg, folder)
    if job.get('lyrics') and not (folder/'lyrics-import.json').exists():
        local.import_lyrics(cfg, folder, job['lyrics'], False)
    if job.get('aligned') and not (folder/'aligned.json').exists():
        save(folder/'aligned.json', read(job['aligned']))


def check_lyric_draft(folder):
    from asr_draft_quality import validate_asr_draft
    try:
        return validate_asr_draft({'segments':read(folder/'transcript.json')})
    except (ValueError,FileNotFoundError) as exc:
        raise ReviewRequired(str(exc)) from exc


def require_lyrics(cfg, folder):
    check_lyric_draft(folder)
    try:local.require_transcript_review(cfg, folder)
    except ValueError as exc:raise ReviewRequired(str(exc)) from exc


def verify_preview(cfg, folder, branding=True):
    validation = read(folder/'preview-validation.json')
    from output_size import MAX_BYTES
    if Path(validation['output']).stat().st_size > MAX_BYTES:
        raise ReviewRequired('Preview exceeds 150 MB. Re-render with the current size-limited renderer.')
    if validation['fingerprint'] != fingerprint(cfg, folder) or digest(validation['output']) != validation['sha256']:
        raise ReviewRequired('Preview changed. Render and review it again.')
    if branding:check_branding(validation['output'],folder/'branding-output.json')
    return validation


def check_branding(video,report):
    from branding_guard import scan,BrandingDetected
    try: return scan(video,report)
    except BrandingDetected as exc:raise ReviewRequired(str(exc)) from exc


def execute(stage, job, folder, args):
    from audio_cache import scope
    from stage_metrics import call
    with lock(folder), scope(folder/'decoded'), ExitStack() as workers:
        save(folder/'job.json', job)
        if stage == 'status':
            print(folder); print(read(folder/'state.json') if (folder/'state.json').exists() else 'new'); return
        call(folder,'preparation',preflight,job,folder)
        background_worker = None
        if stage == 'run' and getattr(args, 'parallel_stages', False):
            from parallel_background import BackgroundJob
            source = job['source'] if job['background']=='original' else job['background']
            background_worker = workers.enter_context(BackgroundJob(
                source, folder/'parallel-background', job.get('profile')=='optimized'))
        cfg = context(job, folder, strict_quality=stage not in ['run','audio-qc','separate'])
        if stage in ['run','separate']:
            call(folder,'separation',local.separate,cfg,folder)
            local.verify_stems(cfg, folder)
            if stage == 'separate': return
        if stage in ['run','audio-qc']:
            local.verify_stems(cfg, folder); call(folder,'audio_screening',screen,job,folder)
            cfg = context(job, folder)
            if stage == 'audio-qc': return
        if stage in ['run','transcribe']:
            separation_guard.validate(job['source'], folder/'audio-quality')
            call(folder,'transcription_or_import',transcripts,job,folder,cfg)
            cfg = context(job, folder)
            if stage == 'transcribe': return
        if stage == 'lyrics-review':
            if not args.checked_lyrics: raise ReviewRequired('Review transcript.json against the song, then use --checked-lyrics')
            check_lyric_draft(folder)
            save(folder/'transcript-review.json', local.transcript_identity(cfg, folder)); return
        if stage in ADVANCED:
            local.run_stage(stage, cfg, folder, args.advanced)
            return
        if getattr(args, 'draft_export', False):
            print('[DRAFT] Using unreviewed lyrics. No lyric/audio approval is recorded.', flush=True)
        else:
            require_lyrics(cfg, folder)
        if stage in ['run','align','quick-preview']:
            if job['mode']=='music' and not job.get('aligned'):
                wanted = {'transcript':digest(folder/'transcript.json'), 'vocals':digest(cfg['align_audio']),
                          'language':cfg['language'], 'model':cfg['alignment_model'],
                          'code':digest(ROOT/'tools/zoom_local_pipeline.py')}
                if not (folder/'align-stage.json').exists() or read(folder/'align-stage.json') != wanted:
                    if (folder/'aligned.json').exists():
                        history=folder/'history'; history.mkdir(exist_ok=True)
                        backup=history/('aligned-before-realign-'+digest(folder/'aligned.json')[:12]+'.json')
                        if not backup.exists(): shutil.copy2(folder/'aligned.json',backup)
                    call(folder,'alignment',local.align,cfg,folder); save(folder/'align-stage.json', wanted)
            else:
                import lyric_editor
                segments = read(folder/'aligned.json')
                lyric_editor.validate(segments)
                words = lambda rows: ''.join(c.casefold() for row in rows for c in row.get('text','') if c.isalnum())
                if words(segments) != words(read(folder/'transcript.json')):
                    raise ReviewRequired('Edited lyrics differ from imported timing. Correct aligned.json or use music mode to realign.')
                save(folder/'alignment-inputs.json', {'transcript':digest(folder/'transcript.json'),
                    'vocal_reference':digest(cfg['vocal_reference'])})
            local.check_timing(cfg, folder)
            if stage == 'align': return
        if stage=='quick-preview':
            from quick_preview import create
            print('QUICK PREVIEW:',create(cfg,folder,args.preview_start,args.preview_seconds),flush=True)
            print('Short review clip only; full-quality preview and approval are still required.',flush=True)
            return
        if stage in ['run','preview']:
            # Audit original source/background, not just our added metadata.
            # A source hit blocks rendering until the background is cleaned.
            from branding_guard import prepare_background,BrandingDetected
            original_background=job['source'] if job['background']=='original' else job['background']
            try:
                if background_worker is not None:
                    prepared = background_worker.result()
                    cfg['background'] = prepared['background']
                    if prepared['plan']:
                        cfg['branding_plan'] = {'file':prepared['plan'],'sha256':digest(prepared['plan'])}
                elif job.get('profile')=='optimized':
                    from inline_branding import prepare
                    cfg['background'],plan=prepare(original_background,folder/'branding-background')
                    if plan:cfg['branding_plan']={'file':str(plan),'sha256':digest(plan)}
                else:cfg['background']=prepare_background(original_background,folder/'branding-background')
            except BrandingDetected as exc:raise ReviewRequired(str(exc)) from exc
            from fontTools.ttLib import TTFont
            font = TTFont(font_file()); glyphs = font.getBestCmap(); font.close()
            texts = [job['title'],job['artist']] + [s.get('text','') for s in read(folder/'aligned.json')]
            missing = sorted({c for text in texts for c in text if not c.isspace() and ord(c) not in glyphs})
            if missing: raise ReviewRequired('Set KARAOKE_FONT to a font containing these characters: '+''.join(missing))
            local.require_translation_review(cfg, folder)
            local.audit(cfg, folder)
            if (folder/'preview-validation.json').exists():
                try: verify_preview(cfg, folder, branding=False)
                except ReviewRequired: call(folder,'render',render,cfg,folder,preview=True)
            else: call(folder,'render',render,cfg,folder,preview=True)
            call(folder,'output_branding_verification',check_branding,read(folder/'preview-validation.json')['output'],folder/'branding-output.json')
            print('PREVIEW:', read(folder/'preview-validation.json')['output'], flush=True)
            print('Audio comparisons:', folder/'audio-quality/review/index.html', flush=True)
            if getattr(args, 'draft_export', False):
                source = Path(read(folder/'preview-validation.json')['output'])
                from output_size import MAX_BYTES
                if source.stat().st_size > MAX_BYTES:
                    raise ValueError('Draft exceeds 150 MB; refusing delivery')
                destination = OUT/(cfg['slug']+'_DRAFT.mp4')
                OUT.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    if digest(destination) != digest(source):
                        raise FileExistsError('Different draft already exists: '+str(destination))
                else:
                    with source.open('rb') as incoming, destination.open('xb') as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
                print('DRAFT MP4 (unreviewed):', destination, flush=True)
            return
        if stage == 'approve':
            if not all([args.listened,args.checked_lyrics,args.reviewed_audio,args.reviewed_timing]):
                raise ReviewRequired('Approval requires --listened --checked-lyrics --reviewed-audio --reviewed-timing')
            separation_guard.validate(job['source'], folder/'audio-quality')
            verify_preview(cfg, folder); local.require_translation_review(cfg, folder)
            local.approve(cfg, folder, True)
            save(folder/'full-review.json', {'fingerprint':fingerprint(cfg,folder),
                'reviewer':args.reviewer, 'listened':True, 'checked_lyrics':True,
                'reviewed_audio_flags':True, 'reviewed_timing':True})
            return
        if stage == 'render':
            separation_guard.validate(job['source'], folder/'audio-quality')
            if not (folder/'full-review.json').exists() or read(folder/'full-review.json')['fingerprint'] != fingerprint(cfg,folder):
                raise ReviewRequired('Full review is missing/stale. Run approve after reviewing the preview.')
            verify_preview(cfg, folder); local.require_translation_review(cfg, folder)
            validation = verify_preview(cfg, folder)
            source = Path(validation['output']); final = OUT/(cfg['slug']+'_Karaoke.mp4')
            OUT.mkdir(parents=True, exist_ok=True)
            if final.exists() and digest(final) != validation['sha256']:
                raise FileExistsError('Different final output already exists; refusing overwrite')
            if not final.exists():
                with source.open('rb') as src, final.open('xb') as dst: shutil.copyfileobj(src, dst)
            if digest(final) != validation['sha256']: raise ValueError('Final copy integrity check failed')
            save(folder/'validation.json', {**validation,'output':str(final),'preview':False,
                'delivery_basis':'exact reviewed high-quality preview; no additional lossy encode'})
            print('FINAL:', read(folder/'validation.json')['output'], flush=True)
        elif stage == 'extras':
            if not (folder/'full-review.json').exists() or read(folder/'full-review.json')['fingerprint'] != fingerprint(cfg,folder):
                raise ReviewRequired('Final review is stale; do not export extras from changed lyrics')
            local.make_extras(cfg, folder)


def doctor():
    problems = []
    for label, ok in [('FFmpeg',FFMPEG.is_file()), ('logo',LOGO.is_file()), ('Demucs Python',DEMUCSPY.is_file())]:
        print(('OK ' if ok else 'MISSING ')+label)
        if not ok: problems.append(label)
    try: print('Font:',font_file())
    except ValueError as exc: problems.append(str(exc)); print(exc)
    for name in ['av','numpy','scipy','PIL','whisperx','faster_whisper','transformers','onnxruntime','rapidocr_onnxruntime']:
        present = importlib.util.find_spec(name) is not None
        print(('OK ' if present else 'MISSING ')+name)
        if not present: problems.append(name)
    if DEMUCSPY.is_file():
        try:
            result=subprocess.run([str(DEMUCSPY),'-c','from demucs.api import Separator; import torch; print(torch.__version__)'],
                capture_output=True,text=True,timeout=30,env=child_env())
            if result.returncode: problems.append('Demucs import failed'); print(result.stderr[-1200:])
            else: print('Demucs import OK; torch',result.stdout.strip())
        except (OSError,subprocess.TimeoutExpired) as exc: problems.append(str(exc))
    if FFMPEG.is_file():
        check = subprocess.run([str(FFMPEG),'-hide_banner','-filters'],capture_output=True,text=True)
        for name in ['subtitles','rubberband','ebur128']:
            if name not in check.stdout: problems.append('FFmpeg '+name)
        encoders=subprocess.run([str(FFMPEG),'-hide_banner','-encoders'],capture_output=True,text=True)
        for name in ['libx264','aac']:
            if name not in encoders.stdout: problems.append('FFmpeg encoder '+name)
    ast_ready=any((MODELS/'audioset').glob('**/model.safetensors'))
    print('AST detector cache:', 'present' if ast_ready else 'needs first-use download')
    if os.environ.get('KARAOKE_ALLOW_MODEL_DOWNLOAD','1')!='1' and not ast_ready:
        problems.append('AST detector missing in offline mode')
    print('Model cache:',MODELS, '(downloads on first use unless disabled)')
    print('This checks setup, not model accuracy or listening approval.')
    return int(bool(problems))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=STAGES)
    p.add_argument('--job', type=Path, help='One JSON job, paths relative to its directory')
    p.add_argument('--manifest',type=Path,help='A JSON list or {"jobs": [...]} for sequential processing')
    p.add_argument('--source', type=Path); p.add_argument('--title'); p.add_argument('--artist')
    p.add_argument('--language', default='auto'); p.add_argument('--mode', choices=['music','zoom'], default='music')
    p.add_argument('--background',default='original')
    p.add_argument('--countdown-style',choices=['arc','circle'])
    p.add_argument('--countdown-colour',help='Ring colour #RRGGBB')
    p.add_argument('--profile',choices=['optimized'],help='New jobs: standard Demucs, 0.25 overlap, veryfast CRF 14 export')
    p.add_argument('--warm-models',action='store_true',help='Reuse bounded resident models across manifest jobs')
    p.add_argument('--parallel-stages',action='store_true',help='Overlap isolated background preparation with audio stages; dependencies and reviews remain enforced')
    p.add_argument('--draft-export',action='store_true',help='run only: export an unreviewed DRAFT MP4 without recording lyric approval')
    p.add_argument('--preview-start',type=float,default=0,help='quick-preview: output timeline start, including intro')
    p.add_argument('--preview-seconds',type=float,default=20,help='quick-preview: 1 to 60 seconds')
    for flag in ['listened','checked-lyrics','reviewed-audio','reviewed-timing']: p.add_argument('--'+flag,action='store_true')
    p.add_argument('--reviewer',default='operator')
    p.add_argument('--apply',action='store_true',help='cleanup only: delete the validated job data; otherwise dry run')
    p.add_argument('--keep-work',action='store_true',help='Keep temporary job data after final delivery')
    a, remaining = p.parse_known_args()
    if a.draft_export and a.stage != 'run': p.error('--draft-export is only valid with run')
    if a.warm_models:os.environ['KARAOKE_KEEP_MODELS']='1'
    if a.apply and a.stage != 'cleanup': p.error('--apply is only valid for cleanup')
    if remaining and a.stage not in ADVANCED: p.error('Unrecognised options: '+' '.join(remaining))
    if a.stage in ADVANCED: a.advanced = local.build_parser().parse_args([a.stage, *remaining])
    if a.stage == 'doctor': return doctor()
    if sum(bool(v) for v in (a.job,a.source,a.manifest)) != 1:
        p.error('Specify exactly one of --job, --source or --manifest')
    if a.manifest:
        data=read(a.manifest); jobs=data.get('jobs') if isinstance(data,dict) else data
        if not isinstance(jobs,list) or not jobs: p.error('Manifest needs a nonempty job list')
        base=a.manifest.resolve().parent
    else:
        jobs=[read(a.job) if a.job else {'source':str(a.source.resolve()),'title':a.title or a.source.stem,
            'artist':a.artist,'language':a.language,'mode':a.mode,'background':a.background}]
        base=a.job.resolve().parent if a.job else Path.cwd()
    results=[]
    for raw in jobs:
        folder=None
        try:
            if a.profile: raw={**raw,'profile':a.profile}
            overrides={k:v for k,v in {'countdown_style':a.countdown_style,'countdown_colour':a.countdown_colour}.items() if v is not None}
            if overrides:raw={**raw,'render':{**raw.get('render',{}),**overrides}}
            job,folder=normalize(raw,base)
            if a.stage == 'cleanup':
                from cleanup_job import plan_cleanup, cleanup
                plan = plan_cleanup(folder)
                if a.apply: cleanup(plan)
                print(json.dumps({**plan,'deleted':a.apply},indent=2))
                results.append({'title':job['title'],'status':'completed','cleanup':plan})
                continue
            execute(a.stage,job,folder,a)
            state={'run':'preview_ready_needs_review','preview':'preview_ready_needs_review',
                   'approve':'reviewed','render':'delivered'}.get(a.stage,'completed')
            if a.stage!='status': save(folder/'state.json',{'stage':a.stage,'status':state,'at':time.time()})
            if a.draft_export and not a.keep_work and os.getenv('KARAOKE_CLEANUP_AFTER_SONG','1')=='1':
                from song_cleanup import local_export
                local_export(folder,OUT/(folder.name+'_DRAFT.mp4'))
            if a.stage == 'render' and not a.keep_work:
                from cleanup_job import plan_cleanup,cleanup
                cleanup(plan_cleanup(folder))
                print('Generated job data removed; verification receipts retained in reports/completed.',flush=True)
            results.append({'title':job['title'],'status':'completed','work':str(folder)})
        except Exception as exc:
            status='needs_review' if isinstance(exc,ReviewRequired) else 'failed'
            if a.stage != 'cleanup' and folder and folder.exists() and not (folder/'running.lock').exists():
                save(folder/'state.json',{'stage':a.stage,'status':status,'error':str(exc)})
            print(str(exc),file=sys.stderr);results.append({'status':status,'error':str(exc)})
    if a.manifest and a.stage != 'cleanup': save(WORK/('batch-'+a.stage+'.json'),results)
    return 1 if any(r['status']=='failed' for r in results) else 2 if any(r['status']=='needs_review' for r in results) else 0
