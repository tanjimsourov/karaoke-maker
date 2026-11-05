"""Complete logos, moving outer countdown ring, synchronized removal of silent lead-in."""
import json,subprocess,concurrent.futures
from pathlib import Path
import numpy as np
from project_runtime import ROOT,FFMPEG

BASE=ROOT/'out/comparison/ftp-raw-light-heavy/repaired/Charlie Jeer - Jennifer - Light - Updated.mp4'
DEST=BASE.parent/'lim'
REPORT=ROOT/'reports/jennifer-countdown-pair'
CUT=1.84

def run(brand,logo):
    out=DEST/f'Charlie Jeer - Jennifer - {brand} - Moving Countdown - Under 180MB.mp4'
    if out.exists():raise FileExistsError(out)
    folder=REPORT/brand;folder.mkdir(parents=True,exist_ok=True)
    angle='mod(atan2(Y-250,X-250)+PI/2+2*PI,2*PI)'
    # Thin full circle stays visible; a thicker 60-degree sector travels clockwise.
    sweep=f'lt(mod({angle}-2*PI*T/10+4*PI,2*PI),PI/3)'
    alpha=f'255*max(between(hypot(X-250,Y-250),212,214),between(hypot(X-250,Y-250),209,217)*{sweep})'
    graph=(
      '[0:v]split[head][tail];[head]trim=end=10,setpts=PTS-STARTPTS[h];'
      f'[tail]trim=start={10+CUT},setpts=PTS-STARTPTS[s];[h][s]concat=n=2:v=1:a=0[base];'
      '[0:a]asplit[ah][at];[ah]atrim=end=10,asetpts=PTS-STARTPTS[a0];'
      f'[at]atrim=start={10+CUT},asetpts=PTS-STARTPTS[a1];[a0][a1]concat=n=2:v=0:a=1[a];'
      f'[1:v]trim=start={CUT},setpts=PTS-STARTPTS,fps=30,scale=1920:1080,'
      'setsar=1,tpad=start_mode=clone:start_duration=10,crop=180:180:1692:42[cornerbg];'
      '[2:v]scale=1920:1080,crop=500:500:710:80[introbg];'
      "[base][introbg]overlay=710:80:enable='lt(t,10)'[b];"
      "[b][cornerbg]overlay=1692:42:enable='gte(t,10)':eof_action=pass[c];"
      '[3:v]split[li][lc];[li]scale=420:420[il];[lc]scale=180:180[cl];'
      "[c][il]overlay=750:120:enable='lt(t,10)'[d];"
      "[d][cl]overlay=1692:42:enable='gte(t,10)'[e];"
      f"[4:v]format=rgba,geq=r=255:g=255:b=255:a='{alpha}'[ring];"
      "[e][ring]overlay=710:80:eof_action=pass:repeatlast=0:enable='lt(t,10)'[v]"
    )
    cmd=[str(FFMPEG),'-v','warning','-stats','-nostdin','-n','-filter_complex_threads','1',
      '-threads','1','-i',str(BASE),'-threads','1','-i',str(ROOT/'Charlie Jeer - Jennifer (1080).mp4'),
      '-loop','1','-framerate','30','-i',str(ROOT/'work/bowlnfun/Jennifer-light-repaired/intro-background.png'),
      '-loop','1','-framerate','30','-i',str(logo),
      '-f','lavfi','-i','color=white:s=500x500:r=30:d=10','-filter_complex',graph,
      '-map','[v]','-map','[a]','-c:v','libx264','-threads','3','-preset','fast','-crf','18',
      '-maxrate','7800k','-bufsize','7800k','-pix_fmt','yuv420p','-r','30',
      '-c:a','aac','-b:a','192k','-t',str(168.66-CUT),'-map_metadata','0','-movflags','+faststart',str(out)]
    (folder/'command.json').write_text(json.dumps(cmd,indent=2))
    with (folder/'encode.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=log,check=True)
    subprocess.run([str(FFMPEG),'-v','error','-xerror','-threads','1','-i',str(out),'-f','null','-'],check=True)
    assert out.stat().st_size<180000000
    def samples(path):
        b=subprocess.run([str(FFMPEG),'-v','error','-i',str(path),'-ar','16000','-ac','1','-f','f32le','-'],capture_output=True,check=True).stdout
        return np.frombuffer(b,dtype=np.float32)
    a=samples(out);b=samples(BASE)
    expected=np.concatenate([b[:160000],b[round((10+CUT)*16000):]])
    n=min(len(a),len(expected));corr=float(np.corrcoef(a[:n],expected[:n])[0,1]);assert corr>.995,corr
    levels=[]
    for start,end in [(9,9.9),(10,10.2),(10.2,10.5)]:
        chunk=a[round(start*16000):round(end*16000)];levels.append({'start':start,'end':end,'dbfs':float(20*np.log10(max(1e-12,np.sqrt(np.mean(chunk*chunk)))))})
    assert levels[0]['dbfs'] < -60 and levels[1]['dbfs'] > -55
    data={'output':str(out),'bytes':out.stat().st_size,'decode_passed':True,'song_start':10,
      'removed_near_silent_lead_in':CUT,'audio_correlation_after_expected_trim':corr,'audio_levels':levels,
      'logo':'complete artwork preserved','ring':'full thin circle plus clockwise moving thicker sector'}
    (folder/'verification.json').write_text(json.dumps(data,indent=2));print(json.dumps(data),flush=True)
    return data

if __name__=='__main__':
    REPORT.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(run,'Karaoke',ROOT/'assets/logo.png'),pool.submit(run,'VoxNova',ROOT/'assets/voxnova-transparent.png')]
        results=[j.result() for j in jobs]
    (REPORT/'delivery.json').write_text(json.dumps(results,indent=2))
