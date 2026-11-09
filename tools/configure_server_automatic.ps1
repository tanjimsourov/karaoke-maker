param([string]$MediaDirectory = 'D:/Application/Website/ftpPrivate/Danish New')
$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectDirectory '.env'
$settings = [ordered]@{
    KARAOKE_MEDIA_HOST_DIR = '"' + $MediaDirectory.Replace('\','/') + '"'
    KARAOKE_DOCKER_CPUS = '4'
    KARAOKE_DOCKER_MEMORY = '12g'
    KARAOKE_SERVER_WORKERS = '6'
    KARAOKE_SERVER_THREADS = '1'
    KARAOKE_SERVER_MODEL = 'htdemucs'
    KARAOKE_SERVER_PARALLEL = '1'
    KARAOKE_OCR_WORKERS = '2'
    KARAOKE_DELIVERY_MODE = 'automatic'
    KARAOKE_SERVER_AUDIO_FALLBACK = '0'
    KARAOKE_SERVER_ATTEMPTS = '2'
    KARAOKE_LANGUAGE = 'auto'
    KARAOKE_CLEANUP_AFTER_RUN = '1'
    KARAOKE_CLEANUP_AFTER_SONG = '1'
}
$lines = @()
if (Test-Path -LiteralPath $envPath) {
    Copy-Item -LiteralPath $envPath -Destination ($envPath + '.backup-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff'))
    $lines = @(Get-Content -LiteralPath $envPath)
}
$result = [System.Collections.Generic.List[string]]::new()
$seen = @{}
foreach ($line in $lines) {
    $key = ($line -split '=',2)[0].Trim()
    if ($settings.Contains($key)) {
        if (-not $seen.ContainsKey($key)) { $result.Add($key + '=' + $settings[$key]); $seen[$key] = $true }
    } else { $result.Add($line) }
}
foreach ($key in $settings.Keys) {
    if (-not $seen.ContainsKey($key)) { $result.Add($key + '=' + $settings[$key]) }
}
[System.IO.File]::WriteAllLines($envPath,$result,[System.Text.UTF8Encoding]::new($false))
Write-Host 'Configured automatic exports: 6 workers, 4 shared CPUs, 12 GB RAM cap, light model.'
Write-Host 'No services restarted. Run docker compose up --build from the project folder.'
