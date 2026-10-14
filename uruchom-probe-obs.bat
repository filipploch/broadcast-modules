@echo off
rem Proba reczna E2d2 z ATRAPA OBS: HUB sam uruchamia modul, pluginy (timer + falszywy obs-ws-plugin) i atrape OBS (maly proces z oknem
rem "OBS ..." i portem 14455). Prawdziwy OBS i Debian NIE sa ruszane. Wersja transmisyjna musi byc wylaczona (porty 8080 i 8081 wolne).
rem   uruchom-probe-obs.bat              -> futsal
rem   uruchom-probe-obs.bat garbarnia    -> garbarnia
rem   uruchom-probe-obs.bat wznow        -> tylko ponowne uruchomienie HUB-a (po jego zabiciu albo zamknieciu; modul i atrapa OBS moga dzialac dalej)
rem Zatrzymanie: zatrzymaj-probe-obs.bat albo Ctrl+C w oknie HUB-a (zachowanie zalezy od sesji: patrz docs\proba-reczna-E2d.md).
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"
set "MODULE=futsal_nalf"
if /i "%~1"=="garbarnia" set "MODULE=garbarnia"
if /i "%~1"=="wznow" set "WZNOW=1"
if /i "%~2"=="wznow" set "WZNOW=1"
set "PY=%ROOT%modules\.venv\Scripts\python.exe"
set "BASE=%ROOT%wp-local\probe-obs"
if defined WZNOW goto :wznow_env

echo === Proba E2d2 z atrapa OBS: modul %MODULE% ===
echo [1/4] Sprawdzam porty 8080, 8081 i 14455...
for %%P in (8080 8081 14455) do (
  netstat -ano | findstr /R /C:":%%P .*LISTENING" >nul && (echo BLAD: port %%P jest zajety. Zamknij wersje transmisyjna albo poprzednia probe ^(zatrzymaj-probe-obs.bat^). & goto :fail)
)
echo       porty wolne.

echo [2/4] Buduje HUB, timer-plugin, atrape OBS i falszywy obs-ws-plugin, zapisuje konfiguracje...
"%PY%" tests\modules\probe_obs_setup.py %MODULE% > "%TEMP%\probe-obs-setup.txt" 2>&1
if errorlevel 1 (type "%TEMP%\probe-obs-setup.txt" & echo BLAD: przygotowanie nie powiodlo sie. & goto :fail)
if exist "%BASE%\timer-plugin\state" rmdir /s /q "%BASE%\timer-plugin\state"
del /q "%BASE%\uslugi.json" 2>nul

echo [3/4] Przygotowuje baze testowa ^(kopia lokalnej bazy + migracja^)...
"%PY%" tests\modules\prepare_dry_run.py %MODULE% > "%TEMP%\probe-prepare.txt" 2>&1
if errorlevel 1 (type "%TEMP%\probe-prepare.txt" & echo BLAD: przygotowanie bazy nie powiodlo sie. & goto :fail)
findstr /C:"Gotowa baza testowa" "%TEMP%\probe-prepare.txt"

set "ROOTFWD=%ROOT:\=/%"
:wznow_env
set "ROOTFWD=%ROOT:\=/%"
if not defined MODULE set "MODULE=futsal_nalf"
set "DATABASE_URL=sqlite:///%ROOTFWD%modules/%MODULE%/instance/database-proba.db"
set "BM_REQUIRED_PLUGINS=timer-plugin,obs-ws-plugin"
set "BM_LOGS_DIR=%ROOT%logs"
set "OBS_ATRAPA_PORT=14455"
set "OBS_ATRAPA_LOG=%BASE%\obs-atrapa.log"

echo [4/4] Uruchamiam HUB w osobnym oknie ^(on uruchomi modul, pluginy i atrape OBS^)...
start "Probe HUB E2d2" /D "%BASE%" cmd /k .\hub.exe --config "%BASE%\hub.json"
call :wait_port 8081 modul
if errorlevel 1 goto :fail

echo.
echo ================================================================
echo  Gotowe. Panel:        http://localhost:8081
echo  Atrapa OBS:           okno "OBS 30.0 ..." poza ekranem, port 14455
echo  Dziennik atrapy:      %BASE%\obs-atrapa.log
echo  Sterowanie falszywym obs-ws-pluginem ^(stream/nagrywanie trwa^):
echo     %BASE%\fake-obs-state.json  ^("stream": true  itd.^)
echo  Logi HUB-a i modulu:  %ROOT%logs\ ^(najnowszy folder^)
echo  Zatrzymanie:          zatrzymaj-probe-obs.bat
echo ================================================================
if not defined PROBE_NOPAUSE pause
exit /b 0

:wait_port
rem %1 = port, %2 = nazwa; czeka do 120 s
set /a tries=0
:wait_loop
netstat -ano | findstr /R /C:":%~1 .*LISTENING" >nul && exit /b 0
set /a tries+=1
if %tries% GEQ 120 (echo BLAD: %~2 nie wystartowal w 120 s ^(port %~1^). Sprawdz okno "Probe HUB E2d2". & exit /b 1)
ping -n 2 127.0.0.1 >nul
goto :wait_loop

:fail
if not defined PROBE_NOPAUSE pause
exit /b 1
