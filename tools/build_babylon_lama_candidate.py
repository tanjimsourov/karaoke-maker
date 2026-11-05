"""Resumable chunked background candidate. Never approves or publishes a video."""
from pathlib import Path
import subprocess,sys,math,time
import av
from project_runtime import ROOT,FFMPEG
from zoom_local_pipeline import read,save,digest


def main():
    source=ROOT/'inputs/Taylor Swift - Babylon - YouTube (1080p).mp4'
    work=ROOT/'work/babylon-reference-repair/lama-chunks-v3'
    work.mkdir(parents=True,exist_ok=True)
    worker=ROOT/'tools/lama_temporal_trial.py'
    binding={'source':digest(source),'worker':digest(worker),'chunk_seconds':10}
    state_path=work/'progress.json'
    state=read(state_path) if state_path.exists() else {'binding':binding,'completed':[],'status':'running'}
    if state['binding']!=binding:raise ValueError('Repair inputs changed; use a fresh work directory')
    with av.open(str(source)) as c:duration=c.duration/av.time_base
    start_clock=time.perf_counter()
    for number in range(math.ceil(duration/10)):
        target=work/f'{number:03d}.mp4';receipt=target.with_suffix('.json')
        if receipt.exists() and target.exists():
            if digest(target)!=read(receipt)['output_sha256']:raise ValueError('Cached chunk changed')
        else:
            if target.exists():
                # Preserve interrupted data; never delete or silently reuse it.
                target.rename(target.with_name(target.stem+f'-interrupted-{time.time_ns()}.mp4'))
            command=[sys.executable,str(worker),'--start',str(number*10),'--seconds',str(min(10,duration-number*10)),
                     '--output',str(target)]
            with (work/f'{number:03d}-worker.log').open('a') as log:
                subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,cwd=ROOT)
        if number not in state['completed']:state['completed'].append(number)
        state.update(status='running',completed_source_seconds=min(duration,(number+1)*10),total_source_seconds=duration)
        save(state_path,state);print(f'Completed {state["completed_source_seconds"]:.1f}/{duration:.1f} seconds',flush=True)
    listing=work/'concat.txt'
    listing.write_text('\n'.join(f"file '{i:03d}.mp4'" for i in range(math.ceil(duration/10))),encoding='utf-8')
    output=work/'background-lama.mp4'
    if not output.exists():subprocess.run([str(FFMPEG),'-v','error','-n','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(output)],check=True)
    subprocess.run([str(FFMPEG),'-v','error','-xerror','-i',str(output),'-f','null','-'],check=True)
    state.update(status='candidate_complete_needs_visual_review',output=str(output),sha256=digest(output),elapsed_this_run=time.perf_counter()-start_clock)
    save(state_path,state)


if __name__=='__main__':main()
