"""Export a technically checked review sample without inventing human approval.

The normal final-delivery approval gate is unchanged. Only unrelated helper/test
code revisions may differ from the render snapshot; renderer dependencies and
every recorded media/lyric/font/template input must still match.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import av
from project_runtime import ROOT,OUT,FFMPEG
from workflow import normalize,context,require_lyrics
from zoom_local_pipeline import read,save,digest,audio,check_audio
from branding_guard import scan

RENDER_CODE={'build_bowlnfun_karaoke.py','zoom_local_pipeline.py','intro_countdown.py','inline_branding.py',
             'prepare_zoom_local.py','layers.py','project_runtime.py','workflow.py'}
BUNDLED_INTRO='e770db9a58210a07c7441fdf7bec2864e1a3a4e9760dbfc392a9e48250ffaa74'


def verify_inputs(validation,cfg):
    if validation['fingerprint']['config']!=cfg:raise ValueError('Render configuration changed')
    changed=[]
    for name,sha in validation['fingerprint']['files'].items():
        p=Path(name)
        if digest(p)==sha:continue
        if p.suffix!='.py' or p.name in RENDER_CODE:
            raise ValueError('Rendered input/dependency changed: '+name)
        changed.append(name)
    if cfg.get('render',{}).get('intro_countdown'):
        p=ROOT/'assets/logo-original.png'
        expected=validation['fingerprint']['files'].get(str(p),BUNDLED_INTRO)
        if digest(p)!=expected:raise ValueError('Reference logo artwork changed')
    return changed


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--job',type=Path,required=True);p.add_argument('--name',required=True)
    p.add_argument('--keep-work',action='store_true',help='Retain generated job files for editing')
    p.add_argument('--discard-draft-work',action='store_true',help='Explicitly discard unapproved draft work after verified export')
    p.add_argument('--resume-existing',action='store_true',help='Reuse only an identical verified export after interruption')
    p.add_argument('--unreviewed-benchmark',action='store_true',
        help='Explicitly export an unapproved ASR benchmark draft; filename must end in - BENCHMARK.mp4')
    a=p.parse_args()
    if Path(a.name).name!=a.name or Path(a.name).suffix.lower()!='.mp4':p.error('Name must be an MP4 filename')
    job,folder=normalize(read(a.job),a.job.resolve().parent);cfg=context(job,folder)
    if a.unreviewed_benchmark:
        if not a.name.endswith(' - BENCHMARK.mp4'):p.error('Unreviewed benchmark needs the BENCHMARK filename suffix')
        from workflow import check_lyric_draft
        check_lyric_draft(folder)
        if read(folder/'review-status.json').get('status')!='unapproved_benchmark_draft':
            raise ValueError('Missing explicit benchmark draft provenance')
    else:require_lyrics(cfg,folder)
    v=read(folder/'preview-validation.json');source=Path(v['output'])
    changed=verify_inputs(v,cfg)
    if digest(source)!=v['sha256']:raise ValueError('Export video changed')
    branding=scan(source,folder/'branding-output.json')
    with av.open(str(source)) as c:
        s=c.streams.video[0]
        if [s.width,s.height]!=v['resolution'] or int(s.average_rate)!=v['render_options']['fps']:
            raise ValueError('Output canvas/frame rate mismatch')
        if abs(c.duration/av.time_base-v['expected_duration'])>.15:raise ValueError('Output duration mismatch')
    options=v['render_options']
    if options['guide_vocal_level'] or options['pitch_semitones'] or options['start'] or options['end'] or cfg.get('layers',{}).get('changes_audio'):
        raise ValueError('This sample exporter requires an unchanged, full-length instrumental timeline')
    audio_check=check_audio(audio(cfg['zoom_video']),audio(source),delay=round(options['intro_seconds']*16000),
        gain_invariant=options['loudness_lufs'] is not None,
        skip_start=round(options['fade_in']*16000),skip_end=round(options['fade_out']*16000))
    subprocess.run([str(FFMPEG),'-v','error','-xerror','-i',str(source),'-f','null','-'],check=True)
    destination=OUT/a.name
    if destination.exists() and (not a.resume_existing or digest(destination)!=v['sha256']):raise FileExistsError(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.exists():
        with source.open('rb') as src,destination.open('xb') as dst:shutil.copyfileobj(src,dst)
    if digest(destination)!=v['sha256']:raise ValueError('Copy integrity check failed')
    save(folder/'sample-export.json',{'output':str(destination),'sha256':v['sha256'],
        'status':'review_sample_technical_checks_passed','full_listening_completed':False,
        'human_content_approved':False,'audio_check':audio_check,
        'unreviewed_benchmark':a.unreviewed_benchmark,'lyrics_reviewed':not a.unreviewed_benchmark,
        'benchmark_phases':read(folder/'benchmark-phases.json') if (folder/'benchmark-phases.json').exists() else None,
        'branding_samples':branding['sampled_frames'],'strict_decode':'passed',
        'changed_nonrender_helper_files':changed,
        'timing_flags':len(read(folder/'timing-report.json').get('issues',[]))})
    print('CHECKED SAMPLE:',destination,flush=True)
    if a.discard_draft_work and not a.keep_work:
        from cleanup_job import plan_cleanup,cleanup
        cleanup(plan_cleanup(folder,sample=True))
        print('Generated job data removed; verification receipts retained in reports/completed.',flush=True)
    else:
        print('Draft work retained for lyric/timing corrections. Approved final delivery handles cleanup.',flush=True)

if __name__=='__main__':main()
