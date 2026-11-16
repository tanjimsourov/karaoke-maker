# Zoom and Sing King source-backed conversion

The existing `zoom_converter/converter.py` was inspected before making this change.
Its glyph-area-to-clip calculation and cue validation now live once in
`tools/screen_sweep.py`, used by the bundled importer and the shared renderer.
The sibling zoom_converter code and its media were not modified.

For `KARAOKE_SOURCE_TYPE=zoom` or `singking`:

1. Validate/decode the input, then import existing screen lyrics and measured sweeps.
2. Retain the original source audio as the backing. Do not run Demucs, vocal
   classification, residual-vocal ASR, Whisper transcription or WhisperX alignment.
3. Validate recovered words, cue boundaries and monotonic sweep samples. Missing
   samples fail explicitly. The instrumental track is not used as a singing reference.
4. Wrap text without changing word/sample times. The renderer uses measured
   holds/progression and shifts both audio and samples by the same added-intro offset.
5. Use the existing logo/countdown renderer, size cap, publication and cleanup path.

Normal MP3/MP4 music routes keep their separation/transcription/alignment workflow.
The screen route also skips the normal-song loudness and fade defaults. Explicit
render effects still apply if supplied in a job. Source vocals, if present, remain;
this route does not claim a supplied karaoke recording has no vocals.

No new package, model download, parallel pipeline or sibling repository dependency
was added. OCR still needs its existing runtime packages. Screen colour presets
must match the source; arbitrary layouts and OCR accuracy are not guaranteed.

## Verification

- 91 focused checks passed in a clean temporary archive of the committed project
  plus this patch, excluding unrelated local Colab/ASR changes.
- Those checks include an actual 1920x1080 MP4 render: a measured hold stays white,
  later progress turns orange, intro duration is applied, and audio correlation
  exceeds 0.98 after accounting for the intro delay.
- Both complete automatic workflow routes were checked with model calls forbidden;
  the optional delivery verification also does not invoke singing ASR.
- Publication, completed-output skip, size limits, cleanup, background-end handling
  and countdown checks passed. Pre-fix screen outputs are regenerated once with
  distinct filenames, preserving old files; corrected outputs are subsequently skipped.
- The existing 29 zoom_converter checks passed against the reused converter code.
  Its legacy hardcoded FFmpeg executable was redirected to the existing installed
  FFmpeg in the test harness; production files were not changed for that harness.
- The broader portable-workflow suite has 26 passing tests and one existing
  missing-fixture error in `test_final_delivery_copies_exact_reviewed_bytes_and_refuses_collision`.
  The same missing delivery-verification.json error was reproduced on unchanged HEAD.

Full-length Sing King footage, OCR extraction on a real Sing King source and an
actual Linux Docker build/run remain untested here: local source files/OCR runtime
and Docker are unavailable. These results verify the fixed code paths and rendered
sweep behavior, not universal source compatibility or complete lyric correctness.
