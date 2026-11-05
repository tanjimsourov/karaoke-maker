# Server folder-to-karaoke batch

This deployment follows tag_creator's bind-mounted media, environment configuration,
non-root container and CPU limits. It calls the existing karaoke workflow; it does
not replace the separation/alignment/rendering implementations.

## Configure

The tracked `.env` is prepared with the first server source folder:
`D:/Application/Website/ftpPrivate/XtendaMix/Top 40/Nov 2026`.
Plain `docker compose` reads it automatically.
Set `KARAOKE_MEDIA_HOST_DIR` to the server video root. Compose passes only whitelisted server settings into Linux containers; host paths
are used only for bind mounts. Keep secrets out of this tracked `.env`.

Example layout:

```text
/srv/videos/Artist - Song.mp4
/srv/videos/Top 40/Artist - Another Song.mp4
/srv/videos/karaoke/Artist - Song - Karaoke DRAFT - <id>.mp4
/srv/videos/karaoke/Top 40/Artist - Another Song - Karaoke DRAFT - <id>.mp4
```

The `karaoke-init` service creates/prepares the `karaoke` folder and runtime volume
roots automatically. The configured UID/GID still needs read access to input videos. The parent media mount is read-only;
only its `karaoke` child is writable. On Linux, use the default UID/GID 10001 or set
both to the server service user's IDs. If overriding IDs, ensure named volumes are
writable by that user too. Do not run `docker compose down -v`: it removes model/work
volumes and resume records.

This is a **Linux-container** image (CPU by default). A native Windows Server Docker
engine in Windows-container mode cannot run it; use a Linux VM/host or a supported
Linux-container engine. A GPU is not required. This image has not been GPU-enabled.

## Build, inspect, run

First run (build, initialize, download missing models, then convert):

```sh
docker compose up --build
```

For later input folders, edit `KARAOKE_MEDIA_HOST_DIR` in `.env`, then run the same
command again. `docker compose build` alone does not start processing.


Run from the `pro` project directory on the server:

```sh
docker compose config
docker compose build
docker compose run --rm karaoke --dry-run
docker compose run --rm karaoke --limit 1
docker compose run --rm karaoke
```

Use the attached `run --rm` command to see live progress. Docker's logging driver is
`none`, so console output is not retained by Docker and `docker compose logs` cannot
retrieve old progress. A detached run is possible, but it has no saved console log.

This is a one-shot batch, not a permanent watcher. Rerun the `run --rm` command to
scan newly added files (or schedule it with cron/Task Scheduler). An OS lock prevents
two batch runners sharing the same work volume from processing concurrently.
Finish uploads using a temporary extension, then rename to `.mp4`; files modified
within `KARAOKE_SETTLE_SECONDS` are ignored. A changed file is rejected at publication.

The first run can download open-source model weights. They remain in `karaoke_models`.
After required language models are downloaded, set `KARAOKE_ALLOW_MODEL_DOWNLOAD=0`
for offline execution. Different languages may require additional alignment weights.
Keep internet access for first setup. Build/runtime disk space includes two Python
environments, model weights, temporary stems and video exports.

## Behaviour and review

* Recursive `.mp4` input scan; excludes output and symbolic links.
* `Artist - Title.mp4` supplies artist/title. Override metadata with a sibling
  `Artist - Title.karaoke.json`: `{"artist":"Artist","title":"Title","language":"da"}`.
* Automatic exports are explicitly **DRAFT**, never falsely marked reviewed. All
  technical, audio selection and branding checks remain. Some files may still stop
  with `needs_review`; inspect their logs rather than treating them as complete.
* 1920x1080, 30 fps, original video background, transparent supplied logo, 10-second
  magenta closing circle and orange lyrics. The first sung word follows the source
  song timing; a musical lead-in is not automatically cut to start singing at 10 s.
* Maximum **150,000,000 bytes**, target budget 140 MB. Short/simple videos can be
  smaller than 100 MB. A limit cannot guarantee identical visual quality at every duration.
* `KARAOKE_SERVER_WORKERS=2` keeps up to two songs active by default (up to six is supported). Each completion immediately
  releases a slot for the next file. Each song has isolated work/render/tmp/export paths.
  Light `htdemucs` is configured without automatic heavy-model fallback. Failed checks
  still stop that song; remaining queued songs continue.
* Independent background overlap is disabled by default on a shared server; enable it
  explicitly with `KARAOKE_SERVER_PARALLEL=1` if capacity permits. Model initialization/downloads
  and OCR retain their shared locks; inference can otherwise overlap. Shared-server default quota is
  2 CPUs / 10 GB with one inference thread per song. The server must have enough RAM;
  six concurrent songs do not guarantee six-fold speedup or perfect lyric/audio quality.
* While records exist, published-file hashes support skip/resume. After cleanup,
  existing version filenames are checked for streams/size/full decoding before skipping.
  New input/settings/code/logo
  identities produce another version; existing different outputs are not overwritten.
* After each successful song is published and its copy checksum is verified, its
  temporary work, render assets, staging export and per-song logs are deleted immediately.
  This also works for the local folder runner. Failed-job data is retained until batch-end
  cleanup in Docker; locally it remains available for diagnosis.
* Inputs, source code, models and published MP4s are never deleted. With the default
  `KARAOKE_CLEANUP_AFTER_RUN=1`, work, reports/logs, temporary files and staging exports
  are cleared after the batch, including failed jobs' data. Only the empty OS lock
  file remains in the work volume. Failed jobs must start again on the next run.
  Broad end-of-batch cleanup requires `/app` and the dedicated container flag. Local
  per-song cleanup is narrowly scoped and cannot delete another song's work. A local
  `karaoke.py run --draft-export` also cleans its completed work unless `--keep-work`
  or `KARAOKE_CLEANUP_AFTER_SONG=0` is specified. Old unrelated work is not swept.

While a batch runs, logs and receipts live in `/app/reports/server`. They distinguish
`draft_exported`, `needs_review`, and `failed`. They are deleted at batch completion.
If troubleshooting is needed, explicitly set `KARAOKE_CLEANUP_AFTER_RUN=0` to keep
them, then retry failed items after correcting the cause:

```sh
docker compose run --rm karaoke --retry-failed
docker compose run --rm --entrypoint /app/.venv-zoom/bin/python karaoke /app/karaoke.py doctor
```

An abrupt power loss or `docker kill` cannot execute cleanup; the next completed
batch clears the runtime volumes. Do not delete mounted volumes while a job runs.

Exit code 0 means the selected batch exported/skipped successfully. Exit 2 means at
least one file failed or needs review. Reading/decoding success does not certify
accurate Danish lyrics or complete vocal removal. Review drafts before customer delivery.

## Verification limits

Local tests cover scan exclusions, metadata, resumable receipt validation, safe
publication and command construction. Docker build and a real Linux song conversion
must still be performed on a Docker-capable host. Do not call the image production
verified until the `--limit 1` output has passed listening/lyric and playback review.

## Local folder processing

With the processing environment installed:

```powershell
.\.venv-zoom\Scripts\python.exe -u tools/server_batch.py --input-dir "C:\Videos" --workers 6 --threads 1 --model htdemucs
```

The folder runner defaults to per-song cleanup. `--no-cleanup-song` preserves successful
work when troubleshooting. Local source/output files are preserved. The local environment
was missing at the latest update; rebuild dependencies with `setup.py` if necessary.

## Shared-server resource protection

The latest `.env` deliberately lowers the earlier six-worker setup to two workers,
two CPU cores and 10 GB RAM. Root filesystem is read-only, capabilities are dropped,
privilege escalation is disabled, process count is bounded and no ports, host network,
Docker socket or other projects' volumes are exposed. The short init service retains
only the permissions required to prepare the output and runtime directories.

These limits reduce impact; they do not reserve performance for websites/FTP. Disk
I/O, free disk space and model-download bandwidth are still shared. Compose runtime
limits do not constrain image builds. Build during a quiet period when possible.
The Docker daemon/VM must itself have adequate resources. No host/global Docker
settings are changed. Do not use global prune or stop commands.

After copying the updated Dockerfile, docker-compose.yml, .env and tools to the
server project, stop only this worker and rebuild:

```powershell
cd "D:\karaoke-tool\karaoke-maker"
docker compose stop karaoke
docker compose config --quiet
docker compose up --build
```

Do not change the Compose project name or delete volumes when applying this update;
existing model downloads remain available. Monitor with `docker stats`. The full
container runtime still requires server validation; local tests check configuration
and queue behaviour, not actual service latency under server load.
