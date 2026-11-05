"""Pick the compute device for local models: CUDA when available, else CPU.

Set KARAOKE_DEVICE=cpu or KARAOKE_DEVICE=cuda to override the automatic choice.
"""
import os


def best_device():
    forced = os.environ.get('KARAOKE_DEVICE', '').strip().lower()
    if forced in ('cpu', 'cuda'):
        if forced=='cuda':
            import torch
            if not torch.cuda.is_available():raise ValueError('CUDA requested but unavailable in this Python environment')
        return forced
    if forced:
        raise ValueError('KARAOKE_DEVICE must be cpu or cuda')
    # A CPU-only wheel cannot expose CUDA. Avoid loading PyTorch merely to ask
    # this question: faster-whisper uses CTranslate2, and loading both runtimes
    # consumed the memory needed to load its recognition model on this host.
    from importlib.metadata import version, PackageNotFoundError
    try:
        if '+cpu' in version('torch'):
            return 'cpu'
    except PackageNotFoundError:
        pass
    try:
        import torch
        return 'cuda' if torch.cuda.is_available() else 'cpu'
    except ImportError:
        return 'cpu'


def whisper_compute_type(device):
    """float16 on GPU; int8 keeps CPU transcription fast and small."""
    return 'float16' if device == 'cuda' else 'int8'
