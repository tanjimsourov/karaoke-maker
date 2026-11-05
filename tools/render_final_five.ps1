$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$outDir = Join-Path $root 'out'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $outDir 'AEr_lig_Freestyle_Karaoke_BG2.mp4'))) {
    Copy-Item -LiteralPath (Join-Path $root 'delivery\Bowlnfun Jakob For Visuals\AEr_lig_Freestyle_Karaoke_BG2.mp4') -Destination (Join-Path $outDir 'AEr_lig_Freestyle_Karaoke_BG2.mp4') -Force
}
Write-Output 'AEr_lig_Freestyle REUSED'
$background = Join-Path $root 'audio-bg-sample\org\Bowlnfun_Image_2.png'
$songs = @(
    @('Bliv_her_lidt_endnu', 'BLIV HER LIDT ENDNU', 'Annika feat. JOSVA', 'DANSK KARAOKE'),
    @('Blodigt', 'BLODIGT', 'Anton Westerlin feat. Annika', 'DANSK KARAOKE'),
    @('Barry_Cant_Swim_Kimbara', 'KIMBARA', 'Barry Can''t Swim', 'ORIGINAL KARAOKE')
)
foreach($song in $songs) {
    $slug,$title,$artist,$language = $song
    & python tools\build_bowlnfun_karaoke.py --slug $slug --title $title --artist $artist --background-file $background --output-dir $outDir --language-label $language
    if (-not (Test-Path -LiteralPath (Join-Path $outDir ($slug + '_Karaoke.mp4')))) { throw "$slug render failed" }
    Write-Output "$slug READY"
}
Write-Output 'EXISTING_FOUR_READY'
