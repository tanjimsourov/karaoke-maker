$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'karaoke.py'))) {
    throw 'Not the karaoke project root'
}
$savedVideos = @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'out') -File -Filter '*.mp4')
if (-not $savedVideos.Count) { throw 'No saved final MP4s found; nothing deleted' }
$savedHashes = @{}
foreach ($video in $savedVideos) {
    $savedHashes[$video.FullName] = (Get-FileHash -LiteralPath $video.FullName -Algorithm SHA256).Hash
}
foreach ($required in @('tools','config','models','assets\logo.png','assets\font.ttf',
        '.venv-zoom\Scripts\python.exe','.venv-demucs\Scripts\python.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $required))) {
        throw "Required project item is missing: $required"
    }
}
$targets = @()
foreach ($name in @('work','tmp')) {
    $candidate = Join-Path $projectRoot $name
    if (-not (Test-Path -LiteralPath $candidate)) { continue }
    $resolved = (Resolve-Path -LiteralPath $candidate).Path
    if ((Split-Path -Parent $resolved) -ne $projectRoot -or
            (Split-Path -Leaf $resolved) -notin @('work','tmp')) {
        throw "Unsafe cleanup path: $resolved"
    }
    if ((Get-Item -LiteralPath $resolved).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Cleanup refuses junctions: $resolved"
    }
    $unsafe = Get-ChildItem -LiteralPath $resolved -Recurse -Force | Where-Object {
        ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        ((-not $_.PSIsContainer) -and ($_.Extension -in @('.py','.ps1','.mjs','.js','.ts',
            '.exe','.dll','.onnx','.safetensors','.pt','.pth','.ckpt','.ttf') -or $_.Name -eq '.env'))
    }
    if ($unsafe) { throw "Code/models/links found in $resolved; nothing deleted" }
    $targets += $resolved
}
# Refuse actual active processing, while allowing the cleanup-waiting launcher.
$activeJobs = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -in @('python.exe','ffmpeg.exe') -and $_.CommandLine -and
    $_.CommandLine.Contains($projectRoot) -and
    ($_.CommandLine -match 'karaoke.py|separate_local_stems.py|uvr_instrumental.py|build_bowlnfun_karaoke.py|benchmark_job.py|branding_guard.py|export_checked_sample.py|clean_source_branding.py' -or $_.Name -eq 'ffmpeg.exe')
}
if ($activeJobs) { throw 'A processing job is still active; nothing deleted' }
$receiptRoot = Join-Path $projectRoot ('reports\cleanup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $receiptRoot -Force | Out-Null
$receiptNames = @('validation.json','preview-validation.json','sample-export.json',
    'full-review.json','timing-report.json','delivery.json','verification.json','layers.json','timings.json')
$bytesRemoved = 0L
foreach ($target in $targets) {
    foreach ($file in (Get-ChildItem -LiteralPath $target -Recurse -File -Force)) {
        $bytesRemoved += $file.Length
        if ($file.Name -in $receiptNames) {
            $relative = $file.FullName.Substring($projectRoot.Length + 1)
            $destination = Join-Path $receiptRoot $relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
            Copy-Item -LiteralPath $file.FullName -Destination $destination
        }
    }
}
$savedHashes | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $receiptRoot 'output-hashes.json')
foreach ($target in $targets) {
    Write-Host "Removing generated data: $target"
    Remove-Item -LiteralPath $target -Recurse -Force
}
foreach ($videoPath in $savedHashes.Keys) {
    if ((Get-FileHash -LiteralPath $videoPath -Algorithm SHA256).Hash -ne $savedHashes[$videoPath]) {
        throw "Output checksum changed: $videoPath"
    }
}
Write-Host 'Old work and temporary data removed. Code, models, inputs and out are preserved.'
Write-Host ("Removed {0:N2} GiB. Final MP4 hashes unchanged. Receipts: {1}" -f ($bytesRemoved / 1GB), $receiptRoot)
