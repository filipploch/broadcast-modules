@echo off
rem Buduje hub.exe z wpisanym commitem (E2d3c1). hub.exe budowac WYLACZNIE tym skryptem: zwykle "go build" daje "wersja nieznana".
rem Commit: git rev-parse HEAD; "-dirty", gdy w folderze hub\ sa niezapisane zmiany (takze nowe pliki). Bez gita: wersja nieznana.
setlocal
cd /d "%~dp0"
set "COMMIT="
for /f "delims=" %%c in ('git rev-parse --short^=12 HEAD 2^>nul') do set "COMMIT=%%c"
if not defined COMMIT (
  echo UWAGA: brak gita albo repozytorium - hub.exe bez commitu ^(wersja nieznana^)
  goto build
)
set "DIRTY="
for /f "delims=" %%s in ('git status --porcelain -- . 2^>nul') do set "DIRTY=1"
if defined DIRTY set "COMMIT=%COMMIT%-dirty"
:build
echo Buduje hub.exe (commit: %COMMIT%)
go build -ldflags "-X main.buildCommit=%COMMIT%" -o hub.exe .
if errorlevel 1 (
  echo BLAD: budowanie hub.exe nie powiodlo sie
  exit /b 1
)
echo Gotowe: hub\hub.exe
endlocal
