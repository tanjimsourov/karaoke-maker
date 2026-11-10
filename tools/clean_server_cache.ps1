param([switch]$IncludeOldRancherLogs)
$ErrorActionPreference = 'Stop'
Write-Host 'Scope: eligible karaoke build cache only. No containers, volumes, models or videos are removed.'
docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Docker unavailable. Cleanup stopped.' }
# Do not add shared/private boolean filters: older Buildx versions handle them differently.
docker buildx prune --force --filter 'description~=karaoke|venv-zoom|venv-demucs|requirements-zoom'
if ($LASTEXITCODE -ne 0) { throw 'Karaoke cache cleanup failed.' }
if ($IncludeOldRancherLogs) {
    # These are shared diagnostic logs, not application data. Only old, closed files qualify.
    $logRoot = Join-Path $env:LOCALAPPDATA 'rancher-desktop\logs'
    $removedBytes = 0L
    if (Test-Path -LiteralPath $logRoot) {
        $rootItem = Get-Item -LiteralPath $logRoot
        if ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing linked log directory.' }
        $cutoff = (Get-Date).AddDays(-7)
        foreach ($item in Get-ChildItem -LiteralPath $logRoot -File) {
            if ($item.LastWriteTime -ge $cutoff -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { continue }
            $handle = $null
            try {
                # DeleteOnClose performs removal under an exclusive handle, avoiding a close/delete race.
                $handle = [IO.FileStream]::new($item.FullName, [IO.FileMode]::Open,
                    [IO.FileAccess]::ReadWrite, [IO.FileShare]::None, 4096, [IO.FileOptions]::DeleteOnClose)
                $removedBytes += $handle.Length
                $handle.Dispose(); $handle = $null
                Write-Host "Deleted old log: $($item.Name)"
            } catch {
                Write-Host "Skipped log: $($item.Name) ($($_.Exception.Message))"
            } finally { if ($null -ne $handle) { $handle.Dispose() } }
        }
    }
    Write-Host ('Old diagnostic log bytes removed: {0:N0}' -f $removedBytes)
}
Write-Host 'Cleanup completed. A zero cache total means no eligible cache was reclaimed.'
Write-Host 'Docker virtual-disk space may remain allocated on C:. This script does not compact or delete the shared VHDX.'
