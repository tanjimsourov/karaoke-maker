"""Refresh only four backgrounds, preserving accepted ASS and AAC packets."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import av

ROOT = Path(__file__).resolve().parents[1]
FF = ROOT / 'tools/ffmpeg/ffmpeg.exe'
OUT = ROOT / 'out'
WORK = ROOT / 'work/background_refresh_14_10'
WORK.mkdir(parents=True, exist_ok=True)
(WORK/'originals').mkdir(exist_ok=True)
LOGO = ROOT / 'work/webmail/Logo-Karaoke-2025-WHITE.png'
JOBS = [
 ('Bliv_her_lidt_endnu', 'Image-1.png'),
 ('Blodigt', 'Image-2.png'),
 ('Barry_Cant_Swim_Kimbara', 'jan-chatgpt/Dromerige neonbowling in Aalborg.png'),
 ('BUNT_TRIPPIN', 'jan-chatgpt/Neon bowlinglounge in dromerige bokeh.png'),
]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def audio_hash(path):
    r = subprocess.run([str(FF),'-v','error','-i',str(path),'-map','0:a:0','-c:a','copy','-f','hash','-hash','sha256','-'],capture_output=True,text=True,check=True)
    return r.stdout.strip()

def metadata(path):
    with av.open(str(path)) as c:
        v=c.streams.video[0]
        return {'width':v.width,'height':v.height,'fps':str(v.average_rate),'duration':c.duration/av.time_base}

manifest=[]
for slug, relative in JOBS:
    final=OUT/f'{slug}_Karaoke.mp4'
    original=WORK/'originals'/final.name
    if not original.exists():
        shutil.copy2(final, original)
    picture=ROOT/'audio-bg-sample/14-10'/relative
    ass=ROOT/'work/bowlnfun'/slug/'karaoke.ass'
    ass_before=digest(ass)
    source_meta=metadata(original)
    source_audio=audio_hash(original)
    staged=WORK/f'{slug}_new_background.mp4'
    log=WORK/f'{slug}.log'
    ass_filter=str(ass.resolve()).replace('\\','/').replace(':','\\:')
    filters=(
        '[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1[bg];'
        '[2:v]scale=180:-1[logo];'
        f"[bg][logo]overlay=W-w-48:42,subtitles='{ass_filter}'[v]"
    )
    cmd=[str(FF),'-y','-loop','1','-framerate','25','-i',str(picture),'-i',str(original),'-i',str(LOGO),
         '-filter_complex',filters,'-map','[v]','-map','1:a:0','-c:a','copy',
         '-t',str(source_meta['duration']),'-r','25','-c:v','libx264','-preset','fast','-crf','19',
         '-pix_fmt','yuv420p','-movflags','+faststart',str(staged)]
    print(f'{slug}: rendering background {relative}',flush=True)
    reuse=False
    if staged.exists():
        try:
            reuse=abs(metadata(staged)['duration']-source_meta['duration'])<0.05 and audio_hash(staged)==source_audio
        except Exception:
            reuse=False
    if not reuse:
        with log.open('w',encoding='utf-8') as fh:
            subprocess.run(cmd,stdout=fh,stderr=fh,check=True)
    meta=metadata(staged)
    assert (meta['width'],meta['height'])==(1920,1080) and meta['fps'] in ('25','25/1'),meta
    assert abs(meta['duration']-source_meta['duration'])<0.05,(meta,source_meta)
    assert digest(ass)==ass_before,'Subtitle source changed during render'
    assert audio_hash(staged)==source_audio,'Audio packets changed'
    subprocess.run([str(FF),'-v','error','-i',str(staged),'-f','null','-'],check=True)
    shutil.copy2(staged,final)
    assert digest(final)==digest(staged),'Copy mismatch'
    manifest.append({'video':str(final.relative_to(ROOT)),'background':str(picture.relative_to(ROOT)),
        'video_sha256':digest(final),'subtitle_sha256':ass_before,'audio_payload_hash':source_audio,
        'audio_identical_to_previous':True,'decode_passed':True,**meta})
    (WORK/'validation.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(f'{slug}: READY; audio identical; subtitles unchanged; 1920x1080; decode OK',flush=True)

kept=OUT/'AEr_lig_Freestyle_Karaoke_BG2.mp4'
assert kept.exists()
files=list(OUT.glob('*.mp4'))
assert len(files)==5,[p.name for p in files]
print('DONE: five distinct backgrounds; AEr_lig_Freestyle reused unchanged',flush=True)
