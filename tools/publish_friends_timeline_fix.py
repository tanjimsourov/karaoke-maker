"""Validate and replace only the requested local comparison; retain old copy."""
import json, shutil
import av
from zoom_local_pipeline import ROOT, audio, check_audio, digest, save
from compare_zoom_friends import SOURCE, WORK

new=WORK/'Friends_Local_SourceTimeline.mp4'
destination=ROOT/'out/zoom/comparison/Friends_Local_REVIEW.mp4'
backup=WORK/'Friends_Local_previous_added_intro.mp4'
with av.open(str(SOURCE)) as c:source_seconds=c.duration/av.time_base
with av.open(str(new)) as c:
    seconds=c.duration/av.time_base
    assert abs(seconds-source_seconds)<.15
    assert (c.streams.video[0].width,c.streams.video[0].height)==(1920,1080)
result=check_audio(audio(SOURCE),audio(new),delay=0)
ass=(ROOT/'work/bowlnfun/Compare_Friends_Local_SourceTimeline/karaoke.ass').read_text(encoding='utf-8-sig')
assert any('0:00:08.92' in line and 'PageSweep' in line and 'What' in line for line in ass.splitlines())
if not backup.exists():shutil.copy2(destination,backup)
shutil.copy2(new,destination)
assert digest(new)==digest(destination)
report={'file':str(destination),'sha256':digest(destination),'source_duration':source_seconds,'duration':seconds,'added_intro_seconds':0,'first_highlight_seconds':8.92,'audio_check':result,'backup':str(backup)}
save(WORK/'source-timeline-fix-validation.json',report)
print(json.dumps(report))
