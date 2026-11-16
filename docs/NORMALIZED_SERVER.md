# Normalized Danish MP4 server batch

The active `.env` input is:

`D:\Application\Website\ftpPrivate\Basic & More Danish\MP4\normalized`

The FTP inventory on 16 November 2026 contained 442 MP4 files here. The runner
discovers inputs recursively and excludes its own `karaoke` output directories.
Published outputs go to:

`D:\Application\Website\ftpPrivate\Basic & More Danish\MP4\normalized\karaoke`

`KARAOKE_EXTRA_INPUT_DIRS=[]` disables scanning the previous Mellow/DB inputs.
Their existing bind mounts remain for compatibility; those host folders must
still exist. To restore scanning them later, set the variable to
`["/media-mellow","/media-db"]` and recreate the container.

The light `htdemucs` model, 3 workers, shared 8-CPU/12-GB limits, branding,
countdown, output-size policy and cleanup settings remain unchanged. Completed
exports are checked and skipped. Each published song's scratch is removed;
models stay under the project's `docker-data` on D:.

Run this single line in server PowerShell:

```powershell
Set-Location 'D:\karaoke-tool\karaoke-maker'; git pull --ff-only origin main; if ($LASTEXITCODE -eq 0) { docker compose up --build }
```

Conversion starts after the build and initialization complete. A failed pull
prevents startup. This updates only this Compose project, without pruning Docker
data or stopping other projects. Some source files can still fail processing;
the batch continues and reports their failures rather than publishing incomplete
videos.
