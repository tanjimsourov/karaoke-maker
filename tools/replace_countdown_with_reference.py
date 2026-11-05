"""Replace only the ten-second intro; retain encoded song video and all audio."""
from pathlib import Path
import subprocess,json,hashlib,concurrent.futures,argparse
import av
from project_runtime import ROOT,FFMPEG
from add_reference_countdown_circle import reference_arc_filter

DEST=ROOT/'out/comparison/ftp-raw-light-heavy/repaired/lim'
REPORT=ROOT/'reports/jennifer-reference-closing-pair'
VERIFY_ONLY=False
ROUND_CIRCLE=False
NO_TRACK=False

def run(brand,logo):
    src=DEST/f'Charlie Jeer - Jennifer - {brand} - Moving Countdown - Under 180MB.mp4'
    out=DEST/f'Charlie Jeer - Jennifer - {brand} - Reference Closing Circle - Under 180MB.mp4'
    if ROUND_CIRCLE:
        out=DEST/'fresh'/f'Charlie Jeer - Jennifer - {brand} - Round Closing Countdown.mp4'
    if NO_TRACK:
        out=ROOT/'out'/f'Charlie Jeer - Jennifer - {brand} - v2 - Clean Countdown.mp4'
    out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists() and not VERIFY_ONLY:raise FileExistsError(out)
    folder=REPORT/brand;folder.mkdir(parents=True,exist_ok=True)
    def ff(args,name):
        if VERIFY_ONLY and name!='decode':return
        cmd=[str(FFMPEG),'-v','error','-nostdin','-n',*map(str,args)]
        with (folder/(name+'.log')).open('w') as log:subprocess.run(cmd,stdout=log,stderr=log,check=True)
    # This boundary was verified; reject other inputs without an exact keyframe.
    with av.open(str(src)) as c:
        s=c.streams.video[0]
        assert any(p.is_keyframe and p.pts is not None and abs(float(p.pts*s.time_base)-10)<.001
                   for p in c.demux(s)),'Missing keyframe at intro boundary'
    circle_filter=reference_arc_filter(10)
    if ROUND_CIRCLE:
        angle='mod(atan2(Y-250,X-250)+PI/2+2*PI,2*PI)'
        alpha=f'255*max(between(hypot(X-250,Y-250),234,236),between(hypot(X-250,Y-250),231,239)*gte({angle},2*PI*T/10))'
        if NO_TRACK:
            alpha=f'255*between(hypot(X-250,Y-250),231,239)*gte({angle},2*PI*T/10)'
        circle_filter=f"scale=500:500,format=rgba,geq=r=255:g=255:b=255:a='{alpha}'"
    graph=(
      '[1:v]scale=1920:1080,crop=500:500:710:80[patch];'
      '[0:v][patch]overlay=710:80[base];[2:v]scale=420:420[logo];'
      '[base][logo]overlay=750:120[branded];'
      f'[3:v]{circle_filter}[arc];[branded][arc]overlay=710:80[v]')
    ff(['-filter_complex_threads','1','-threads','1','-i',src,
        '-loop','1','-framerate','30','-i',ROOT/'work/bowlnfun/Jennifer-light-repaired/intro-background.png',
        '-loop','1','-framerate','30','-i',logo,
        '-loop','1','-framerate','30','-i',ROOT/'assets/logo-original.png',
        '-filter_complex',graph,'-map','[v]','-an','-t','10','-r','30',
        '-c:v','libx264','-threads','2','-preset','fast','-crf','18','-maxrate','7800k','-bufsize','7800k',
        '-pix_fmt','yuv420p','-video_track_timescale','15360',folder/'intro.mp4'],'intro')
    ff(['-ss','10','-i',src,'-map','0:v:0','-c','copy','-an',folder/'tail.mp4'],'tail')
    (folder/'concat.txt').write_text("file 'intro.mp4'\nfile 'tail.mp4'\n",encoding='utf-8')
    ff(['-f','concat','-safe','0','-i',folder/'concat.txt','-i',src,
        '-map','0:v:0','-map','1:a:0','-c','copy','-map_metadata','1','-movflags','+faststart',out],'mux')
    ff(['-xerror','-i',out,'-f','null','-'],'decode')
    def packets(path,kind,start=0):
        h=hashlib.sha256();count=0
        with av.open(str(path)) as c:
            stream=next(s for s in c.streams if s.type==kind)
            for packet in c.demux(stream):
                if packet.pts is not None and float(packet.pts*stream.time_base)>=start-.0001:
                    data=bytes(packet)
                    if kind=='video':
                        # Concat inserts SPS/PPS parameter sets at keyframes.
                        # Compare all coded picture NAL units, excluding headers.
                        offset=0
                        while offset<len(data):
                            length=int.from_bytes(data[offset:offset+4],'big')
                            nal=data[offset+4:offset+4+length]
                            assert length and len(nal)==length
                            if 1<=nal[0]&31<=5:h.update(nal)
                            offset+=4+length
                    else:h.update(data)
                    count+=1
        return h.hexdigest(),count
    assert packets(src,'audio',-1)==packets(out,'audio',-1),'Encoded audio differs'
    assert packets(src,'video',10)==packets(out,'video',10),'Encoded song video differs'
    with av.open(str(out)) as c:
        s=c.streams.video[0];assert (s.width,s.height)==(1920,1080) and s.average_rate==30
        duration=float(c.duration/av.time_base)
        assert abs(duration-166.8333)<.05,duration
    assert out.stat().st_size<180000000
    data={'output':str(out),'bytes':out.stat().st_size,'strict_decode':True,
          'song_coded_frames_identical':True,'audio_packets_identical':True,
          'duration':duration,'song_start':10,'circle':('Geometric circle: complete thin outline plus clockwise closing thick arc' if ROUND_CIRCLE else 'Exact reference arc filter, closing clockwise')}
    if NO_TRACK:data['circle']='Geometric white closing arc only; no residual outline or shadow track'
    (folder/'verification.json').write_text(json.dumps(data,indent=2));return data

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify-only',action='store_true')
    parser.add_argument('--round-circle',action='store_true')
    parser.add_argument('--no-track',action='store_true')
    args=parser.parse_args();VERIFY_ONLY=args.verify_only;ROUND_CIRCLE=args.round_circle or args.no_track;NO_TRACK=args.no_track
    if ROUND_CIRCLE:REPORT=ROOT/'reports/jennifer-round-closing-pair'
    if NO_TRACK:REPORT=ROOT/'reports/jennifer-clean-countdown-pair'
    REPORT.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(run,'Karaoke',ROOT/'assets/logo.png'),pool.submit(run,'VoxNova',ROOT/'assets/voxnova-transparent.png')]
        results=[j.result() for j in jobs]
    (REPORT/'delivery.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
