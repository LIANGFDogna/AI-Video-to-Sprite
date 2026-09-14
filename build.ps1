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
Copy-Item -LiteralPath 'README.md','ARCHITECTURE.md','TASKS.md','VALIDATION.md' -Destination $spriteReleaseDirectory
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
Write-Host "Built $spriteExecutable. Video input uses FFmpeg; frame sequence input does not. All release checks passed."
