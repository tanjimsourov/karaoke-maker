# One Docker command, four source types

Edit `.env`, then run from the project folder:

```powershell
docker compose up --build
```

Set `KARAOKE_MEDIA_HOST_DIR` to the Windows source folder (forward slashes).
The batch scans its subfolders, excludes its output folder and publishes each completed
MP4 under that source folder's `karaoke` directory, preserving relative subfolders.
One source type applies to the entire run; select a folder containing that type.

| Input | KARAOKE_SOURCE_TYPE | KARAOKE_LANGUAGE | Processing |
|---|---|---|---|
| Normal music video | mp4 | auto or language code | Vocal separation, transcription, alignment, original video background |
| Audio song | mp3 | auto or language code | Vocal separation, transcription, alignment, selected background |
| Zoom karaoke MP4 | zoom | fixed code, e.g. en | Existing on-screen lyrics and colour timing extraction |
| Sing King karaoke MP4 | singking | fixed code, e.g. en | Existing on-screen lyrics and colour timing extraction |

Example MP3 settings:

```dotenv
KARAOKE_SOURCE_TYPE=mp3
KARAOKE_LANGUAGE=da
KARAOKE_BACKGROUND=auto
KARAOKE_AUDIO_BACKGROUND=assets/audio-bg/6.jpeg
KARAOKE_SCREEN_PROFILE=auto
```

`KARAOKE_BACKGROUND=auto` keeps normal MP4 video and uses the selected background
for MP3, Zoom and Sing King. Set `original` to retain a karaoke source video,
or set a container-accessible image/video path to override the background.
Place custom assets under `assets` before building; host Windows paths are not
usable as background paths inside the Linux container.

Screen profile names describe original base text then highlight colour:
`white-blue`, `blue-yellow`, `white-magenta`, `magenta-white`.
`auto` selects white-blue for Zoom and white-magenta for Sing King. This is a
preset, not automatic colour detection. Select the matching source profile.
Different layouts, colours or unreadable lyrics can fail extraction; a complete
Sing King song conversion has not been validated as part of this routing change.

Existing logo/countdown/rendering, the under-100-MB publication check, per-song
work cleanup, stored models and completion receipts remain in place. Matching
completed exports are skipped even after settings change. To intentionally redo
completed songs, use the batch CLI's `--reprocess-completed` option.

Legacy Mellow/DB mount settings remain for compatibility; keep their paths valid.
`KARAOKE_EXTRA_INPUT_DIRS=[]` leaves these folders inactive. Source files and
published karaoke outputs are preserved during cleanup. Automatic export does
not certify error-free lyrics or complete vocal removal.

Build dependency layers are reused when unchanged; changing requirements or
losing Docker's build cache can require installation again. Models persist in
`docker-data/models`. Docker itself is not available on the development machine,
so an actual server build/run is still required.
