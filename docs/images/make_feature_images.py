"""Generate the feature infographics in docs/images (one PNG per main feature).

Each image: title, numbered stage cards joined by arrows (the working process),
sub-features with icons inside each card, and a strip of cross-cutting features.
Rendered to PNG with headless Edge/Chrome. Run:  python docs/images/make_feature_images.py
"""
from __future__ import annotations
import html
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGO = HERE / 'logo_SMC.png'  # SMC brand mark shown in every header
WIDTH, HEIGHT = 1920, 1080
BROWSERS = [r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
            r'C:\Program Files\Google\Chrome\Application\chrome.exe']

# Lucide icon paths (ISC licence), 24x24 stroke icons.
ICONS = {
    'music': '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    'database': '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
    'cpu': '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M15 2v2M15 20v2M2 15h2M2 9h2M20 15h2M20 9h2M9 2v2M9 20v2"/>',
    'layers': '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    'mic': '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/>',
    'wave': '<path d="M2 13a2 2 0 0 0 2-2V7a2 2 0 0 1 4 0v13a2 2 0 0 0 4 0V4a2 2 0 0 1 4 0v13a2 2 0 0 0 4 0v-4a2 2 0 0 1 2-2"/>',
    'check': '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    'shield': '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    'clock': '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    'type': '<path d="M4 7V4h16v3M9 20h6M12 4v16"/>',
    'languages': '<path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="m22 22-5-10-5 10"/><path d="M14 18h6"/>',
    'globe': '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
    'sparkles': '<path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.13-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.14a.5.5 0 0 1 .96 0L14.06 8.5A2 2 0 0 0 15.5 9.94l6.14 1.58a.5.5 0 0 1 0 .96L15.5 14.06a2 2 0 0 0-1.44 1.44l-1.58 6.14a.5.5 0 0 1-.96 0z"/>',
    'book': '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>',
    'file': '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8M16 13H8M16 17H8"/>',
    'list': '<path d="M3 12h.01M3 18h.01M3 6h.01M8 12h13M8 18h13M8 6h13"/>',
    'sliders': '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M2 14h4M10 8h4M18 16h4"/>',
    'palette': '<circle cx="13.5" cy="6.5" r="1"/><circle cx="17.5" cy="10.5" r="1"/><circle cx="8.5" cy="7.5" r="1"/><circle cx="6.5" cy="12.5" r="1"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.93 0 1.65-.75 1.65-1.69 0-.44-.18-.84-.44-1.12-.29-.29-.44-.65-.44-1.13a1.64 1.64 0 0 1 1.67-1.67h2c3.05 0 5.55-2.5 5.55-5.55C21.97 6.01 17.46 2 12 2z"/>',
    'image': '<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21"/>',
    'film': '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 3v18M3 7.5h4M3 12h18M3 16.5h4M17 3v18M17 7.5h4M17 16.5h4"/>',
    'move': '<path d="M12 2v20M2 12h20"/><path d="m15 19-3 3-3-3M19 9l3 3-3 3M5 9l-3 3 3 3M9 5l3-3 3 3"/>',
    'volume': '<path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
    'refresh': '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    'gear': '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    'download': '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5M12 15V3"/>',
    'gauge': '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    'undo': '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>',
    'eye': '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
    'play': '<circle cx="12" cy="12" r="10"/><path d="m10 8 6 4-6 4z"/>',
    'zap': '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
    'users': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    'scissors': '<circle cx="6" cy="6" r="3"/><path d="M8.12 8.12 12 12M20 4 8.12 15.88"/><circle cx="6" cy="18" r="3"/><path d="M14.8 14.8 20 20"/>',
    'split': '<path d="M16 3h5v5M8 3H3v5"/><path d="M12 22v-8.3a4 4 0 0 0-1.17-2.87L3 3"/><path d="m15 9 6-6"/>',
    'merge': '<path d="m8 6 4-4 4 4"/><path d="M12 2v10.3a4 4 0 0 1-1.17 2.87L4 22"/><path d="m20 22-5-5"/>',
    'trash': '<path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    'plus': '<circle cx="12" cy="12" r="10"/><path d="M8 12h8M12 8v8"/>',
    'pencil': '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>',
    'search': '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    'alert': '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
    'lock': '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    'server': '<rect width="20" height="8" x="2" y="2" rx="2"/><rect width="20" height="8" x="2" y="14" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
    'monitor': '<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8M12 17v4"/>',
    'phone': '<rect width="14" height="20" x="5" y="2" rx="2"/><path d="M12 18h.01"/>',
    'activity': '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    'terminal': '<path d="m4 17 6-6-6-6M12 19h8"/>',
    'package': '<path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5M12 22V12"/>',
    'clipboard': '<rect width="8" height="4" x="8" y="2" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
    'history': '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    'timer': '<path d="M10 2h4M12 14l3-3"/><circle cx="12" cy="14" r="8"/>',
    'tag': '<path d="M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.42l8.7 8.7a2.43 2.43 0 0 0 3.42 0l6.58-6.58a2.43 2.43 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
}

CARD_TINTS = ['#ffffff', '#f2f7ff', '#effaf8', '#f6f3ff', '#f3f8ff']
NUMBER_COLOURS = ['#1559d6', '#1559d6', '#11998e', '#5b3fd1', '#1559d6']
ICON_COLOURS = ['#1559d6', '#11998e', '#e8892a', '#5b3fd1', '#d63a6b', '#0e8ac7']


def icon(name, colour, size=30):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{colour}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')


def card(index, stage):
    number = stage.get('number', str(index + 1))
    colour = NUMBER_COLOURS[index % len(NUMBER_COLOURS)]
    badge = (f'<div class="badge" style="background:{colour}">{number}</div>' if number != '✓' else
             f'<div class="badge" style="background:{colour}"><svg width="30" height="30" viewBox="0 0 24 24" '
             f'fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"><path d="m5 12 5 5 9-10"/></svg></div>')
    items = ''.join(
        f'<div class="item">{icon(i, ICON_COLOURS[n % len(ICON_COLOURS)], 34)}'
        f'<div><b>{html.escape(t)}</b><span>{html.escape(d)}</span></div></div>'
        for n, (i, t, d) in enumerate(stage['items']))
    output = ''
    if stage.get('output'):
        output = (f'<div class="output">{icon("database", colour, 34)}<div><b style="color:{colour}">Output</b>'
                  f'<span>{html.escape(stage["output"])}</span></div></div>')
    return (f'<section class="card" style="background:{CARD_TINTS[index % len(CARD_TINTS)]}">{badge}'
            f'<h2 style="color:{colour}">{html.escape(stage["title"])}</h2>'
            f'<div class="items">{items}</div>{output}</section>')


def page(spec):
    arrow = ('<div class="arrow"><svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#173a7a" '
             'stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h15M13 6l6 6-6 6"/></svg></div>')
    cards = arrow.join(card(i, s) for i, s in enumerate(spec['stages']))
    strip = '<div class="sep"></div>'.join(
        f'<div class="foot">{icon(i, "#1559d6", 46)}<div><b>{html.escape(t)}</b><span>{html.escape(d)}</span></div></div>'
        for i, t, d in spec['strip'])
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0}}
body{{width:{WIDTH}px;height:{HEIGHT}px;background:#fff;font-family:"Segoe UI",Arial,sans-serif;color:#1d2433;padding:26px 30px}}
header{{display:flex;align-items:center;justify-content:center;gap:22px;margin-bottom:6px}}
.brand{{width:110px;height:auto}}
h1{{font-size:68px;font-weight:700;color:#14213d;letter-spacing:-1px;line-height:1}}
h1 small{{display:block;font-size:24px;font-weight:400;color:#4a5568;letter-spacing:0;margin-top:8px}}
.row{{display:flex;align-items:stretch;gap:0;margin-top:18px;height:{HEIGHT - 330}px}}
.card{{flex:1;border:2px solid #d6e2f5;border-radius:22px;padding:18px 16px;display:flex;flex-direction:column;align-items:center}}
.arrow{{display:flex;align-items:center;padding:0 4px}}
.badge{{width:54px;height:54px;border-radius:50%;color:#fff;font-size:30px;font-weight:700;display:grid;place-items:center}}
h2{{font-size:28px;line-height:1.15;text-align:center;margin:12px 0 16px;min-height:66px;display:flex;align-items:center}}
.items{{width:100%;display:flex;flex-direction:column;gap:14px;flex:1}}
.item{{display:flex;gap:12px;align-items:flex-start;background:#fff;border:1px solid #e3eaf5;border-radius:12px;padding:15px 14px}}
.item svg{{flex:none;margin-top:2px}}
.item b{{display:block;font-size:20.5px;color:#14213d}}
.item span{{display:block;font-size:16.5px;color:#566074;line-height:1.3}}
.output{{width:100%;display:flex;gap:12px;align-items:center;border-top:1px solid #d6e2f5;padding-top:12px;margin-top:10px}}
.output b{{display:block;font-size:18px}}.output span{{font-size:15px;color:#3a4458;line-height:1.25}}
.strip{{display:flex;align-items:center;border:2px solid #1559d6;border-radius:18px;margin:26px 40px 0;padding:20px 28px}}
.foot{{flex:1;display:flex;gap:16px;align-items:center}}
.foot b{{display:block;font-size:19px;color:#1559d6}}.foot span{{font-size:15px;color:#3a4458;line-height:1.3}}
.sep{{width:1px;height:58px;background:#c9d6ea;margin:0 22px}}
.dense .card{{padding:16px 10px}}.dense .arrow{{padding:0}}.dense .arrow svg{{width:30px;height:30px}}
.dense h2{{font-size:23px;min-height:58px;margin:10px 0 12px}}.dense .items{{gap:10px}}
.dense .item{{padding:10px 9px;gap:9px}}.dense .item svg{{width:26px;height:26px}}
.dense .item b{{font-size:16.5px}}.dense .item span{{font-size:13.5px}}
.dense .output span{{font-size:14px}}
</style></head><body class="{'dense' if len(spec['stages']) > 6 else ''}">
<header><img class="brand" src="{LOGO.as_uri()}" alt="SMC">
<h1>{html.escape(spec["title"])}<small>{html.escape(spec["subtitle"])}</small></h1></header>
<div class="row">{cards}</div><div class="strip">{strip}</div></body></html>'''


SPECS = {
    '00_overview': {
        'logo': 'mic', 'title': 'karaoke-maker',
        'subtitle': 'SMC powered Karaoke AI tool',
        'stages': [
            {'title': 'Song Input', 'items': [('music', 'Audio files', 'MP3, WAV, M4A, FLAC'),
                ('file', 'Lyrics (optional)', 'Your own .txt'), ('image', 'Background', 'Image or video'),
                ('plus', 'add command', 'Into the song list'), ('globe', 'Language', 'Fixed or auto-detect'), ('check', 'doctor', 'Checks every file')], 'output': 'Song job'},
            {'title': 'Vocal Removal', 'items': [('layers', 'Demucs', 'Vocals, drums, bass, other'),
                ('sparkles', 'BS-Roformer', 'Optional ensemble'), ('users', 'UVR Karaoke', 'Keep backing choir'),
                ('shield', 'Audio audit', 'Silence & duration checks'), ('lock', 'Hash-locked', 'Safe stem reuse'), ('zap', 'Prefetch', 'Next song in parallel')], 'output': 'Instrumental + stems'},
            {'title': 'Lyrics & Timing', 'items': [('mic', 'Whisper turbo', 'Hears the vocal stem'),
                ('file', 'Your lyrics', 'Placed on Whisper timing'), ('clock', 'WhisperX', 'Word-by-word timing'),
                ('alert', 'Timing check', 'Flags bad words'), ('users', 'Duet parts', 'M / F / D'), ('history', 'Lyric history', 'Restore any version')], 'output': 'Reviewed word timings'},
            {'title': 'Translation', 'items': [('sparkles', 'AI 5-pass', 'OpenL-style quality'),
                ('book', 'Opus-MT', 'Fast offline option'), ('list', 'Glossary & style', 'Your tone'),
                ('database', 'Memory', 'Corrections reused'), ('check', 'Back-check', 'Flags meaning drift'), ('type', 'Below / only', 'How it shows on screen')], 'output': 'Reviewed translation'},
            {'title': 'Editor', 'items': [('pencil', 'Lyric edits', 'Text, insert, split, merge'),
                ('move', 'Timing edits', 'Shift, word times, beats'), ('palette', 'Styles & layers', 'Text, media, audio'),
                ('undo', 'Undo history', 'Every change saved'), ('move', 'Keyframes', 'Move, scale, fade, rotate'), ('activity', 'Snap to beat', 'Built-in BPM tracker')], 'output': 'Final lyrics & design'},
            {'title': 'Rendering', 'items': [('monitor', 'Any canvas', '16:9, 9:16, square, 4K'),
                ('list', 'Templates', '4 / 2 / 1-line pages'), ('sparkles', 'Motion graphics', 'Intro, countdowns, pan'),
                ('gauge', 'Pro audio', '-14 LUFS, fades, key'), ('mic', 'Guide vocal', 'Quiet original singer'), ('film', '24-60 fps', 'H.264 + AAC')], 'output': 'Branded MP4'},
            {'number': '✓', 'title': 'Review & Delivery', 'items': [('zap', 'One-command draft', 'Queue, parallel'),
                ('play', 'Preview & clip', 'Watch before approving'), ('clipboard', 'Approve', 'Hash-locked sign-off'),
                ('download', 'Extras', 'LRC, thumbnail, teaser'), ('shield', 'Final checks', 'Size, duration, audio'), ('lock', 'Never overwrites', 'Safe delivery to out/')]},
        ],
        'strip': [('lock', '100% local', 'No paid API, no login'), ('shield', 'Review gates', 'Hash-locked approvals'),
                  ('cpu', 'GPU or CPU', 'CUDA used automatically'), ('terminal', 'Setup & doctor', 'One script, full health check')],
    },
    '01_vocal_removal': {
        'logo': 'layers', 'title': 'Vocal Removal',
        'subtitle': 'Clean instrumentals from any song with open AI models (all < 0.1B params)',
        'stages': [
            {'title': 'Original Song', 'items': [('music', 'Source audio', 'MP3, WAV, M4A, FLAC'),
                ('lock', 'SHA-256 fingerprint', 'Stems tied to this exact file'),
                ('cpu', 'Device', 'CUDA GPU or CPU, automatic')], 'output': 'Decoded 44.1 kHz stereo'},
            {'title': 'Demucs htdemucs_ft', 'items': [('mic', 'Vocals', 'Lead + backing voices'),
                ('activity', 'Drums', 'Separate stem'), ('wave', 'Bass', 'Separate stem'),
                ('music', 'Other', 'Guitars, keys, synths')], 'output': 'drums + bass + other = instrumental'},
            {'title': 'Ensemble (optional)', 'items': [('sparkles', 'BS-Roformer', '~93M params, SOTA vocals'),
                ('merge', 'Average of 2 models', 'Cancels each model\'s bleed'),
                ('check', 'Same timeline', 'Sample-exact alignment')], 'output': 'Cleaner vocals & instrumental'},
            {'title': 'Lead / Backing (optional)', 'items': [('users', 'UVR MDX Karaoke 2', '~30M params'),
                ('mic', 'lead_vocals.wav', 'Used for alignment'),
                ('music', 'instrumental_with_backing', 'Choir stays in the music')], 'output': 'Lead-only removal'},
            {'number': '✓', 'title': 'Verified Stems', 'items': [('file', 'separation.json', 'Settings + file hashes'),
                ('shield', 'Audio audit', 'Silence, duration, stereo'), ('refresh', 'Safe reuse', 'Never reuses changed stems'),
                ('zap', 'Background prefetch', 'Next song while you work')]},
        ],
        'strip': [('lock', 'Hash-locked', 'Changed source = new stems'), ('gauge', 'Common gain', 'Anti-clipping, float32 WAV'),
                  ('cpu', 'GPU / CPU', 'Same result, only speed differs'), ('package', 'audio-separator', 'One package, two models')],
    },
    '02_lyrics_timing': {
        'logo': 'clock', 'title': 'Lyrics & Timing',
        'subtitle': 'From sung vocals to word-by-word karaoke timing, with review gates',
        'stages': [
            {'title': 'Vocal Stem', 'items': [('mic', 'vocals.wav', 'Or lead_vocals.wav'),
                ('globe', 'Language', 'Fixed or auto-detected'), ('tag', 'Label', 'da -> DANSK KARAOKE')],
                'output': 'Clean voice, no music'},
            {'title': 'Transcribe', 'items': [('sparkles', 'Whisper large-v3-turbo', '0.8B, local'),
                ('wave', 'Voice-activity filter', 'Skips silent parts'), ('clock', 'Word timestamps', 'Timing anchors'),
                ('globe', 'Language detection', 'Saved to language.json')], 'output': 'transcript.json draft'},
            {'title': 'Lyrics Review', 'items': [('file', 'Import your lyrics', 'One sung line per row'),
                ('search', 'Line matching', 'User words on Whisper timing'), ('users', 'Duet parts', 'M: / F: / D: labels'),
                ('history', 'History & restore', 'Undo lyric changes')], 'output': 'Accepted lyrics'},
            {'title': 'Align', 'items': [('clock', 'WhisperX', 'Forced alignment per word'),
                ('mic', 'On the vocal stem', 'More precise than the mix'),
                ('lock', 'Bound to lyrics', 'Lyric change = realign')], 'output': 'aligned.json word times'},
            {'number': '✓', 'title': 'Timing Check', 'items': [('alert', 'Unaligned words', 'Missing timing'),
                ('timer', 'Too short / too long', '< 0.06 s or > 4 s'), ('split', 'Overlaps', 'Words out of order'),
                ('volume', 'Silent placement', 'Word where nobody sings')]},
        ],
        'strip': [('clipboard', 'Review gates', 'Nothing renders unreviewed'), ('history', 'Lyric history', 'Every version kept'),
                  ('gauge', 'Timing score', 'timing-report.json'), ('cpu', 'GPU float16 / CPU int8', 'Automatic choice')],
    },
    '03_translation': {
        'logo': 'languages', 'title': 'Lyric Translation',
        'subtitle': 'OpenL-style, whole-song AI translation that runs locally and learns your corrections',
        'stages': [
            {'title': 'Timed Lines', 'items': [('clock', 'aligned.json', 'Each line keeps its time'),
                ('globe', 'Language pair', 'From song, to --to'), ('tag', 'Song settings', 'Style, glossary, notes')],
                'output': 'Lines to translate'},
            {'title': 'Choose Engine', 'items': [('sparkles', 'AI language model', 'Local Ollama, Qwen2.5 7B'),
                ('server', 'Any OpenAI-compatible', 'Local or paid endpoint'),
                ('book', 'Opus-MT', 'Fast, pivots via English')], 'output': 'Engine + model recorded'},
            {'title': '5-Pass Quality', 'items': [('search', '1 Song brief', 'Story, mood, idioms'),
                ('pencil', '2 Draft', 'Chunks with context'), ('check', '3 Edit', 'Compared with original'),
                ('scissors', '4 Shorten', 'Fits on screen'), ('refresh', '5 Back-check', 'Flags meaning drift')],
                'output': 'translation.json + checks'},
            {'title': 'Customise', 'items': [('sliders', 'Styles', 'natural / singable / literal'),
                ('list', 'Glossary', 'Fixed word translations'), ('file', 'House prompt', 'config/translation_prompt.txt'),
                ('database', 'Translation memory', 'Accepted lines reused')], 'output': 'Your tone, every song'},
            {'number': '✓', 'title': 'On Screen', 'items': [('clipboard', 'Accept translation', 'Review gate'),
                ('type', 'Below mode', 'Original + translation'), ('mic', 'Only mode', 'Sing the translation'),
                ('palette', 'Styling', 'Position, size, colour')]},
        ],
        'strip': [('lock', 'Free & offline', 'Local model, no per-line cost'), ('alert', 'Flagged lines', 'Fix only what needs it'),
                  ('database', 'Memory learns', 'Corrections carry over'), ('shield', 'Approval binding', 'Edit = review again')],
    },
    '04_editor': {
        'logo': 'pencil', 'title': 'Lyric & Timeline Editor',
        'subtitle': 'Karadeo-style editing as backend commands: lyrics, timing, styles, layers, keyframes',
        'stages': [
            {'title': 'Inspect', 'items': [('list', 'edit --show', 'Numbered lines & words'),
                ('alert', 'Timing report', 'Problems by line/word'), ('eye', 'clip', 'Few seconds around a line')],
                'output': 'Know what to fix'},
            {'title': 'Lyric Edits', 'items': [('type', 'Change text', 'Keeps word timing'),
                ('plus', 'Insert line', 'Missing lyric'), ('split', 'Split / merge', 'Re-break lines'),
                ('trash', 'Delete', 'Remove a line'), ('users', 'Duet part', 'M / F / D colours')], 'output': 'Correct lyrics'},
            {'title': 'Timing Edits', 'items': [('move', 'Shift', 'Line, range or whole song'),
                ('timer', 'Word times', 'Exact start / end'), ('sliders', 'Stretch line', 'Fit new start/end'),
                ('activity', 'Snap to beat', 'BPM detection, half-beats')], 'output': 'Tight sync'},
            {'title': 'Style & Layers', 'items': [('palette', 'Per-line style', 'Font, colour, box, rotation'),
                ('type', 'Text overlays', '"Chorus!", credits'), ('image', 'Media layers', 'Images & videos, crop, speed'),
                ('volume', 'Audio tracks', 'dB, offset, fades, mute'), ('move', 'Keyframes', 'Move, scale, fade, rotate')],
                'output': 'layers.json + styles'},
            {'number': '✓', 'title': 'Safe Changes', 'items': [('shield', 'Validation', 'Order, overlap, range'),
                ('undo', 'Undo stack', 'history/ for every edit'), ('refresh', 'Auto re-check', 'Timing check after edits'),
                ('lock', 'Approval reset', 'Preview again after edits')]},
        ],
        'strip': [('terminal', 'No UI needed', 'Scriptable commands'), ('history', 'Full history', 'aligned, layers, translations'),
                  ('activity', 'Built-in beat tracker', 'numpy/scipy, librosa optional'), ('film', '24-60 fps', 'Per song')],
    },
    '05_render': {
        'logo': 'film', 'title': 'Video & Audio Rendering',
        'subtitle': 'Branded karaoke videos with word sweep, motion graphics and broadcast-level audio',
        'stages': [
            {'title': 'Inputs', 'items': [('file', 'Timed lyrics', 'lyrics.ass from alignment'),
                ('music', 'Instrumental', 'Or with backing vocals'), ('image', 'Background', 'Image or looping video'),
                ('tag', 'Logo', 'Brand mark')], 'output': 'Everything for one song'},
            {'title': 'Layout', 'items': [('list', 'Templates', '4-line, 2-line, single-line'),
                ('monitor', 'Canvas', '1920x1080, 4K, square'), ('phone', 'Vertical 9:16', 'Reels / TikTok'),
                ('palette', 'Colours & fonts', 'Per song or per line')], 'output': 'Pages that never overlap'},
            {'title': 'Motion Graphics', 'items': [('sparkles', 'Logo intro', 'Title card animation'),
                ('timer', 'Intro countdown', 'Circle before first line'), ('activity', 'Break countdown', '3-2-1 dots'),
                ('move', 'Camera pan', 'Slow drift on stills'), ('layers', 'Layers', 'Overlays with keyframes')],
                'output': 'Engaging, readable video'},
            {'title': 'Audio Finishing', 'items': [('gauge', 'Loudness -14 LUFS', 'EBU R128, no limiter'),
                ('volume', 'Fades', 'Soft start and end'), ('mic', 'Guide vocal', '0-100% of the singer'),
                ('music', 'Key change', '-12 to +12 semitones')], 'output': 'Even, clean sound'},
            {'number': '✓', 'title': 'MP4 Output', 'items': [('film', 'H.264 + AAC', 'CRF & preset'),
                ('clock', '24 / 25 / 30 / 50 / 60 fps', 'Per song'), ('scissors', 'Export range', 'Any part of the song'),
                ('tag', 'Metadata', 'Title & artist tags')]},
        ],
        'strip': [('shield', 'Output checks', 'Size, duration, decoded audio'), ('globe', 'Any script', 'Right-to-left shaped by libass'),
                  ('languages', 'Translation line', 'Below or instead of lyrics'), ('lock', 'Never overwrites', 'Exclusive final copy')],
    },
    '06_review_delivery': {
        'logo': 'clipboard', 'title': 'Review, Delivery & Automation',
        'subtitle': 'From one command to approved, delivered karaoke videos with extras',
        'stages': [
            {'title': 'Setup', 'items': [('terminal', 'setup.ps1', 'Both environments, CPU or CUDA'),
                ('check', 'doctor', 'FFmpeg, logo, songs, models'), ('plus', 'add', 'New songs to the queue')],
                'output': 'Ready machine'},
            {'title': 'Draft', 'items': [('zap', 'draft command', 'Separate -> transcribe -> align'),
                ('refresh', 'Queue', 'All songs in order'), ('cpu', 'Parallel prefetch', 'Next song separates early'),
                ('list', 'status', 'Progress per song')], 'output': 'Stops only for review'},
            {'title': 'Preview', 'items': [('play', 'Full preview', 'Exactly like the final'),
                ('eye', 'clip', 'Quick check of one line'), ('alert', 'Flagged parts', 'Quiet sections, timing issues')],
                'output': 'Watched & listened'},
            {'title': 'Approve & Render', 'items': [('clipboard', '--confirm-listened', 'Human sign-off'),
                ('lock', 'Fingerprint', 'Inputs, lyrics, layers, code'), ('shield', 'Final checks', 'Format, duration, audio'),
                ('download', 'out/ folder', 'Never overwritten')], 'output': 'Approved MP4'},
            {'number': '✓', 'title': 'Delivery Extras', 'items': [('file', 'Enhanced LRC', 'Word-timed lyrics file'),
                ('image', 'Thumbnail', 'From the busiest chorus'), ('film', '30 s teaser', 'With audio fades'),
                ('tag', 'MP4 tags', 'Title & artist')]},
        ],
        'strip': [('history', 'Status files', 'last-status.json per song'), ('shield', 'Stale approval detection', 'Any change = review'),
                  ('gear', 'Reusable backend', 'Scriptable, no UI'), ('lock', 'Local only', 'Your files stay on your PC')],
    },
}


# Client edition: what the product does for them, never how it is built
# (no model, library, file or command names).
CLIENT_SPECS = {
    '00_overview': {
        'logo': 'mic', 'title': 'karaoke-maker', 'subtitle': 'SMC powered Karaoke AI tool',
        'stages': [
            {'title': 'Song Input', 'items': [('music', 'Any song', 'All common audio formats'),
                ('file', 'Your lyrics', 'Optional, for perfect text'), ('image', 'Background', 'Image or video'),
                ('globe', 'Any language', 'Detected automatically'), ('list', 'Song library', 'Many songs at once'),
                ('check', 'Health check', 'Everything ready to go')], 'output': 'Song ready to process'},
            {'title': 'Vocal Removal', 'items': [('layers', 'AI vocal removal', 'Studio-quality instrumental'),
                ('sparkles', 'Extra-clean mode', 'Two AI passes combined'), ('users', 'Keep the choir', 'Remove only the lead singer'),
                ('shield', 'Quality check', 'Silence & length verified'), ('lock', 'Consistent results', 'Same song, same result'),
                ('zap', 'Fast batches', 'Next song prepared early')], 'output': 'Clean instrumental'},
            {'title': 'Lyrics & Timing', 'items': [('mic', 'AI lyric recognition', 'Listens to the singer'),
                ('file', 'Use your lyrics', 'Matched to the song'), ('clock', 'Word-by-word sync', 'Every word on the beat'),
                ('alert', 'Automatic checks', 'Problems flagged early'), ('users', 'Duets', 'Colour per singer'),
                ('history', 'Version history', 'Go back any time')], 'output': 'Perfectly timed lyrics'},
            {'title': 'Translation', 'items': [('sparkles', 'AI translation', 'Natural, whole-song context'),
                ('sliders', 'Translation styles', 'Natural, singable, literal'), ('list', 'Your vocabulary', 'Fixed word choices'),
                ('database', 'Learns your edits', 'Reused in new songs'), ('check', 'Meaning check', 'Flags doubtful lines'),
                ('type', 'Display options', 'Under or instead of lyrics')], 'output': 'Reviewed translation'},
            {'title': 'Editor', 'items': [('pencil', 'Lyric editing', 'Fix, add, split, join lines'),
                ('move', 'Timing editing', 'Nudge lines and words'), ('palette', 'Per-line styling', 'Fonts, colours, boxes'),
                ('layers', 'Overlays', 'Text, images, video, sound'), ('activity', 'Beat snap', 'Lines locked to the beat'),
                ('undo', 'Undo', 'Every change reversible')], 'output': 'Your final design'},
            {'title': 'Rendering', 'items': [('monitor', 'Every format', 'Widescreen, vertical, square, 4K'),
                ('list', 'Layouts', '4, 2 or 1 line at a time'), ('sparkles', 'Motion graphics', 'Intro, countdowns, motion'),
                ('gauge', 'Studio sound', 'Even loudness, soft fades'), ('mic', 'Singing help', 'Optional guide voice'),
                ('music', 'Key change', 'Up or down to suit voices')], 'output': 'Branded HD video'},
            {'number': '✓', 'title': 'Review & Delivery', 'items': [('zap', 'One-click draft', 'Whole songs automatically'),
                ('play', 'Preview', 'Watch before approving'), ('clipboard', 'Approval', 'Nothing ships unchecked'),
                ('download', 'Extras', 'Lyrics file, thumbnail, teaser'), ('shield', 'Final checks', 'Picture & sound verified'),
                ('lock', 'Safe delivery', 'Finished files protected')]},
        ],
        'strip': [('lock', 'Private', 'Your songs stay on your machine'), ('shield', 'Quality gates', 'Human approval at every key step'),
                  ('zap', 'Fast', 'Batch processing'), ('sparkles', 'AI powered', 'Professional results, less work')],
    },
    '01_vocal_removal': {
        'logo': 'layers', 'title': 'Vocal Removal',
        'subtitle': 'Studio-quality instrumentals from any song',
        'stages': [
            {'title': 'Your Song', 'items': [('music', 'Any audio file', 'All common formats'),
                ('lock', 'Song fingerprint', 'Results tied to this song'), ('cpu', 'Fast processing', 'Uses your graphics card')],
                'output': 'Song ready to split'},
            {'title': 'AI Separation', 'items': [('mic', 'Vocals', 'Every voice in the song'),
                ('activity', 'Drums', 'Separate track'), ('wave', 'Bass', 'Separate track'),
                ('music', 'Other instruments', 'Guitars, keys, synths')], 'output': 'Four clean tracks'},
            {'title': 'Extra-Clean Mode', 'items': [('sparkles', 'Second AI pass', 'Independent second opinion'),
                ('merge', 'Combined result', 'Less voice left in the music'),
                ('check', 'Perfect alignment', 'Nothing shifts in time')], 'output': 'Cleaner instrumental'},
            {'title': 'Keep the Choir', 'items': [('users', 'Lead vs backing', 'AI tells singers apart'),
                ('mic', 'Lead removed', 'Only the main singer goes'),
                ('music', 'Choir stays', 'Fuller karaoke sound')], 'output': 'Lead-only removal'},
            {'number': '✓', 'title': 'Verified Tracks', 'items': [('shield', 'Quality check', 'Silence, length, stereo'),
                ('refresh', 'Reliable reuse', 'Never mixes up songs'), ('zap', 'Batch speed', 'Next song prepared early'),
                ('lock', 'Consistent', 'Same song, same result')]},
        ],
        'strip': [('lock', 'Private', 'Processed on your machine'), ('gauge', 'No clipping', 'Clean, safe levels'),
                  ('cpu', 'Any computer', 'Faster with a graphics card'), ('sparkles', 'Choice of quality', 'Standard or extra-clean')],
    },
    '02_lyrics_timing': {
        'logo': 'clock', 'title': 'Lyrics & Timing',
        'subtitle': 'Every word highlighted exactly when it is sung',
        'stages': [
            {'title': 'Singer Only', 'items': [('mic', 'Isolated voice', 'No music in the way'),
                ('globe', 'Any language', 'Detected automatically'), ('tag', 'Language label', 'Shown on the title card')],
                'output': 'Clean voice'},
            {'title': 'AI Listening', 'items': [('sparkles', 'Lyric recognition', 'Writes down what is sung'),
                ('wave', 'Skips silence', 'Fewer false words'), ('clock', 'Rough timing', 'When each line starts')],
                'output': 'Draft lyrics'},
            {'title': 'Lyrics Review', 'items': [('file', 'Your lyrics', 'Paste the official text'),
                ('search', 'Smart matching', 'Lined up with the song'), ('users', 'Duet parts', 'Male, female, both'),
                ('history', 'Version history', 'Restore older lyrics')], 'output': 'Approved lyrics'},
            {'title': 'Word Sync', 'items': [('clock', 'Word-by-word timing', 'Every single word'),
                ('mic', 'Voice-precise', 'Timed on the singer alone'),
                ('lock', 'Always in step', 'Lyric change = new timing')], 'output': 'Synced words'},
            {'number': '✓', 'title': 'Automatic Checks', 'items': [('alert', 'Missed words', 'Found and listed'),
                ('timer', 'Odd lengths', 'Too short or too long'), ('split', 'Overlaps', 'Words out of order'),
                ('volume', 'Silent spots', 'Words where no one sings')]},
        ],
        'strip': [('clipboard', 'Human approval', 'Nothing goes out unreviewed'), ('history', 'Full history', 'Every version kept'),
                  ('gauge', 'Quality score', 'Timing rated per song'), ('globe', 'Multilingual', 'Danish, English, Spanish...')],
    },
    '03_translation': {
        'logo': 'languages', 'title': 'Lyric Translation',
        'subtitle': 'Professional AI translation that understands the whole song',
        'stages': [
            {'title': 'Timed Lyrics', 'items': [('clock', 'Line timing kept', 'Translation appears in sync'),
                ('globe', 'Language pair', 'From any to any'), ('tag', 'Song notes', 'Tone, audience, context')],
                'output': 'Lines to translate'},
            {'title': 'AI Translator', 'items': [('sparkles', 'Premium AI', 'Context-aware translation'),
                ('zap', 'Quick mode', 'Fast single pass'),
                ('lock', 'Private option', 'Runs on your machine')], 'output': 'First translation'},
            {'title': '5-Step Quality', 'items': [('search', '1 Understand', 'Story, mood, idioms'),
                ('pencil', '2 Translate', 'With full context'), ('check', '3 Edit', 'Compared to the original'),
                ('scissors', '4 Shorten', 'Fits on screen'), ('refresh', '5 Verify', 'Meaning double-checked')],
                'output': 'Polished translation'},
            {'title': 'Your Voice', 'items': [('sliders', 'Styles', 'Natural, singable, literal'),
                ('list', 'Vocabulary', 'Your fixed word choices'), ('file', 'House style', 'Same tone every song'),
                ('database', 'Learns', 'Your corrections reused')], 'output': 'Consistent brand tone'},
            {'number': '✓', 'title': 'On Screen', 'items': [('clipboard', 'Approval', 'You sign off first'),
                ('type', 'Subtitle mode', 'Original + translation'), ('mic', 'Sing-along mode', 'Sing in the new language'),
                ('palette', 'Styling', 'Position, size, colour')]},
        ],
        'strip': [('alert', 'Flagged lines', 'Review only what needs it'), ('database', 'Gets smarter', 'Learns from every song'),
                  ('shield', 'Approval', 'Changes need sign-off'), ('globe', 'Many languages', 'Wide language coverage')],
    },
    '04_editor': {
        'logo': 'pencil', 'title': 'Lyric & Timeline Editor',
        'subtitle': 'Full control over lyrics, timing, styling and overlays',
        'stages': [
            {'title': 'Review', 'items': [('list', 'Line overview', 'Every line and word'),
                ('alert', 'Problem list', 'What to fix, where'), ('eye', 'Quick preview', 'A few seconds per edit')],
                'output': 'Know what to fix'},
            {'title': 'Lyric Edits', 'items': [('type', 'Change text', 'Timing kept'),
                ('plus', 'Add lines', 'Anything missing'), ('split', 'Split & join', 'Better line breaks'),
                ('trash', 'Remove lines', 'Clean up extras'), ('users', 'Duet parts', 'Colour per singer')], 'output': 'Correct lyrics'},
            {'title': 'Timing Edits', 'items': [('move', 'Shift', 'A line, a part, the song'),
                ('timer', 'Word timing', 'Exact start and end'), ('sliders', 'Stretch', 'Fit a line to new times'),
                ('activity', 'Beat snap', 'Lines locked to the beat')], 'output': 'Tight sync'},
            {'title': 'Style & Overlays', 'items': [('palette', 'Per-line styling', 'Font, colour, box, angle'),
                ('type', 'Text overlays', 'Titles, "Chorus!", credits'), ('image', 'Images & video', 'Placed on the timeline'),
                ('volume', 'Extra sounds', 'Effects, applause, intros'), ('move', 'Animation', 'Move, scale, fade, rotate')],
                'output': 'Your design'},
            {'number': '✓', 'title': 'Safe Changes', 'items': [('shield', 'Error prevention', 'Impossible timing blocked'),
                ('undo', 'Unlimited undo', 'Every change reversible'), ('refresh', 'Auto re-check', 'After every edit'),
                ('lock', 'Re-approval', 'Edits are reviewed again')]},
        ],
        'strip': [('pencil', 'Pro editing', 'Karaoke-studio control'), ('history', 'Full history', 'Nothing is ever lost'),
                  ('activity', 'Beat aware', 'Music-driven timing'), ('film', 'Smooth video', 'Up to 60 frames per second')],
    },
    '05_render': {
        'logo': 'film', 'title': 'Video & Audio',
        'subtitle': 'Branded karaoke videos with motion graphics and studio sound',
        'stages': [
            {'title': 'Ingredients', 'items': [('file', 'Synced lyrics', 'From the timing step'),
                ('music', 'Instrumental', 'With or without choir'), ('image', 'Background', 'Image or moving video'),
                ('tag', 'Your logo', 'On every video')], 'output': 'Everything for one song'},
            {'title': 'Layout', 'items': [('list', 'Layouts', '4, 2 or 1 line at a time'),
                ('monitor', 'Widescreen & 4K', 'TV and big screens'), ('phone', 'Vertical', 'Reels, TikTok, Shorts'),
                ('palette', 'Brand styling', 'Your fonts and colours')], 'output': 'Clean, readable pages'},
            {'title': 'Motion Graphics', 'items': [('sparkles', 'Logo intro', 'Animated title card'),
                ('timer', 'Intro countdown', 'Ready-to-sing signal'), ('activity', 'Break countdown', '3-2-1 before lyrics return'),
                ('move', 'Moving backdrop', 'Gentle camera motion'), ('layers', 'Overlays', 'Animated extras')],
                'output': 'Engaging video'},
            {'title': 'Studio Sound', 'items': [('gauge', 'Even loudness', 'Streaming standard'),
                ('volume', 'Soft fades', 'Smooth start and end'), ('mic', 'Guide voice', 'Quiet original singer'),
                ('music', 'Key change', 'Suit any voice')], 'output': 'Professional audio'},
            {'number': '✓', 'title': 'HD Video', 'items': [('film', 'MP4 video', 'Plays everywhere'),
                ('clock', 'Smooth motion', 'Up to 60 fps'), ('scissors', 'Clips', 'Any part of the song'),
                ('tag', 'Song details', 'Title & artist built in')]},
        ],
        'strip': [('shield', 'Quality checked', 'Picture, length, sound'), ('globe', 'Any script', 'Including right-to-left'),
                  ('languages', 'Translations', 'Shown with the lyrics'), ('lock', 'Safe output', 'Finished files protected')],
    },
    '06_review_delivery': {
        'logo': 'clipboard', 'title': 'Review & Delivery',
        'subtitle': 'From one click to approved, ready-to-publish karaoke videos',
        'stages': [
            {'title': 'Set Up', 'items': [('gear', 'Quick setup', 'One-time installation'),
                ('check', 'Health check', 'Everything verified'), ('plus', 'Add songs', 'Build your playlist')],
                'output': 'Ready to produce'},
            {'title': 'Automatic Draft', 'items': [('zap', 'One click', 'Whole song processed'),
                ('refresh', 'Batches', 'Many songs in a row'), ('cpu', 'Parallel work', 'Next song prepared early'),
                ('list', 'Progress', 'Status per song')], 'output': 'Draft video'},
            {'title': 'Preview', 'items': [('play', 'Full preview', 'Exactly like the final'),
                ('eye', 'Quick clips', 'Check single moments'), ('alert', 'Highlights', 'Spots worth a second look')],
                'output': 'Watched & checked'},
            {'title': 'Approval', 'items': [('clipboard', 'Sign-off', 'A person approves'),
                ('lock', 'Locked approval', 'Any change needs re-approval'), ('shield', 'Final checks', 'Picture and sound verified'),
                ('download', 'Safe delivery', 'Finished files protected')], 'output': 'Approved video'},
            {'number': '✓', 'title': 'Delivery Pack', 'items': [('file', 'Lyrics file', 'For karaoke players'),
                ('image', 'Thumbnail', 'From the chorus'), ('film', '30-second teaser', 'Ready for social media'),
                ('tag', 'Song details', 'Title & artist built in')]},
        ],
        'strip': [('list', 'Clear status', 'Know where every song is'), ('shield', 'Quality first', 'Human approval required'),
                  ('zap', 'Efficient', 'Batch production'), ('lock', 'Private', 'Your files stay with you')],
    },
}


def main():
    browser = next((b for b in BROWSERS if Path(b).is_file()), None) or shutil.which('msedge') or shutil.which('chrome')
    if not browser:
        raise SystemExit('Edge or Chrome is needed to render the PNGs')
    # team: full detail for SMC staff; client: features only, no internal tools or models.
    for edition, specs in (('team', SPECS), ('client', CLIENT_SPECS)):
        build = HERE / '_html' / edition
        build.mkdir(parents=True, exist_ok=True)
        (HERE / edition).mkdir(exist_ok=True)
        for name, spec in specs.items():
            source = build / f'{name}.html'
            source.write_text(page(spec), encoding='utf-8')
            target = HERE / edition / f'{name}.png'
            subprocess.run([browser, '--headless=new', '--disable-gpu', '--hide-scrollbars',
                            '--force-device-scale-factor=1', f'--window-size={WIDTH},{HEIGHT}',
                            f'--screenshot={target}', source.as_uri()], check=True, capture_output=True)
            print(target)


if __name__ == '__main__':
    main()
