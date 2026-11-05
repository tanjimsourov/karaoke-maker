"""Download an available native 1080p YouTube MP4 and verify both streams.

No profiles/cookies/accounts are used. Interrupted transfers resume through yt-dlp.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time
from project_runtime import ROOT, FFMPEG
from zoom_local_pipeline import digest


def main():
    from yt_dlp import YoutubeDL
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('url')
    p.add_argument('--name',required=True,help='MP4 filename within inputs/')
    args=p.parse_args()
    if Path(args.name).name != args.name or Path(args.name).suffix.lower()!='.mp4':
        p.error('--name must be an MP4 filename')
    destination=ROOT/'inputs'/args.name
    destination.parent.mkdir(parents=True,exist_ok=True)
    receipt=destination.with_suffix('.source.json')
    if destination.exists():
        if not receipt.is_file():raise ValueError('Untracked existing MP4; choose a new output name')
        previous=json.loads(receipt.read_text(encoding='utf-8'))
        if previous.get('url')!=args.url or previous.get('sha256')!=digest(destination):
            raise ValueError('Existing source does not match its saved URL/checksum; refusing reuse')
    options={'format':'bestvideo[height=1080][ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/best[height=1080][ext=mp4]',
        'outtmpl':str(destination.with_suffix(''))+'.%(ext)s', 'merge_output_format':'mp4',
        'ffmpeg_location':str(FFMPEG.parent),'noplaylist':True,'continuedl':True,
        'overwrites':False,'retries':2,'fragment_retries':2,'socket_timeout':30,
        'concurrent_fragment_downloads':2,'cachedir':str(ROOT/'tmp/yt-dlp-cache')}
    node=shutil.which('node')
    if node:options['js_runtimes']={'node':{'path':node}}
    started=time.perf_counter()
    with YoutubeDL(options) as downloader:
        info=downloader.extract_info(args.url,download=True)
    import av
    with av.open(str(destination)) as media:
        if not media.streams.video or not media.streams.audio:
            raise ValueError('Downloaded file needs video and audio')
        video=media.streams.video[0]
        if video.height!=1080:raise ValueError('Source is not native 1080p')
        report={'url':args.url,'id':info['id'],'title':info['title'],'path':str(destination),
            'duration_seconds':media.duration/av.time_base,'width':video.width,'height':video.height,
            'fps':float(video.average_rate),'download_and_merge_seconds':time.perf_counter()-started}
    subprocess.run([str(FFMPEG),'-v','error','-xerror','-nostdin','-i',str(destination),
        '-map','0:v:0','-map','0:a:0','-f','null','-'],check=True)
    report['strict_decode_passed']=True
    report['sha256']=digest(destination)
    receipt.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
