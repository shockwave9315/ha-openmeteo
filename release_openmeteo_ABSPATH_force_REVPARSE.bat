@echo on
setlocal enabledelayedexpansion

:: Open-Meteo Release Helper (ABS PATHS + rev-parse tag check)
set "REPO=C:\Users\huber\OneDrive\Pulpit\ha-openmeteo"
set "MANIFEST=C:\Users\huber\OneDrive\Pulpit\ha-openmeteo\custom_components\openmeteo\manifest.json"
set "GIT=C:\Program Files\Git\bin\git.exe"
set "GH=C:\Program Files\GitHub CLI\gh.exe"

title Open-Meteo Release Helper [REVPARSE CHECK]

echo Repo: %REPO%
echo Manifest: %MANIFEST%
echo Git: %GIT%
echo GH: %GH%

if not exist "%GIT%" ( echo [ERROR] git not found & pause & exit /b 1 )
if not exist "%GH%"  ( echo [ERROR] gh not found  & pause & exit /b 1 )
if not exist "%REPO%\.git" ( echo [ERROR] .git not found in %REPO% & pause & exit /b 1 )
if not exist "%MANIFEST%" ( echo [ERROR] manifest not found: %MANIFEST% & pause & exit /b 1 )

pushd "%REPO%" || (echo [ERROR] pushd fail & pause & exit /b 1)

set "VERSION="
set /p VERSION=Podaj numer wersji (np. 1.1.80): 
if "%VERSION%"=="" ( echo [ERROR] No version & popd & pause & exit /b 1 )

set "NOTES="
set /p NOTES=Krotki opis zmian (opcjonalnie, Enter aby pominac): 
if "%NOTES%"=="" set "NOTES=Release %VERSION%"

echo [STEP] Aktualizuje manifest.json -> %VERSION%
powershell -NoProfile -Command "$p='C:\Users\huber\OneDrive\Pulpit\ha-openmeteo\custom_components\openmeteo\manifest.json'; $json = Get-Content -Raw -LiteralPath $p | ConvertFrom-Json; $json.version = '%VERSION%'; $json | ConvertTo-Json -Depth 32 | Set-Content -LiteralPath $p -Encoding UTF8" || ( echo [ERROR] PowerShell update failed & popd & pause & exit /b 1 )

echo [STEP] "%GIT%" add .
"%GIT%" add . || (echo [ERROR] git add fail & popd & pause & exit /b 1)

echo [STEP] "%GIT%" commit
"%GIT%" commit -m "Release %VERSION%: %NOTES%"
if errorlevel 1 ( echo [WARN] no changes to commit - continue )

echo [STEP] Sprawdzam czy tag istnieje: %VERSION%
"%GIT%" rev-parse -q --verify "refs/tags/%VERSION%" >nul 2>&1
if not errorlevel 1 (
  echo [WARN] Tag %VERSION% juz istnieje.
  set "CHOICE=N"
  set /p CHOICE=Czy NADPISAC tag? (T/N): 
  if /I "%CHOICE%"=="T" (
    echo [STEP] Nadpisuje lokalny tag
    "%GIT%" tag -f -a %VERSION% -m "Release %VERSION%" || (echo [ERROR] git tag -f fail & popd & pause & exit /b 1)
    set "FORCE_TAG=1"
  ) else (
    set "FORCE_TAG=0"
  )
) else (
  echo [STEP] Tworze nowy tag
  "%GIT%" tag -a %VERSION% -m "Release %VERSION%" || (echo [ERROR] git tag create fail & popd & pause & exit /b 1)
  set "FORCE_TAG=0"
)

echo [STEP] "%GIT%" push (code)
"%GIT%" push || (echo [ERROR] git push fail & popd & pause & exit /b 1)

echo [STEP] push tag
if "%FORCE_TAG%"=="1" (
  "%GIT%" push -f origin %VERSION% || (echo [ERROR] push tag -f fail & popd & pause & exit /b 1)
) else (
  "%GIT%" push origin %VERSION% || (echo [ERROR] push tag fail & popd & pause & exit /b 1)
)

echo [STEP] gh release (create/edit)
"%GH%" auth status || (echo [ERROR] gh not logged in & popd & pause & exit /b 1)
"%GH%" release view %VERSION% >nul 2>&1
if errorlevel 1 (
  "%GH%" release create %VERSION% --title "%VERSION%" --notes "%NOTES%" --latest || echo [WARN] gh release create failed
) else (
  "%GH%" release edit %VERSION% --title "%VERSION%" --notes "%NOTES%" --latest || echo [WARN] gh release edit failed
)

echo Done.
popd
pause
exit /b 0
