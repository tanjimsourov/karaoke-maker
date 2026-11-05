"""Tempo and beat times of the backing track, for snapping lyric lines.

Uses librosa when installed; otherwise a built-in numpy/scipy tracker
(spectral-flux onsets, autocorrelation tempo, dynamic-programming beats after
Ellis 2007, the same method librosa uses), so no extra package is required.
"""
from __future__ import annotations
import numpy as np

NPERSEG = 1024
HOP = 128  # 8 ms at 16 kHz: fine enough that integer beat periods are within ~1% of the tempo


def onset_envelope(samples, rate):
    """Positive spectral flux on a log-magnitude spectrogram, one value per hop."""
    from scipy.signal import stft
    _, _, spectrum = stft(samples, rate, nperseg=NPERSEG, noverlap=NPERSEG - HOP, boundary=None)
    magnitude = np.log1p(100 * np.abs(spectrum))
    flux = np.maximum(0, np.diff(magnitude, axis=1)).sum(axis=0)
    flux = np.concatenate([[0], flux])
    flux -= np.convolve(flux, np.ones(16) / 16, mode='same')  # remove slow loudness drift
    flux = np.maximum(flux, 0)
    return flux / (flux.std() + 1e-9)


def estimate_period(envelope, frames_per_second, low=60, high=180):
    """Beat period (in frames) from the autocorrelation peak, weighted toward ~120 BPM."""
    n = len(envelope)
    ac = np.correlate(envelope, envelope, mode='full')[n - 1:]
    lags = np.arange(len(ac))
    bpm = 60 * frames_per_second / np.maximum(lags, 1)
    valid = (bpm >= low) & (bpm <= high)
    # Log-normal preference around 120 BPM avoids picking half/double tempo.
    prior = np.exp(-0.5 * (np.log2(np.maximum(bpm, 1) / 120) / 0.9) ** 2)
    score = np.where(valid, ac * prior, -np.inf)
    return int(np.argmax(score))


def track_beats(envelope, period, tightness=100.0):
    """Dynamic programming: beats sit on strong onsets about one period apart."""
    n = len(envelope)
    score = envelope.copy()
    backlink = np.full(n, -1)
    window = np.arange(-2 * period, -period // 2 + 1)
    penalty = -tightness * np.log(-window / period) ** 2
    for i in range(n):
        candidates = i + window
        ok = candidates >= 0
        if not ok.any():
            continue
        values = score[candidates[ok]] + penalty[ok]
        best = int(np.argmax(values))
        score[i] += values[best]
        backlink[i] = candidates[ok][best]
    # Start from the best-scoring frame in the final period and walk back.
    tail = np.arange(max(0, n - period), n)
    beat = int(tail[np.argmax(score[tail])])
    beats = []
    while beat >= 0:
        beats.append(beat)
        beat = int(backlink[beat])
    return np.array(beats[::-1])


def builtin_beats(samples, rate):
    envelope = onset_envelope(samples.astype(np.float64), rate)
    frames_per_second = rate / HOP
    period = estimate_period(envelope, frames_per_second)
    frames = track_beats(envelope, period)
    # Frame k's window is centred NPERSEG/2 samples after k*HOP: report onset times, not window starts.
    return 60 * frames_per_second / period, ((frames * HOP + NPERSEG // 2) / rate).tolist()


def detect_beats(samples, rate=16000, subdivision=1):
    """Returns (bpm, beat_times). subdivision=2 adds the half-beats between beats."""
    try:
        import librosa
        tempo, frames = librosa.beat.beat_track(y=samples.astype(np.float32), sr=rate, units='frames')
        bpm, times = float(np.atleast_1d(tempo)[0]), librosa.frames_to_time(frames, sr=rate).tolist()
    except ImportError:
        bpm, times = builtin_beats(samples, rate)
    if subdivision > 1 and len(times) > 1:
        fine = []
        for a, b in zip(times, times[1:]):
            fine += [a + (b - a) * k / subdivision for k in range(subdivision)]
        times = fine + [times[-1]]
    return bpm, [round(t, 3) for t in times]
