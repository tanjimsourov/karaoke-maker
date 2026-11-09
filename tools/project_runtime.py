"""Portable project settings. Paths never depend on a sibling checkout or cwd."""
from pathlib import Path
import os
import shutil
import sys

ROOT = Path(os.environ.get('KARAOKE_PROJECT_ROOT', Path(__file__).resolve().parents[1])).resolve()


def load_env(path=None):
    """Read simple KEY=value settings without executing shell code or overriding env."""
    path = Path(path or ROOT / '.env')
    if not path.is_file():
        return
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not key.strip().replace('_', '').isalnum():
            raise ValueError(f'Invalid environment setting at {path}:{number}')
        value = value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in '\"\'':
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


load_env()


def path_setting(name, default):
    value = Path(os.path.expandvars(os.environ.get(name, str(default)))).expanduser()
    return value.resolve() if value.is_absolute() else (ROOT / value).resolve()


def python_in(environment):
    return Path(environment) / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def python_setting(name, default):
    # Linux venv/bin/python is a symlink to the base interpreter. Resolving it
    # bypasses pyvenv.cfg and loses the virtual environment's installed packages.
    value = Path(os.path.expandvars(os.environ.get(name, str(default)))).expanduser()
    return Path(os.path.abspath(value if value.is_absolute() else ROOT/value))


def executable(name, bundled):
    configured = os.environ.get(name)
    if configured:
        return path_setting(name, configured)
    candidate = ROOT / bundled
    if candidate.is_file() and os.name == 'nt':
        return candidate
    found = shutil.which('ffmpeg')
    return Path(found) if found else candidate


FFMPEG = executable('KARAOKE_FFMPEG', 'tools/ffmpeg/ffmpeg.exe')
LOGO = path_setting('KARAOKE_LOGO', 'assets/logo.png')
if not LOGO.exists() and not os.environ.get('KARAOKE_LOGO'):
    LOGO = ROOT / 'work/webmail/Logo-Karaoke-2025-WHITE.png'
DEMUCSPY = python_setting('KARAOKE_DEMUCS_PYTHON', python_in(ROOT / '.venv-demucs'))
WORK = path_setting('KARAOKE_WORK_DIR', 'work/local_open_source')
OUT = path_setting('KARAOKE_OUTPUT_DIR', 'out')
MODELS = path_setting('KARAOKE_MODEL_DIR', 'models')
MANIFEST = path_setting('KARAOKE_MANIFEST', 'local_karaoke_jobs.json')
os.environ.setdefault('HF_HOME', str(MODELS/'huggingface'))
os.environ.setdefault('TORCH_HOME', str(MODELS/'torch'))
os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT', '60')
os.environ.setdefault('HF_HUB_ETAG_TIMEOUT', '30')
# Standard HTTPS transfers are resumable and work without the optional Xet client.
os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
if os.environ.get('KARAOKE_ALLOW_MODEL_DOWNLOAD','1') != '1':
    os.environ.setdefault('HF_HUB_OFFLINE','1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE','1')


def font_file():
    requested = os.environ.get('KARAOKE_FONT')
    candidates = ([path_setting('KARAOKE_FONT', requested)] if requested else []) + [
        ROOT / 'assets/font.ttf', Path('C:/Windows/Fonts/arialbd.ttf'),
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
        Path('/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf'),
        Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf')]
    for path in candidates:
        if path.is_file():
            return path
    raise ValueError('No font found. Set KARAOKE_FONT to a readable .ttf file.')


def child_env():
    return {**os.environ, 'KARAOKE_PROJECT_ROOT': str(ROOT),
            'PATH': str(FFMPEG.parent) + os.pathsep + os.environ.get('PATH', '')}


def ffmpeg_thread_args():
    value=os.environ.get('KARAOKE_FFMPEG_THREADS')
    if value is None:return []
    if not value.isdigit() or not 1<=int(value)<=64:
        raise ValueError('KARAOKE_FFMPEG_THREADS must be 1..64')
    return ['-threads:v',str(int(value))]


def ffmpeg_input_filter_args():
    value=os.environ.get('KARAOKE_FFMPEG_FILTER_THREADS',os.environ.get('KARAOKE_FFMPEG_THREADS','2'))
    if not value.isdigit() or not 1<=int(value)<=64:
        raise ValueError('FFmpeg input/filter threads must be 1..64')
    return ['-filter_complex_threads',str(int(value)),'-threads',str(int(value))]
