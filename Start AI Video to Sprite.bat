@echo off
cd /d "%~dp0"
if not exist "dist\AI Video to Sprite\AI Video to Sprite.exe" (
  echo The packaged application is missing. Please build or restore the release.
  pause
  exit /b 1
)
start "" "dist\AI Video to Sprite\AI Video to Sprite.exe" %*
