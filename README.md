# SMC Karaoke Pro

The maintained entry point is **`karaoke.py`**. This project contains the existing
ten-stage processing workflow, portable runtime configuration, residual-voice
and audio-loss screening, bounded alternative-model retries, comparison clips,
and explicit review before final delivery. Existing output videos are preserved.

Read [the portable workflow and commands](docs/PORTABLE_WORKFLOW.md).

Windows setup:

```powershell
py -3.11 setup.py
.\.venv-zoom\Scripts\python.exe karaoke.py doctor
.\.venv-zoom\Scripts\python.exe karaoke.py run --job config\my-song.json
```

Copy `config/job.example.json` for a normal video or
`config/job.zoom.example.json` for a Zoom source. Fill in your source/title/artist.
Linux/macOS use Python 3.11 and `.venv-zoom/bin/python`; see the platform notes
in the guide. Copy `.env.example` to `.env` for path/device/cache overrides.

The first run stops for lyric review. A final export requires actual listening,
lyric and timing review; model confidence is never an automatic approval.
The high-quality preview is the exact file copied to final delivery after review.

No fresh environment installation, AI-model run or full-song render was executed
for this refactor, as requested. Lightweight checks: 71 tests, 3 fixture skips.

## Earlier local-tool documentation

The notes below describe the preserved legacy entry points. Use the guide above
for the new standalone workflow and its additional quality requirements.

Open-source karaoke workflows: Demucs separation, Faster-Whisper transcription, WhisperX alignment, RapidOCR screen recovery, and FFmpeg rendering. No paid API, API key, browser login, or Node setup is required.

Step 7 highlight colour is configurable per song: set `"highlight_colour": "#00FF00"`
inside the job's `render` object for green, or `"#FFA500"` for orange. If omitted,
the selected template colour is used (orange in the default four-line template).
The standalone renderer also accepts `--highlight-colour "#00FF00"`. Existing
per-line/duet colour overrides retain their precedence. Changing only this render
setting reuses the separation/transcript/alignment workspace and requires a new
render/review; it does not recolour already exported MP4s.

New canonical jobs show a numeric countdown and a closing white arc around the
centred logo throughout the added intro (10 seconds by default). The title/artist
sit below it, then the original white-circle logo moves to the top-right. The
original video's first visible frame remains behind the intro; video and instrumental
start together after that delay. Set `render.intro_countdown` to `false` to opt out.
This intro is independent of how soon the first lyric occurs. Existing MP4s are
not changed until rendered again.

The arc uses the same original artwork, 1.18× expansion and angular alpha wipe
as the Taylor Swift – Patient Zero reference, not a drawn circle outline. The
centred logo stays in place for the countdown, then the white-circle corner logo
appears at the intro boundary. `tools/refresh_intro.py` can update an existing
output through the next keyframe while retaining all audio and later video
packets/timestamps; it refuses mismatching codec headers and verifies full decode.

Canonical preview/delivery now checks visible source branding. Full-frame OCR
samples include the corners, opening and final frame. Recognised source credits
(Xtendamix, record-label/copyright text and related marks) trigger a bounded
localized background cleanup that includes the adjacent artist/title credit
stack. The original source and processed instrumental remain intact. The cleaned
background and rendered output are scanned again; a remaining known mark or a
failed/missing scan blocks delivery. Reports are saved under the job's
`branding-background/` and `branding-output.json`. Cleanup interpolates a small
region; it cannot recover the hidden original pixels. OCR sampling cannot
guarantee detection of brief/unreadable text or graphical/invisible watermarks;
visual review remains required. Removing text does not alter copyright or grant
distribution rights.

OCR uses bounded 1280-pixel full-frame inputs, small recognition batches and one
shared OCR slot. Completed samples are saved atomically and an interrupted scan
resumes from its last saved timestamp. A missing, failed or partial scan is never
treated as a pass. Audio-model jobs use their separate existing processing slot.

`tools/export_checked_sample.py --job config/job.json --name "Artist - Song.mp4"`
exports a review sample after fresh decode, audio-timeline and branding checks.
It does not mark a video as listened to or fully approved, and does not weaken
the normal `approve`/`render` delivery gate. Changed renderer/media dependencies
block this export; unrelated helper/test revisions are recorded in its report.

The two downloaded test jobs are `config/hilary-duff-catastrophe.json` and
`config/kygo-ava-max-before-you-know-it-final.json`. For the latter, run
`python tools/prepare_kygo_background.py` before processing after a work-folder
cleanup. It regenerates the source-bound clean frame/feathered lyric-band patch
under `assets/source-patches` and the job's layer settings. These are pixels from
the original source, not a replacement background. Media layers can explicitly
use `"timeline": "output"` to cover the added intro without negative song times;
the existing default remains the source timeline.

If a native CPU separation worker needs a bounded retry, the environment variable
`KARAOKE_SEPARATION_THREADS=2` reduces its thread count without changing the model,
source or processing workspace. This is not a promised processing-time limit.

## Setup

Run `.\setup.ps1` (or `.\setup.ps1 -Cuda` on an NVIDIA PC) to create the separate Python 3.11 environments `.venv-zoom` and `.venv-demucs` from `requirements-zoom.txt` and `requirements-demucs.txt`. It finishes with `tools/local_karaoke.py doctor`, which checks FFmpeg, logo, environments, templates and every song's files. Models use the GPU automatically when CUDA is available; set `KARAOKE_DEVICE=cpu` or `cuda` to override. Model weights were deliberately not copied or downloaded. Running model stages may download them again and consume disk space.

FFmpeg is at `tools/ffmpeg/ffmpeg.exe`. The logo and font are in `assets/`; the existing white-circle logo is the default. Source songs must be supplied separately. Work files are generated automatically; no email integration remains.

## Song workflow

Use `tools/local_karaoke.py` with stages `status`, `add`, `separate`, `audit`, `transcribe`, `lyrics`, `accept-transcript`, `history`, `restore`, `align`, `translate`, `accept-translation`, `preview`, `approve`, `render`, and `draft`. Configure songs in `local_karaoke_jobs.json` (or with `add`). Optional per-song `render` settings choose a layout template from `config/templates`, canvas size (e.g. vertical 1080x1920), export range, guide-vocal level and key change. Language can be `auto`. Lyrics require correction and `--confirm-lyrics`; final delivery requires listening review and `--confirm-listened`.

Detailed instructions: [local workflow](docs/LOCAL_OPEN_SOURCE.md).

## Existing Zoom karaoke videos

`recover_zoom_screen.py` and `finish_zoom_screen.py` recover visible lyrics and their colour sweeps. `compare_zoom_friends.py` now has only local stages: `scan`, `tracks`, `measure`, `recover`, `contact`, `render`, `verify`. Its historical filename is retained for imports. These adapters contain song-specific paths/corrections, not a generic automatic importer.

The renderer supports `--approved-intro --preserve-source-timeline` to show the logo during an existing intro without delaying audio or lyrics.

## Scope

The original sibling `karaoke` workspace remains untouched. Paid integrations, account configuration, browser/email automation, and the machine-specific model-deletion utility were removed from this copy. Local renderers, audits, tests and optional open-source translation remain. Historical service names in comments or cached-input paths do not make API calls.

The subsequent local preparation installed both environments and downloaded the required English-song models into `models/`. Offline model loading and a synthetic 1080p render have passed. The full-song Taylor Swift test also produced a 1080p review preview with technical decode/audio checks passing. It required lyric corrections and retains timing flags; full listening/content approval is pending. Setup success alone is not a quality certificate.

## Prepare and clean completed jobs

For measured single-song overlap, install `requirements-benchmark.txt` into the
zoom environment and use `tools/parallel_song_benchmark.py --job config/job.json
--report reports/benchmarks/unique-run`. Source branding checks overlap Demucs;
after separation, vocal ASR overlaps instrumental QC in isolated directories
when RAM permits. CSV samples record the project's process tree separately from
total PC memory. Report working sets and private committed bytes separately:
neither is an exact exclusive physical-RAM measurement. Download/model setup
and processing times are recorded separately. `--draft` explicitly renders and
exports a `BENCHMARK.mp4` with unreviewed ASR lyrics, no human approval, and fresh
technical checks. Normal `karaoke.py` approval gates remain in effect.

Run `prepare_project.py` with Python 3.11 to install and verify the project. Resume
using `prepare_project.py --verify-installed`. See [portable workflow](docs/PORTABLE_WORKFLOW.md).

Successful final `render` and `export_checked_sample.py` exports now automatically
remove that song's work folder and renderer scratch after verifying the saved MP4
hash and full audio/video decode. Small verification receipts remain under
`reports/completed`; a technical sample still has no human approval. Failed or
unfinished jobs retain their files for recovery. Pass `--keep-work` to retain
files when you plan to edit or export extras. Source videos, code, models,
configuration, environments, and `out` are preserved.

For an older retained, human-approved delivery, inspect cleanup with:

```powershell
.\.venv-zoom\Scripts\python.exe karaoke.py cleanup --job config/rei-ami-2loud.json
```

Add `--apply` to delete that song's work folder and renderer scratch. Cleanup checks
the final MP4 hash, full audio/video decode, delivery status and review evidence.
It preserves the final output, original source, scripts, configuration, environments
and models. It refuses running jobs, links/junctions, unsafe paths, and code/models
found inside a work folder. Cleaning removes correction/resume history; processing
again then starts from the original source.
