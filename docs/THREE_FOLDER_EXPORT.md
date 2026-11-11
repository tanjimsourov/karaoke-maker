# Three-folder automatic server export

Source folders (including subfolders):

- `D:\Application\Website\ftpPrivate\Danish New`
- `D:\Application\Website\ftpPrivate\Danish Mellow\normalization-mp4\MP4`
- `D:\Application\Website\ftpPrivate\Danish DB Songs\mp4`

Each source has its own `karaoke` output subfolder. Three jobs share the existing
8-CPU / 12-GB container limit across all folders. The runner never scans its own
output subfolders. Identical relative names in different source roots have
separate temporary workspaces.

Automatic delivery runs the existing separation, audio screening, transcription,
alignment, background preparation, rendering and output checks. It publishes a
completed `Karaoke.mp4` without a manual review gate or DRAFT filename. This is
automatic completion, not a claim of human listening or perfect lyrics.
Processing failures are retried within the configured attempt limit; unusable
files are not published and do not stop other songs.

Publication checks the source did not change, enforces the under-100-MB cap,
copies to a temporary destination, verifies the checksum and renames it to the
final MP4. That song's generated workspace and job specification are then
removed immediately. Failed-job scratch is also removed after the attempt.
Dedicated runtime scratch from earlier interrupted runs is cleared before the
queue and at batch exit. Code, models, source media and published MP4s remain.

No persistent console/Docker logs or batch-summary log are created. Small JSON
completion/skip receipts remain in each `karaoke/.karaoke-status` folder to
recognize existing exports by source/output hashes, including legacy exports.
They are bookkeeping, not retained stems, renders or model work. Console progress
is still visible while attached. Abrupt host termination can leave scratch;
the next batch removes it before starting.

After copying the updated files to `D:\karaoke-tool\karaoke-maker`, use PowerShell:

```powershell
Set-Location 'D:\karaoke-tool\karaoke-maker'
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\configure_server_automatic.ps1
if ($LASTEXITCODE -ne 0) { throw 'Configuration failed' }
docker compose up --build
```

All three source folders must exist; Docker refuses to silently create an empty
source path. Models/work remain under the project's `docker-data` on D:.
Docker image/build cache remains managed by Docker itself.

Validation: 16 batch-runner tests, 6 Docker-layout tests and 13 cleanup tests pass.
PowerShell parses successfully. Docker is unavailable on this local host, so no
server image build or full song conversion was executed for this change.
The broader portable suite has one pre-existing manual-reviewed-delivery test
missing its delivery-verification fixture; reproduced against unchanged HEAD.
