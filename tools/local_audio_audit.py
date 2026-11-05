"""Read-only source/stem comparison. Quiet sections are flags, not diagnoses."""
from pathlib import Path
import subprocess
import numpy as np
from zoom_local_pipeline import FFMPEG


def stereo_audio(path):
    result = subprocess.run([str(FFMPEG),'-v','error','-i',str(path),'-ar','8000',
        '-ac','2','-f','f32le','-'],capture_output=True,check=True)
    return np.frombuffer(result.stdout,dtype='<f4').reshape(-1,2)


def level(samples):
    return float(20*np.log10(max(1e-9,float(np.sqrt(np.mean(samples.astype(float)**2))))))


def quiet_intervals(samples, threshold=-48, min_seconds=.4, sr=8000):
    width = round(sr*.02)
    count = len(samples)//width
    if count == 0:
        return []
    frames = samples[:count*width].reshape(count,width,-1).astype(float)
    db = 20*np.log10(np.maximum(1e-9,np.sqrt(np.mean(frames**2,axis=(1,2)))))
    change = np.diff(np.r_[False,db<threshold,False].astype(int))
    starts, ends = np.where(change==1)[0],np.where(change==-1)[0]
    return [(round(float(s)*.02,2),round(float(e)*.02,2)) for s,e in zip(starts,ends)
            if (e-s)*.02 >= min_seconds]


def compare(source, backing, vocals=None):
    tracks = {'source':stereo_audio(source),'instrumental':stereo_audio(backing)}
    if vocals:
        tracks['vocals'] = stereo_audio(vocals)
    durations = {name:len(samples)/8000 for name,samples in tracks.items()}
    if max(durations.values())-min(durations.values()) > .1:
        raise ValueError('Audio durations differ; cannot compare sections without mapping')
    events = []
    for start,end in quiet_intervals(tracks['instrumental']):
        db = {name:round(level(samples[round(start*8000):round(end*8000)]),2)
              for name,samples in tracks.items()}
        if db['source'] < -48:
            label = 'quiet_in_original_source'
        elif 'vocals' in db and db['vocals'] > db['source']-8:
            label = 'possibly_vocal_dominated_or_separation_loss'
        else:
            label = 'possible_separation_loss_needs_listening'
        events.append({'start':start,'end':end,'internal':start>2 and end<durations['source']-2,
                       'levels_dbfs':db,'classification':label})
    return {'durations':durations,'quiet_sections':events,
            'source_quiet_sections':quiet_intervals(tracks['source']),
            'peak_levels':{name:float(np.max(np.abs(samples))) for name,samples in tracks.items()},
            'status':'needs_listening' if events else 'no_near_silence_detected',
            'warning':'Energy cannot prove cause or separation quality. Do not auto-fill gaps or restore vocals.'}
