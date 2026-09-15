param([Parameter(Mandatory=$true)][string]$SourceRoot, [string]$DestinationRoot = 'dist')
$ErrorActionPreference = 'Stop'
$spriteWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$spritePrefix = $spriteWorkspace.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
function Resolve-Release([string]$relativeRoot) {
    $resolved = [IO.Path]::GetFullPath((Join-Path $spriteWorkspace $relativeRoot))
    if (-not $resolved.StartsWith($spritePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Release directory must remain inside the workspace.'
    }
    $resolved = Join-Path $resolved 'AI Video to Sprite'
    $cursor = $resolved
    while ($cursor -ne $spriteWorkspace) {
        if ((Test-Path -LiteralPath $cursor) -and ((Get-Item -LiteralPath $cursor).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Release paths must not traverse links or junctions.'
        }
        $cursor = Split-Path -Parent $cursor
    }
    return $resolved
}
$spriteSource = Resolve-Release $SourceRoot
$spriteDestination = Resolve-Release $DestinationRoot
if ($spriteSource -eq $spriteDestination) { throw 'Source and destination releases must differ.' }
$spriteName = 'AI Video to Sprite.exe'
$spriteReceipt = Get-Content -LiteralPath (Join-Path $spriteSource 'release-validation.json') -Raw | ConvertFrom-Json
$spriteExpectedHash = (Get-FileHash -LiteralPath (Join-Path $spriteSource $spriteName) -Algorithm SHA256).Hash
if ($spriteReceipt.status -ne 'passed' -or $spriteReceipt.executable_sha256 -ne $spriteExpectedHash) {
    throw 'Run build.ps1 and all packaged checks successfully before publishing.'
}
$spriteTargetExe = Join-Path $spriteDestination $spriteName
$spriteRunning = Get-Process -Name 'AI Video to Sprite' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $spriteTargetExe }
if ($spriteRunning) { throw 'The destination application is running; close it before updating.' }
# Backup only application runtime files. No user project, media, cache or export
# is removed or moved. All copying below stays within verified workspace paths.
$spriteBackup = Join-Path $spriteWorkspace ('build\previous-runtime-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $spriteBackup -Force | Out-Null
New-Item -ItemType Directory -Path $spriteDestination -Force | Out-Null
foreach ($runtime in @($spriteName, '_internal')) {
    $target = Join-Path $spriteDestination $runtime
    if ((Test-Path -LiteralPath $target) -and ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Runtime target must not be a link.' }
    if (Test-Path -LiteralPath $target) { Copy-Item -LiteralPath $target -Destination $spriteBackup -Recurse }
    Copy-Item -LiteralPath (Join-Path $spriteSource $runtime) -Destination $spriteDestination -Recurse -Force
}
foreach ($document in @('README.md', 'ARCHITECTURE.md', 'TASKS.md', 'VALIDATION.md', 'UI_AUDIT.md', 'release-validation.json')) {
    Copy-Item -LiteralPath (Join-Path $spriteSource $document) -Destination $spriteDestination -Force
}
# Existing examples may have been edited by the user. Add only missing bundled
# top-level assets; never copy generated example cache directories.
$spriteExamples = Join-Path $spriteDestination 'examples'
New-Item -ItemType Directory -Path $spriteExamples -Force | Out-Null
foreach ($asset in Get-ChildItem -LiteralPath (Join-Path $spriteSource 'examples')) {
    if ($asset.Extension -notin @('.mp4', '.aivsprite') -and $asset.Name -ne 'sequence_idle') { continue }
    $target = Join-Path $spriteExamples $asset.Name
    if (-not (Test-Path -LiteralPath $target)) { Copy-Item -LiteralPath $asset.FullName -Destination $spriteExamples -Recurse }
}
if ((Get-FileHash -LiteralPath $spriteTargetExe -Algorithm SHA256).Hash -ne $spriteExpectedHash) { throw 'Published EXE does not match verified EXE.' }
$spriteSmoke = Start-Process -FilePath $spriteTargetExe -ArgumentList '--smoke-test' -WorkingDirectory $spriteWorkspace -WindowStyle Hidden -PassThru
if (-not $spriteSmoke.WaitForExit(20000)) { $spriteSmoke.Kill(); throw 'Published EXE startup timed out.' }
$spriteSmoke.Refresh()
if ($spriteSmoke.ExitCode -ne 0) { throw "Published EXE startup failed. Previous runtime backup: $spriteBackup" }
Write-Host "Published $spriteTargetExe"
Write-Host "SHA256: $spriteExpectedHash"
Write-Host "Previous runtime backup: $spriteBackup"
