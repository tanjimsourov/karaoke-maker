"""Same-source screening and level-matched A/B clips, not a listening certificate."""
import argparse
from datetime import datetime,timezone
import html
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

from project_runtime import ROOT,FFMPEG
from zoom_local_pipeline import read,save,digest
from parallel_song_benchmark import Measurement


def common_factors(peaks,gains):
    if len(peaks)!=len(gains) or not peaks:raise ValueError('Missing tracks')
    if any(not np.isfinite(x) or x<0 for x in peaks) or any(not np.isfinite(g) or g<=0 for g in gains):
        raise ValueError('Invalid peak/gain')
    restored=max(p/g for p,g in zip(peaks,gains))
    shared=min(1.,.99/max(restored,1e-12))
    return [shared/g for g in gains]


def fixed_asr_windows(reports,duration,limit=6):
    """Same coverage for both models: intro/middle/end plus high-score sections."""
    end=max(0.,duration-10.)
    starts=list(dict.fromkeys([0.,end/2,end]))
    scored={}
    for report in reports:
        for row in report['detector']['windows']:
            start=min(end,max(0.,row['start']))
            scored[start]=max(scored.get(start,0.),row['voice_score'])
    for start in sorted(scored,key=lambda x:scored[x],reverse=True):
        if len(starts)>=limit:break
        if all(abs(start-s)>=10 for s in starts):starts.append(start)
    for start in np.linspace(0,end,limit):
        if len(starts)>=limit:break
        if all(abs(float(start)-s)>.11 for s in starts):starts.append(float(start))
    return [{'start':s,'end':min(duration,s+10),'flagged':True} for s in sorted(starts[:limit])]


def source_matching_phrases(candidate,reference):
    matches=[]
    words=lambda text:re.findall(r'[^\W\d_]+',text.casefold(),flags=re.UNICODE)
    for item in candidate:
        a=words(item['text'])
        for original in reference:
            if item['start']>original['end']+2 or original['start']>item['end']+2:continue
            b=words(original['text']);comparison=SequenceMatcher(None,a,b,autojunk=False)
            shared=sum(block.size for block in comparison.get_matching_blocks())
            if shared>=3 and comparison.ratio()>=.5:
                matches.append({'candidate':item,'source_asr':original,
                    'word_sequence_similarity':comparison.ratio()});break
    return matches


def control_summary(source_quality,source_asr):
    windows=source_quality['detector']['windows']
    flagged=sum(w['flagged'] for w in windows)
    maximum=max((w['voice_score'] for w in windows),default=0.)
    return {'source_windows':len(windows),'source_voice_flagged_windows':flagged,
        'source_max_voice_score':maximum,
        'voice_control_responded':bool(source_quality['screening_complete'] and flagged>=3 and maximum>=.5),
        'voice_control_rule':'Sanity check only: at least 3 source windows flagged and max score >= 0.5.',
        'source_asr_qualifying_phrases':len(source_asr['evidence']),
        'asr_control_responded':bool(source_asr['complete'] and source_asr['evidence'])}


def finalize_controls(out):
    control=read(out/'original-control/quality.json')
    for name in ['htdemucs','htdemucs_ft']:
        candidate=read(out/name/'quality.json')
        for key in ['source','config','code','detector','revision','language']:
            if candidate['binding'][key]!=control['binding'][key]:raise ValueError('Control settings/source differ')
        intervals=lambda q:[(w['start'],w['end']) for w in q['detector']['windows']]
        if intervals(candidate)!=intervals(control):raise ValueError('Control scan windows differ')
    controls=control_summary(control,read(out/'original-asr.json'))
    report=read(out/'comparison.json');report['positive_controls']=controls
    if not controls['asr_control_responded']:
        report['limitations'].append('ASR returned no qualifying phrases from the original vocals; empty candidate ASR is inconclusive.')
    if not controls['voice_control_responded']:
        report['screening_preference']=None
        report['limitations'].append('Voice classifier did not pass the original-audio positive-control sanity check.')
    report['automated_vocal_comparison_verdict']=('inconclusive_positive_controls' if
        not controls['voice_control_responded'] or not controls['asr_control_responded'] else 'screening_only_listening_required')
    report['limitations']=list(dict.fromkeys(report['limitations']))
    report['quality_winner']=None
    save(out/'comparison.json',report)
    message=(f"Original-audio control: {controls['source_voice_flagged_windows']} of {controls['source_windows']} windows triggered the voice detector. "
        'This sanity check does not certify the detection accuracy. ')
    if not controls['asr_control_responded']:
        message+='The speech recognizer found no qualifying phrases in the original vocals, so empty speech results are inconclusive and cannot prove vocal removal.'
    if not controls['voice_control_responded']:
        message='Vocal-removal comparison is inconclusive: the original audio failed the detector sanity check. '+message
    page=(out/'index.html').read_text(encoding='utf-8')
    page=re.sub(r'<p class="note"><strong>Positive controls:</strong>.*?</p>','',page,flags=re.S)
    page=page.replace('<table>',
        '<p class="note"><strong>Positive controls:</strong> '+html.escape(message)+'</p><table>',1)
    (out/'index.html').write_text(page,encoding='utf-8')
    return controls


def ffmpeg(*args):
    subprocess.run([str(FFMPEG),'-v','error','-nostdin','-n',*map(str,args)],check=True)


def native_audio(path):
    raw=subprocess.run([str(FFMPEG),'-v','error','-i',str(path),'-ar','44100','-ac','2',
        '-f','f32le','-'],capture_output=True,check=True).stdout
    return np.frombuffer(raw,'<f4').reshape(-1,2)


def prepare(source,a_report,b_report,out):
    from scipy.io import wavfile
    source_hash=digest(source);records=[]
    for name,report_path in [('htdemucs',a_report),('htdemucs_ft',b_report)]:
        benchmark=read(report_path/'measurement.json')
        stems=Path(benchmark['work'])/'stems';manifest=read(stems/'separation.json')
        if manifest['settings']['source_sha256']!=source_hash or manifest['settings']['model']!=name:
            raise ValueError('Different source/model; cannot compare')
        if manifest['is_excerpt'] or manifest.get('is_intermediate'):raise ValueError('Not a full separation')
        if not all(digest(stems/file)==sha for file,sha in manifest['files'].items()):raise ValueError('Stem changed')
        records.append({'name':name,'stems':str(stems),'manifest':manifest,
            'benchmark_report':str(report_path/'measurement.json'),
            'separation_seconds':benchmark['separation_wall_seconds']})
    settings=[{k:v for k,v in r['manifest']['settings'].items() if k!='model'} for r in records]
    if settings[0]!=settings[1]:raise ValueError('Separation settings differ beyond model name')
    scratch=ROOT/'work/separator-comparisons'/out.name;scratch.mkdir(parents=True,exist_ok=True)
    source_wave=native_audio(source);peaks=[float(np.max(np.abs(source_wave)))];gains=[1.]
    if not np.isfinite(source_wave).all():raise ValueError('Invalid source samples')
    for r in records:
        sr,x=wavfile.read(Path(r['stems'])/'instrumental.wav',mmap=True)
        if sr!=44100 or x.shape!=source_wave.shape:raise ValueError('Different sample count/rate/channels')
        if not np.isfinite(x).all():raise ValueError('Invalid candidate samples')
        peaks.append(float(np.max(np.abs(x))));gains.append(r['manifest']['common_gain'])
        reconstructed=np.zeros_like(source_wave)
        for stem in ['drums','bass','other','vocals']:
            stem_rate,value=wavfile.read(Path(r['stems'])/(stem+'.wav'),mmap=True)
            if stem_rate!=44100 or value.shape!=source_wave.shape:raise ValueError('Invalid stem timeline')
            reconstructed+=value/r['manifest']['common_gain']
        r['sum_stems_relative_error']=float(np.sqrt(np.mean((reconstructed.astype('float64')-source_wave)**2)/
            max(np.mean(source_wave.astype('float64')**2),1e-20)))
    factors=common_factors(peaks,gains)
    paths=[source,*[Path(r['stems'])/'instrumental.wav' for r in records]]
    names=['original',*[r['name'] for r in records]]
    for name,path,factor in zip(names,paths,factors):
        target=scratch/(name+'.wav')
        if target.exists():raise FileExistsError('Existing comparison; use a new report directory')
        ffmpeg('-i',path,'-map','0:a:0','-ar',44100,'-ac',2,'-af',f'volume={factor:.12g}',
            '-c:a','pcm_f32le',target)
    for r,factor in zip(records,factors[1:]):
        r['comparison_gain_factor']=factor;r['normalized_audio']=str(scratch/(r['name']+'.wav'))
    save(out/'comparison-inputs.json',{'source':str(source),'source_sha256':source_hash,
        'duration_seconds':len(source_wave)/44100,'records':records,
        'normalized_source':str(scratch/'original.wav'),'source_gain_factor':factors[0],
        'gain_note':'Undo each separator protective common_gain, then apply one shared anti-clipping gain to all tracks. No per-track loudness normalization.'})
    save(out/'screening-config.json',{'threads':3,'alternatives':[],'asr':False,
        'voice_threshold':.25,'window_seconds':10,'step_seconds':5,'max_asr_windows':6})


def residual_asr(out,name):
    from audio_quality import decode,asr_evidence,settings
    inputs=read(out/'comparison-inputs.json')
    path=(inputs['normalized_source'] if name=='original' else
        next(r['normalized_audio'] for r in inputs['records'] if r['name']==name))
    windows=read(out/'shared-asr-windows.json')
    rows=asr_evidence(path,decode(path),windows,
        settings({**read(out/'screening-config.json'),'asr':True}),'da')
    save(out/(name+'-asr.json'),{'shared_windows':windows,'evidence':rows,
        'complete':True,'warning':'Recognized words may be hallucinated; absence of words does not prove vocal removal.'})


def build_report(out):
    inputs=read(out/'comparison-inputs.json');result=[]
    reference_asr=read(out/'original-asr.json')['evidence']
    for track in inputs['records']:
        name=track['name'];q=read(out/name/'quality.json');asr=read(out/(name+'-asr.json'))
        windows=q['detector']['windows']
        if not q['screening_complete'] or not asr['complete']:raise ValueError('Incomplete screening')
        scores=[w['voice_score'] for w in windows]
        result.append({'model':name,'separation_seconds':track['separation_seconds'],
            'voice_flagged_windows':sum(w['flagged'] for w in windows),'total_windows':len(windows),
            'max_voice_score':max(scores),'median_voice_score':float(np.median(scores)),
            'asr_evidence_count':len(asr['evidence']),
            'asr_phrases_matching_source':len(source_matching_phrases(asr['evidence'],reference_asr)),
            'duration_error_seconds':q['signal']['duration_error_seconds'],
            'clipped_fraction':q['signal']['clipped_fraction'],
            'new_silent_fraction':q['signal']['new_silent_fraction'],
            'signal_reject_reasons':q['signal']['reject_reasons'],
            'level_drop_flags':len(q['signal']['flags']),
            'retained_energy_ratio':q['signal']['energy_ratio'],
            'sum_stems_relative_error':track['sum_stems_relative_error']})
    # Tiny differences between sub-threshold, uncalibrated scores are not a win.
    rank=lambda x:(bool(x['signal_reject_reasons']),x['asr_phrases_matching_source'],
        x['voice_flagged_windows'])
    preference=None if rank(result[0])==rank(result[1]) else min(result,key=rank)['model']
    starts=[max(0,w['start']-1) for w in read(out/'shared-asr-windows.json')]
    clips=[];tracks={'original':inputs['normalized_source'],**{r['name']:r['normalized_audio'] for r in inputs['records']}}
    for name,path in tracks.items():
        full=out/(name+'.m4a')
        ffmpeg('-i',path,'-c:a','aac','-b:a','320k',full)
        ffmpeg('-i',full,'-f','null','-')
    for index,start in enumerate(starts):
        length=min(10,inputs['duration_seconds']-start);row={'start':start,'duration':length,'tracks':{}}
        for name,path in tracks.items():
            filename=f'{index+1:02d}-{name}.wav';target=out/filename
            ffmpeg('-ss',start,'-i',path,'-t',length,'-c:a','pcm_s16le',target)
            row['tracks'][name]={'file':filename,'sha256':digest(target)}
        clips.append(row)
    report={'source_sha256':inputs['source_sha256'],'source_duration_seconds':inputs['duration_seconds'],
        'models':result,'screening_preference':preference,'quality_winner':None,
        'full_listening_completed':False,'shared_asr_windows':read(out/'shared-asr-windows.json'),
        'clips':clips,'gain_note':inputs['gain_note'],
        'limitations':['AST scores are uncalibrated classifier outputs, not quality percentages.',
            'Residual ASR can hallucinate. No recognized words does not prove no vocals.',
            'No clean reference stems are available; instrument damage and SDR cannot be certified.',
            'Separation speed is one observed run per model; other apps and thermal state can affect it.',
            'No full-song listening or lyric/alignment correctness certification was performed.']}
    save(out/'comparison.json',report)
    esc=html.escape
    rows=''.join('<tr><th>'+esc(label)+'</th>'+''.join('<td>'+esc(str(r[key]))+'</td>' for r in result)+'</tr>'
        for label,key in [('Separation seconds','separation_seconds'),('Flagged voice windows','voice_flagged_windows'),
            ('Windows scanned','total_windows'),('Highest voice-classifier score','max_voice_score'),
            ('Possible recognized-voice phrases','asr_evidence_count'),('New silent fraction','new_silent_fraction'),
            ('ASR phrases also matching original audio','asr_phrases_matching_source'),
            ('Level-drop warnings','level_drop_flags'),('Clipped fraction','clipped_fraction'),
            ('Duration error (seconds)','duration_error_seconds')])
    sections=''
    for index,clip in enumerate(clips,1):
        sections+=f'<section><h2>Section {index} — source {clip["start"]:.1f}s</h2><div class="players">'
        for name in tracks:
            sections+=f'<div><strong>{esc(name)}</strong><audio controls preload="none" src="{esc(clip["tracks"][name]["file"])}"></audio></div>'
        sections+='</div></section>'
    full=''.join(f'<p>{esc(name)} <audio controls preload="none" src="{esc(name)}.m4a"></audio></p>' for name in tracks)
    player_script='<script>document.querySelectorAll("audio").forEach(a=>a.addEventListener("play",()=>document.querySelectorAll("audio").forEach(b=>{if(a!==b)b.pause()})));</script>'
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Mucki Bar — separator comparison</title><style>body{font:16px system-ui;background:#f5f6fa;color:#182232;max-width:1100px;margin:35px auto;padding:0 20px}h1{font-size:30px}p{line-height:1.6}table{border-collapse:collapse;width:100%;background:white}td,th{padding:12px;border-bottom:1px solid #d9dfe9;text-align:left}section{background:white;padding:20px;margin:20px 0;border-radius:10px}.players{display:flex;flex-wrap:wrap;gap:15px}.players>div{flex:1;min-width:270px}audio{display:block;width:100%;margin:10px 0}.note{padding:18px;background:#fff1ca;border-radius:10px}</style>
<h1>Mucki Bar — htdemucs vs htdemucs_ft</h1><p>Same source, four CPU threads, seed 0, one shift and 0.5 overlap. Temporary separator gains were undone, then one common safe gain was applied to all three tracks.</p>
<p class="note"><strong>Automated screening only; no certified sound-quality winner.</strong> Scores are not quality percentages. Listen for remaining singing, missing instruments and watery/distorted sound. A clean reference instrumental is unavailable.</p>
<table><tr><th>Measured check</th><th>htdemucs</th><th>htdemucs_ft</th></tr>'''+rows+'</table><h2>Matched sections</h2><p>Each row contains the same source interval. Starting one player pauses the others.</p>'+sections+'<h2>Full tracks</h2>'+full+player_script+'</html>'
    (out/'index.html').write_text(page,encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path);p.add_argument('--a-report',type=Path);p.add_argument('--b-report',type=Path)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--worker',choices=['asr','finalize-controls']);p.add_argument('--name',choices=['htdemucs','htdemucs_ft','original'])
    a=p.parse_args();out=a.out.resolve()
    if a.worker=='asr':residual_asr(out,a.name);return
    if a.worker=='finalize-controls':print(json.dumps(finalize_controls(out),indent=2));return
    if not all([a.source,a.a_report,a.b_report]):p.error('Need source and both benchmark reports')
    out.mkdir(parents=True,exist_ok=True)
    if (out/'measurement.json').exists():raise FileExistsError('Use a new comparison directory')
    report={'status':'running','tasks':[],'started_utc':datetime.now(timezone.utc).isoformat(),
        'full_listening_completed':False,'working_set_note':'Summed sampled working sets; may double-count shared pages.',
        'private_note':'Private committed bytes are not equivalent to physical RAM.'}
    m=Measurement(out,report);m.thread.start()
    try:
        prepare(a.source.resolve(),a.a_report.resolve(),a.b_report.resolve(),out)
        inputs=read(out/'comparison-inputs.json');py=sys.executable
        m.group([m.start(r['name']+'-screen',[py,str(ROOT/'tools/audio_quality.py'),
            '--source',inputs['normalized_source'],'--candidate',r['normalized_audio'],
            '--output',str(out/r['name']),'--config',str(out/'screening-config.json'),'--language','da']) for r in inputs['records']])
        quality=[read(out/r['name']/'quality.json') for r in inputs['records']]
        if not all(q['screening_complete'] for q in quality):raise ValueError('Detector scan failed')
        save(out/'shared-asr-windows.json',fixed_asr_windows(quality,inputs['duration_seconds']))
        m.group([m.start(r['name']+'-asr',[py,str(Path(__file__).resolve()),'--worker','asr',
            '--name',r['name'],'--out',str(out)]) for r in inputs['records']])
        m.wait(m.start('original-asr',[py,str(Path(__file__).resolve()),'--worker','asr',
            '--name','original','--out',str(out)]))
        build_report(out)
        m.wait(m.start('original-control',[py,str(ROOT/'tools/audio_quality.py'),
            '--source',inputs['normalized_source'],'--candidate',inputs['normalized_source'],
            '--output',str(out/'original-control'),'--config',str(out/'screening-config.json'),'--language','da']))
        finalize_controls(out);report['status']='automated_comparison_complete_listening_pending'
    except Exception as exc:report['status']='failed';report['error']=str(exc);raise
    finally:
        m.stop.set();m.thread.join();report['wall_seconds']=time.monotonic()-m.started
        save(out/'measurement.json',report)
    print('COMPARISON:',out/'index.html',flush=True)


if __name__=='__main__':main()
