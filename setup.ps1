# Thin Windows entry point. No environment or user data is deleted.
param([switch]$Cuda, [switch]$ExtraSeparation, [string]$Python = 'py')
$ErrorActionPreference = 'Stop'
$setupArgs = @((Join-Path $PSScriptRoot 'setup.py'))
if ($Cuda) { $setupArgs += @('--cuda','cu128') }
if ($ExtraSeparation) { $setupArgs += '--extra-separation' }
if ($Python -eq 'py') { & py -3.11 @setupArgs } else { & $Python @setupArgs }
exit $LASTEXITCODE
