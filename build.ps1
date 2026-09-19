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

$spriteSetDirectory = Join-Path $PSScriptRoot ('build\set-smoke-' + [Guid]::NewGuid().ToString('N'))
$spriteSetSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-animation-sets', ('"' + $spriteSetDirectory + '"')) -WindowStyle Hidden -PassThru
if (-not $spriteSetSmoke.WaitForExit(300000)) {
    $spriteSetSmoke.Kill()
    throw 'Packaged Animation Set preview / export timed out.'
}
$spriteSetSmoke.Refresh()
if ($spriteSetSmoke.ExitCode -ne 0) { throw "Packaged Animation Set failed ($($spriteSetSmoke.ExitCode)). Check logs/app.log." }
$spriteSetVerify = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-animation-sets', ('"' + $spriteSetDirectory + '"'), '--verify-animation-sets') -WindowStyle Hidden -PassThru
if (-not $spriteSetVerify.WaitForExit(200000)) {
    $spriteSetVerify.Kill()
    throw 'Packaged Animation Set restart verification timed out.'
}
$spriteSetVerify.Refresh()
if ($spriteSetVerify.ExitCode -ne 0) { throw "Packaged Animation Set restart verification failed ($($spriteSetVerify.ExitCode)). Check logs/app.log." }
$spriteSetReport = Get-Content -LiteralPath (Join-Path $spriteSetDirectory 'validation.json') -Raw | ConvertFrom-Json
if ($spriteSetReport.status -ne 'passed' -or -not $spriteSetReport.restart_verified -or -not $spriteSetReport.jump_ready) { throw 'Missing Animation Set acceptance result.' }

$spriteMachineDirectory = Join-Path $PSScriptRoot ('build\machine-smoke-' + [Guid]::NewGuid().ToString('N'))
$spriteMachineSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-state-machine', ('"' + $spriteMachineDirectory + '"')) -WindowStyle Hidden -PassThru
if (-not $spriteMachineSmoke.WaitForExit(360000)) {
    $spriteMachineSmoke.Kill()
    throw 'Packaged State Machine graph / simulator / export timed out.'
}
$spriteMachineSmoke.Refresh()
if ($spriteMachineSmoke.ExitCode -ne 0) { throw "Packaged State Machine failed ($($spriteMachineSmoke.ExitCode)). Check logs/app.log." }
$spriteMachineVerify = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-state-machine', ('"' + $spriteMachineDirectory + '"'), '--verify-state-machine') -WindowStyle Hidden -PassThru
if (-not $spriteMachineVerify.WaitForExit(220000)) {
    $spriteMachineVerify.Kill()
    throw 'Packaged State Machine restart verification timed out.'
}
$spriteMachineVerify.Refresh()
if ($spriteMachineVerify.ExitCode -ne 0) { throw "Packaged State Machine restart verification failed ($($spriteMachineVerify.ExitCode)). Check logs/app.log." }
$spriteMachineReport = Get-Content -LiteralPath (Join-Path $spriteMachineDirectory 'validation.json') -Raw | ConvertFrom-Json
if ($spriteMachineReport.status -ne 'passed' -or -not $spriteMachineReport.restart_verified -or -not $spriteMachineReport.set_state_plays_via_set_provider) { throw 'Missing State Machine acceptance result.' }

$spriteSheetDirectory = Join-Path $PSScriptRoot ('build\sheet-smoke-' + [Guid]::NewGuid().ToString('N'))
$spriteSheetSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-sprite-sheet', ('"' + $spriteSheetDirectory + '"')) -WindowStyle Hidden -PassThru
if (-not $spriteSheetSmoke.WaitForExit(300000)) {
    $spriteSheetSmoke.Kill()
    throw 'Packaged Sprite Sheet slicer smoke timed out.'
}
$spriteSheetSmoke.Refresh()
if ($spriteSheetSmoke.ExitCode -ne 0) { throw "Packaged Sprite Sheet slicer failed ($($spriteSheetSmoke.ExitCode)). Check logs/app.log." }
$spriteSheetVerify = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-sprite-sheet', ('"' + $spriteSheetDirectory + '"'), '--verify-sprite-sheet') -WindowStyle Hidden -PassThru
if (-not $spriteSheetVerify.WaitForExit(180000)) {
    $spriteSheetVerify.Kill()
    throw 'Packaged Sprite Sheet restart verification timed out.'
}
$spriteSheetVerify.Refresh()
if ($spriteSheetVerify.ExitCode -ne 0) { throw "Packaged Sprite Sheet restart verification failed ($($spriteSheetVerify.ExitCode)). Check logs/app.log." }
$spriteSheetReport = Get-Content -LiteralPath (Join-Path $spriteSheetDirectory 'validation.json') -Raw | ConvertFrom-Json
if ($spriteSheetReport.status -ne 'passed' -or -not $spriteSheetReport.restart_verified -or -not $spriteSheetReport.row_major_order -or $spriteSheetReport.frames -ne 8) { throw 'Missing Sprite Sheet slicer acceptance result.' }

$spriteInteractionReports = @()
$spritePreviousScreenScale = $env:QT_SCREEN_SCALE_FACTORS
$spritePreviousScale = $env:QT_SCALE_FACTOR
try {
    $env:QT_SCALE_FACTOR = '1'
    foreach ($spriteInteractionScale in @('1.0', '1.25', '1.5')) {
        $env:QT_SCREEN_SCALE_FACTORS = (@($spriteInteractionScale) * 8) -join ';'
        $spriteInteractionDirectory = Join-Path $PSScriptRoot ('build\interaction-smoke-' + $spriteInteractionScale + '-' + [Guid]::NewGuid().ToString('N'))
        $spriteInteractionVerifyTarget = $spriteInteractionDirectory
        $spriteInteractionSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-interaction-performance', ('"' + $spriteInteractionDirectory + '"')) -WindowStyle Hidden -PassThru
        if (-not $spriteInteractionSmoke.WaitForExit(600000)) {
            $spriteInteractionSmoke.Kill()
            throw 'Packaged frame move / interaction performance smoke timed out.'
        }
        $spriteInteractionSmoke.Refresh()
        if ($spriteInteractionSmoke.ExitCode -ne 0) { throw "Packaged interaction smoke failed at DPR $spriteInteractionScale ($($spriteInteractionSmoke.ExitCode)). Check logs/app.log." }
        $spriteInteractionReport = Get-Content -LiteralPath (Join-Path $spriteInteractionDirectory 'validation.json') -Raw | ConvertFrom-Json
        $spriteInteractionReport | Add-Member -NotePropertyName dpr -NotePropertyValue ([double]$spriteInteractionScale) -Force
        if ($spriteInteractionReport.status -ne 'passed' -or $spriteInteractionReport.canvas_visual_diff -ne 0 -or $spriteInteractionReport.timeline_visual_diff -ne 0 -or $spriteInteractionReport.tree_visual_diff -ne 0 -or -not $spriteInteractionReport.paint_median_ok -or -not $spriteInteractionReport.paint_p95_ok) {
            throw "Missing interaction acceptance result at DPR $spriteInteractionScale."
        }
        $spriteInteractionReports += $spriteInteractionReport
    }
} finally {
    $env:QT_SCREEN_SCALE_FACTORS = $spritePreviousScreenScale
    $env:QT_SCALE_FACTOR = $spritePreviousScale
}
$spriteInteractionVerify = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-interaction-performance', ('"' + $spriteInteractionVerifyTarget + '"'), '--verify-interaction') -WindowStyle Hidden -PassThru
if (-not $spriteInteractionVerify.WaitForExit(240000)) {
    $spriteInteractionVerify.Kill()
    throw 'Packaged frame move restart verification timed out.'
}
$spriteInteractionVerify.Refresh()
if ($spriteInteractionVerify.ExitCode -ne 0) { throw "Packaged frame move restart verification failed ($($spriteInteractionVerify.ExitCode)). Check logs/app.log." }

$spritePixelDirectory = Join-Path $PSScriptRoot ('build\pixel-smoke-' + [Guid]::NewGuid().ToString('N'))
$spritePixelSmoke = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-pixel-tools', ('"' + $spritePixelDirectory + '"')) -WindowStyle Hidden -PassThru
if (-not $spritePixelSmoke.WaitForExit(420000)) {
    $spritePixelSmoke.Kill()
    throw 'Packaged pixel tools / Group drop zones / derived frames timed out.'
}
$spritePixelSmoke.Refresh()
if ($spritePixelSmoke.ExitCode -ne 0) { throw "Packaged pixel tools failed ($($spritePixelSmoke.ExitCode)). Check logs/app.log." }
$spritePixelVerify = Start-Process -FilePath $spriteExecutable -ArgumentList @('--smoke-pixel-tools', ('"' + $spritePixelDirectory + '"'), '--verify-pixel-tools') -WindowStyle Hidden -PassThru
if (-not $spritePixelVerify.WaitForExit(240000)) {
    $spritePixelVerify.Kill()
    throw 'Packaged pixel tool restart verification timed out.'
}
$spritePixelVerify.Refresh()
if ($spritePixelVerify.ExitCode -ne 0) { throw "Packaged pixel tool restart verification failed ($($spritePixelVerify.ExitCode)). Check logs/app.log." }
$spritePixelReport = Get-Content -LiteralPath (Join-Path $spritePixelDirectory 'validation.json') -Raw | ConvertFrom-Json
if ($spritePixelReport.status -ne 'passed' -or -not $spritePixelReport.restart_verified -or $spritePixelReport.canvas_trail_pixel_difference -ne 0) { throw 'Missing pixel tool acceptance result.' }

$spritePathReports = & (Join-Path $PSScriptRoot 'scripts\verify_path_ui.ps1') -Executable $spriteExecutable
$spriteReceipt = @{ status = 'passed'; build_version = '20260919-sprite-sheet-slicer'; sheet_validation = $spriteSheetReport; interaction_validation = $spriteInteractionReports; path_validation = $spritePathReports; reference_validation = $spriteReferenceReports; group_validation = $spriteGroupReport; character_validation = $spriteCharacterReport; frame_validation = $spriteFrameReport; set_validation = $spriteSetReport; machine_validation = $spriteMachineReport; pixel_validation = $spritePixelReport; editor_validation = $spriteEditorReport; executable_sha256 = (Get-FileHash -LiteralPath $spriteExecutable -Algorithm SHA256).Hash; verified_at = (Get-Date).ToString('o') }
$spriteReceipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $spriteReleaseDirectory 'release-validation.json') -Encoding UTF8
Write-Host "Built $spriteExecutable. Video input uses FFmpeg; frame sequence input does not. All release checks passed."
