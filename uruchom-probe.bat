@echo off
rem Proba reczna: buduje HUB i timer-plugin z biezacej galezi, przygotowuje baze testowa, uruchamia HUB i modul w osobnych oknach.
rem   uruchom-probe.bat              -> futsal (modul futsal_nalf, plik nalf.py)
rem   uruchom-probe.bat garbarnia    -> garbarnia (modul garbarnia, plik garbarnia.py)
rem Wersja transmisyjna musi byc wylaczona (porty 8080 i 8081 wolne). Zatrzymanie: zatrzymaj-probe.bat albo zamknij oba okna (Ctrl+C).
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

set "MODULE=futsal_nalf"
set "SCRIPT=nalf.py"
if /i "%~1"=="garbarnia" (
  set "MODULE=garbarnia"
  set "SCRIPT=garbarnia.py"
)
if /i "%~2"=="garbarnia" (
  set "MODULE=garbarnia"
  set "SCRIPT=garbarnia.py"
)
set "PY=%ROOT%modules\.venv\Scripts\python.exe"

echo === Proba reczna: modul %MODULE% ===

echo [1/6] Sprawdzam porty 8080 i 8081...
netstat -ano | findstr /R /C:":8080 .*LISTENING" >nul && (echo BLAD: port 8080 jest zajety ^(wersja transmisyjna dziala?^). Zamknij ja i uruchom ponownie. & goto :fail)
netstat -ano | findstr /R /C:":8081 .*LISTENING" >nul && (echo BLAD: port 8081 jest zajety ^(wersja transmisyjna dziala?^). Zamknij ja i uruchom ponownie. & goto :fail)
tasklist /FI "IMAGENAME eq hub.exe" | findstr /I "hub.exe" >nul && (echo BLAD: dziala hub.exe. Zamknij go i uruchom ponownie. & goto :fail)
tasklist /FI "IMAGENAME eq timer-plugin.exe" | findstr /I "timer-plugin.exe" >nul && (echo BLAD: dziala timer-plugin.exe. Zamknij go i uruchom ponownie. & goto :fail)
echo       porty wolne.

echo [2/6] Buduje hub.exe...
pushd hub
go build -o hub.exe .
if errorlevel 1 (popd & echo BLAD: budowanie hub.exe nie powiodlo sie. & goto :fail)
popd

echo [3/6] Buduje timer-plugin.exe...
pushd plugins\timer-plugin
go build -o timer-plugin.exe ./cmd/timer-plugin
if errorlevel 1 (popd & echo BLAD: budowanie timer-plugin.exe nie powiodlo sie. & goto :fail)
popd
rem Stan zegarow z poprzedniej proby nie moze wrocic do nowej (plik stanu wazny 12 h)
if exist "plugins\timer-plugin\state" (
  echo       usuwam stary stan zegarow z poprzedniej proby ^(plugins\timer-plugin\state^)
  rmdir /s /q "plugins\timer-plugin\state"
)

echo [4/6] Przygotowuje baze testowa ^(kopia lokalnej bazy + migracja^)...
"%PY%" tests\modules\prepare_dry_run.py %MODULE% > "%TEMP%\probe-prepare.txt" 2>&1
if errorlevel 1 (type "%TEMP%\probe-prepare.txt" & echo BLAD: przygotowanie bazy nie powiodlo sie. & goto :fail)
findstr /C:"Gotowa baza testowa" "%TEMP%\probe-prepare.txt"

set "ROOTFWD=%ROOT:\=/%"
set "DATABASE_URL=sqlite:///%ROOTFWD%modules/%MODULE%/instance/database-proba.db"

echo [5/6] Uruchamiam HUB w osobnym oknie...
start "Probe HUB" /D "%ROOT%hub" cmd /k .\hub.exe
call :wait_port 8080 HUB
if errorlevel 1 goto :fail

rem Modul pisze logi do tego samego folderu co HUB (najnowszy logs\logs-*), zeby caly przebieg byl w jednym miejscu
set "BM_LOG_RUN_DIR="
for /f "delims=" %%D in ('dir /b /ad /o-n "%ROOT%logs\logs-*" 2^>nul') do (
  if not defined BM_LOG_RUN_DIR set "BM_LOG_RUN_DIR=%ROOT%logs\%%D"
)

echo [6/6] Uruchamiam modul %MODULE% na bazie testowej w osobnym oknie...
start "Probe Modul %MODULE%" /D "%ROOT%modules" cmd /k ""%PY%" %SCRIPT%"
call :wait_port 8081 modul
if errorlevel 1 goto :fail

echo.
echo ================================================================
echo  Gotowe. Panel:  http://localhost:8081
echo  Logi:           %BM_LOG_RUN_DIR%
echo  Baza testowa:   modules\%MODULE%\instance\database-proba.db
echo  Zatrzymanie:    zatrzymaj-probe.bat albo zamknij oba okna ^(Ctrl+C^)
echo ================================================================
if not defined PROBE_NOPAUSE pause
exit /b 0

:wait_port
rem %1 = port, %2 = nazwa; czeka do 90 s
set /a tries=0
:wait_loop
netstat -ano | findstr /R /C:":%~1 .*LISTENING" >nul && exit /b 0
set /a tries+=1
if %tries% GEQ 90 (echo BLAD: %~2 nie wystartowal w 90 s ^(port %~1^). Sprawdz okno "Probe". & exit /b 1)
ping -n 2 127.0.0.1 >nul
goto :wait_loop

:fail
if not defined PROBE_NOPAUSE pause
exit /b 1
