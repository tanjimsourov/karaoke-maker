"""Isolated subprocess entry point for the bundled, proven Zoom OCR importer."""
import argparse
import json
from pathlib import Path
import sys
from project_runtime import ROOT, FFMPEG, LOGO


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--profile', choices=['white-blue','blue-yellow'], default='white-blue')
    a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT/'tools/zoom_import'))
    import converter
    cfg = {'ffmpeg': str(FFMPEG), 'logo': str(LOGO), 'backgrounds': [str(LOGO)]*2,
           'work_dir': str(a.output/'scan'), 'output_dir': str(a.output), 'jobs': []}
    job = {'source': str(a.source.resolve()), 'title': a.source.stem, 'artist': '',
           'profile': a.profile, 'background': 0}
    folder, state = converter.job_state(cfg, job)
    converter.extract(cfg, job, folder, state)
    cues = converter.read(folder/'cues.json')
    converter.validate_cues(cues, state['duration'])
    # Keep measured sweep samples in aligned.json for review; OCR is never auto-approved.
    converter.save(a.output/'aligned.json', [dict(c, words=c['words']) for c in cues])
    converter.save(a.output/'import.json', {'source_sha256': converter.digest(a.source),
        'cues': str(folder/'cues.json'), 'status': 'needs_full_source_screen_review'})


if __name__ == '__main__': main()
