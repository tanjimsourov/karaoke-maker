# Portable pro workflow

The maintained entry point is `karaoke.py`. It reuses the existing Demucs,
Whisper/WhisperX, editor, translation and FFmpeg implementations. The original
ten-stage sequence is retained; audio screening augments stages 3/4 and review.
No sibling checkout, API key, browser account or paid inference is required.

## Supported environment

Use Python 3.11 on Windows x64, Linux, or macOS Apple Silicon, with sufficient
RAM/storage for the chosen models. Intel macOS is excluded by the pinned modern
WhisperX/PyTorch stack. CUDA is optional on supported NVIDIA Windows/Linux hosts.
This is portable configuration, not a claim that every hardware/OS combination
has been executed or that every recording can yield clean accompaniment.

Windows includes a local FFmpeg binary. Linux/macOS need FFmpeg on PATH (including
libass, libx264, AAC, rubberband and ebur128). Fonts must cover the chosen language.
Set `KARAOKE_FONT` to a TTF if the system defaults do not cover the lyrics.

## Setup

The prepared Windows installation keeps both environments in this directory and
the required English-song model set in `models/`. `assets/logo.png` is the existing
white-circle logo; the original coloured asset is retained as `logo-original.png`.

For fresh CPU preparation, run `prepare_project.py` with Python 3.11. It installs
dependencies, downloads and loads Demucs, Whisper large-v3-turbo/base, the large
English WAV2VEC2 alignment model, AST and UVR, then runs the checks.
`prepare_project.py --verify-installed` resumes without reinstalling environments.
First preparation needs internet and several GB of space. Other alignment
languages and optional translation/BS-Roformer features can need additional models.

Check the prepared models without downloads:

```powershell
.\.venv-zoom\Scripts\python.exe tools/prepare_models.py --offline
```

Installed versions are recorded in `config/environment-zoom.freeze.txt` and
`config/environment-demucs.freeze.txt`. Successful model checks do not certify a
particular song's lyrics or the quality of its vocal removal.

From the project directory:

```powershell
py -3.11 setup.py
.\.venv-zoom\Scripts\python.exe karaoke.py doctor
```

Linux/macOS:

```sh
python3.11 setup.py
.venv-zoom/bin/python karaoke.py doctor
```

`setup.py --check` prints installation commands without installing or loading
models. `--cuda cu128` opts into NVIDIA wheels; `--extra-separation` installs the
optional BS-Roformer adapter. Setup preserves existing environments and never
deletes them. It copies `.env.example` to `.env` only when `.env` does not exist.
An interrupted pip installation can be resumed by running setup again.

The two pinned environments are separate to avoid changes to one model stack
affecting the other. Torch 2.8 is a shared supported baseline; models and the
separation algorithm have not been replaced. Only the optional extra separation
environment installs audio-separator. The original source refactor did not run
models; the subsequent preparation installs and verifies the local environments.

All path settings are in `.env.example`. Relative settings resolve against this
project, independently of the terminal directory. An existing environment can
be used explicitly through `KARAOKE_DEMUCS_PYTHON`; it is never guessed from a
sibling directory. Default model caches are inside `models/` rather than shared
user caches. First use downloads free model files when allowed. Set
`KARAOKE_ALLOW_MODEL_DOWNLOAD=0` for offline operation after caching the models.
Missing models then produce explicit incomplete-screening/error reports.

## The ten stages

1. Load the source, verify its fingerprint and strictly decode its audio/video.
2. Decode the original audio without lossy intermediate audio compression.
3. Run the existing Demucs htdemucs_ft vocal/instrument separation.
4. Combine drums+bass+other and screen for remaining singing, silence, clipping,
   unexpected level drops and severe energy loss. If flagged, try configured
   alternatives on the ORIGINAL audio, retaining each candidate and its logs.
5. Transcribe the vocal stem with Whisper large-v3-turbo, then correct/review it.
6. Align accepted lyrics using WhisperX and generate the timing report. English
   uses the working large WAV2VEC2 alignment model, with the existing memory-map
   loading approach. `alignment_model` can explicitly override it. Whisper
   transcription retains the working 15-second chunk setting by default.
7. Generate the timed ASS subtitles using the existing subtitle/layout code.
8. Render the background, intro, title, logo and orange highlights.
9. Apply the configured high-quality encoding directly (CRF14/fast by default).
   There is no benefit in encoding the same picture a second time. Delivery
   copies the exact reviewed high-quality preview without another lossy encode.
10. Complete technical verification and explicit full listening/lyric/timing
    review before publishing to `out/`.

The new path defaults to a ten-second added intro. With the original video as
background, its first frame is held during that intro so picture/audio retain
the same song clock. Older tool defaults retain their existing three-second
intro. Existing exported videos have not been changed.

## Configure one song

Copy `config/job.example.json` to your own job JSON and set source/title/artist.
Paths in job JSON are relative to that JSON's directory, or may be absolute.
`background: "original"` keeps the source video. A path selects a custom image or
looping video. Supply a clean source when embedded text/branding is unwanted:
this workflow does not pretend to remove text baked into arbitrary video.
Audio-only MP3/WAV/M4A/FLAC sources use music mode with a custom background.

Run, using the same job JSON for every subsequent command:

```powershell
.\.venv-zoom\Scripts\python.exe karaoke.py run --job config\my-song.json
```

The first run creates separation/audio-review evidence and a transcript, then
returns exit code 2 requesting lyric review. The work path is reported in
`work/local_open_source/`. Correct `transcript.json` against the original song.
Do not confirm unreviewed automatic words.

```powershell
.\.venv-zoom\Scripts\python.exe karaoke.py lyrics-review --job config\my-song.json --checked-lyrics
.\.venv-zoom\Scripts\python.exe karaoke.py run --job config\my-song.json
```

Now review the full preview, `timing-report.json`,
`audio-quality/selection.json`, and `audio-quality/review/index.html`.
Comparison clips play original audio first and processed audio second, at the
original levels. Correct lyrics/timings and rerun the affected stages as needed.

After actually completing the reviews:

```powershell
.\.venv-zoom\Scripts\python.exe karaoke.py approve --job config\my-song.json --listened --checked-lyrics --reviewed-audio --reviewed-timing --reviewer "Your name"
.\.venv-zoom\Scripts\python.exe karaoke.py render --job config\my-song.json
.\.venv-zoom\Scripts\python.exe karaoke.py extras --job config\my-song.json
```

The approval is bound to the exact preview, source, selected backing, lyrics,
timings, templates, fonts, configuration, layers/media and active Python code.
Changed inputs invalidate approval. Final files use exclusive creation and
existing deliveries are preserved. The audio-quality stage never writes a
human approval. If every candidate has severe loss/clipping/silence, there is
no automatic selection: supply a suitable recording/instrumental before delivery.

## Zoom sources

Use `config/job.zoom.example.json`, a fixed language, and the correct screen
profile (`white-blue` or `blue-yellow`). It uses a bundled copy of the existing
Zoom OCR/sweep importer. Zoom still passes through vocal separation and audio
screening: original backing vocals are not silently kept.

Zoom OCR supplies words/timings in place of Whisper/WhisperX. Inspect the source
screen contacts and recovered repetitions carefully. Unsupported layouts fail
for review; extraction is not guaranteed for all sources. To supply corrected
word timings directly, add an `aligned` path (the existing segment/words JSON
format); those values still require lyric/timing review. Imported timings need
a fixed language. Mode `music` uses the ordinary Whisper/WhisperX route.

## Editing and other existing features

These use the same job folder and the existing backend implementations:

```powershell
python karaoke.py edit --job config/my-song.json --show
python karaoke.py edit --job config/my-song.json --line 3 --shift 0.1
python karaoke.py edit --job config/my-song.json --line 3 --word 2 --start 12.2 --end 12.7
python karaoke.py edit --job config/my-song.json --line 3 --text "Correct words here"
python karaoke.py edit --job config/my-song.json --undo
python karaoke.py clip --job config/my-song.json --line 3
python karaoke.py layer --job config/my-song.json --list
python karaoke.py translate --job config/my-song.json --to da --translation-style natural
python karaoke.py accept-translation --job config/my-song.json --confirm-translation
```

Use the configured environment's Python, not an unrelated system Python. For
translation rendering add a `translation` block with `to` and `mode` (`below`
or `only`). Local Ollama is default; Opus-MT is available with `--engine opus`.
Remote endpoints are explicitly configured by the operator, never required.
Guide-vocal mixing and key shifts remain deliberate render options; default
guide level is zero. Those intentional audio changes require listening review.

Additional existing commands include `lyrics`, `history`, `restore`,
`check-timing`, `edit --snap-beats`, per-line `--style`, and text/media/audio
layers with keyframes. Translation style is now `--translation-style`; lyric
formatting keeps `--style` so the parser cannot conflict.

## Queue, resume and errors

Use `--manifest jobs.json` instead of `--job` for a JSON list or
`{"jobs": [...]}`. Jobs run sequentially; one failure does not suppress others.
Never run model jobs in uncontrolled parallel processes to fill RAM.

Stages: `separate`, `audio-qc`, `transcribe`, `lyrics-review`, `align`, `preview`,
`approve`, `render`, `extras`, `status`. `run` runs up to the next required review.
Reusing a job reuses hash-verified stems, quality scans and transcripts. UVR
fallback chunks checkpoint individually. A per-job lock prevents two writers;
after a crash check the PID in `running.lock` before removing a stale lock.
Existing partial or changed media are retained and reported, not silently
treated as completed. Changing the source or data-affecting settings creates a
new work revision. Render/layout changes reuse processing results and create a
new preview revision, retaining previous previews. Preserve your job JSON to
find the same processing revision again.

Exit codes: 0 = requested stage completed, 1 = execution/configuration error,
2 = review/input is required. Read `state.json` and candidate `worker.log` files.

## Audio-review limitations

AST uses a pinned AudioSet classifier revision to flag singing, choir, rapping,
humming and speech. Its scores are screening indicators, not calibrated proof
of vocal removal. Whisper ASR adds possible recognised-word evidence; no words
is never interpreted as "no vocals". Signal checks flag possible damage but
cannot certify instrument preservation without a clean reference.

Default retry is pinned UVR MDX Inst HQ 3. `alternatives: ["uvr","roformer"]`
also enables the optional BS-Roformer/Demucs ensemble when its dependencies are
installed. Each alternative reads the original and is attempted at most once.
Rejected candidates cannot win merely by having less sound. An unavailable
classifier/model is recorded as incomplete screening, not a successful check.
Full human listening remains required, including when there are zero flags.

Quality-detector/ASR scans run in isolated subprocesses so their large model
allocations are released before transcription/alignment begins. Each candidate
has a `scan.log`; fallback separation also has `worker.log`.

## What to move / keep

Copy this project, `.env.example`, requirements, setup scripts, `assets/`,
templates and your chosen inputs/backgrounds. Recreate virtual environments;
do not copy Windows virtual environments onto Linux. Models are redownloadable.
To reproduce an existing song, also preserve its job JSON, corrected lyrics,
timings, translation memory and review records. Approvals need fresh review if
the environment/font or inputs change. `assets/logo.png` replaces the active
renderer dependency on `work/webmail` (the old fallback remains for compatibility).

Historical one-off scripts and reports remain for reference. The supported
production entry point is `karaoke.py`; older CLI functions are retained as
backend/compatibility tools, not independent claims of the new quality workflow.

## Current local verification

Both Windows CPU environments have been installed. All six required English-song
models load successfully with downloads disabled. A synthetic 1920x1080 render
with a 10-second intro, orange sweep and white-circle logo passed. Demucs also
completed actual separation inference on the synthetic fixture. The suite runs
87 tests with 3 skips for historical song fixtures. Cleanup tests use real small
MP4 files and preserve source/code/model files. These checks do not establish
real-song lyric accuracy, complete vocal removal, or non-Windows execution.

## Wait for a source download

The REI AMI job is `config/rei-ami-2loud.json`. To wait for its complete MP4 and start processing:

```powershell
.\.venv-zoom\Scripts\python.exe tools/wait_for_song.py --job config/rei-ami-2loud.json
```

The bounded watcher waits for stable size/mtime, checks complete MP4 atoms, then strictly decodes both streams. It does not bypass lyric/listening review gates, approve a song, or delete work. Restarting the command reuses verified processing checkpoints. Do not start a duplicate watcher while one is active.
