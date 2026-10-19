@echo off
rem Krok 1 "Wdroz na transmisje" (CLAUDE.md): zabezpieczenie powrotu w folderze transmisyjnym.
rem Uzycie: uruchomic W KATALOGU GLOWNYM folderu transmisyjnego. Skrypt dziala na biezacym folderze, nie na swoim polozeniu,
rem bo przed wdrozeniem folder transmisyjny nie ma jeszcze tych skryptow. Przyklad:
rem   cd /d C:\Users\filip\Projects\broadcast-modules
rem   ..\broadcast-modules-wp\tools\wdrozenie\zabezpiecz-przed-wdrozeniem.bat przed-wdrozeniem-RRRR-MM-DD
rem Robi: znacznik git na biezacym commicie, kopie baz modulow, kopie hub\hub.exe i plikow .exe pluginow (nie sa w gicie)
rem do kopie\<znacznik>\ oraz plik przywroc-poprzednia-wersje.bat w katalogu glownym (powrot jednym uruchomieniem).
setlocal EnableExtensions
if not exist "hub\" (echo BLAD: uruchom w katalogu glownym folderu ^(brak hub\^) & exit /b 1)
if not exist "modules\" (echo BLAD: uruchom w katalogu glownym folderu ^(brak modules\^) & exit /b 1)
set "TAG=%~1"
if "%TAG%"=="" (
  echo BLAD: podaj nazwe znacznika, np. przed-wdrozeniem-2026-10-20
  exit /b 2
)
for %%p in (8079 8080 8081) do (
  netstat -ano | findstr /R /C:"127.0.0.1:%%p .*LISTENING" /C:"0.0.0.0:%%p .*LISTENING" >nul && (
    echo BLAD: port %%p jest zajety. Zamknij HUB i modul przed kopia baz ^(kopia dzialajacej bazy moze byc niespojna^).
    exit /b 3
  )
)
git rev-parse -q --verify "refs/tags/%TAG%" >nul && (
  echo BLAD: znacznik %TAG% juz istnieje
  exit /b 4
)
set "KOPIA=kopie\%TAG%"
if exist "%KOPIA%" (
  echo BLAD: folder %KOPIA% juz istnieje
  exit /b 5
)
mkdir "%KOPIA%" || exit /b 6
for %%m in (futsal_nalf garbarnia) do (
  if exist "modules\%%m\instance\database.db" (
    mkdir "%KOPIA%\modules\%%m\instance" >nul 2>&1
    copy /Y "modules\%%m\instance\database.db" "%KOPIA%\modules\%%m\instance\database.db" >nul || (echo BLAD: kopia bazy %%m & exit /b 7)
    echo Kopia bazy: modules\%%m\instance\database.db
  )
)
if exist "hub\hub.exe" (
  mkdir "%KOPIA%\hub" >nul 2>&1
  copy /Y "hub\hub.exe" "%KOPIA%\hub\hub.exe" >nul || (echo BLAD: kopia hub.exe & exit /b 8)
  echo Kopia: hub\hub.exe
)
robocopy plugins "%KOPIA%\plugins" *.exe /S /NJH /NJS /NDL /NP >nul
if errorlevel 8 (echo BLAD: kopia plikow .exe pluginow & exit /b 9)
echo Kopia: pliki .exe pluginow
git tag "%TAG%" || (echo BLAD: nie mozna utworzyc znacznika & exit /b 10)
echo Znacznik: %TAG% na commicie
git rev-parse --short HEAD
> przywroc-poprzednia-wersje.bat echo @echo off
>> przywroc-poprzednia-wersje.bat echo set "TAG=%TAG%"
type "%~dp0przywroc-szablon.bat" >> przywroc-poprzednia-wersje.bat
echo Gotowe: przywroc-poprzednia-wersje.bat (powrot do %TAG%)
endlocal
