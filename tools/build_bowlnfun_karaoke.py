"""Create a clean Bowl'n Fun karaoke master from Karadeo ASS timing.

The generated subtitle track deliberately keeps each four-line page intact until
the page ends.  Only the active lyric gets the orange word sweep, so a new cue
can never collide with the previous page or leave coloured fragments behind.
"""
from __future__ import annotations

import argparse
import json
import re
import math
import os
import subprocess
from pathlib import Path
from PIL import ImageFont
import av
import layers as layer_tools
import intro_countdown

from project_runtime import ROOT, FFMPEG, LOGO, font_file, ffmpeg_thread_args, ffmpeg_input_filter_args
BACKGROUNDS = sorted((ROOT / "audio-bg-sample").glob("*.jpeg"))
INTRO_DELAY = 2.60

parser = argparse.ArgumentParser()
parser.add_argument("--slug", required=True)
parser.add_argument("--title", required=True)
parser.add_argument("--artist", required=True)
parser.add_argument("--background", type=int, default=0)
parser.add_argument("--background-folder", type=Path)
parser.add_argument("--background-file", type=Path)
parser.add_argument('--branding-plan', type=Path)
parser.add_argument("--output-name")
parser.add_argument("--output-dir", type=Path)
parser.add_argument("--source-ass", type=Path, help="Reviewed local word-timed ASS")
parser.add_argument("--audio-file", type=Path, help="Existing backing audio; no separation")
parser.add_argument("--language-label", default="DANSK KARAOKE")
parser.add_argument("--approved-intro", action="store_true")
parser.add_argument("--center-intro-countdown", action="store_true", help="Keep a large centered logo and numeric countdown until the first lyric, then move to the corner")
parser.add_argument("--preserve-source-timeline", action="store_true", help="Overlay intro on existing source intro without delaying audio or lyrics")
parser.add_argument("--preset", choices=['veryfast','faster','fast','medium','slow'], default='fast')
parser.add_argument("--crf", type=int, default=19, help="x264 quality: lower is better/larger")
parser.add_argument('--encoder', choices=['libx264','h264_nvenc'], default='libx264')
parser.add_argument('--nvenc-cq', type=int, choices=range(52), default=19)
parser.add_argument("--template", default="four_line", help="Name in config/templates or a JSON path")
parser.add_argument('--highlight-colour', help='Override template sweep colour: #RRGGBB (default template uses orange)')
parser.add_argument("--canvas", default="1920x1080", help="WIDTHxHEIGHT, e.g. 1080x1920 for vertical")
parser.add_argument("--start", type=float, help="Export from this output second (includes intro)")
parser.add_argument("--end", type=float, help="Export until this output second")
parser.add_argument("--guide-vocal-file", type=Path, help="Separated vocals mixed quietly under the backing")
parser.add_argument("--guide-vocal-level", type=float, default=0.0, help="0 (off) to 1 (full original vocal)")
parser.add_argument("--pitch", type=float, default=0.0, help="Key change in semitones, e.g. -3")
parser.add_argument("--translation-file", type=Path, help="translation.json from local_karaoke.py translate")
parser.add_argument("--translation-mode", choices=["below", "only"], default="below",
                    help="below: original sweep + translated line underneath; only: sing the translation")
parser.add_argument("--gain-db", type=float, default=0.0, help="Linear loudness gain from the pipeline's EBU R128 measurement")
parser.add_argument("--fade-in", type=float, default=0.0, help="Backing fade-in seconds")
parser.add_argument("--fade-out", type=float, default=0.0, help="Backing fade-out seconds")
parser.add_argument("--gap-countdown", action="store_true", help="3-2-1 dots before lyrics return after a long instrumental gap")
parser.add_argument("--motion", choices=["none", "pan"], default="none", help="Slow camera drift over the background")
parser.add_argument("--metadata-title")
parser.add_argument("--metadata-artist")
parser.add_argument("--fps", type=float, default=25)
parser.add_argument("--video-bitrate",type=int,default=None)
parser.add_argument("--line-styles", type=Path, help="JSON list of per-line style overrides, in lyric order")
parser.add_argument("--layers", type=Path, help="layers.json: text overlays, media layers, audio tracks")
parser.add_argument('--intro-seconds', type=float, default=3.0)
parser.add_argument('--intro-countdown', action='store_true', help='White closing arc and numeric countdown during the added intro')
parser.add_argument('--countdown-style',choices=['arc','circle'],help='Closing arc or complete static circle; defaults to .env')
parser.add_argument('--countdown-colour',help='Ring colour #RRGGBB; defaults to .env')
parser.add_argument('--sync-background', action='store_true', help='Hold the opening video frame during the added intro')
args = parser.parse_args()
try:
    countdown_settings=intro_countdown.settings(args.countdown_style,args.countdown_colour)
except ValueError as exc:parser.error(str(exc))
for path_option in ('background_folder','background_file','output_dir','source_ass','audio_file',
                    'guide_vocal_file','translation_file','line_styles','layers'):
    value = getattr(args, path_option)
    if value is not None: setattr(args, path_option, value.resolve())
if args.output_name and Path(args.output_name).name != args.output_name:
    parser.error('--output-name must be a filename, not a directory path')
from output_size import resolve_fps
FPS = resolve_fps(args.fps)
if args.video_bitrate is not None and not 100000<=args.video_bitrate<=50000000:parser.error('Invalid video bitrate')
if args.center_intro_countdown and not args.approved_intro:
    parser.error('--center-intro-countdown requires --approved-intro')
if args.intro_countdown and (not args.approved_intro or args.preserve_source_timeline or args.intro_seconds<=0):
    parser.error('--intro-countdown requires --approved-intro with a positive added intro')

canvas = re.fullmatch(r"(\d{3,4})x(\d{3,4})", args.canvas)
if not canvas or int(canvas[1]) % 2 or int(canvas[2]) % 2:
    parser.error("--canvas must be WIDTHxHEIGHT with even numbers, e.g. 1920x1080")
W, H = int(canvas[1]), int(canvas[2])
# Sizes are authored for 1080p and follow the short side, so vertical video
# keeps readable text; positions follow each axis.
FS = min(W, H) / 1080
SX, SY = W / 1920, H / 1080
template_path = Path(args.template)
if template_path.suffix.lower() != ".json":
    template_path = ROOT / "config" / "templates" / f"{args.template}.json"
if not template_path.is_file():
    parser.error(f"Template not found: {template_path}")
TEMPLATE = json.loads(template_path.read_text(encoding="utf-8"))
if args.highlight_colour is not None:
    if not re.fullmatch(r'#[0-9A-Fa-f]{6}',args.highlight_colour):
        parser.error('--highlight-colour must be #RRGGBB')
    TEMPLATE['highlight_colour'] = args.highlight_colour
LINES_PER_PAGE = int(TEMPLATE["lines_per_page"])
if not 1 <= LINES_PER_PAGE <= 6:
    parser.error("Template lines_per_page must be 1-6")
if not 0 <= args.guide_vocal_level <= 1:
    parser.error("--guide-vocal-level must be between 0 and 1")
if args.guide_vocal_level and not (args.guide_vocal_file and args.guide_vocal_file.is_file()):
    parser.error("--guide-vocal-level needs an existing --guide-vocal-file")
if not -12 <= args.pitch <= 12:
    parser.error("--pitch must be between -12 and 12 semitones")
if args.start is not None and args.start < 0 or args.end is not None and args.end <= (args.start or 0):
    parser.error("Export range needs 0 <= --start < --end")


def px(value: float) -> int:
    return round(value)


def num(value: float) -> str:
    """FFmpeg expression number without a needless trailing .0."""
    return str(int(value)) if float(value).is_integer() else f"{value:.3f}"


def ass_colour(hex_rgb: str) -> str:
    value = hex_rgb.lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", value):
        raise SystemExit(f"Template colour must be #RRGGBB: {hex_rgb}")
    return f"&H00{value[4:6]}{value[2:4]}{value[0:2]}".upper()

if args.approved_intro:
    if not math.isfinite(args.intro_seconds) or not 0 <= args.intro_seconds <= 60:
        parser.error('Intro must be finite and between 0 and 60 seconds')
    INTRO_DELAY = args.intro_seconds
if args.preserve_source_timeline:
    if not args.approved_intro:
        parser.error('--preserve-source-timeline requires --approved-intro')
    INTRO_DELAY = 0.0

import os
song_dir = Path(os.environ.get('KARAOKE_RENDER_WORK_DIR',ROOT/'work/bowlnfun')) / args.slug
song_dir.mkdir(parents=True, exist_ok=True)
source_ass = args.source_ass or song_dir / "lyrics.ass"
audio = args.audio_file or song_dir / "instrumental.mp3"
output_ass = song_dir / "karaoke.ass"
delivery = ROOT / "delivery" / "Bowlnfun Jakob For Visuals"
if args.output_dir:
    delivery = args.output_dir
delivery.mkdir(parents=True, exist_ok=True)
output_mp4 = delivery / f"{args.slug}_Karaoke.mp4"
if args.output_name:
    output_mp4 = delivery / args.output_name
if output_mp4.exists():
    raise FileExistsError(f'Refusing to overwrite {output_mp4}')

FONT = ImageFont.truetype(str(font_file()), 20).getname()[0]
LYRIC_SIZE = px(TEMPLATE["font_size"] * FS)
TEXT = ass_colour(TEMPLATE.get("text_colour", "#FFFFFF"))
HIGHLIGHT = ass_colour(TEMPLATE.get("highlight_colour", "#FFA500"))
EDGE = ass_colour(TEMPLATE.get("outline_colour", "#101010"))
OUTLINE, SHADOW = px(TEMPLATE.get("outline", 5) * FS), px(TEMPLATE.get("shadow", 1) * FS)
HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: PageBase,{FONT},{LYRIC_SIZE},{TEXT},{TEXT},{EDGE},&H00000000,-1,0,0,0,100,100,0,0,1,{OUTLINE},{SHADOW},5,80,80,0,1
Style: PageActive,{FONT},{LYRIC_SIZE},{HIGHLIGHT},&HFF000000,&HFF000000,&HFF000000,-1,0,0,0,100,100,0,0,1,{OUTLINE},{SHADOW},5,80,80,0,1
Style: Title,{FONT},{px(104*FS)},&H00FFFFFF,&H00FFFFFF,{EDGE},&H00000000,-1,0,0,0,100,100,3,0,1,{px(6*FS)},{px(2*FS)},5,100,100,0,1
Style: Artist,{FONT},{px(52*FS)},&H00FFFFFF,&H00FFFFFF,{EDGE},&H00000000,-1,0,0,0,100,100,1,0,1,{px(4*FS)},{px(1*FS)},5,100,100,0,1
Style: Footer,{FONT},{px(28*FS)},&H00D0D0D0,&H00D0D0D0,{EDGE},&H00000000,0,0,0,0,100,100,1,0,1,{px(2*FS)},0,2,70,70,46,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""

def fix_text(value: str) -> str:
    # Karadeo's endpoint returns UTF-8 without an explicit charset; Windows
    # PowerShell may have stored it as mojibake. Recover it before rendering.
    for _ in range(2):
        if "Ã" not in value and "â" not in value:
            break
        try:
            value = value.encode("latin1").decode("utf-8")
        except UnicodeError:
            break
    # The incoming cue deliberately contains ASS {\kf...} timing tags. Do
    # not escape them: libass must receive those tags as markup rather than
    # visible text. Karadeo lyric content itself does not use literal braces.
    # Repair the known damaged accent in the saved Spanish refrain.
    return value.replace('mam\ufffd', 'mamá')

def stamp(value: str) -> float:
    h, m, s = value.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)

def ass_time(value: float) -> str:
    value = max(0, round(value * 100))
    h, rest = divmod(value, 360000)
    m, rest = divmod(rest, 6000)
    s, cs = divmod(rest, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def strip_tags(text: str) -> str:
    return re.sub(r"\{[^}]*\}", "", text).strip()

def font_size(text: str) -> int:
    length = len(strip_tags(text))
    if length <= 30:
        return 72
    if length <= 42:
        return 64
    if length <= 55:
        return 54
    return 46

raw = source_ass.read_text(encoding="utf-8")
line_styles = json.loads(args.line_styles.read_text(encoding="utf-8")) if args.line_styles else []
# Template-wide text styling that is not part of the ASS style line itself.
TEMPLATE_STYLE = {key: TEMPLATE[key] for key in ("letter_spacing", "highlight_outline_colour", "opacity")
                  if key in TEMPLATE}
cues = []
for row in raw.splitlines():
    if not row.startswith("Dialogue:"):
        continue
    fields = row.split(",", 9)
    if len(fields) != 10:
        continue
    try:
        # Reserve the opening title card for every track.  Audio and every
        # lyric cue are delayed together, so the first on-screen highlight is
        # always the first sung line rather than a later line on the page.
        start, end = stamp(fields[1]) + INTRO_DELAY, stamp(fields[2]) + INTRO_DELAY
    except ValueError:
        continue
    karaoke = fix_text(fields[9])
    plain = strip_tags(karaoke)
    if plain:
        # The Name field carries an optional duet part (M/F/D...).
        style = {**TEMPLATE_STYLE, **(line_styles[len(cues)] or {})} if len(cues) < len(line_styles) else dict(TEMPLATE_STYLE)
        cues.append((start, end, karaoke, plain, fields[4].strip(), style))

translation_lines = []
if args.translation_file:
    translation_lines = [
        (line["start"] + INTRO_DELAY, line["end"] + INTRO_DELAY, " ".join(re.sub(r"[{}\\]", "", line["translation"]).split()))
        for line in json.loads(args.translation_file.read_text(encoding="utf-8"))["lines"]
        if line.get("translation", "").strip()
    ]
    if not translation_lines:
        raise SystemExit("Translation file has no translated lines")
    if args.translation_mode == "only":
        # A translation cannot follow the melody word by word, so each line's
        # sweep is spread evenly over the time the original line is sung.
        cues = []
        for start, end, text in translation_lines:
            words = text.split()
            share = max(1, round((end - start) * 100 / len(words)))
            karaoke = "".join(f"{{\\kf{share}}}{word} " for word in words).rstrip()
            cues.append((start, end, karaoke, text, "", dict(TEMPLATE_STYLE)))

if not cues:
    raise SystemExit("No timed Karadeo lyric cues found")

# The Jan-approved Rehab pattern: centred title card first, with no lyric
# highlight competing against it. The approved intro sits below the big logo.
title_end = ass_time(max(0, INTRO_DELAY-.05))
title_y = (640, 760, 830) if args.approved_intro else (390, 510, 580)
if args.intro_countdown:
    title_y = (800, 910, 980)
cx = W // 2
ty = [px(y * SY) for y in title_y]
events = [
    f"Dialogue: 2,0:00:00.00,{title_end},Title,,0,0,0,,{{\\pos({cx},{ty[0]})\\fad(250,250)}}{args.title}",
    f"Dialogue: 2,0:00:00.08,{title_end},Artist,,0,0,0,,{{\\pos({cx},{ty[1]})\\fad(300,250)}}{args.artist}",
    rf"Dialogue: 2,0:00:00.16,{title_end},Footer,,0,0,0,,{{\pos({cx},{ty[2]})\fs{px(30*FS)}\fad(350,250)}}{args.language_label}",
]
if args.intro_countdown:
    events=[]
    for value,y,size in [(args.title,820,90),(args.artist,925,48),(args.language_label,995,28)]:
        events.append(f'Dialogue: 5,0:00:00.00,{ass_time(max(0,INTRO_DELAY-.15))},PageBase,,0,0,0,,{{\\pos({cx},{px(y*SY)})\\fs{px(size*FS)}\\fad(80,160)}}{value}')

# Split long cues into measured rows instead of changing their font size.
font = ImageFont.truetype(str(font_file()), max(1, LYRIC_SIZE))
max_width = TEMPLATE.get('max_text_width', 1640) * SX
rows = []
for start, end, karaoke, plain, part, style in cues:
    words = re.findall(r'\{\\kf(\d+)\}([^{}]*)', karaoke)
    if not words:
        words = [(str(round((end-start)*100)), plain)]
    total = sum(max(1, int(t)) for t, word in words)
    elapsed = 0
    group_start = start
    from lyric_wrap import balanced_groups
    groups=balanced_groups(words,font.getlength,max_width)
    for index,items in enumerate(groups):
        group=[]
        for timing,word in items:
            duration=(end-start)*max(1,int(timing))/total
            group.append((max(1,round(duration*100)),word));elapsed+=duration
        text = ''.join(f'{{\\kf{t}}}{w}' for t,w in group)
        group_end=end if index==len(groups)-1 else start+elapsed
        rows.append((group_start,group_end,text,strip_tags(text),part,style))
        group_start=group_end
cues = rows
def line_style_tags(style):
    """ASS override tags for one line's style: (resting text, word sweep)."""
    def colour(key):
        return f"&H{ass_colour(style[key])[4:]}&"
    shared = ""
    if "font" in style:
        shared += f"\\fn{style['font']}"
    if "bold" in style:
        shared += f"\\b{1 if style['bold'] else 0}"
    if "italic" in style:
        shared += f"\\i{1 if style['italic'] else 0}"
    if "outline" in style:
        shared += f"\\bord{style['outline'] * FS:.1f}"
    if "shadow" in style:
        shared += f"\\shad{style['shadow'] * FS:.1f}"
    if "opacity" in style and style["opacity"] < 1:
        shared += f"\\alpha&H{round((1 - style['opacity']) * 255):02X}&"
    if "letter_spacing" in style:
        shared += f"\\fsp{style['letter_spacing'] * FS:.1f}"
    if "rotation" in style:
        shared += f"\\frz{style['rotation']:g}"
    if style.get("fade_in") or style.get("fade_out"):
        shared += f"\\fad({round(style.get('fade_in', 0) * 1000)},{round(style.get('fade_out', 0) * 1000)})"
    base, sweep = shared, shared
    if "colour" in style:
        base += f"\\1c{colour('colour')}"
        sweep += f"\\2c{colour('colour')}"
    if "highlight_colour" in style:
        sweep += f"\\1c{colour('highlight_colour')}"
    edge = "box_colour" if "box_colour" in style else "outline_colour"
    if edge in style:
        base += f"\\3c{colour(edge)}"
    sweep_edge = "box_colour" if "box_colour" in style else "highlight_outline_colour" if "highlight_outline_colour" in style else edge
    if sweep_edge in style:
        sweep += f"\\3c{colour(sweep_edge)}"
    return base, sweep


PART_COLOURS = {key.upper(): ass_colour(value) for key, value in
                TEMPLATE.get("part_colours", {"M": "#4FC3F7", "F": "#FF6FAE", "D": "#FFD54F"}).items()}

# One persistent ASS event per row: no duplicate text layers, no highlight
# disappearing back to white, and no fragments during page transitions.
spacing = TEMPLATE['line_spacing'] * TEMPLATE.get('line_height', 1.0) * FS
center = TEMPLATE['block_center_y'] * SY
row_y = [px(center + (i - (LINES_PER_PAGE - 1) / 2) * spacing) for i in range(LINES_PER_PAGE)]
previous_page_end = INTRO_DELAY - 0.03
page_starts = []
for page_start_index in range(0, len(cues), LINES_PER_PAGE):
    page = cues[page_start_index: page_start_index + LINES_PER_PAGE]
    page_start = max(previous_page_end, page[0][0] - 0.35)
    if args.center_intro_countdown and page_start_index == 0:
        # Keep the lyric page off-screen until the logo has reached its corner.
        page_start = max(page_start, page[0][0])
    page_starts.append(page_start)
    next_index = page_start_index + len(page)
    page_end = page[-1][1] + 0.10
    if next_index < len(cues):
        # Hold the current page right up to the next one.  No empty frames
        # flash between lyric pages, even when there is a pause in singing.
        page_end = min(cues[next_index][0], max(page[-1][1], cues[next_index][0] - 0.35))
    for position, (start, end, karaoke, plain, part, style) in enumerate(page):
        x = px(style['x'] * SX) if 'x' in style else cx
        y = px(style['y'] * SY) if 'y' in style else row_y[position]
        size = px(style['size'] * FS) if 'size' in style else LYRIC_SIZE
        base_tags, sweep_tags = line_style_tags(style)
        pos = f"{{\\pos({x},{y})\\fs{size}{base_tags}}}"
        sweep_pos = f"{{\\pos({x},{y})\\fs{size}{sweep_tags}}}"
        # Duets: the sweep takes the singer's colour; other rows stay neutral.
        if part.upper() in PART_COLOURS:
            sweep_pos = sweep_pos[:-1] + f"\\1c&H{PART_COLOURS[part.upper()][4:]}&}}"
        base_name, sweep_name = ('PageBaseBox', 'PageSweepBox') if style.get('box_colour') else ('PageBase', 'PageSweep')
        # Adjacent, non-overlapping events keep identical text geometry.
        # Only the active interval uses orange; past/future rows are white.
        active_start = max(start, page_start)
        active_end = min(end, page_end)
        if page_start < active_start:
            events.append(f"Dialogue: 0,{ass_time(page_start)},{ass_time(active_start)},{base_name},,0,0,0,,{pos}{plain}")
        if active_start < active_end:
            events.append(f"Dialogue: 0,{ass_time(active_start)},{ass_time(active_end)},{sweep_name},,0,0,0,,{sweep_pos}{karaoke}")
        if active_end < page_end:
            events.append(f"Dialogue: 0,{ass_time(active_end)},{ass_time(page_end)},{base_name},,0,0,0,,{pos}{plain}")
        # Stop before the following cue begins. This prevents the progress
        # highlight from meeting the next lyric page.
        absolute = page_start_index + position
        active_start = max(start, page_start)
        active_end = min(end, cues[absolute + 1][0] - 0.06) if absolute + 1 < len(cues) else end
        # Do not show a coloured lyric until its page is on screen. For songs
        # with vocals at 0:00, an already-finished opening cue stays white
        # rather than bleeding through the title card.
        # Progress stays on this single row until the page changes.
    previous_page_end = page_end

if args.gap_countdown:
    # After an instrumental break of 8 s or more, three dots above the next
    # line disappear one per second, so singers know exactly when to come in.
    for index in range(1, len(cues)):
        start = cues[index][0]
        if start - cues[index - 1][1] < 8:
            continue
        y = row_y[index % LINES_PER_PAGE] - px(LYRIC_SIZE * 0.95)
        for step, dots in enumerate(("● ● ●", "● ●", "●")):
            events.append(f"Dialogue: 2,{ass_time(start - 3 + step)},{ass_time(start - 2 + step)},PageBase,,0,0,0,,"
                          f"{{\\pos({cx},{y})\\fs{px(LYRIC_SIZE * 0.6)}\\1c&H{HIGHLIGHT[4:]}&}}{dots}")

if translation_lines and args.translation_mode == "below":
    # The translation of the line being sung, in one fixed place below the page.
    translation_y = px(TEMPLATE.get("translation_y", 975) * SY)
    translation_size = px(TEMPLATE.get("translation_size", TEMPLATE["font_size"] * 0.72) * FS)
    translation_colour = ass_colour(TEMPLATE.get("translation_colour", "#9FE7FF"))
    HEADER = HEADER.replace("[Events]", f"Style: Translation,{FONT},{translation_size},{translation_colour},{translation_colour},{EDGE},&H00000000,0,-1,0,0,100,100,0,0,1,{px(4*FS)},{px(1*FS)},5,80,80,0,1\n\n[Events]")
    for start, end, text in translation_lines:
        events.append(f"Dialogue: 1,{ass_time(start)},{ass_time(end)},Translation,,0,0,0,,{{\\pos({cx},{translation_y})\\q0\\fad(120,120)}}{text}")

sweep_style = next(l for l in HEADER.splitlines() if l.startswith('Style: PageBase,')).replace('PageBase,', 'PageSweep,').replace(f'{TEXT},{TEXT}', f'{HIGHLIGHT},{TEXT}')
HEADER = HEADER.replace('[Events]', sweep_style + '\n\n[Events]')
if any(cue[5].get('box_colour') for cue in cues):
    # BorderStyle 3 draws an opaque box (in the outline colour) behind the line.
    boxes = [line.replace('Style: PageBase,', 'Style: PageBaseBox,').replace('Style: PageSweep,', 'Style: PageSweepBox,')
                 .replace(f',0,0,1,{OUTLINE},', f',0,0,3,{OUTLINE},')
             for line in HEADER.splitlines() if line.startswith(('Style: PageBase,', 'Style: PageSweep,'))]
    HEADER = HEADER.replace('[Events]', '\n'.join(boxes) + '\n\n[Events]')

# Circular logo countdown during a substantial instrumental introduction.
# Use the actual first Karadeo cue, not an assumed twenty-second duration.
first_vocal = cues[0][0]
logo_move_end = first_vocal
logo_move_start = max(3.0, first_vocal - 0.5)
center_countdown = args.center_intro_countdown and logo_move_start > 3.0
if args.intro_countdown:
    events += intro_countdown.events(INTRO_DELAY,FPS,W,H,ass_time)
elif first_vocal - INTRO_DELAY >= 8:
    countdown_start = max(3.0, INTRO_DELAY) if args.preserve_source_timeline else INTRO_DELAY
    countdown_end = logo_move_start if center_countdown else first_vocal
    for frame in range(math.ceil((countdown_end-countdown_start)*FPS)):
        t = countdown_start + frame/FPS
        fraction = max(0, (countdown_end-t)/(countdown_end-countdown_start))
        angles = [(-math.pi/2 + fraction*2*math.pi*i/90) for i in range(91)]
        ox, oy = (W/2, 330*SY) if center_countdown else (W-138*FS, 132*FS)
        radius = 245 if center_countdown else 112
        points = [(ox+radius*FS*math.cos(a),oy+radius*FS*math.sin(a)) for a in angles]
        points += [(ox+(radius-6)*FS*math.cos(a),oy+(radius-6)*FS*math.sin(a)) for a in reversed(angles)]
        drawing = 'm ' + ' l '.join(f'{round(x)} {round(y)}' for x,y in points)
        events.append(f'Dialogue: 3,{ass_time(t)},{ass_time(min(t+1/FPS,first_vocal))},PageBase,,0,0,0,,{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&HFFFF00&}}{drawing}{{\\p0}}')
    if center_countdown:
        # One stable number per second, below the large logo. The final zero
        # marks the move to the corner; the first lyric keeps its old timestamp.
        for remaining in range(math.ceil(countdown_end-3), 0, -1):
            start=max(3.0, countdown_end-remaining)
            end=countdown_end-remaining+1
            events.append(f'Dialogue: 4,{ass_time(start)},{ass_time(end)},PageBase,,0,0,0,,{{\\pos({cx},{px(690*SY)})\\fs{px(110*FS)}\\bord{px(5*FS)}}}{remaining}')
        events.append(f'Dialogue: 4,{ass_time(logo_move_start)},{ass_time(logo_move_end)},PageBase,,0,0,0,,{{\\pos({cx},{px(690*SY)})\\fs{px(110*FS)}}}0')
LAYERS = layer_tools.empty()
if args.layers:
    LAYERS = layer_tools.validate({**layer_tools.empty(), **json.loads(args.layers.read_text(encoding="utf-8"))}, ROOT)
for item in LAYERS["texts"]:
    # Free text overlays (titles, "Chorus!", credits) above the lyrics, with keyframes.
    events += layer_tools.text_events(item, INTRO_DELAY, SX, SY, FS, ass_time, ass_colour,
                                      cues[-1][1] - INTRO_DELAY + 5)
output_ass.write_text(HEADER + "\n".join(events) + "\n", encoding="utf-8-sig")

background_index = args.background % max(1, len(BACKGROUNDS))
background = BACKGROUNDS[background_index] if BACKGROUNDS else None
second_background = None
if args.background_file:
    background = args.background_file
if args.background_folder:
    selected = sorted(p for p in args.background_folder.iterdir() if p.suffix.lower() in ('.jpeg', '.jpg', '.png'))
    if len(selected) != 2:
        raise SystemExit('The selected background folder must contain two images')
    background, second_background = selected
animated_background = ROOT / "work" / "bowlnfun" / "animated_backgrounds" / f"bg_{background_index}.mp4"
ass_filter = output_ass.name  # FFmpeg cwd is song_dir; avoids drive/quote escaping bugs.
fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
# Video backgrounds loop for the whole song; stills may drift slowly ("pan").
background_is_video = Path(background).suffix.lower() in (".mp4", ".mov", ".webm", ".mkv")
if not background_is_video:
    # Preserve the entire still image. Fill/crop removes heads on portrait photos.
    fit = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    if os.environ.get('KARAOKE_STILL_FIT') == 'cover-top':
        fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}:(iw-ow)/2:0,setsar=1"
if background_is_video:
    fit = f"fps={FPS}," + fit
    if args.sync_background:
        fit += f',tpad=start_mode=clone:start_duration={INTRO_DELAY:g}:stop_mode=clone:stop=-1,setpts=PTS-STARTPTS'
motion = ""
if args.motion == "pan":
    motion = (f",scale={px(W*1.12)//2*2}:{px(H*1.12)//2*2},crop={W}:{H}"
              ":x='(iw-ow)/2*(1+sin(t/17))':y='(ih-oh)/2*(1+cos(t/23))'")
background_filter = f"[0:v]{fit}{motion}[bg];"
extra_inputs = []
if second_background:
    switch_time = min(page_starts, key=lambda t: abs(t - cues[-1][1]/2))
    background_filter = (
        f"[0:v]{fit}[bg0];"
        f"[3:v]{fit}[bg1];"
        f"[bg0][bg1]overlay=0:0:enable='gte(t,{switch_time:.2f})'[bg];"
    )
    extra_inputs = ['-loop', '1', '-framerate', str(FPS), '-i', str(second_background)]

# Backing audio, optionally with a quiet guide vocal and a key change.
audio_steps = []
audio_source = "[1:a]"
if args.guide_vocal_level:
    guide_index = 3 + (1 if second_background else 0)
    extra_inputs += ['-i', str(args.guide_vocal_file)]
    audio_source = f"[1:a][{guide_index}:a]"
    audio_steps += [f"amix=inputs=2:duration=first:normalize=0:weights='1 {args.guide_vocal_level:g}'",
                    "alimiter=limit=0.98"]
if args.pitch:
    audio_steps.append(f"rubberband=pitch={2 ** (args.pitch / 12):.6f}")
if args.gain_db:
    audio_steps.append(f"volume={args.gain_db:.2f}dB")
with av.open(str(audio)) as audio_container:
    audio_duration = audio_container.duration / av.time_base
if args.fade_in:
    audio_steps.append(f"afade=t=in:st=0:d={args.fade_in:g}")
if args.fade_out:
    audio_steps.append(f"afade=t=out:st={max(0, audio_duration - args.fade_out):.3f}:d={args.fade_out:g}")


backing = LAYERS.get("backing", {})
if backing.get("mute"):
    audio_steps.append("volume=0")
elif backing.get("volume_db"):
    audio_steps.append(f"volume={backing['volume_db']:.2f}dB")

# Media layers and extra audio tracks become extra FFmpeg inputs after the fixed ones.
next_input = 3 + extra_inputs.count('-i')
media_inputs, media_chains = layer_tools.media_graph(LAYERS["media"], next_input, ROOT, INTRO_DELAY, SX, SY, FPS)
next_input += media_inputs.count('-i')
track_inputs, track_labels, track_chains = layer_tools.audio_graph(LAYERS["audio"], next_input, ROOT, INTRO_DELAY)
extra_inputs += media_inputs + track_inputs


def audio_graph(delay_ms: int) -> str:
    if not track_labels:
        return audio_source + ",".join(audio_steps + [f"adelay={delay_ms}:all=1"]) + "[a]"
    main = audio_source + ",".join(audio_steps + [f"adelay={delay_ms}:all=1"]) + "[a0]"
    mix = f"[a0]{''.join(track_labels)}amix=inputs={len(track_labels) + 1}:duration=first:normalize=0[a]"
    return ";".join([main, *track_chains, mix])

filter_graph = background_filter + (
    # Clear, gently animated bowling background.  It stays subdued enough
    # for lyrics to dominate without the previous heavy blur.
    f"[2:v]scale={px(180*FS)}:-1[logo];"
    f"[bg][logo]overlay=W-w-{px(48*FS)}:{px(42*FS)},subtitles='{ass_filter}'[v];"
    + audio_graph(2600)
)
if args.approved_intro:
    q = f'min(1,max(0,(t-{max(0,INTRO_DELAY-.6):g})/0.5))'
    if center_countdown:
        q = f'min(1,max(0,(t-{logo_move_start:.3f})/{logo_move_end-logo_move_start:.3f}))'
    # Cache the scaled still frame instead of decoding/scaling a large PNG
    # 25 times per second. The displayed pixels and timestamps are unchanged.
    if not second_background:
        still = '' if background_is_video else f',loop=loop=-1:size=1:start=0,setpts=N/({FPS}*TB)'
        background_filter = f'[0:v]{fit}{still}{motion}[bg];'
    # The logo starts large in the centre and settles into the top-right corner.
    logo_x, logo_y = W/2, 330*SY
    filter_graph = background_filter + (
        f"[2:v]format=rgba,loop=loop=-1:size=1:start=0,setpts=N/({FPS}*TB),scale=w='{num(420*FS)}-{num(240*FS)}*{q}':h=-1:eval=frame[logo];"
        f"[bg][logo]overlay=x='{num(logo_x)}+{num(W-138*FS-logo_x)}*{q}-w/2':y='{num(logo_y)}-{num(logo_y-132*FS)}*{q}-h/2',subtitles='{ass_filter}'[v];"
        + audio_graph(round(INTRO_DELAY*1000))
    )
if media_chains:
    # Media layers sit between the background and the logo/lyrics.
    filter_graph = filter_graph.replace("[bg][logo]", media_chains + "[bgx][logo]", 1)
logo_asset = LOGO
if args.intro_countdown:
    logo_asset = LOGO
    if not logo_asset.is_file():raise FileNotFoundError(logo_asset)
    corner_index = 3 + extra_inputs.count('-i')
    extra_inputs += ['-framerate',str(FPS),'-i',str(LOGO)]
    if background_is_video and args.sync_background:
        intro_still,still_source_time=intro_countdown.first_visible_frame(background,song_dir/'intro-background.png',with_time=True)
        intro_cleanup=''
        if args.branding_plan:
            from inline_branding import filters
            intro_cleanup=filters(background,args.branding_plan,at_time=still_source_time)
            if intro_cleanup:intro_cleanup+=','
        still_index=3+extra_inputs.count('-i')
        extra_inputs += ['-framerate',str(FPS),'-i',str(intro_still)]
        background_filter=background_filter.replace('[bg];','[bgraw];') + (
            f'[{still_index}:v]{intro_cleanup}loop=loop=-1:size=1:start=0,setpts=N/({FPS}*TB),'
            f'scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[introbackground];'
            f"[bgraw][introbackground]overlay=0:0:enable='lt(t,{INTRO_DELAY:g})'[bg];"
        )
    background_label='bgx' if media_chains else 'bg'
    intro_scale = float(os.environ.get('KARAOKE_INTRO_LOGO_SCALE', '1'))
    corner_margin_x = int(os.environ.get('KARAOKE_CORNER_MARGIN_X', '48'))
    corner_margin_y = int(os.environ.get('KARAOKE_CORNER_MARGIN_Y', '42'))
    if not math.isfinite(intro_scale) or not 0.1 <= intro_scale <= 1:
        raise ValueError('KARAOKE_INTRO_LOGO_SCALE must be between 0.1 and 1')
    if not 0 <= corner_margin_x <= 300 or not 0 <= corner_margin_y <= 300:
        raise ValueError('Corner margins must be between 0 and 300')
    filter_graph = background_filter + media_chains + (
        f"[2:v]format=rgba,loop=loop=-1:size=1:start=0,setpts=N/({FPS}*TB),trim=duration={INTRO_DELAY:g},{intro_countdown.reference_logo_filter(INTRO_DELAY,FS*intro_scale,countdown_settings['countdown_style'],countdown_settings['countdown_colour'])}[intrologo];"
        f"[{corner_index}:v]format=rgba,loop=loop=-1:size=1:start=0,setpts=N/({FPS}*TB),scale={px(180*FS)}:-1[cornerlogo];"
        f"[{background_label}][intrologo]overlay=x='{num(W/2)}-w/2':y='{num(330*SY)}-h/2':enable='lt(t,{INTRO_DELAY:g})'[opening];"
        f"[opening][cornerlogo]overlay=W-w-{px(corner_margin_x*FS)}:{px(corner_margin_y*FS)}:enable='gte(t,{INTRO_DELAY:g})',subtitles='{ass_filter}'[v];"
        + audio_graph(round(INTRO_DELAY*1000))
    )
staged_mp4 = output_mp4.with_name(output_mp4.stem + '.rendering.mp4')
output_duration = audio_duration + INTRO_DELAY
range_start = args.start or 0.0
range_end = min(args.end, output_duration) if args.end is not None else output_duration
if range_start >= range_end:
    raise SystemExit(f'Export range starts after the video ends ({output_duration:.2f}s)')
# Output-side seek: frames are rendered on the full timeline, then trimmed,
# so lyric timing inside the excerpt is identical to the full export.
trim = ['-ss', f'{range_start:.3f}'] if range_start else []
still_input = [] if args.approved_intro and not second_background else ['-loop','1']
logo_input = [] if args.approved_intro else ['-loop','1']
background_input = ((['-i', str(background)] if args.sync_background else ['-stream_loop', '-1', '-i', str(background)]) if background_is_video
                    else [*still_input, "-framerate", str(FPS), "-i", str(background)])
metadata = []
for key, value in (("title", args.metadata_title), ("artist", args.metadata_artist)):
    if value:
        metadata += ["-metadata", f"{key}={value}"]
encoding = (['-c:v','libx264','-preset',args.preset,'-crf',str(args.crf)]
            if args.encoder == 'libx264' else
            ['-c:v','h264_nvenc','-preset','p4','-rc','vbr','-cq',str(args.nvenc_cq),'-b:v','0'])
from output_size import constrained_args, enforce
if args.video_bitrate is not None:
    from output_size import bitrate_args
    encoding = ['-c:v',args.encoder,'-preset',args.preset if args.encoder=='libx264' else 'p4'] + bitrate_args(range_end-range_start,args.video_bitrate)
else:
    encoding += constrained_args(range_end-range_start)
if args.branding_plan:
    from inline_branding import filters
    cleanup = filters(background,args.branding_plan)
    if cleanup:
        # Source coordinates and times, BEFORE scaling, frame-rate conversion or intro padding.
        filter_graph=filter_graph.replace('[0:v]',f'[0:v]{cleanup},',1)
command = [
    str(FFMPEG), "-y", *ffmpeg_input_filter_args(), *background_input, "-i", str(audio), *logo_input, "-framerate", str(FPS), "-i", str(logo_asset),
    *extra_inputs, "-filter_complex", filter_graph, "-map", "[v]", "-map", "[a]", "-shortest", *trim, "-t", str(range_end - range_start),
    "-r", str(FPS), *encoding, *ffmpeg_thread_args(), "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "192k", '-map_metadata', '-1', *metadata, "-movflags", "+faststart", str(staged_mp4),
]
print("rendering", output_mp4)
subprocess.run(command, check=True, cwd=song_dir)
enforce(staged_mp4)
subprocess.run([str(FFMPEG), '-v', 'error', '-i', str(staged_mp4), '-f', 'null', '-'], check=True)
with staged_mp4.open('rb') as src, output_mp4.open('xb') as dst:
    import shutil
    shutil.copyfileobj(src, dst)
staged_mp4.unlink()
print(output_mp4)
