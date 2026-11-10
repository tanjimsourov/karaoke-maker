param([switch]$DeleteOldProjectData)
$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectDirectory
if (-not $DeleteOldProjectData) {
    Write-Host 'No data deleted. Use -DeleteOldProjectData to stop karaoke and delete its old models, work, staging exports, reports and tmp volumes.'
    exit 0
}
# Fixed legacy project identity: never infer a broader deletion scope.
$projectName = 'karaoke-maker'
$volumeKeys = @('karaoke_models', 'karaoke_work', 'karaoke_exports', 'karaoke_reports', 'karaoke_tmp')
docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'Docker is unavailable; nothing deleted.' }
$existing = @(docker volume ls --format '{{.Name}}')
if ($LASTEXITCODE -ne 0) { throw 'Could not list volumes; nothing deleted.' }
$targets = @()
foreach ($key in $volumeKeys) {
    $name = $projectName + '_' + $key
    if ($existing -contains $name) {
        $raw = docker volume inspect $name
        if ($LASTEXITCODE -ne 0) { throw "Cannot inspect $name; nothing deleted." }
        $volume = @($raw | ConvertFrom-Json)[0]
        if ($volume.Labels.'com.docker.compose.project' -ne $projectName -or
            $volume.Labels.'com.docker.compose.volume' -ne $key) {
            throw "Ownership check failed for $name; nothing deleted."
        }
        $targets += $name
    }
}
& (Join-Path $PSScriptRoot 'configure_server_automatic.ps1')
if (-not $?) { throw 'Configuration failed; nothing deleted.' }
# Check the resolved mounts before removing the previous storage.
$configText = docker compose -p $projectName config --format json
if ($LASTEXITCODE -ne 0) { throw 'Compose configuration failed; nothing deleted.' }
$config = $configText | ConvertFrom-Json
$mounts = @($config.services.karaoke.volumes)
foreach ($target in @('/app/models','/app/work','/app/out','/app/reports','/app/tmp')) {
    $mount = @($mounts | Where-Object { $_.target -eq $target })
    if ($mount.Count -ne 1 -or $mount[0].type -ne 'bind' -or
        $mount[0].source.Replace('\','/').TrimEnd('/') -notlike ($projectDirectory.Replace('\','/').TrimEnd('/') + '/docker-data/*')) {
        throw "Expected project-local bind mount for $target; nothing deleted."
    }
}
docker compose -p $projectName down --timeout 120
if ($LASTEXITCODE -ne 0) { throw 'Could not stop karaoke; nothing deleted.' }
foreach ($name in $targets) {
    # Docker refuses removal if any other container still uses this volume.
    docker volume rm $name
    if ($LASTEXITCODE -ne 0) { throw "Could not remove $name. No forced removal attempted." }
}
Write-Host 'Old karaoke volumes deleted. Sources, published Windows outputs and other projects preserved.'
Write-Host "New runtime storage: $projectDirectory\docker-data"
Write-Host 'Models will download again. Images/build cache remain in Docker shared storage; C: VHDX may not shrink automatically.'
