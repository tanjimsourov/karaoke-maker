"""Source-backed checks for existing karaoke tracks; no separation or singing ASR."""
from pathlib import Path
from zoom_local_pipeline import digest,read,save
from screen_sweep import validate_cues


def audit(cfg,folder):
    source=Path(cfg['vocal_reference'])
    if Path(cfg['zoom_video']).resolve()!=source.resolve():
        raise ValueError('Screen karaoke backing must be the original source')
    source_sha=digest(source)
    report={'source_sha256':source_sha,'backing_sha256':source_sha,
            'status':'original_source_audio_preserved',
            'warning':'No vocal removal performed. Any vocals in the source remain.'}
    save(folder/'audio-audit.json',report)
    return report


def timing(cfg,folder):
    import av
    with av.open(cfg['zoom_video']) as media:
        duration=media.duration/av.time_base
    segments=validate_cues(read(folder/'aligned.json'),duration,require_sweep=True)
    report={'basis':'measured_source_screen_sweep','words':sum(len(s['words']) for s in segments),
            'issues':[],'status':'structure_validated',
            'warning':'Valid samples do not prove OCR completeness or lyric spelling.'}
    save(folder/'timing-report.json',report)
    return report
