"""Recheck existing five instrumentals against originals; read-only audio scan."""
from zoom_local_pipeline import ROOT,read,save
from local_audio_audit import compare

results=[]
for job in read(ROOT/'local_karaoke_jobs.json'):
    try:
        report=compare(ROOT/job['source'],ROOT/'work/bowlnfun'/job['slug']/'instrumental.mp3')
        results.append({'song':job['slug'],**report})
        print(job['slug'],len([x for x in report['quiet_sections'] if x['internal']]),'internal flags',flush=True)
    except Exception as exc:
        results.append({'song':job['slug'],'status':'comparison_failed','reason':str(exc)})
        print(job['slug'],str(exc),flush=True)
save(ROOT/'work/local_open_source/existing-five-audit.json',results)
