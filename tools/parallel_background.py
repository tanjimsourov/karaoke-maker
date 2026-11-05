"""Isolated background preparation overlapping the audio pipeline."""
import json
import os
from pathlib import Path
import subprocess
import sys


class BackgroundJob:
    def __init__(self, source, folder, optimized):
        self.folder = Path(folder)
        self.source = str(source)
        self.optimized = optimized

    def __enter__(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder/'result.json').unlink(missing_ok=True)
        # Separate folder from the foreground renderer's cache avoids partial reads.
        self.process = subprocess.Popen(
            [sys.executable, '-u', __file__, self.source, str(self.folder),
             'optimized' if self.optimized else 'standard'],
            env={**os.environ, 'OMP_NUM_THREADS':'2', 'MKL_NUM_THREADS':'2'})
        print('[PARALLEL] Background screening started alongside audio stages', flush=True)
        return self

    def result(self):
        code = self.process.wait()
        if code:
            raise ValueError(f'Background preparation failed (exit {code}); see console output')
        return json.loads((self.folder/'result.json').read_text(encoding='utf-8'))

    def __exit__(self, kind, value, tb):
        # Do not leave a writer running after releasing the job lock.
        if kind is not None and self.process.poll() is None:
            self.process.terminate()
        self.process.wait()


def main():
    from stage_metrics import call
    from zoom_local_pipeline import digest
    source, folder, profile = sys.argv[1:]
    folder = Path(folder)
    if profile == 'optimized':
        from inline_branding import prepare
        background, plan = call(folder, 'background_preparation', prepare, source, folder)
    else:
        from branding_guard import prepare_background
        background = call(folder, 'background_preparation', prepare_background, source, folder)
        plan = None
    result = {'background':str(background), 'source_sha256':digest(source),
              'plan':str(plan) if plan else None}
    temporary = folder/'result.tmp'
    temporary.write_text(json.dumps(result), encoding='utf-8')
    temporary.replace(folder/'result.json')


if __name__ == '__main__':
    main()
