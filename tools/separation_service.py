"""One bounded resident Demucs worker, using the existing separation CLI."""
import atexit
import contextlib
import json
import os
import queue
import subprocess
import sys
import threading
from project_runtime import DEMUCSPY,ROOT,child_env

class Worker:
    def __init__(self):
        self.process=subprocess.Popen([str(DEMUCSPY),str(Path(__file__).resolve()),'--serve'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding='utf-8',env=child_env())
        self.results=queue.Queue()
        def reader():
            for line in self.process.stdout:self.results.put(line)
            self.results.put(None)
        threading.Thread(target=reader,daemon=True).start()
    def run(self,args):
        request={'args':args,'cache':os.environ.get('KARAOKE_AUDIO_CACHE')}
        self.process.stdin.write(json.dumps(request)+'\n');self.process.stdin.flush()
        try:line=self.results.get(timeout=14400)
        except queue.Empty:
            self.close();raise TimeoutError('Resident separation exceeded four hours; see worker logs')
        if line is None:raise RuntimeError('Resident separator exited unexpectedly')
        result=json.loads(line)
        if not result['ok']:raise RuntimeError(result['error'])
        return result
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=10)

from pathlib import Path
_worker=None
def run(args):
    global _worker
    if _worker is None:
        _worker=Worker();atexit.register(_worker.close)
    _worker.run(args)

def serve():
    # Imports and inference progress must not corrupt the JSON response channel.
    with contextlib.redirect_stdout(sys.stderr):
        import separate_local_stems
    os.environ['KARAOKE_KEEP_MODELS']='1'
    for line in sys.stdin:
        try:
            request=json.loads(line)
            if request['cache']:os.environ['KARAOKE_AUDIO_CACHE']=request['cache']
            else:os.environ.pop('KARAOKE_AUDIO_CACHE',None)
            sys.argv=['separate_local_stems',*request['args']]
            with contextlib.redirect_stdout(sys.stderr):separate_local_stems.main()
            from model_reuse import stats
            result={'ok':True,'model_reuse':dict(stats)}
        except (Exception,SystemExit) as exc:result={'ok':False,'error':str(exc)}
        print(json.dumps(result),flush=True)

if __name__=='__main__':serve()
