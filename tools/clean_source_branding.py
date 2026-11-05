"""Clean an existing source/output without rerunning vocal/lyric models."""
import argparse
from pathlib import Path
import shutil
import av
from branding_guard import prepare_background,scan
from refresh_intro import packet_identity
from zoom_local_pipeline import digest,save


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prepared-clean-video',type=Path,
                   help='Resume verification of the exact retained cleanup-plan output')
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    source_hash=digest(a.source)
    if a.prepared_clean_video:
        from zoom_local_pipeline import read
        plan=read(a.work/'cleanup-plan.json')
        cleaned=a.prepared_clean_video.resolve()
        if Path(plan['source']).resolve()!=a.source.resolve() or Path(plan['command'][-1]).resolve()!=cleaned:
            raise ValueError('Prepared video does not match the saved cleanup command')
        scan(cleaned,a.work/'clean-scan.json')
    else:cleaned=Path(prepare_background(a.source,a.work))
    with av.open(str(a.source)) as c:
        has_audio=bool(c.streams.audio)
        size=(c.streams.video[0].width,c.streams.video[0].height,str(c.streams.video[0].average_rate))
        duration=c.duration/av.time_base
    with av.open(str(cleaned)) as c:
        v=c.streams.video[0]
        if (v.width,v.height,str(v.average_rate))!=size or abs(c.duration/av.time_base-duration)>.15:
            raise ValueError('Background clock/canvas changed')
    if has_audio and packet_identity(a.source,'audio')!=packet_identity(cleaned,'audio'):
        raise ValueError('Audio packets/timestamps changed')
    if digest(a.source)!=source_hash:raise ValueError('Source changed during processing')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with cleaned.open('rb') as src,a.output.open('xb') as dst:shutil.copyfileobj(src,dst)
    if digest(a.output)!=digest(cleaned):raise ValueError('Copy failed integrity verification')
    save(a.work/'delivery.json',{'source':str(a.source.resolve()),'output':str(a.output.resolve()),
         'sha256':digest(a.output),'audio_packets_and_timestamps_identical':has_audio,
         'status':'no_known_branding_detected_in_samples','full_listening_completed':False,
         'limitations':['Localized interpolation may be visible','OCR cannot certify invisible/unreadable marks']})
    print('VERIFIED CLEANUP:',a.output,flush=True)

if __name__=='__main__':main()
