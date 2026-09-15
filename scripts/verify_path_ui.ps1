param(
    [Parameter(Mandatory=$true)][string]$Executable,
    [string]$OutputPrefix='path-frozen',
    [string[]]$Scales=@('1','1.25','1.5')
)
$ErrorActionPreference='Stop'
$spriteRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$spriteExe=[IO.Path]::GetFullPath($Executable)
if (-not (Test-Path -LiteralPath $spriteExe -PathType Leaf)) { throw 'Validation EXE not found.' }
$spriteOldScale=$env:QT_SCALE_FACTOR
$spriteOldScreens=$env:QT_SCREEN_SCALE_FACTORS
$spriteReports=@()
try {
    foreach ($spriteScale in $Scales) {
        # An explicit non-unit screen factor avoids Qt treating 1 as an unset override.
        $env:QT_SCALE_FACTOR=if ($spriteScale -eq '1') { '0.8' } else { '1' }
        $spriteScreenFactor=if ($spriteScale -eq '1') { '1.25' } else { $spriteScale }
        $env:QT_SCREEN_SCALE_FACTORS=(@($spriteScreenFactor)*8)-join ';'
        $spriteOut=Join-Path $spriteRoot ('build\'+$OutputPrefix+'-'+$spriteScale+'-'+[Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $spriteOut | Out-Null
        if ($spriteScale -eq '1.25') {
            '{"language":"en_US"}' | Set-Content -LiteralPath (Join-Path $spriteOut 'machine-settings.json') -Encoding Ascii
        }
        foreach ($spriteVerify in @($false,$true)) {
            $spriteArgs=@('--smoke-path-memory',('"'+$spriteOut+'"'))
            if ($spriteVerify) { $spriteArgs+='--verify-path-memory' }
            $spriteProcess=Start-Process -FilePath $spriteExe -ArgumentList $spriteArgs -WorkingDirectory $spriteRoot -WindowStyle Hidden -PassThru
            if (-not $spriteProcess.WaitForExit(180000)) { $spriteProcess.Kill();throw 'Path/UI acceptance timed out.' }
            $spriteProcess.Refresh()
            if ($spriteProcess.ExitCode -ne 0) { throw "Path/UI acceptance failed: $spriteOut (restart=$spriteVerify). Check logs/app.log." }
        }
        $spriteExercise=Get-Content -LiteralPath (Join-Path $spriteOut 'exercise.json') -Raw | ConvertFrom-Json
        $spriteRestart=Get-Content -LiteralPath (Join-Path $spriteOut 'restart.json') -Raw | ConvertFrom-Json
        foreach ($spriteResult in @($spriteExercise,$spriteRestart)) {
            if ($spriteResult.status -ne 'passed' -or [math]::Abs($spriteResult.dpr-[double]$spriteScale) -gt 0.001) { throw "Incorrect DPI or missing path validation: $spriteOut" }
        }
        $spriteReports+=@{status='passed';directory=$spriteOut;dpr=$spriteExercise.dpr;language=$spriteExercise.language;fresh_process=$true;control_observations=$spriteExercise.buttons_actions;executable=$spriteExe}
    }
} finally {
    $env:QT_SCALE_FACTOR=$spriteOldScale
    $env:QT_SCREEN_SCALE_FACTORS=$spriteOldScreens
}
return $spriteReports
