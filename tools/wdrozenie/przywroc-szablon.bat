rem Tresc pliku przywroc-poprzednia-wersje.bat (pierwsze dwa wiersze, z nazwa znacznika, dopisuje zabezpiecz-przed-wdrozeniem.bat).
rem Powrot do poprzedniej wersji jednym uruchomieniem: kod do znacznika (git reset --keep: zachowuje lokalne niezapisane zmiany,
rem a przy konflikcie odmawia, zamiast je kasowac), bazy modulow i pliki .exe (hub.exe, pluginy) z kopii zrobionej przed wdrozeniem.
rem Nie przebudowuje hub.exe: przywraca dokladnie ten plik, ktory dzialal przed wdrozeniem.
setlocal EnableExtensions
cd /d "%~dp0"
set "KOPIA=kopie\%TAG%"
echo Powrot do wersji %TAG% (kopie z %KOPIA%)
if not exist "%KOPIA%" (
  echo BLAD: brak folderu kopii %KOPIA%
  exit /b 2
)
git rev-parse -q --verify "refs/tags/%TAG%" >nul || (
  echo BLAD: brak znacznika %TAG%
  exit /b 3
)
for %%p in (8079 8080 8081) do (
  netstat -ano | findstr /R /C:"127.0.0.1:%%p .*LISTENING" /C:"0.0.0.0:%%p .*LISTENING" >nul && (
    echo BLAD: port %%p jest zajety. Zamknij HUB, modul i manager, potem uruchom ponownie.
    exit /b 4
  )
)
git checkout -q main || (echo BLAD: nie mozna przejsc na main & exit /b 5)
git reset -q --keep "%TAG%" || (
  echo BLAD: kod nie wrocil do %TAG%: lokalne niezapisane zmiany koliduja z powrotem. Nic nie zmieniono w bazach ani plikach .exe.
  exit /b 6
)
echo Kod: main na znaczniku %TAG%
for %%m in (futsal_nalf garbarnia) do (
  if exist "%KOPIA%\modules\%%m\instance\database.db" (
    copy /Y "%KOPIA%\modules\%%m\instance\database.db" "modules\%%m\instance\database.db" >nul || (echo BLAD: przywrocenie bazy %%m & exit /b 7)
    echo Baza przywrocona: modules\%%m\instance\database.db
  )
)
if exist "%KOPIA%\hub\hub.exe" (
  copy /Y "%KOPIA%\hub\hub.exe" "hub\hub.exe" >nul || (echo BLAD: przywrocenie hub.exe & exit /b 8)
  echo Przywrocono: hub\hub.exe
)
if exist "%KOPIA%\plugins" (
  robocopy "%KOPIA%\plugins" plugins *.exe /S /NJH /NJS /NDL /NP >nul
  if errorlevel 8 (echo BLAD: przywrocenie plikow .exe pluginow & exit /b 9)
  echo Przywrocono: pliki .exe pluginow
)
echo GOTOWE: przywrocono wersje %TAG%. Uruchom HUB i moduly jak przed wdrozeniem.
endlocal
