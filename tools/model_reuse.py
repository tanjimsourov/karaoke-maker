"""Bounded process-local reuse, opt-in for warmed-up batch processing."""
import gc
import os

_models={}
stats={'loads':0,'hits':0}

def get(kind,key,load):
    # Serialize model initialization/downloads, not inference, for folder workers.
    def safe_load():
        if os.environ.get('KARAOKE_SERVER_CONCURRENT')=='1':
            from model_queue import model_slot
            with model_slot(name='model-download'):return load()
        return load()
    if os.environ.get('KARAOKE_KEEP_MODELS')!='1':return safe_load()
    item=_models.get(kind)
    if item and item[0]==key:
        stats['hits']+=1
        return item[1]
    _models.pop(kind,None)
    # Retain at most one model family: separation, ASR, or alignment. This
    # prevents a warm CPU/GPU run from accumulating all three large models.
    item=None
    _models.clear();gc.collect()
    result=safe_load();stats['loads']+=1;_models[kind]=(key,result)
    return result

def clear():
    _models.clear();gc.collect()
