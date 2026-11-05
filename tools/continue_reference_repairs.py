"""Serialize memory-heavy recovery work; preserve all existing deliveries."""
from pathlib import Path
import sys,subprocess,time
from project_runtime import ROOT
from zoom_local_pipeline import read,save,digest


def main():
    report=ROOT/'reports/reference-repair/active-repair.json'
    stems=ROOT/'work/babylon-audio-repair/uvr-full'
    started=time.monotonic()
    save(report,{'status':'waiting_for_running_uvr','existing_deliveries_changed':False})
    while not (stems/'result.json').exists():
        if time.monotonic()-started>7200:raise TimeoutError('UVR did not finish; inspect uvr-full.log')
        time.sleep(5)
    receipt=read(stems/'result.json')
    for name,value in receipt['files'].items():
        if digest(stems/name)!=value:raise ValueError('UVR output integrity mismatch')
    save(report,{'status':'checking_full_uvr_audio','existing_deliveries_changed':False})
    qc=ROOT/'work/babylon-audio-repair/uvr-full-check'
    command=[sys.executable,str(ROOT/'tools/audio_quality.py'),'--source',
             str(ROOT/'inputs/Taylor Swift - Babylon - YouTube (1080p).mp4'),
             '--candidate',str(stems/'instrumental.wav'),'--output',str(qc),'--language','en']
    with (report.parent/'uvr-full-check.log').open('a') as log:
        subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    american=ROOT/'work/american-reference-repair/uvr'
    save(report,{'status':'extracting_american_vocals_for_lyric_check','existing_deliveries_changed':False})
    with (report.parent/'american-uvr.log').open('a') as log:
        subprocess.run([sys.executable,str(ROOT/'tools/uvr_instrumental.py'),'--source',
            str(ROOT/'inputs/Geordie Kieffer - American - YouTube (1080p).mp4'),
            '--output',str(american),'--threads','3'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    transcription=report.parent/'american-uvr-transcript.json'
    if not transcription.exists():
        save(report,{'status':'transcribing_american_alternative_vocals','existing_deliveries_changed':False})
        with (report.parent/'american-uvr-transcript.log').open('a') as log:
            subprocess.run([sys.executable,str(ROOT/'tools/transcribe_source_reference.py'),'--source',
                str(american/'vocals.wav'),'--output',str(transcription),'--language','en'],
                cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    save(report,{'status':'resuming_background_repair','audio_report':str(qc/'quality.json'),'existing_deliveries_changed':False})
    with (report.parent/'lama-full-candidate.log').open('a') as log:
        subprocess.run([sys.executable,str(ROOT/'tools/build_babylon_lama_candidate.py')],cwd=ROOT,
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    save(report,{'status':'candidates_complete_need_visual_and_listening_review',
        'background_report':str(ROOT/'work/babylon-reference-repair/lama-chunks-v3/progress.json'),
        'audio_report':str(qc/'quality.json'),'existing_deliveries_changed':False,
        'american_alternative_transcript':str(transcription),
        'note':'No approval or final-delivery claim is generated automatically.'})


if __name__=='__main__':
    try:main()
    except Exception as exc:
        save(ROOT/'reports/reference-repair/active-repair-error.json',{'error':repr(exc)})
        raise
