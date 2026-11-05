"""Resumable parallel downloads using the user's saved WinSCP site (no stored credentials here)."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import time

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--winscp',default=r'C:\Program Files (x86)\WinSCP\WinSCP.com')
    a=p.parse_args();cfg=json.loads(a.manifest.read_text(encoding='utf-8'))
    dest=Path(cfg['destination']);dest.mkdir(parents=True,exist_ok=True)
    reports=a.manifest.parent
    def quoted(value):
        if any(c in str(value) for c in '\r\n"'):raise ValueError('Unsupported command character')
        return '"'+str(value)+'"'
    def one(item):
        name=item['name']
        if Path(name).name!=name or '/' in name:raise ValueError('Expected a basename')
        target=dest/name;partial=dest/(name+'.script-part')
        key=hashlib.sha256(name.encode()).hexdigest()[:12]
        receipt=reports/(key+'.json');log=reports/(key+'.log');script=reports/(key+'.txt')
        if target.exists():
            if target.stat().st_size==item['bytes']:
                return {'name':name,'status':'existing_not_overwritten'}
            raise FileExistsError(target)
        started=time.time();initial=partial.stat().st_size if partial.exists() else 0
        script.write_text('\n'.join(['option batch abort','option confirm off',
            'open '+quoted(cfg['session']),
            'get -transfer=binary -resumesupport=on -resume -speed=0 '+quoted(cfg['remote_dir'].rstrip('/')+'/'+name)+' '+quoted(partial),
            'exit'])+'\n',encoding='utf-8-sig')
        row={'name':name,'status':'downloading','started':started,'expected_bytes':item['bytes'],'partial':str(partial),'output':str(target)}
        def save():receipt.write_text(json.dumps(row,indent=2),encoding='utf-8')
        save()
        for attempt in range(1,4):
            with log.open('a',encoding='utf-8') as f:
                r=subprocess.run([a.winscp,'/script='+str(script.resolve())],stdout=f,stderr=subprocess.STDOUT)
            row['attempt']=attempt
            if r.returncode==0:break
            row['status']='retrying';save()
        else:
            row['status']='failed';save();return row
        if not partial.exists() or partial.stat().st_size!=item['bytes']:
            row['status']='size_mismatch';save();return row
        row['transfer_seconds']=time.time()-started
        row['average_KiB_s']=(item['bytes']-initial)/1024/row['transfer_seconds']
        row['status']='verifying';save()
        from project_runtime import FFMPEG
        with log.open('a',encoding='utf-8') as f:
            result=subprocess.run([str(FFMPEG),'-v','error','-xerror','-i',str(partial),'-map','0:v:0','-map','0:a:0','-f','null','-'],stdout=f,stderr=subprocess.STDOUT)
        if result.returncode:
            row['status']='decode_failed';save();return row
        h=hashlib.sha256()
        with partial.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        row['sha256']=h.hexdigest();partial.rename(target)
        row['status']='completed';row['finished']=time.time();save();return row
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(one,cfg['files']))
    (reports/'downloads.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    return int(any(r['status'] not in ('completed','existing_not_overwritten') for r in results))

if __name__=='__main__':raise SystemExit(main())
