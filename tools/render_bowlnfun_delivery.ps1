$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python).Source

$songs = @(
    @('Bliv_her_lidt_endnu', 'BLIV HER LIDT ENDNU', 'Annika feat. JOSVA', '0', 'DANSK KARAOKE'),
    @('AEr_lig_Freestyle', 'ÆRLIG FREESTYLE', 'TogA', '1', 'DANSK KARAOKE'),
    @('Alle_Skuffer_Over_Tid', 'ALLE SKUFFER OVER TID', 'The Minds of 99', '2', 'DANSK KARAOKE'),
    @('Barry_Cant_Swim_Kimbara', 'KIMBARA', 'Barry Can''t Swim', '1', 'ORIGINAL KARAOKE'),
    @('Blodigt', 'BLODIGT', 'Anton Westerlin feat. Annika', '2', 'DANSK KARAOKE')
)

foreach ($song in $songs) {
    $slug, $title, $artist, $background, $language = $song
    Write-Output "[$slug] render started"
    & $python (Join-Path $root 'tools\build_bowlnfun_karaoke.py') --slug $slug --title $title --artist $artist --background $background --language-label $language
    if ($LASTEXITCODE -ne 0) { throw "[$slug] renderer failed" }
    $output = Join-Path $root ("delivery\Bowlnfun Jakob For Visuals\" + $slug + '_Karaoke.mp4')
    & (Join-Path $root 'tools\ffmpeg\ffmpeg.exe') -v error -i $output -f null -
    if ($LASTEXITCODE -ne 0) { throw "[$slug] decode validation failed" }
    Write-Output "[$slug] READY"
}
Write-Output 'ALL_REMAINING_READY'
