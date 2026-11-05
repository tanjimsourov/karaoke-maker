"""Run additional independent original-song examples without paid inputs.

Each stage is logged; failed examples do not prevent the next example's test.
Only technically validated PREVIEW files are copied to the review directory.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path
from zoom_local_pipeline import ROOT,read,save,digest

SLUGS=['Bliv_her_lidt_endnu','Barry_Cant_Swim_Kimbara']
BASE=ROOT/'work/local_open_source'

def run(slug,stage,args):
    folder=BASE/slug;folder.mkdir(parents=True,exist_ok=True)
    save(folder/'example-status.json',{'stage':stage,'status':'running'})
    print(slug,stage,flush=True)
    with (folder/(stage+'.log')).open('w',encoding='utf-8') as log:
        result=subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'{stage}: exit {result.returncode}; see {folder/(stage+".log")}')

def main():
    os.environ['PYTHONUTF8']='1'
    jobs={j['slug']:j for j in read(ROOT/'local_karaoke_jobs.json')}
    results={};original_outputs={}
    for p in (ROOT/'out').glob('*.mp4'):original_outputs[str(p)]=digest(p)
    save(BASE/'examples-baseline.json',original_outputs)
    # Serial separation avoids competing for memory with the large ASR model.
    for slug in SLUGS:
        try:run(slug,'separate',['tools/local_karaoke.py','separate','--song',slug])
        except Exception as exc:results[slug]={'status':'blocked','error':str(exc)}
    for slug in SLUGS:
        if slug in results:continue
        job=jobs[slug];folder=BASE/slug;draft=folder/'vocals-medium-draft.json'
        try:
            run(slug,'audit',['tools/local_karaoke.py','audit','--song',slug])
            if not draft.exists():
                run(slug,'transcribe',['tools/transcribe_local_draft.py','--source',folder/'stems/vocals.wav',
                    '--output',draft,'--model','medium','--language',job['language']])
            work=folder/'vocal_aligned_preview'
            if not (work/'preview-validation.json').exists():
                run(slug,'preview',['tools/build_original_local_preview.py','--song',slug,'--draft',draft])
            validation=read(work/'preview-validation.json');source=Path(validation['output'])
            assert digest(source)==validation['sha256']
            run(slug,'contact',['tools/karaoke_contact_sheet.py','--video',source,'--output',folder/'review_contact.jpg',
                '--times',','.join(map(str,[1,2.7,15,45,90,max(91,validation['duration']-12)]))])
            results[slug]={'status':'technical_checks_passed_needs_visual_and_listening_review',
                'video':str(source),'validation':validation,'audit':read(folder/'audio-audit.json'),
                'paid_operations':0,'asr_model':'medium','transcript':str(draft)}
        except Exception as exc:
            results[slug]={'status':'blocked','error':str(exc)}
        save(folder/'example-status.json',results[slug]);save(BASE/'examples-results.json',results)
    assert all(digest(Path(p))==sha for p,sha in original_outputs.items()),'Existing output changed'
    save(BASE/'examples-results.json',results)
    print(results,flush=True)

if __name__=='__main__':main()
