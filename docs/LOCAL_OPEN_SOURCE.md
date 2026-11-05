LOCAL OPEN-SOURCE KARAOKE WORKFLOW

Implemented stages (no Karadeo API/key/credits):
1. Demucs htdemucs_ft: vocals, drums, bass, other, combined instrumental.
   Same sample length, shared anti-clipping gain, float32 WAV intermediates.
   Hash-verified reuse; incomplete or changed stems are not silently reused.
2. Faster-Whisper transcription: local CPU int8. Select transcription_model in
   local_karaoke_jobs.json if a larger model is needed. Default small is a draft
   generator, not a guarantee of correct singing transcription.
3. Explicit lyric review/correction, then language-specific WhisperX alignment.
   Danish, English and Spanish configured for the five current songs.
4. Original/stem audio comparison: stereo-aware silence and duration checks;
   preserves anti-phase stereo audio rather than treating it as silence.
   Reports suspected causes; does NOT pretend to identify them conclusively.
5. Existing approved background/logo/intro/four-row renderer.
6. Full preview review, hash-bound approval, decoded-audio checks, 1080p/duration/
   decode checks, and non-overwriting final output.

Runner (use this environment):
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py status

One-by-one workflow, for example:
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py separate --song AEr_lig_Freestyle
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py audit --song AEr_lig_Freestyle
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py transcribe --song AEr_lig_Freestyle

Correct work/local_open_source/AEr_lig_Freestyle/transcript.json against the
original recording. Keep segment start/end times as useful alignment windows.
Then:
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py accept-transcript --song AEr_lig_Freestyle --confirm-lyrics
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py align --song AEr_lig_Freestyle
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py preview --song AEr_lig_Freestyle

Inspect/correct aligned.json word timings when necessary. Move the old preview
aside before rerendering. Review full preview including all flagged quiet parts.
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py approve --song AEr_lig_Freestyle --confirm-listened
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py render --song AEr_lig_Freestyle

Omit --song to process all jobs in manifest order (a queue; a failing song is
reported and the next one continues). 'draft' runs separate, audit and
transcribe, then stops for lyric review. If the job has a "lyrics" file, or the
transcript was already accepted, it continues with align and preview.
It never approves or publishes videos automatically.

Adding a song (paths are relative to the project root):
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py add --source "Bowlnfun Jakob For Visuals\smugryger.mp3" --title Smugryger --artist "Artist" --language da --background "audio-bg-sample\14-10\jan-chatgpt\Dromerige neonbowling in Aalborg.png" [--file lyrics\smugryger.txt] [--template single_line] [--canvas 1080x1920] [--guide-vocal 0.15] [--pitch -2]

--language auto (default) lets Faster-Whisper detect the language during
transcribe; it is saved to language.json and used for WhisperX alignment and
the label (da -> DANSK KARAOKE).

Your own lyrics instead of correcting Whisper's text (one sung line per row;
blank rows and [Chorus]-style labels are ignored):
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py lyrics --song AEr_lig_Freestyle --file lyrics\aerlig.txt --confirm-lyrics
Whisper's words are used only as timing anchors; lyrics-import.json reports how
many lines matched. Unmatched lines are spread between neighbours, and WhisperX
then times every word. Omit --confirm-lyrics to inspect transcript.json first.

Lyric history (undo): every replaced transcript.json is kept in history/.
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py history --song AEr_lig_Freestyle
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py restore --song AEr_lig_Freestyle --version 20261017-170325-275869

Translation (after align). Two engines:
- llm (default): an AI language model translates the whole song in context,
  like OpenL: consistent repeated lines and pronouns, idiomatic phrasing,
  names and "oh/yeah/la la" kept, optional glossary. Styles: natural
  (default), singable (keeps syllable count/rhyme for "only" mode), literal.
  Default server is local Ollama (free, offline): install Ollama, then
    ollama pull qwen2.5:7b-instruct
  Any OpenAI-compatible endpoint works instead, local or paid:
    $env:LLM_URL = 'https://provider.example/v1/chat/completions'
    $env:LLM_MODEL = 'model-name'; $env:LLM_API_KEY = '...'
  quality "best" (default) runs five passes, like a translation agency:
    1. brief    - reads the whole song: story, who sings to whom, mood, idioms
    2. draft    - translates in chunks of 40 with earlier lines as context
    3. edit     - compares each line with the original and fixes it
    4. shorten  - rewrites only lines too long to read while singing
    5. check    - back-translates and writes a "check" note on lines whose
                  meaning drifted (or that are still long); fix them, delete
                  the note, then accept
  quality "fast" is one draft pass (about 5x fewer model calls).
  Customising the result:
    - config/translation_prompt.txt: house style for every song
    - job "instructions": notes for one song ("he sings to his daughter")
    - job "glossary": fixed word translations
    - translation memory (work/translation_memory.json): every accepted
      translation is reused verbatim when the same line appears again, so
      corrections carry over to later songs
  A reply with the wrong line count is retried, then reported (never cut).
- opus: Helsinki-NLP Opus-MT, line by line; no server needed, more literal.
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py translate --song AEr_lig_Freestyle --to en [--engine opus] [--style singable]
Correct the "translation" values in translation.json, then:
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py accept-translation --song AEr_lig_Freestyle --confirm-translation
Enable it in the job: "translation": {"to": "en", "mode": "below",
  "engine": "llm", "style": "natural", "quality": "best",
  "glossary": {"skat": "darling"}, "instructions": "Playful, he sings to his girlfriend"}
translation.json records the engine, model, style, glossary, instructions and
the song brief used.
- below: original lyrics keep the word sweep; the translated line being sung
  is shown under the page (template keys translation_y, translation_size,
  translation_colour).
- only: the translation replaces the lyrics; each line sweeps evenly over the
  time the original line is sung (a translation cannot follow word timing).
Uses Helsinki-NLP/opus-mt-<from>-<to>, or pivots through English when no direct
model exists (e.g. es -> en -> da). Preview/approve/render refuse to run until
the current translation.json is accepted; edits make the approval stale.
Re-translating keeps the previous file in history/.
tools\translate_opus_mt.py is the old Auld Lang Syne one-off, kept for reference.

Accuracy and finishing defaults (song jobs):
- Whisper large-v3-turbo (0.8B) by default; "transcription_model" overrides.
- Transcription (with voice-activity filter) and WhisperX alignment both use
  the isolated vocal stem, not the full mix.
- After align, an automatic timing check writes timing-report.json and lists
  words that are unaligned, too short, too long, overlapping, or placed where
  the vocal stem is silent. Rerun with: check-timing --song X
- Finishing: loudness -14 LUFS (EBU R128, linear gain, peak <= -1 dBFS, so
  the audio check still verifies the backing), 0.3 s fade-in, 2 s fade-out,
  and 3-2-1 dots before lyrics return after an 8 s+ instrumental break.
  Override any of these in the job's "render" block (e.g. "fade_out": 0).

Better separation (optional, per job; models via audio-separator, < 0.1B each):
  "separation": {"ensemble": true, "keep_backing_vocals": true}
- ensemble: Demucs averaged with BS-Roformer: cleaner vocals, less bleed.
- keep_backing_vocals: UVR MDX Karaoke 2 splits lead from backing vocals; the
  video uses instrumental_with_backing.wav and aligns on lead_vocals.wav.
Changing separation options needs a new job slug (stems are hash-locked).

Duets: prefix lyric lines with a part label; it lasts until changed.
  M: first male line       F: female line       D: both together
The active sweep takes the part colour (template "part_colours",
default M #4FC3F7, F #FF6FAE, D #FFD54F).

Backgrounds: images or looping videos (.mp4/.mov/.webm/.mkv); "motion": "pan"
adds a slow camera drift to still images.

Queue speed: draft over all songs starts Demucs for the next song in the
background while the current one transcribes.

Editing lyrics and timing after align (backend commands on aligned.json):
  edit --song X --show [--line 5]                 numbered lines/words with times
  edit --song X --line 5 --text "new words"       same word count keeps timing
  edit --song X --line 5 --shift 0.3              move a line (--until 8: range)
  edit --song X --shift -0.1                      move the whole song
  edit --song X --line 5 --start 41.2 --end 44.0  fit a line into new times
  edit --song X --line 5 --word 2 --start 41.6 --end 41.9
  edit --song X --line 5 --split-at 4             new line starts at word 4
  edit --song X --line 5 --merge                  join with the next line
  edit --song X --line 5 --delete
  edit --song X --line 5 --until 9 --part F       duet part ("" clears it)
  edit --song X --undo                            step back one edit (repeatable)
  edit --song X --insert-after 5 --text "new line" --start 41 --end 43
  edit --song X --line 5 --until 8 --style size=90 colour=#FFFFFF highlight_colour=#FF3366
       (no --line = every line; --style-clear removes). Style keys: font size
       bold italic colour highlight_colour outline outline_colour
       highlight_outline_colour shadow opacity letter_spacing rotation x y
       fade_in fade_out box_colour (box behind the line)
  edit --song X --snap-beats [--line 5 --until 20] [--subdivision 2] [--tolerance 0.12]
       detects the tempo (librosa, saved to beats.json) and moves line starts
       onto the nearest (half-)beat
Template-wide text keys: letter_spacing, line_height, highlight_outline_colour,
opacity. Right-to-left scripts (Arabic, Hebrew) are shaped automatically by
libass (FriBidi/HarfBuzz).

Layers (Karadeo-style extra tracks; layers.json per song, format in tools/layers.py):
  layer --song X --list
  layer --song X --add-text "Chorus!" --start 30 --end 34 --values x=960 y=160 size=80 colour=#FFD54F
  layer --song X --add-media work/logo.png --start 10 --end 20 --values x=300 y=200 width=400 opacity=0.8
  layer --song X --add-media clips/dance.mp4 --start 60 --end 75 --values x=960 y=540 width=1920 speed=1.5 crop=0,0,0,80
  layer --song X --add-audio sfx/applause.wav --start 200 --values volume_db=-6 duration=8 fade_out=1
  layer --song X --item texts:1 --keyframe 2 --values x=1200 scale=1.4 rotation=10
  layer --song X --item media:1 --values opacity=0.5      (change)  /  --remove
  layer --song X --backing-db -3   /   --mute-backing on
Keyframes: t = seconds from the item start, linear in between. Text animates
x, y, scale, opacity, rotation; media animates x, y, scale. Layers and their
files are part of the approval fingerprint. Frame rate: "render": {"fps": 30}
(24/25/30/50/60).
Every edit is validated (order, overlap, duration, inside the song), saved to
history/, and followed by the timing check. Check it quickly with
  clip --song X --line 5 [--window 3]             renders work/.../clips/*.mp4
then run preview again (edits make earlier previews and approvals stale).

Delivery extras after the final render:
.\.venv-zoom\Scripts\python.exe tools\local_karaoke.py extras --song X
writes next to the MP4: word-timed enhanced .lrc, _thumb.jpg (from the
busiest chorus) and a 30 s _teaser.mp4. The MP4 carries title/artist tags.

Per-song render options, in the job's "render" block of local_karaoke_jobs.json:
  "render": {"template": "single_line", "canvas": "1080x1920",
             "start": 30, "end": 75, "crf": 19, "preset": "veryfast",
             "guide_vocal_level": 0.15, "pitch_semitones": -2,
             "loudness_lufs": -14, "fade_in": 0.3, "fade_out": 2,
             "gap_countdown": true, "motion": "pan"}
- template: config/templates/<name>.json (four_line default, two_line,
  single_line). Copy one to make your own: lines per page, font, colours,
  outline, line spacing and position.
- canvas: any even WIDTHxHEIGHT, e.g. 1920x1080, 1080x1920 (vertical),
  1080x1080, 3840x2160. Text sizes follow the shorter side.
- start/end: export only that part, in output seconds (the 3-second intro
  counts). Lyrics keep the full-song timing.
- guide_vocal_level: 0-1 of the separated vocals mixed under the backing.
- pitch_semitones: -12 to 12 key change (rubberband, tempo unchanged).
Changing any option makes the approval stale, so preview and approve again.
When the audio is intentionally changed (guide vocal, key, range), the decoded
backing comparison is skipped and recorded as such: listen to the preview.
The renderer also accepts the same flags directly: --template, --canvas,
--start, --end, --crf, --guide-vocal-file/--guide-vocal-level, --pitch.
Final files: out/Local_<slug>_Karaoke.mp4. Existing deliveries stay unchanged.
Preview and test files remain under work/local_open_source, not out.

Separate environments:
- .venv-demucs: Demucs 4.1.0 / torch 2.14.1+cpu; invoked by the runner.
- .venv-zoom: WhisperX 3.8.6 / Faster-Whisper 1.2.1 / torch 2.8.0.
The environments are separate to avoid dependency conflicts. FFmpeg is local.
Models may download on first use; inference/audio processing stays local.
No per-song/API charge, but CPU/GPU, storage, downloads and electricity are not
costless. This is not a claim of unlimited hardware capacity.

Scope limits:
- No promise that vocal removal can restore backing that never existed.
- No automatic gap filling or global lyric slowdown. Original-vocal mixing is
  only the optional guide_vocal_level above.
- Demucs separates ALL vocals; lead-vs-backing-vocal isolation is not implemented.
  UVR is not installed/integrated by this implementation; do not claim parity.
- The Zoom cover workflow still needs matching vocal references or another
  reviewed lyric/timing source. Removing vocals cannot recover those vocals.
- The five original songs are present; their full new versions have NOT been
  processed/approved just because the stage implementations were tested.

References for model APIs:
https://github.com/facebookresearch/demucs
https://github.com/m-bain/whisperX
