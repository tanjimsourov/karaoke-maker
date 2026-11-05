"""Publish verified text-cleaned Babylon comparisons, archiving the previous files."""
from pathlib import Path
import os
import shutil
from fractions import Fraction
import av
from project_runtime import ROOT,OUT
from zoom_local_pipeline import read,save,digest
from refresh_intro import packet_identity
from replace_backing import video_hash

def main():
    work=ROOT/'work/babylon-text-cleanup'
    ready=read(work/'ready.json')
    archive=work/'previous';archive.mkdir(exist_ok=True)
    variants={
        'heavy':('Taylor Swift - Babylon - BENCHMARK.mp4','Taylor Swift - Babylon - htdemucs_ft (heavy) - DRAFT.mp4'),
        'light':('Taylor Swift - Babylon - htdemucs - BENCHMARK.mp4','Taylor Swift - Babylon - htdemucs (light) - DRAFT.mp4')}
    plan=[];rounding={}
    for kind,(name,comparison) in variants.items():
        old=OUT/name;new=work/('final-'+kind+'.mp4');backup=archive/name
        if digest(new)!=ready['variants'][kind]['sha256']:raise ValueError('Staged output changed')
        reference=backup if backup.exists() else old
        before=packet_identity(reference,'audio');after=packet_identity(new,'audio')
        exact=(before[0]==after[0] and len(before[1])==len(after[1])
               and all(a[:2]==b[:2] for a,b in zip(before[1],after[1]))
               and before[1][:-1]==after[1][:-1])
        delta=float(Fraction(after[1][-1][2])-Fraction(before[1][-1][2])) if exact else 1
        # MP4 remuxing rounds the final packet duration to container timescale.
        # Encoded samples and every packet start timestamp must remain exact.
        if not exact or abs(delta)>.001:
            raise ValueError('Audio packets or timeline changed: '+kind)
        if ready['variants'][kind]['audio_check']['relative_error']>1e-6:
            raise ValueError('Decoded audio changed: '+kind)
        rounding[kind]=delta
        with av.open(str(new)) as c:
            v=c.streams.video[0]
            if (v.width,v.height,int(v.average_rate))!=(1920,1080,30):raise ValueError('Unexpected picture format')
        expected=digest(reference);new_hash=digest(new)
        for target in (old,OUT/'comparison'/comparison):
            if not target.resolve().is_relative_to(OUT.resolve()):raise ValueError('Unsafe output target')
            if not target.exists() or digest(target) not in (expected,new_hash):raise ValueError('Output changed since comparison copy: '+str(target))
        if backup.exists() and digest(backup)!=expected:raise ValueError('Different backup exists')
        if not backup.exists():shutil.copy2(old,backup)
        if digest(backup)!=expected:raise ValueError('Backup verification failed')
        plan.append((kind,new,old,OUT/'comparison'/comparison,backup))
    if video_hash(work/'final-heavy.mp4')!=video_hash(work/'final-light.mp4'):raise ValueError('Pictures differ')
    receipt={'status':'text_cleanup_technical_checks_passed','variants':{},
        'lyrics_changed':False,'audio_packets_and_start_timestamps_unchanged':True,
        'last_packet_duration_rounding_seconds':rounding,
        'limitation':'Filled background regions may be softer. Prior lyric and listening review warnings remain.',
        'text_verification':str(ROOT/'reports/babylon-text-cleanup/verification/possible-residuals.json')}
    for kind,new,old,comparison,backup in plan:
        for target in (old,comparison):
            if digest(target)==digest(new):continue
            temp=target.with_suffix('.text-cleanup-pending.mp4')
            if temp.exists() and digest(temp)!=digest(new):raise FileExistsError(temp)
            if not temp.exists():shutil.copy2(new,temp)
            if digest(temp)!=digest(new):raise ValueError('Copy verification failed')
            os.replace(temp,target)
        receipt['variants'][kind]={'output':str(old),'comparison':str(comparison),
            'sha256':digest(old),'backup':str(backup)}
    save(ROOT/'reports/babylon-text-cleanup/delivery.json',receipt)
    print(receipt)

if __name__=='__main__':main()
