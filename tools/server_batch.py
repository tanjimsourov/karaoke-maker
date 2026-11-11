"""Resumable folder batch. Automatic export is the default; verified review is optional."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def write_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
    temp.replace(path)

def discover(root, output, settle=30):
    root,output=root.resolve(),output.resolve()
    for parent, directories, files in os.walk(root,followlinks=False):
        parent=Path(parent)
        directories[:]=sorted(d for d in directories if not (parent/d).is_symlink()
            and not (parent/d).resolve().is_relative_to(output))
        for name in sorted(files):
            p=parent/name
            if p.suffix.lower()!='.mp4' or p.is_symlink():continue
            if p.resolve().is_relative_to(output):continue
            if p.stat().st_size and time.time()-p.stat().st_mtime>=settle:yield p

def make_job(source, language, model, threads):
    artist, separator, title=source.stem.partition(' - ')
    if not separator:artist,title='Unknown Artist',source.stem
    sidecar=source.with_suffix('.karaoke.json')
    overrides=json.loads(sidecar.read_text(encoding='utf-8')) if sidecar.exists() else {}
    if not isinstance(overrides,dict) or set(overrides)-{'title','artist','language'}:
        raise ValueError('Metadata sidecar only accepts title, artist, language: '+str(sidecar))
    return {'source':str(source.resolve()),'title':title,'artist':artist,'language':language,
        'mode':'music','background':'original','profile':'optimized',
        'separation':{'model':model,'overlap':.25},'audio_quality':{'threads':threads,'alternatives':
            ['htdemucs_ft'] if os.getenv('KARAOKE_SERVER_AUDIO_FALLBACK','0')=='1' and model=='htdemucs' else []},
        'render':{'canvas':'1920x1080','fps':'source','video_bitrate':2000000,'intro_seconds':10,'intro_countdown':True,
                  'countdown_style':os.getenv('KARAOKE_COUNTDOWN_STYLE','arc'),
                  'countdown_colour':os.getenv('KARAOKE_COUNTDOWN_COLOUR','#BB3794')},**overrides}

def receipt_matches(receipt, source_sha, recipe_sha):
    if receipt.get('status') not in ('exported','draft_exported','verified_exported') or receipt.get('source_sha256')!=source_sha \
            or receipt.get('recipe_sha256')!=recipe_sha:return False
    p=Path(receipt.get('output',''))
    return p.is_file() and p.stat().st_size<=99999999 and sha(p)==receipt.get('output_sha256')

def completed_output_matches(receipt, source_sha, output_root, verified=False):
    """Keep completed exports across code/config updates, including legacy sizes."""
    statuses=('verified_exported',) if verified else ('exported','draft_exported','verified_exported')
    if receipt.get('status') not in statuses or receipt.get('source_sha256')!=source_sha:
        return False
    path=Path(receipt.get('output',''))
    try:
        if not path.resolve().is_relative_to(output_root.resolve()) or path.suffix.lower()!='.mp4':
            return False
        return path.is_file() and path.stat().st_size>0 and sha(path)==receipt.get('output_sha256')
    except OSError:
        return False


def publish(source, destination):
    if source.stat().st_size>99999999:raise ValueError('Output exceeds 100 MB')
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():
        if sha(destination)==sha(source):return
        raise FileExistsError('Refusing to overwrite another export: '+str(destination))
    partial=destination.with_suffix('.mp4.partial')
    with source.open('rb') as incoming, partial.open('wb') as outgoing:
        shutil.copyfileobj(incoming,outgoing)
        outgoing.flush();os.fsync(outgoing.fileno())
    if sha(partial)!=sha(source):raise ValueError('Export copy checksum mismatch')
    # A single OS-locked server runner owns publication; never replace a final MP4.
    if destination.exists():raise FileExistsError(destination)
    partial.rename(destination)

def verify_existing(path):
    import av
    from project_runtime import FFMPEG
    if not 0 < path.stat().st_size <= 99999999:raise ValueError('Invalid existing export size')
    with av.open(str(path)) as media:
        if not media.streams.video or not media.streams.audio:raise ValueError('Missing media stream')
        v=media.streams.video[0]
        if (v.width,v.height)!=(1920,1080) or not v.average_rate or not 1<=float(v.average_rate)<=30.001:
            raise ValueError('Existing export has unexpected video format')
    subprocess.run([str(FFMPEG),'-v','error','-xerror','-nostdin','-i',str(path),
                    '-f','null','-'],check=True)

def cleanup_runtime(root):
    """Clear dedicated container volumes only; keep source media, models and code."""
    root=Path(root).resolve()
    for name in ('work','out','reports','tmp'):
        target=root/name
        if target.is_symlink() or target.resolve().parent!=root:
            raise ValueError('Unsafe cleanup volume: '+str(target))
        if not target.exists():continue
        for item in target.iterdir():
            if name=='work' and item.name=='.server-batch-runtime.lock':continue
            if item.is_symlink():item.unlink()
            elif item.is_dir():shutil.rmtree(item)
            else:item.unlink()

def run_one(source, root, output, report_dir, args):
    verified=getattr(args,'delivery_mode','automatic')=='verified'
    before=(source.stat().st_size,source.stat().st_mtime_ns)
    source_sha=sha(source)
    job=make_job(source,args.language,args.model,args.threads)
    identity=hashlib.sha256(str(source.relative_to(root)).encode()).hexdigest()[:20]
    receipt_path=report_dir/(identity+'.json')
    code=hashlib.sha256()
    for p in sorted((ROOT/'tools').glob('*.py')):code.update(p.name.encode());code.update(p.read_bytes())
    from project_runtime import LOGO
    recipe_sha=hashlib.sha256((json.dumps(job,sort_keys=True)+str(verified)+source_sha+code.hexdigest()+sha(LOGO)).encode()).hexdigest()
    old=json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    if not getattr(args,'reprocess_completed',False) and completed_output_matches(old,source_sha,output,verified):
        print('[SKIP COMPLETED]',source,'->',old['output'],flush=True)
        return 'skipped'
    if receipt_matches(old,source_sha,recipe_sha) and (not verified or old.get('status')=='verified_exported'):
        print('[SKIP] Verified existing export:',source,flush=True);return 'skipped'
    if old.get('status') in ('failed','needs_review') and old.get('source_sha256')==source_sha \
            and old.get('recipe_sha256')==recipe_sha and not args.retry_failed:
        print('[SKIP] Previous failure/review; use --retry-failed:',source,flush=True);return 'needs_review'
    # Preserve the source hierarchy; content/recipe identity prevents name collisions.
    destination=output/source.relative_to(root).parent/(source.stem+' - Karaoke - '+recipe_sha[:8]+'.mp4')
    if destination.exists():
        if verified:raise ValueError('Existing final has no matching verified receipt; refusing automatic acceptance')
        verify_existing(destination)
        print('[SKIP] Existing version passed media checks:',destination,flush=True)
        return 'skipped'
    record={'source':str(source),'source_sha256':source_sha,'recipe_sha256':recipe_sha,
            'output':str(destination),'status':'running','started':time.time()}
    write_json(receipt_path,record)
    runtime=ROOT/'work/server-jobs'/(hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:8]+'-'+identity)
    try:
        from workflow import normalize
        from project_runtime import OUT
        _,folder=normalize(job)
        export_dir=runtime/'exports'
        (runtime/'tmp').mkdir(parents=True,exist_ok=True)
        spec=report_dir/(identity+'.job.json');write_json(spec,job)
        job_folder=runtime/'jobs'/folder.name
        reviewed=verified and (job_folder/'full-review.json').exists()
        command=[sys.executable,'-u',str(ROOT/'karaoke.py'),'render' if reviewed else 'run','--job',str(spec),'--keep-work']
        if not reviewed:
            command.append('--draft-export' if verified else '--automatic-export')
            if verified:command.append('--verify-output')
        if args.parallel:command.append('--parallel-stages')
        print('[PROCESS]',source,flush=True)
        def complete_export():
            if before!=(source.stat().st_size,source.stat().st_mtime_ns) or sha(source)!=source_sha:
                raise ValueError('Input changed during processing; output not published')
            if verified and not reviewed:
                record.update(status='needs_review',reviewed=False,job_folder=str(job_folder),
                              review_report=str(job_folder/'delivery-verification.json'),
                              reason='Resolve lyric/timing/audio issues and approve the complete video before publication')
                print('[NEEDS REVIEW] Final withheld:',source,'Report:',record['review_report'],flush=True)
                return 'needs_review'
            artifact=export_dir/(folder.name+('_DRAFT.mp4' if verified and not reviewed else '_Karaoke.mp4'))
            if verified:
                record['delivery_review']=json.loads((job_folder/'delivery-review.json').read_text(encoding='utf-8'))
                record['verification']=json.loads((job_folder/'delivery-verification.json').read_text(encoding='utf-8'))
            publish(artifact,destination)
            status='verified_exported' if verified else 'exported'
            record.update(status=status,bytes=destination.stat().st_size,
                          output_sha256=sha(destination),reviewed=verified)
            print('[VERIFIED EXPORTED]' if verified else '[AUTOMATIC EXPORTED]',destination,flush=True)
            record['published_at']=time.time()
            write_json(receipt_path,record)
            return status
        # Console only. Keep a bounded error tail in memory, never a disk log.
        tail=deque(maxlen=80)
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                 text=True,encoding='utf-8',errors='replace',bufsize=1,
                                 env={**os.environ,'KARAOKE_OUTPUT_DIR':str(export_dir),
                                      'KARAOKE_WORK_DIR':str(runtime/'jobs'),
                                      'KARAOKE_RENDER_WORK_DIR':str(runtime/'render'),
                                      'KARAOKE_CLEANUP_AFTER_SONG':'0',
                                      'KARAOKE_SERVER_CONCURRENT':'1',
                                      'TMPDIR':str(runtime/'tmp'),'TEMP':str(runtime/'tmp'),
                                      'TMP':str(runtime/'tmp')})
        try:
            for line in process.stdout:
                print(line,end='',flush=True);tail.append(line)
                if line.startswith('[EXPORT_READY] ') and (not verified or reviewed):
                    expected=export_dir/(folder.name+('_DRAFT.mp4' if verified and not reviewed else '_Karaoke.mp4'))
                    ready=Path(json.loads(line[len('[EXPORT_READY] '):])['path'])
                    if ready.resolve()!=expected.resolve():raise ValueError('Unexpected export-ready path')
                    complete_export()
                    # The event is emitted after all worker file writes and locks finish.
                    if getattr(args,'cleanup_song',True):
                        from song_cleanup import remove_generated
                        if sha(destination)!=record['output_sha256']:raise ValueError('Published checksum changed')
                        remove_generated(runtime,ROOT/'work/server-jobs',[source,destination])
                        spec.unlink(missing_ok=True)
                        print('[CLEANUP] Published song work removed:',source.name,flush=True)
            code=process.wait()
        except BaseException:
            process.terminate();process.wait();raise
        finally:
            process.stdout.close()
        if code and record['status'] in ('exported','draft_exported','verified_exported'):
            record['shutdown_exit_code']=code
            return record['status']
        if code:
            record.update(status=('needs_review' if verified else 'skipped_invalid') if code==2 else 'failed',exit_code=code)
            print('[SOURCE NOT EXPORTED]',source,''.join(tail)[-4000:],flush=True)
            return record['status']
        if record['status'] in ('exported','draft_exported','verified_exported'):
            return record['status']
        return complete_export()
    except Exception as exc:
        record.update(status='failed',error=str(exc));print('[FAILED]',exc,flush=True)
        return 'failed'
    finally:
        record['finished']=time.time();write_json(receipt_path,record)
        if getattr(args,'cleanup_song',True):
            from song_cleanup import remove_generated
            if record['status'] in ('exported','draft_exported','verified_exported'):
                if sha(destination)!=record['output_sha256']:raise ValueError('Published file changed before cleanup')
            remove_generated(runtime,ROOT/'work/server-jobs',[source,destination])
            for path in (report_dir/(identity+'.job.json'),report_dir/(identity+'.log')):
                path.unlink(missing_ok=True)
            print('[CLEANUP] Song temporary data removed:',source.name,flush=True)



def run_with_retries(source, root, output, report_dir, args):
    """Retry operational failures without bypassing quality/review stops."""
    from copy import copy
    options=copy(args)
    for attempt in range(1, args.attempts+1):
        try:
            status=run_one(source,root,output,report_dir,options)
        except Exception as exc:
            identity=hashlib.sha256(str(source.relative_to(root)).encode()).hexdigest()[:20]
            write_json(report_dir/(identity+'.json'),{
                'source':str(source),'status':'failed','error':str(exc),'finished':time.time()})
            print('[FAILED]',source,exc,flush=True)
            status='failed'
        if status!='failed' or attempt==args.attempts:
            return {'source':str(source),'status':status,'attempts':attempt}
        print(f'[RETRY {attempt+1}/{args.attempts}]',source,flush=True)
        options.retry_failed=True
        time.sleep(min(10,attempt*2))

def run_queue(files, worker, workers):
    """Keep at most workers tasks active; refill immediately on any completion."""
    statuses=[];pending={};items=iter(files)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        def fill():
            while len(pending)<workers:
                try:source=next(items)
                except StopIteration:return
                pending[pool.submit(worker,source)]=source
        fill()
        while pending:
            completed,_=wait(pending,return_when=FIRST_COMPLETED)
            for future in completed:
                source=pending.pop(future)
                try:statuses.append(future.result())
                except Exception as exc:
                    statuses.append('failed');print('[FAILED]',source,exc,flush=True)
            fill()
    return statuses

def main():
    from project_runtime import load_env
    load_env()
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir',type=Path,default=Path(os.getenv('KARAOKE_INPUT_DIR','/media')))
    p.add_argument('--output-dir',type=Path,default=None)
    p.add_argument('--extra-input-dir',type=Path,action='append',default=[])
    p.add_argument('--language',default=os.getenv('KARAOKE_LANGUAGE','auto'))
    p.add_argument('--model',choices=['htdemucs','htdemucs_ft'],default=os.getenv('KARAOKE_SERVER_MODEL','htdemucs'))
    p.add_argument('--delivery-mode',choices=['automatic','verified','samples'],default=os.getenv('KARAOKE_DELIVERY_MODE','automatic'))
    p.add_argument('--threads',type=int,default=int(os.getenv('KARAOKE_SERVER_THREADS','1')))
    p.add_argument('--settle-seconds',type=float,default=float(os.getenv('KARAOKE_SETTLE_SECONDS','30')))
    p.add_argument('--parallel',action=argparse.BooleanOptionalAction,default=os.getenv('KARAOKE_SERVER_PARALLEL','1')=='1')
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--reprocess-completed',action='store_true',help='Apply changed code/settings to completed songs instead of keeping existing outputs')
    p.add_argument('--retry-failed',action=argparse.BooleanOptionalAction,default=True)
    p.add_argument('--attempts',type=int,default=int(os.getenv('KARAOKE_SERVER_ATTEMPTS','2')))
    p.add_argument('--limit',type=int,default=0)
    p.add_argument('--workers',type=int,default=int(os.getenv('KARAOKE_SERVER_WORKERS','3')))
    p.add_argument('--cleanup-song',action=argparse.BooleanOptionalAction,default=True)
    args=p.parse_args()
    root=args.input_dir.resolve()
    output=(args.output_dir or Path(os.getenv('KARAOKE_SERVER_OUTPUT_DIR',str(root/'karaoke')))).resolve()
    if not root.is_dir():p.error('Input directory does not exist: '+str(root))
    if output==root or not output.is_relative_to(root):p.error('Output must be a subfolder of the input root')
    if not 1<=args.workers<=6 or not 1<=args.threads<=8 or not 1<=args.attempts<=3 or args.settle_seconds<0 or args.limit<0:p.error('Invalid worker/thread/attempt/settle/limit setting')
    extra=json.loads(os.getenv('KARAOKE_EXTRA_INPUT_DIRS','[]'))
    if not isinstance(extra,list) or any(not isinstance(v,str) or not v for v in extra):p.error('KARAOKE_EXTRA_INPUT_DIRS must be a JSON list of paths')
    roots=[root]+[Path(v).resolve() for v in [*extra,*args.extra_input_dir]]
    if len(set(roots))!=len(roots):p.error('Duplicate input directories')
    if any(a!=b and a.is_relative_to(b) for a in roots for b in roots):p.error('Input directories must not overlap')
    for directory in roots:
        if not directory.is_dir():p.error('Input directory does not exist: '+str(directory))
    tasks=[]
    for directory in roots:
        destination=output if directory==root else directory/'karaoke'
        tasks.extend((source,directory,destination,destination/'.karaoke-status')
                     for source in discover(directory,destination,args.settle_seconds))
    if args.limit:tasks=tasks[:args.limit]
    files=[task[0] for task in tasks]
    if args.dry_run:
        print(json.dumps({'inputs':[str(v) for v in roots],'output':str(output),'files':[str(f) for f in files],
                          'mode':args.delivery_mode,'max_bytes':99999999},indent=2));return 0
    output.mkdir(parents=True,exist_ok=True)
    report_dir=output/'.karaoke-status';report_dir.mkdir(parents=True,exist_ok=True)
    from model_queue import model_slot
    cleanup=os.getenv('KARAOKE_CLEANUP_AFTER_RUN','0')=='1'
    if cleanup and (os.getenv('KARAOKE_SERVER_CONTAINER')!='1' or ROOT.as_posix()!='/app'):
        cleanup=False
        print('[CLEANUP] Local mode: only each completed song is cleaned; unrelated project work is preserved.',flush=True)
    statuses=[]
    with model_slot(ROOT,timeout=0,name='server-batch'):
        try:
            if cleanup:
                cleanup_runtime(ROOT)
            for directory in roots:
                status_dir=(output if directory==root else directory/'karaoke')/'.karaoke-status'
                status_dir.mkdir(parents=True,exist_ok=True)
                for pattern in ('*.log','*.job.json','batch-summary.json'):
                    for old in status_dir.glob(pattern):old.unlink()
            results=run_queue(tasks,lambda task:run_with_retries(*task,args),args.workers)
            statuses=[r['status'] if isinstance(r,dict) else r for r in results]
            counts=dict(Counter(statuses))
            print('[BATCH FINISHED]',json.dumps({'total':len(files),'counts':counts}),flush=True)
        finally:
            if cleanup:
                cleanup_runtime(ROOT)
                print('[CLEANUP] Work, staging exports, reports and temporary files removed. Sources, models and published MP4s preserved.',flush=True)
    return 2 if any(s in ('failed','needs_review') for s in statuses) else 0

if __name__=='__main__':raise SystemExit(main())
