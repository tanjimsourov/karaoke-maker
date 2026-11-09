# Automatic folder processing: six workers, four CPUs

This configuration supersedes the mandatory human-review default. It exports automatically after the existing processing and technical checks. It does not run the extra original-audio verification pass or require manual approval. Receipts continue to record reviewed=false; this is not a claim of perfect lyrics or complete vocal removal.

Defaults: six active song jobs with automatic refill, four CPUs shared by the container, 12 GB container RAM limit, one model/encoder thread per worker, light htdemucs, optimized veryfast rendering, background screening alongside audio stages, two attempts for operational failures. The output style and 150 MB ceiling are unchanged. The heavier audio retry is disabled for this speed configuration. Two OCR scans may run concurrently; model initialization/downloads remain serialized. Input, filter and encoder threads respect the one-thread worker setting. Exact repeated OCR frames reuse recognition results without dropping sampled timestamps or hits.

On the server, finish/stop only this karaoke batch before replacing its files. Extract the update into D:\karaoke-tool\karaoke-maker, preserving unrelated files. Then:

```powershell
cd "D:\karaoke-tool\karaoke-maker"
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\configure_server_automatic.ps1
docker compose up --build
```

The configuration script backs up the existing .env and updates only the relevant settings. Other projects and their containers are not modified. Input is D:/Application/Website/ftpPrivate/Danish New, including subfolders. Outputs mirror that hierarchy below its karaoke folder. Original videos remain read-only. Completed-song work is removed; errors and unresolved jobs are retained for diagnosis. Invalid/corrupt media or blocking processing errors may still fail; the runner continues to later songs. No human approval prompt is required.

Four CPUs are twice the allocation of two CPUs, not a guarantee of twice the throughput. Six workers share the four CPUs. Model loading, serialized OCR, disk and RAM can limit speed. No server benchmark has been run for this configuration. The 12 GB RAM cap should be considered alongside other services on the host.

To opt back into strict delivery review later, set KARAOKE_DELIVERY_MODE=verified. The review procedure is documented in VERIFIED_DELIVERY.md.
