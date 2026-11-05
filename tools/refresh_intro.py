"""Render only through the first post-intro keyframe, then preserve the rest.

Refuses incompatible codec headers rather than silently transcoding the song.
The source MP4 is never overwritten. All original audio packets are retained.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
import av
from project_runtime import FFMPEG
from workflow import normalize,context
from zoom_local_pipeline import read,save,run_renderer,digest


def packet_identity(path,kind,start=0):
    h=hashlib.sha256();timeline=[]
    with av.open(str(path)) as c:
        for p in c.demux(**{kind:0}):
            if not p.size or p.pts is None or float(p.pts*p.time_base)<start-.001:continue
            h.update(bytes(p))
            timeline.append(tuple(str(x*p.time_base) for x in (p.pts,p.dts,p.duration)))
    return h.hexdigest(),timeline


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--job',required=True,type=Path)
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();a.source=a.source.resolve();a.output=a.output.resolve()
    if a.output.exists():raise FileExistsError(a.output)
    job,folder=normalize(read(a.job),a.job.resolve().parent)
    cfg=context(job,folder)
    with av.open(str(a.source)) as c:
        duration=c.duration/av.time_base
        boundaries=[float(x.pts*x.time_base) for x in c.demux(video=0)
                    if x.pts is not None and x.is_keyframe and float(x.pts*x.time_base)>=job['render']['intro_seconds']]
    if not boundaries:raise ValueError('No post-intro keyframe')
    boundary=min(boundaries);cfg['render']={**cfg['render'],'end':boundary}
    binding={'source':digest(a.source),'render':cfg['render'],
        'code':{name:digest(Path(__file__).parent/name) for name in
                ['refresh_intro.py','intro_countdown.py','build_bowlnfun_karaoke.py','zoom_local_pipeline.py']}}
    key=hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()[:12]
    work=folder/('intro-refresh-'+key);work.mkdir(exist_ok=True)
    save(work/'inputs.json',binding)
    prefix=work/'prefix.mp4'
    if not prefix.exists():run_renderer(cfg,folder,work,prefix.name)
    with av.open(str(a.source)) as c,av.open(str(prefix)) as o:
        if c.streams.video[0].codec_context.extradata!=o.streams.video[0].codec_context.extradata:
            raise ValueError('Codec headers differ; prefix retained, full render required')
    with av.open(str(a.source)) as c,av.open(str(prefix)) as o,av.open(str(a.output),'w',options={'movflags':'+faststart'}) as out:
        video=out.add_stream_from_template(c.streams.video[0]);audio=out.add_stream_from_template(c.streams.audio[0])
        packets=[]
        for packet in o.demux(video=0):
            if packet.size and packet.pts is not None and float(packet.pts*packet.time_base)<boundary-.001:
                packets.append((float(packet.dts*packet.time_base),packet,video))
        for packet in c.demux():
            if not packet.size or packet.pts is None:continue
            if packet.stream.type=='audio':target=audio
            elif packet.stream.type=='video' and float(packet.pts*packet.time_base)>=boundary-.001:target=video
            else:continue
            packets.append((float(packet.dts*packet.time_base),packet,target))
        for _,packet,target in sorted(packets,key=lambda x:x[0]):
            packet.stream=target;out.mux(packet)
    assert packet_identity(a.source,'audio')==packet_identity(a.output,'audio'),'Audio changed'
    assert packet_identity(a.source,'video',boundary)==packet_identity(a.output,'video',boundary),'Later video changed'
    with av.open(str(a.output)) as c:
        assert abs(c.duration/av.time_base-duration)<.05,'Duration changed'
        assert str(c.streams.video[0].average_rate)=='30','Frame rate changed'
    subprocess.run([str(FFMPEG),'-v','error','-xerror','-i',str(a.output),'-f','null','-'],check=True)
    save(work/'verification.json',{'source':str(a.source),'source_sha256':digest(a.source),
        'output':str(a.output),'sha256':digest(a.output),'splice_seconds':boundary,
        'audio_packets_and_timestamps_identical':True,'later_video_packets_and_timestamps_identical':True,
        'strict_decode':'passed','full_listening_completed':False})
    print('VERIFIED:',a.output,flush=True)

if __name__=='__main__':main()
