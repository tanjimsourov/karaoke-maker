# FTP MP3 karaoke automation

Open `notebooks/FTP_MP3_Karaoke.ipynb` in Colab on a normally authorized runtime.
Do not rotate accounts to bypass usage limits. This code does not provision paid
compute, switch accounts or back up to Drive.

## Verified source and outputs

Read-only FTP inspection on 12 November 2026 found eight MP3 files in:
`/LH MP3 (actual situation in pre-defined)/Denmark Charts 2026`.
The other checked Danish DB/Mellow MP3 directories were empty at inspection time.

The default config is `config/ftp-mp3-danish.json`. It matches the STOR MAND reference: Danish language, light `htdemucs`, the
existing 10-second introduction/logo, magenta closing arc, orange moving
highlight, and 1920x1080 at 30 fps with the existing under-100-MB export limit.
`background_folder` randomly selects an eligible 16:9 image of at least 1280x720.
The full image is preserved; source images may be scaled up to the output size.
Currently only `1.jpeg` qualifies; other aspect ratios are excluded.
Remove `background_folder` to select one fixed `background` file instead.

Example remote output:
`/LH MP3 (actual situation in pre-defined)/Denmark Charts 2026/karaoke/Artist - Song - Karaoke - <source-hash>.mp4`
Nested MP3s get a `karaoke` folder beside them, not a mirrored central tree.
Input MP3s are preserved. MP4 sources remain supported by setting extensions to
[".mp3", ".mp4"]; MP4s use their original video unless video_background is set.

## One-time credentials

Create Colab Secrets `KARAOKE_FTP_USER` and `KARAOKE_FTP_PASSWORD` using the key
icon, and authorize notebook access. The notebook reads them into process memory.
No password belongs in a config, a cell, repository, command line or output log.
The saved server uses plain FTP port 2157; traffic is not encrypted. Explicit
FTPS with certificate validation is supported when configured on the server.

## Running

The notebook installs the existing Python 3.11 environments, checks both CUDA
stacks, then runs a five-song queue. GPU-heavy stages share one GPU slot by default;
FTP transfers, CPU background work and rendering can overlap. This is not a
claim of fivefold speed or five simultaneous large models. Change `gpu_slots`
only after measuring VRAM usage on the intended host. First installation/model download can take
longer; models are shared by subsequent songs. The current free Colab runtime can
expire. Rerun in an authorized runtime; completed remote outputs are recognized.

Equivalent cloud Linux Python commands (after cloning the repo):

```sh
python tools/cloud_ftp_workspace.py setup --compute cuda
python tools/cloud_ftp_workspace.py run --compute cuda --config config/ftp-mp3-danish.json
```

Use `--compute cpu` on both commands for a CPU runtime. The entry point rejects
Windows/local desktop conversion. The root must be `/content` in Colab or a cloud
Linux host explicitly marked `KARAOKE_CLOUD_HOST=1`.

Source listing only, using the prepared environment and credential variables:

```sh
.venv-zoom/bin/python tools/ftp_cloud_batch.py --config config/ftp-mp3-danish.json --list-only
```

`limit=0` processes all discovered songs. `limit=3` processes three unfinished
songs. Each run takes a folder snapshot; rerun to find newly added songs.

## Transfer, skip and cleanup behavior

- List recursively, excluding all `karaoke` output folders. IIS servers without
  MLSD use NLST/SIZE/MDTM/CWD, including Unicode Danish file names.
- Download one MP3, run the existing full converter with `--automatic-export`,
  and verify the MP4 streams, dimensions, size and decoding.
- Verify the source still matches its original bytes. Upload to `.partial`,
  re-read it for SHA-256, then rename to the final MP4. A different existing MP4
  is not overwritten; source-content hashes avoid changed-source collisions.
- Upload a small completion receipt to `karaoke/.karaoke-status`. On rerun,
  verify source and output checksums before skipping. Preserve these receipts.
- After successful media and receipt upload, delete that song's downloaded input,
  stems, renders and temporary export. Shared model files remain cached.
- Default Danish config also clears failed local job scratch. Failures are shown
  in the live console; a later run retries. Transfers have at most three attempts;
  permanent FTP errors fail immediately. No persistent log files are produced
  with cleanup_failed enabled. Checksum verification adds transfer bandwidth.

Run only one cloud batch against a source tree at a time; the lock is local to
one host, not distributed. FTP receipt replacement on Windows removes only the
old bookkeeping JSON after verifying its replacement; a disconnect can lose a
skip receipt, but never deletes a source or completed video.

## Validation scope

Eleven focused batch tests, a GPU-stage queue test and a real localhost FTP round-trip test cover download,
Unicode file names, IIS fallback, upload verification, publication, resume,
changed sources and cleanup. The test converter writes fixtures; it does not
prove model or lyric quality. Production FTP discovery was read-only. No new
full song was converted/uploaded on the connected alternate-account T4 runtime.
Automatic lyric recognition remains automatic; completion is not human approval
of every lyric or complete vocal removal.
