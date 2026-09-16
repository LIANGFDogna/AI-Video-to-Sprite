param([string]$DistPath = 'dist')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$spriteOutputRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $DistPath))
$spriteWorkspacePrefix = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $spriteOutputRoot.StartsWith($spriteWorkspacePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Release output must be a subdirectory of the project workspace.'
}
$spriteReleaseDirectory = Join-Path $spriteOutputRoot 'AI Video to Sprite'
$spriteExecutable = Join-Path $spriteReleaseDirectory 'AI Video to Sprite.exe'
$spriteExamples = Join-Path $spriteReleaseDirectory 'examples'
$spriteRunning = Get-Process -Name 'AI Video to Sprite' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $spriteExecutable }
if ($spriteRunning) {
    throw 'The release is running. Use -DistPath with a separate output folder to keep it open.'
}
if (Test-Path -LiteralPath $spriteReleaseDirectory) {
    throw 'Release directory already exists. Build with a fresh -DistPath, then use scripts/publish_release.ps1 to preserve user data.'
}
$spriteOriginalPath = $env:PATH
$spriteOriginalConfig = $env:PYINSTALLER_CONFIG_DIR
try {
    # Third-party tools on PATH may ship incompatible ICU / Windows API shims.
    # Qt 6 on Windows must resolve the operating system ICU, not Poppler's ICU.
    $env:PATH = "$PSScriptRoot\.venv\Scripts;$env:SystemRoot\System32;$env:SystemRoot"
    $env:PYINSTALLER_CONFIG_DIR = "$PSScriptRoot\build\pyinstaller-cache"
    & '.\.venv\Scripts\python.exe' scripts/build_release.py --distpath $spriteOutputRoot
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
} finally {
    $env:PATH = $spriteOriginalPath
    $env:PYINSTALLER_CONFIG_DIR = $spriteOriginalConfig
}
Copy-Item -LiteralPath 'README.md','ARCHITECTURE.md','TASKS.md','VALIDATION.md','UI_AUDIT.md' -Destination $spriteReleaseDirectory
if (Test-Path -LiteralPath 'examples\demo.aivsprite') {
    New-Item -ItemType Directory -Path $spriteExamples -Force | Out-Null
    Copy-Item -LiteralPath 'examples\demo.aivsprite','examples\demo_green_screen.mp4' -Destination $spriteExamples
    if (Test-Path -LiteralPath 'examples\normalized_512.aivsprite') {
        Copy-Item -LiteralPath 'examples\normalized_512.aivsprite','examples\normalized_512.mp4' -Destination $spriteExamples
    }
    if (Test-Path -LiteralPath 'examples\character_profile.aivsprite') {
        Copy-Item -LiteralPath 'examples\character_profile.aivsprite' -Destination $spriteExamples
    }
    if (Test-Path -LiteralPath 'examples\sequence_idle.aivsprite') {
        Copy-Item -LiteralPath 'examples\sequence_idle.aivsprite' -Destination $spriteExamples
        Copy-Item -LiteralPath 'examples\sequence_idle' -Destination $spriteExamples -Recurse
    }
    if (Test-Path -LiteralPath 'examples\keyed_passthrough_56.aivsprite') {
        Copy-Item -LiteralPath 'examples\keyed_passthrough_56.aivsprite','examples\keyed_passthrough_56.mp4' -Destination $spriteExamples
    }
}
$spriteSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList '--smoke-test' -WindowStyle Hidden -PassThru
if (-not $spriteSmoke.WaitForExit(20000)) {
    $spriteSmoke.Kill()
    throw 'Packaged application startup timed out. Check the build dependency search path.'
}
$spriteSmoke.Refresh()
if ($spriteSmoke.ExitCode -ne 0) { throw "Packaged application startup failed ($($spriteSmoke.ExitCode))." }
if (Test-Path -LiteralPath 'examples\normalized_512.aivsprite') {
    $spritePreviousSettings = $env:AIVSPRITE_SETTINGS
    try {
        $env:AIVSPRITE_SETTINGS = Join-Path $PSScriptRoot 'build\release-smoke-settings.json'
        $spriteSampleProject = Join-Path $PSScriptRoot 'examples\normalized_512.aivsprite'
        $spritePreviewSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-preview', ('"' + $spriteSampleProject + '"')) -WindowStyle Hidden -PassThru
        if (-not $spritePreviewSmoke.WaitForExit(90000)) {
            $spritePreviewSmoke.Kill()
            throw 'Packaged final animation preview timed out.'
        }
        $spritePreviewSmoke.Refresh()
        if ($spritePreviewSmoke.ExitCode -ne 0) { throw "Packaged animation preview failed ($($spritePreviewSmoke.ExitCode)). Check logs/app.log." }
    } finally {
        $env:AIVSPRITE_SETTINGS = $spritePreviousSettings
    }
}
if (Test-Path -LiteralPath 'examples\character_profile.aivsprite') {
    $spritePreviousSettings = $env:AIVSPRITE_SETTINGS
    try {
        $env:AIVSPRITE_SETTINGS = Join-Path $PSScriptRoot 'build\release-smoke-settings.json'
        $spriteCharacterProject = Join-Path $PSScriptRoot 'examples\character_profile.aivsprite'
        $spriteCharacterSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-preview', ('"' + $spriteCharacterProject + '"')) -WindowStyle Hidden -PassThru
        if (-not $spriteCharacterSmoke.WaitForExit(90000)) {
            $spriteCharacterSmoke.Kill()
            throw 'Packaged Character Space preview timed out.'
        }
        $spriteCharacterSmoke.Refresh()
        if ($spriteCharacterSmoke.ExitCode -ne 0) { throw "Packaged Character Space failed ($($spriteCharacterSmoke.ExitCode)). Check logs/app.log." }
    } finally {
        $env:AIVSPRITE_SETTINGS = $spritePreviousSettings
    }
}
if (Test-Path -LiteralPath 'examples\sequence_idle.aivsprite') {
    $spritePreviousSettings = $env:AIVSPRITE_SETTINGS
    $spritePreviousFFmpeg = $env:AIVSPRITE_FFMPEG
    $spritePreviousFFprobe = $env:AIVSPRITE_FFPROBE
    try {
        $env:AIVSPRITE_SETTINGS = Join-Path $PSScriptRoot 'build\release-smoke-settings.json'
        $env:AIVSPRITE_FFMPEG = 'sequence-does-not-use-ffmpeg.exe'
        $env:AIVSPRITE_FFPROBE = 'sequence-does-not-use-ffprobe.exe'
        $spriteSequenceProject = Join-Path $spriteExamples 'sequence_idle.aivsprite'
        $spriteSequenceSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-preview', ('"' + $spriteSequenceProject + '"')) -WindowStyle Hidden -PassThru
        if (-not $spriteSequenceSmoke.WaitForExit(90000)) {
            $spriteSequenceSmoke.Kill()
            throw 'Packaged frame sequence preview timed out.'
        }
        $spriteSequenceSmoke.Refresh()
        if ($spriteSequenceSmoke.ExitCode -ne 0) { throw "Packaged frame sequence failed ($($spriteSequenceSmoke.ExitCode)). Check logs/app.log." }
    } finally {
        $env:AIVSPRITE_SETTINGS = $spritePreviousSettings
        $env:AIVSPRITE_FFMPEG = $spritePreviousFFmpeg
        $env:AIVSPRITE_FFPROBE = $spritePreviousFFprobe
    }
}
$spriteWorkspaceDirectory = Join-Path $PSScriptRoot ('build\workspace-smoke-' + [Guid]::NewGuid().ToString('N'))
$spriteWorkspaceSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-workspace', ('"' + $spriteWorkspaceDirectory + '"')) -WindowStyle Hidden -PassThru
if (-not $spriteWorkspaceSmoke.WaitForExit(90000)) {
    $spriteWorkspaceSmoke.Kill()
    throw 'Packaged new-project / folder-picker / RGBA16 smoke timed out.'
}
$spriteWorkspaceSmoke.Refresh()
if ($spriteWorkspaceSmoke.ExitCode -ne 0) { throw "Packaged workspace smoke failed ($($spriteWorkspaceSmoke.ExitCode)). Check logs/app.log." }
$spriteKeyedDirectory = Join-Path $PSScriptRoot ('build\keyed-smoke-' + [Guid]::NewGuid().ToString('N'))
$spriteKeyedProject = Join-Path $spriteExamples 'keyed_passthrough_56.aivsprite'
$spritePreviousSettings = $env:AIVSPRITE_SETTINGS
try {
    $env:AIVSPRITE_SETTINGS = Join-Path $PSScriptRoot 'build\release-smoke-settings.json'
    $spriteKeyedSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-keyed-passthrough', ('"' + $spriteKeyedProject + '"'), '--smoke-output', ('"' + $spriteKeyedDirectory + '"')) -WindowStyle Hidden -PassThru
    if (-not $spriteKeyedSmoke.WaitForExit(90000)) {
        $spriteKeyedSmoke.Kill()
        throw 'Packaged keyed video passthrough / export / full-processing resume timed out.'
    }
    $spriteKeyedSmoke.Refresh()
    if ($spriteKeyedSmoke.ExitCode -ne 0) { throw "Packaged keyed passthrough failed ($($spriteKeyedSmoke.ExitCode)). Check logs/app.log." }
} finally {
    $env:AIVSPRITE_SETTINGS = $spritePreviousSettings
}
$spriteCanvasDirectory = Join-Path $PSScriptRoot ('build\canvas-smoke-' + [Guid]::NewGuid().ToString('N'))
$spriteCanvasSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-project-canvas', ('"' + $spriteCanvasDirectory + '"')) -WindowStyle Hidden -PassThru
if (-not $spriteCanvasSmoke.WaitForExit(90000)) {
    $spriteCanvasSmoke.Kill()
    throw 'Packaged project canvas / mixed sequence / export check timed out.'
}
$spriteCanvasSmoke.Refresh()
if ($spriteCanvasSmoke.ExitCode -ne 0) { throw "Packaged project canvas failed ($($spriteCanvasSmoke.ExitCode)). Check logs/app.log." }
$spriteEditorDirectory = Join-Path $PSScriptRoot ('build\editor-smoke-' + [Guid]::NewGuid().ToString('N'))
$spriteEditorSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-editor', ('"' + $spriteEditorDirectory + '"')) -WindowStyle Hidden -PassThru
if (-not $spriteEditorSmoke.WaitForExit(60000)) {
    $spriteEditorSmoke.Kill()
    throw 'Packaged frame editor / multitrack / retime / export / reopen timed out.'
}
$spriteEditorSmoke.Refresh()
if ($spriteEditorSmoke.ExitCode -ne 0) { throw "Packaged editor failed ($($spriteEditorSmoke.ExitCode)). Check logs/app.log." }
$spriteEditorReport = Get-Content -LiteralPath (Join-Path $spriteEditorDirectory 'validation.json') -Raw | ConvertFrom-Json
if ($spriteEditorReport.status -ne 'passed') { throw 'Missing editor acceptance result.' }
$spriteReferenceReports = @()
$spritePreviousScreenScale = $env:QT_SCREEN_SCALE_FACTORS
$spritePreviousScale = $env:QT_SCALE_FACTOR
try {
    $env:QT_SCALE_FACTOR = '1'
    foreach ($spriteReferenceScale in @('1.25', '1.5')) {
        $env:QT_SCREEN_SCALE_FACTORS = (@($spriteReferenceScale) * 8) -join ';'
        $spriteReferenceDirectory = Join-Path $PSScriptRoot ('build\reference-frozen-' + $spriteReferenceScale + '-' + [Guid]::NewGuid().ToString('N'))
        $spriteReferenceSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-character-reference', ('"' + $spriteReferenceDirectory + '"')) -WindowStyle Hidden -PassThru
        if (-not $spriteReferenceSmoke.WaitForExit(175000)) {
            $spriteReferenceSmoke.Kill()
            throw 'Packaged Character Reference calibration / animation offsets / export timed out.'
        }
        $spriteReferenceSmoke.Refresh()
        if ($spriteReferenceSmoke.ExitCode -ne 0) { throw "Packaged Character Reference failed ($($spriteReferenceSmoke.ExitCode)). Check logs/app.log." }
        $spriteReferenceReport = Get-Content -LiteralPath (Join-Path $spriteReferenceDirectory 'validation.json') -Raw | ConvertFrom-Json
        if ($spriteReferenceReport.status -ne 'passed' -or [math]::Abs($spriteReferenceReport.dpr - [double]$spriteReferenceScale) -gt 0.001) { throw 'Missing reference acceptance or incorrect actual DPI.' }
        $spriteReferenceReports += $spriteReferenceReport
    }
} finally {
    $env:QT_SCREEN_SCALE_FACTORS = $spritePreviousScreenScale
    $env:QT_SCALE_FACTOR = $spritePreviousScale
}
$spriteGroupDirectory = Join-Path $PSScriptRoot ('build\group-smoke-' + [Guid]::NewGuid().ToString('N'))
$spriteGroupSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-groups', ('"' + $spriteGroupDirectory + '"')) -WindowStyle Hidden -PassThru
if (-not $spriteGroupSmoke.WaitForExit(180000)) {
    $spriteGroupSmoke.Kill()
    throw 'Packaged Group workspace / multi-animation export timed out.'
}
$spriteGroupSmoke.Refresh()
if ($spriteGroupSmoke.ExitCode -ne 0) { throw "Packaged Group workspace failed ($($spriteGroupSmoke.ExitCode)). Check logs/app.log." }
$spriteGroupVerify = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-groups', ('"' + $spriteGroupDirectory + '"'), '--verify-groups') -WindowStyle Hidden -PassThru
if (-not $spriteGroupVerify.WaitForExit(120000)) {
    $spriteGroupVerify.Kill()
    throw 'Packaged Group restart verification timed out.'
}
$spriteGroupVerify.Refresh()
if ($spriteGroupVerify.ExitCode -ne 0) { throw "Packaged Group restart verification failed ($($spriteGroupVerify.ExitCode)). Check logs/app.log." }
$spriteGroupReport = Get-Content -LiteralPath (Join-Path $spriteGroupDirectory 'validation.json') -Raw | ConvertFrom-Json
if ($spriteGroupReport.status -ne 'passed' -or -not $spriteGroupReport.restart_verified -or -not $spriteGroupReport.group_status_ready) { throw 'Missing Group acceptance result.' }

$spriteCharacterDirectory = Join-Path $PSScriptRoot ('build\character-smoke-' + [Guid]::NewGuid().ToString('N'))
$spriteCharacterSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-characters', ('"' + $spriteCharacterDirectory + '"')) -WindowStyle Hidden -PassThru
if (-not $spriteCharacterSmoke.WaitForExit(220000)) {
    $spriteCharacterSmoke.Kill()
    throw 'Packaged Character templates / per-Character Reference timed out.'
}
$spriteCharacterSmoke.Refresh()
if ($spriteCharacterSmoke.ExitCode -ne 0) { throw "Packaged Character workspace failed ($($spriteCharacterSmoke.ExitCode)). Check logs/app.log." }
$spriteCharacterVerify = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-characters', ('"' + $spriteCharacterDirectory + '"'), '--verify-characters') -WindowStyle Hidden -PassThru
if (-not $spriteCharacterVerify.WaitForExit(160000)) {
    $spriteCharacterVerify.Kill()
    throw 'Packaged Character restart verification timed out.'
}
$spriteCharacterVerify.Refresh()
if ($spriteCharacterVerify.ExitCode -ne 0) { throw "Packaged Character restart verification failed ($($spriteCharacterVerify.ExitCode)). Check logs/app.log." }
$spriteCharacterReport = Get-Content -LiteralPath (Join-Path $spriteCharacterDirectory 'validation.json') -Raw | ConvertFrom-Json
if ($spriteCharacterReport.status -ne 'passed' -or -not $spriteCharacterReport.restart_verified -or -not $spriteCharacterReport.character_reference_isolation) { throw 'Missing Character acceptance result.' }

$spriteFrameDirectory = Join-Path $PSScriptRoot ('build\frame-smoke-' + [Guid]::NewGuid().ToString('N'))
$spriteFrameSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-frame-alignment', ('"' + $spriteFrameDirectory + '"')) -WindowStyle Hidden -PassThru
if (-not $spriteFrameSmoke.WaitForExit(240000)) {
    $spriteFrameSmoke.Kill()
    throw 'Packaged frame alignment / reference ghost timed out.'
}
$spriteFrameSmoke.Refresh()
if ($spriteFrameSmoke.ExitCode -ne 0) { throw "Packaged frame alignment failed ($($spriteFrameSmoke.ExitCode)). Check logs/app.log." }
$spriteFrameVerify = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-frame-alignment', ('"' + $spriteFrameDirectory + '"'), '--verify-frame-alignment') -WindowStyle Hidden -PassThru
if (-not $spriteFrameVerify.WaitForExit(180000)) {
    $spriteFrameVerify.Kill()
    throw 'Packaged frame alignment restart verification timed out.'
}
$spriteFrameVerify.Refresh()
if ($spriteFrameVerify.ExitCode -ne 0) { throw "Packaged frame alignment restart verification failed ($($spriteFrameVerify.ExitCode)). Check logs/app.log." }
$spriteFrameReport = Get-Content -LiteralPath (Join-Path $spriteFrameDirectory 'validation.json') -Raw | ConvertFrom-Json
if ($spriteFrameReport.status -ne 'passed' -or -not $spriteFrameReport.restart_verified -or -not $spriteFrameReport.ghost_not_in_export) { throw 'Missing frame alignment acceptance result.' }

$spritePathReports = & (Join-Path $PSScriptRoot 'scripts\verify_path_ui.ps1') -Executable $spriteExecutable
$spriteReceipt = @{ status = 'passed'; build_version = '20260916-frame-alignment-reference-ghost'; path_validation = $spritePathReports; reference_validation = $spriteReferenceReports; group_validation = $spriteGroupReport; character_validation = $spriteCharacterReport; frame_validation = $spriteFrameReport; editor_validation = $spriteEditorReport; executable_sha256 = (Get-FileHash -LiteralPath $spriteExecutable -Algorithm SHA256).Hash; verified_at = (Get-Date).ToString('o') }
$spriteReceipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $spriteReleaseDirectory 'release-validation.json') -Encoding UTF8
Write-Host "Built $spriteExecutable. Video input uses FFmpeg; frame sequence input does not. All release checks passed."
