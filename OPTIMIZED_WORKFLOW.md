# Optimized karaoke workflow

Use `config/optimized-example.json` as a template. Paths are relative to the job JSON.
The explicit `optimized` profile uses htdemucs, one shift, overlap 0.25 and x264
veryfast CRF 14. Existing jobs without this profile retain their previous model,
overlap and encoder settings. CPU/GPU selection remains the existing device detector.

Run from this project with `.venv-zoom/Scripts/python.exe karaoke.py` followed by:

1. `run --job config/optimized-example.json`: separate, screen and transcribe once.
   Stops for lyric review. No automatic lyric approval.
2. Correct the transcript using existing `lyrics` / lyric editing tools. Review the
   exact recording, including its outro, then `lyrics-review --job ... --checked-lyrics`.
3. `quick-preview --job ... --preview-start 0 --preview-seconds 20`:
   align corrected text and render a short 720p clip with guide vocals for review.
   Repeat at a chorus or ending using output timestamps, which include the intro.
   These clips are cached separately and cannot approve a final delivery.
4. After corrections, `preview --job ...` creates the full-quality CRF 14 preview.
5. After actual full review, `approve --job ... --listened --checked-lyrics
   --reviewed-audio --reviewed-timing --reviewer NAME`.
6. `render --job ...`: copies the exact reviewed full-quality preview to out with
   no second video encode. Verified final delivery retains the existing automatic
   cleanup policy; add `--keep-work` when revisions are expected.

Draft sample exports now retain work by default. `--discard-draft-work` is an
explicit opt-out; deleting draft intermediates makes revisions require reprocessing.
Do not delete original sources, model weights, code or assets for routine cleanup.

The optimized profile automatically tries `htdemucs_ft` once when the audio screen
flags the baseline. It compares candidates and retains the selected backing. This
screen is advisory: if listening reveals a missed problem, explicitly set
`separation.model` to `htdemucs_ft`
in a copy of the job. This changes the job identity, preserving previous results.
Reviewed text can be reused through the existing `lyrics` input; imported aligned
timings require the same source timeline. Do not assume that changing models fixes
incorrect lyrics. Automatic audio screening remains advisory to listening review.

The historical heavy five-song benchmark remains an explicit heavyweight benchmark.
Its measured runtime is not a prediction for this profile. No under-one-hour batch
guarantee is made. Decode and audio-screen checks are retained. No model downloads,
GPU migration or blanket concurrency increases are performed by selecting the profile.

## Batch and GPU configuration

From the project root:

```powershell
.\.venv-zoom\Scripts\python.exe tools\run_optimized_batch.py --manifest config\my-batch.json --stage run --report reports\my-batch.json
```

The manifest contains a JSON list of ordinary job objects. Two preparation workers
overlap file checks; one model job runs at a time. The Demucs process remains resident
across songs; ASR/alignment models are reused when the same model family is still
resident. Switching model families releases the previous cached family. Review gates
remain in effect, and exit code 2 means review is required, not a crash.

For a single warm invocation, append `--warm-models` to the normal karaoke command.
On a compatible CUDA installation, automatic device selection uses CUDA and float16
recognition. A job may set `"transcription_batch_size": 8`; the CPU default remains 1.
Recognition uses faster-whisper, the backend used by WhisperX; final forced alignment
uses WhisperX after corrected-text approval. There is no second recognition pass.
Do not install `whisperx[fast]` for the pinned 3.8.6 release: that release has no such
extra. GPU operation must be tested on the intended machine; this PC has CPU-only Torch.

## Revisions and cache rules

Decoded native float audio and resampled views live under the job's `decoded` folder.
The source and FFmpeg hashes bind the cache; damaged cached data raises an error.
Model settings and source hashes bind separation. Edit the existing job transcript
with the lyric tools, approve the corrected text, then run `align`: only changed
phrases are realigned. Changing the source/model invalidates the applicable cache.
Importing a different lyrics file may create a new job identity; edit the retained
job transcript for incremental correction. A colour-only edit reuses AI outputs.

For backing-only changes with the same picture/timeline:

```powershell
.\.venv-zoom\Scripts\python.exe tools\replace_backing.py --video out\song.mp4 --backing work\new-instrumental.wav --output out\song-new-audio.mp4 --intro-seconds 10
```

Use the actual intro duration. For already-finalized AAC audio including the intro,
omit the intro argument and add `--copy-audio`. The command refuses overwrite,
checks duration, decodes the result and verifies that encoded video is unchanged.
The new audio requires review; old approval does not transfer automatically.

## Measurements and optional encoder

`stage-metrics.jsonl` records real invocation times, including cache checks and failures.
It is archived with delivery receipts during cleanup. Manual review time must be
recorded by the reviewer; it cannot be inferred from model execution time.

```powershell
.\.venv-zoom\Scripts\python.exe tools\benchmark_optimization.py --source "inputs\song.mp4" --start 50 --seconds 10 --report-dir reports\encoder-test
.\.venv-zoom\Scripts\python.exe tools\benchmark_optimization.py --job config\my-song.json --stage align --report-dir reports\alignment-test
```

Use a fresh report directory. The second command measures first and repeated stage
invocations; a repeated invocation may reuse artifacts rather than run warm inference.
For the optional GPU profile set render `"encoder":"h264_nvenc","nvenc_cq":19`.
CQ19 is not CRF14. Benchmark complete branding/subtitle composition using `--stage
preview` on the target GPU, not just the source-only encoder test. Keep libx264 for
the required CRF14 deliverable. Default video quality, four-line styling, countdown,
logo and original background remain controlled by the existing renderer.

The PDF's longer-term dynamic player is explicitly an architectural option, not part
of the standalone MP4 acceptance target. This integration retains MP4 delivery.

## FTP comparison integration (3 November 2026)

Optimized jobs now plan detected credit-box cleanup without encoding an intermediate
background. Source-coordinate filters run before scaling and intro padding in the
final CRF14 composition. The intro still uses the masks applicable at its source
timestamp. Already verified cleaned backgrounds remain reusable. Final-output OCR
still blocks a delivery with detected provider marks; a plan is not certification.
This interpolation cannot reconstruct the hidden original picture perfectly.

`tools/convert_verified_ftp_raw.py` now overlaps independent source scanning and
separation when at least 6 GiB RAM is available, and backing checks and transcription
when at least 8 GiB is available, with at most two workers and three threads per
child. Less memory selects the sequential path after the observed allocation failure.
Per-song scheduling reports record which path actually ran. Completed stage
checkpoints survive sibling failures. Both light exports precede the requested
heavy comparisons; heavy audio reuses the same encoded picture.

The comparison runner uses isolated AI processes to release memory on this PC.
For ordinary multi-song production with sufficient RAM, the existing
`run_optimized_batch.py` provides resident model reuse and lyric-review gates.
The comparison exports remain unapproved drafts until actual review. They do not
establish the PDF's time-to-approved-delivery target.

Fresh checks cover inline cleanup through the real FFmpeg renderer, source binding,
bad masks, interrupted scans, cache reuse, model reuse, phrase-only realignment,
stream-copy backing replacement, countdown styling, and memory-bounded scheduling.
GPU execution and a complete under-20-minute production run remain unverified on
this CPU-only machine. No checks or quality settings are disabled to claim that target.

### Countdown style (2026-11-03)

The shared renderer now draws a geometric white circle outside the complete logo.
It begins as a full circle and closes clockwise over the configured intro duration,
without a persistent thin outline or shadow track. Countdown numbers use that same
duration. `KARAOKE_LOGO` selects the artwork for both the intro and corner placement;
the artwork is not masked or recoloured to create the ring. Canonical jobs enable
the countdown by default; an explicit `intro_countdown: false` remains supported.
Existing MP4s require a new export to acquire this style; changing code does not
modify already-delivered videos. The Jennifer v2 Clean Countdown exports already
use this appearance. Tests include real FFmpeg frames at the start, halfway and
end, multiple canvas scales, and the shared renderer with a custom logo.

Countdown controls are selectable per run. In `.env`:

```dotenv
KARAOKE_COUNTDOWN_STYLE=arc
KARAOKE_COUNTDOWN_COLOUR=#FFFFFF
```

`arc` begins round and closes clockwise with no residual track. `circle` keeps
the complete round ring visible while the numbers count down. The colour applies
to the ring; numbers stay white and the logo keeps its own colours. Use a six-digit
hex colour, for example `#00AAFF`. Current defaults remain `arc` and white.

Override these for one run by adding `--countdown-style circle --countdown-colour
"#00AAFF"` to the `karaoke.py` command. The low-level renderer accepts the same
flags. Job JSON may set `render.countdown_style` and `render.countdown_colour`.
Precedence is explicit CLI > job configuration > environment/.env > defaults.
Resolved values are included in render verification fingerprints, so changing
them invalidates a stale render approval without discarding audio/lyric work.
