# Verified delivery and correction

`KARAOKE_DELIVERY_MODE=verified` is now the server default. The server still generates an internal preview, but does not publish it as final. A named reviewer must check the full lyrics, rendered highlights, instrumental and instrument preservation. A second transcription of the original mix flags disagreements with the vocal-stem transcript; it does not automatically replace words or certify either transcript.

`KARAOKE_SERVER_AUDIO_FALLBACK=1` enables one htdemucs_ft retry if the baseline has audio warnings. The retry starts from the original source, never from a previously separated instrumental. It adds processing time and does not guarantee better audio. Hard signal failures remain blocking. Use 0 to retain light-model-only processing with review holds.

## Reports and retained work

The batch prints each held job's ID and report path. `/media/karaoke/.karaoke-status/<ID>.json` contains its paths. The Docker work volume retains the job, preview, audio review clips, transcript, aligned words and verification decisions template. Successful published jobs are cleaned individually. Global cleanup is skipped when any jobs fail or require review, so corrections remain possible. Do not run `docker compose down -v`.

## Correct and verify a held song

Stop/wait for the batch before editing a job. Commands below run in the server project directory. Replace `<ID>` with its 20-character ID. The helper preserves the original job's environment and paths. Do not confirm any review you have not performed.

1. Copy out the job's `transcript.json` using `docker cp`, correct it against the full original singing, then copy it back. Keep valid segment start/end times. The review helper's `edit` stage also exposes the existing lyric editor; use its help before editing aligned words.
2. Record actual lyric review:

   `docker compose run --rm --no-deps --entrypoint /app/.venv-zoom/bin/python karaoke /app/tools/server_review.py <ID> lyrics-review --checked-lyrics`

3. Run the same command with stages `align`, then `preview`, then `verify` (omit `--checked-lyrics`). Correct timing issues using the existing lyric editor and repeat preview/verify. Invalid/missing timings and audio rejection reasons cannot be waived.
4. Read `delivery-verification.json`. Compare the original audio and the selected instrumental across the entire song; the existing `audio-quality/review/index.html` and clips help locate issues but are not a substitute for full listening. Inspect the actual orange sweep in the full rendered MP4.
5. Copy `delivery-decisions.template.json` to a new decisions file in the job folder. Supply the actual reviewer, mark only completed full checks true, and give a specific reason for every accepted warning. Fix incorrect words/timing/audio instead of accepting them. Changes invalidate old decisions and require verification again.
6. Approve using the helper with:

   `approve --listened --checked-lyrics --reviewed-audio --reviewed-timing --reviewer "Reviewer name" --verification-decisions /app/work/server-jobs/<ID>/jobs/<slug>/decisions.json`

7. Rerun the normal batch (`docker compose up`). It validates and publishes approved jobs; unapproved jobs remain held. A final receipt includes the evidence and decisions; completed-song work is then removed. No source video is deleted.

## Limits

This prevents unreviewed exports from being presented as verified. It is not an unattended, perfect lyric-correction system. Two ASR passes can agree on wrong words. Without a clean reference instrumental, objective proof of complete instrument preservation is unavailable. Verification requires honest full review; CLI checkboxes do not themselves perform listening. Existing exported samples have not been retrospectively verified. These checks add time; no per-song processing-time guarantee is made.
