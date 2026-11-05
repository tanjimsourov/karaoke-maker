"""Offline model forward-pass smoke check on a synthetic non-song fixture.

This verifies APIs/kernels, not transcription/alignment/vocal-removal accuracy.
Run after prepare_project.py; no downloads or final delivery approvals occur.
"""
import gc
import json
import os
from pathlib import Path
import subprocess
os.environ.update(KARAOKE_ALLOW_MODEL_DOWNLOAD='0', HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
from project_runtime import ROOT, MODELS, FFMPEG


def main():
    from audio_quality import decode, VoiceDetector, settings
    from faster_whisper import WhisperModel
    import torch
    import whisperx
    from low_memory_models import mapped_checkpoint_load
    path=ROOT/'tmp/runtime-smoke/source.mp4'
    if not path.is_file():
        path.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run([str(FFMPEG),'-v','error','-n','-f','lavfi','-i',
            'color=c=navy:s=1920x1080:r=25:d=4','-f','lavfi','-i',
            'sine=frequency=440:sample_rate=44100:duration=4','-c:v','libx264',
            '-preset','ultrafast','-c:a','aac','-shortest',str(path)],check=True)
    samples=decode(path)
    if samples.ndim == 2: samples=samples.mean(axis=1)
    report={'fixture':str(path),'accuracy_certified':False}
    model=WhisperModel('large-v3-turbo',device='cpu',compute_type='int8',cpu_threads=4,
        download_root=str(MODELS/'whisper'),local_files_only=True)
    segments,_=model.transcribe(samples,language='en',beam_size=1,vad_filter=False,
                                condition_on_previous_text=False)
    report['whisper_forward']={'passed':True,'segments':len(list(segments))}
    del model;gc.collect()
    checkpoint=Path(torch.hub.get_dir())/'checkpoints/wav2vec2_fairseq_large_lv60k_asr_ls960.pth'
    if not checkpoint.is_file(): raise ValueError('Alignment checkpoint missing')
    with mapped_checkpoint_load(torch,checkpoint):
        model,metadata=whisperx.load_align_model(language_code='en',device='cpu',
                            model_name='WAV2VEC2_ASR_LARGE_LV60K_960H')
    aligned=whisperx.align([{'start':0.,'end':len(samples)/16000,'text':'Setup verification works'}],
        model,metadata,samples,'cpu',return_char_alignments=False)
    report['alignment_forward']={'passed':True,'segments':len(aligned['segments']),
        'note':'Synthetic tone has no sung words; this does not assess timing accuracy.'}
    del model;gc.collect()
    detector=VoiceDetector(settings())
    detector.scan(decode(path),settings())
    report['detector_forward']={'passed':True}
    destination=ROOT/'tmp/runtime-smoke/model-forward-checks.json'
    destination.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__ == '__main__': main()
