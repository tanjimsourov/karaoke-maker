# Automatic folder processing: three workers, eight CPUs

This configuration supersedes the mandatory human-review default. It exports automatically after the existing processing and technical checks. It does not run the extra original-audio verification pass or require manual approval. Receipts continue to record reviewed=false; this is not a claim of perfect lyrics or complete vocal removal.

Defaults: three active song jobs with automatic refill, eight CPUs shared by the container, 12 GB container RAM limit, two model/encoder threads per worker, light htdemucs, optimized veryfast rendering, background screening alongside audio stages, two attempts for operational failures. The output style and below-100 MB ceiling are unchanged. The heavier audio retry is disabled for this speed configuration. Two OCR scans may run concurrently; model initialization/downloads remain serialized. Input, filter and encoder threads respect the two-thread worker setting. Exact repeated OCR frames reuse recognition results without dropping sampled timestamps or hits.

On the server, finish/stop only this karaoke batch before replacing its files. Extract the update into D:\karaoke-tool\karaoke-maker, preserving unrelated files. Then:

```powershell
cd "D:\karaoke-tool\karaoke-maker"
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\configure_server_automatic.ps1
docker compose up --build
```

The configuration script backs up the existing .env and updates only the relevant settings. Other projects and their containers are not modified. Input is D:/Application/Website/ftpPrivate/Danish New, including subfolders. Outputs mirror that hierarchy below its karaoke folder. Original videos remain read-only. Completed-song work is removed; errors and unresolved jobs are retained for diagnosis. Invalid/corrupt media or blocking processing errors may still fail; the runner continues to later songs. No human approval prompt is required.

Eight CPUs increase the allocation from four; this is not a guarantee of twice the throughput. Three workers share the eight CPUs. Model loading, bounded OCR, disk and RAM can limit speed. No server benchmark has been run for this configuration. The 12 GB RAM cap should be considered alongside other services on the host.

To opt back into strict delivery review later, set KARAOKE_DELIVERY_MODE=verified. The review procedure is documented in VERIFIED_DELIVERY.md.

The Docker VM must expose at least eight logical CPUs. Verify its capacity with `docker info --format "{{.NCPU}}"`; a container quota cannot create CPU capacity absent from the VM. Two threads per job allow more parallel computation, but three jobs still share the eight-CPU ceiling and can exhaust the unchanged RAM limit. Measure completed songs per hour and check failures before judging this configuration faster.

Restart after pulling the updated files: run `docker compose stop -t 120 karaoke`, then `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\configure_server_automatic.ps1`, then `docker compose up --build --force-recreate`. Keep the same Compose project directory. Do not remove named volumes. Completed MP4s and models are preserved, but interrupted stages may repeat; changing threads or code can invalidate cached job identities, so this is not an exact in-place resume.

Each completed song is published immediately after technical verification and checksum-confirmed copying; its dedicated work directory and temporary log/spec are then removed. Other running jobs and failed-job evidence are preserved. Small status receipts remain for retry/skip tracking. New server jobs preserve source average frame rate up to 30 fps (variable-rate sources become constant-rate), render 1920x1080 with 2 Mbps video and 192 kbps audio, and reduce bitrate further when required by a 90 MB planning budget. Publication rejects files of 100,000,000 bytes or larger. Output size depends on duration and content, not input file size.
