"""Export source-corrected Babylon candidates without replacing prior deliveries."""
from pathlib import Path
from project_runtime import ROOT
from zoom_local_pipeline import read, save, digest, render
from replace_backing import replace, video_hash


def main():
    work = ROOT/'work/babylon-reference-repair'
    background = work/'background-glyph.mp4'
    receipt = read(background.with_suffix('.json'))
    if receipt.get('visual_review') != 'accepted':
        raise ValueError('Background candidate has not passed visual review; refusing export')
    if digest(background) != receipt['output_sha256']:
        raise ValueError('Background is incomplete or changed')
    cfg = read(work/'config.json')
    cfg['background'] = str(background)
    cfg['render']['preset'] = 'fast'
    save(work/'config.json', cfg)
    prior = work/'preview-validation.json'
    if prior.exists():
        picture = Path(read(prior)['output'])
        if digest(picture) != read(prior)['sha256']:
            raise ValueError('Staged picture changed')
    else:
        render(cfg, work, preview=True)
        picture = Path(read(prior)['output'])
    destination = ROOT/'out/comparison/repaired-drafts'
    results = {}
    sources = {
        'htdemucs (light)': ROOT/'out/Taylor Swift - Babylon - htdemucs - BENCHMARK.mp4',
        'htdemucs_ft (heavy)': ROOT/'out/Taylor Swift - Babylon - BENCHMARK.mp4',
    }
    for label, source in sources.items():
        target = destination/f'Taylor Swift - Babylon - {label} - REPAIRED DRAFT.mp4'
        if target.exists():
            r = read(target.with_suffix('.replacement.json'))
            if digest(target) != r['sha256']:
                raise ValueError('Previously exported candidate changed')
            results[label] = r
        else:
            results[label] = replace(picture, source, target, copy_audio=True)
    if len({video_hash(r['output']) for r in results.values()}) != 1:
        raise ValueError('Comparison pictures differ')
    save(destination/'repair-status.json', {
        'status': 'improved drafts; not final certification', 'outputs': results,
        'corrections': str(work/'corrections.json'),
        'timing_review': read(work/'timing-qa.json'),
        'limitations': [
            'Selective letter cleanup can leave ghosts and affect scenery under letters.',
            'Source-text corrections are not full listening/lyric approval.',
            'Existing possible-vocal audio flags remain; neither backing was re-separated.',
        ],
    })
    print('Candidate exports completed:', destination, flush=True)


if __name__ == '__main__':
    main()
