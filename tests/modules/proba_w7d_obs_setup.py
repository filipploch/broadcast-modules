"""W7d, krok 5: przygotowanie próby minimum z PRAWDZIWYM OBS (OBS uruchamia i ustawia właściciel; ta próba niczego w nim nie zmienia).

    python tests/modules/proba_w7d_obs_setup.py <futsal_nalf|garbarnia> [--konfiguracja]

--konfiguracja: tylko zapisuje pliki konfiguracyjne i skrypty .bat (bez budowania i bez uruchamiania czegokolwiek).
Bez flagi: dodatkowo buduje hub.exe, timer-plugin.exe i obs-ws-plugin.exe do wp-local/probe-w7d-obs/ i kopiuje nakładki.

Wszystko trafia do wp-local/probe-w7d-obs/ (poza gitem); domyślna konfiguracja HUB-a (hub/config), pliki module.json w repozytorium,
pliki nakładek w hub/overlays i folder transmisyjny nie są zmieniane. Różnice względem zwykłej konfiguracji:
  - HUB nie zarządza procesem OBS (obs.enabled = false) i nie przełącza profilu ani zbioru scen (manifest modułu próby nie ma obs_profile,
    obs_scene_collection ani bloku wp, więc nie startuje też WP);
  - są tylko dwa pluginy: timer-plugin i obs-ws-plugin (bez recordera, replay, kontrolera i kamer);
  - obs-ws-plugin działa w trybie ograniczonym (allowed_requests): do OBS trafiają tylko odczyty i 'odśwież źródło przeglądarki'
    (PressInputPropertiesButton); StartStream, StartRecord, zmiana sceny, włączanie źródeł i filtrów, zmiana ustawień wejść i przełączanie
    profilu są odrzucane przez plugin z błędem w jego logu;
  - moduł działa na KOPII bazy roboczej (instance/database-proba.db), uruchamiany przez tests/modules/dry_run_module.py (bez kopiowania plików do hub/overlays)."""
import json
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
ARGS = [a for a in sys.argv[1:] if not a.startswith('--')]
MODULE = ARGS[0] if ARGS else 'futsal_nalf'
ONLY_CONFIG = '--konfiguracja' in sys.argv
BASE = REPO / 'wp-local' / 'probe-w7d-obs'
HUB_PORT, MODULE_PORT, CONTROL_PORT = 8080, 8081, 18099
# Żądania do OBS dozwolone w próbie: odczyty i odświeżenie źródła przeglądarki (to samo robi "Odśwież nakładkę w OBS")
DOZWOLONE_ZADANIA = ['GetVersion', 'GetStreamStatus', 'GetRecordStatus', 'GetSceneList', 'GetSceneItemList', 'GetSceneItemEnabled', 'PressInputPropertiesButton']
FOLDER_NAKLADEK = {'futsal_nalf': 'futsal-nalf', 'garbarnia': 'garbarnia'}


def zapisz_konfiguracje():
    manifest_src = json.loads((REPO / 'modules' / MODULE / 'module.json').read_text(encoding='utf-8-sig'))
    mid = manifest_src['id']
    (BASE / 'hub' / 'config').mkdir(parents=True, exist_ok=True)
    (BASE / 'timer-plugin').mkdir(exist_ok=True)
    (BASE / 'obs-ws-plugin').mkdir(exist_ok=True)
    (BASE / 'logs').mkdir(exist_ok=True)
    # manifest modułu próby: bez obs_profile, obs_scene_collection i bloku wp
    manifest = {k: v for k, v in manifest_src.items() if k not in ('obs_profile', 'obs_scene_collection', 'wp')}
    manifest.update(script=str(REPO / 'tests' / 'modules' / 'dry_run_module.py'), args=[MODULE], port=MODULE_PORT, log_name=MODULE)
    (BASE / 'modules' / mid).mkdir(parents=True, exist_ok=True)
    (BASE / 'modules' / mid / 'module.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    common = {'type': 'local', 'args': [], 'auto_start': True, 'restart_on_crash': True, 'max_restarts': 10, 'restart_delay_ms': 3000,
              'startup_delay_ms': 1000, 'health_check_interval': 10, 'is_critical': False}
    plugins = {
        'timer-plugin': {**common, 'id': 'timer-plugin', 'name': 'Timer Plugin', 'executable_path': str(BASE / 'timer-plugin.exe'),
                         'working_dir': str(BASE / 'timer-plugin'), 'env': ['PLUGIN_ID=timer-plugin']},
        'obs-ws-plugin': {**common, 'id': 'obs-ws-plugin', 'name': 'OBS WebSocket Plugin (tryb ograniczony, próba W7d)',
                          'executable_path': str(BASE / 'obs-ws-plugin.exe'), 'working_dir': str(BASE / 'obs-ws-plugin'), 'env': ['PLUGIN_ID=obs-ws-plugin']},
    }
    (BASE / 'hub' / 'config' / 'plugins.json').write_text(json.dumps(plugins, indent=2, ensure_ascii=False), encoding='utf-8')
    (BASE / 'hub' / 'config' / 'overlays.json').write_text('{}', encoding='utf-8')
    hub_cfg = {
        'hub_port': HUB_PORT, 'module': mid, 'modules_dir': str(BASE / 'modules'), 'control_port': CONTROL_PORT,
        'python_path': str(REPO / 'modules' / '.venv' / 'Scripts' / 'python.exe'), 'module_dir': str(REPO / 'modules' / MODULE),
        'module_ready_timeout_s': 90, 'module_stop_grace_s': 10,
        'obs': {'enabled': False, 'path': '', 'ws_port': 0, 'process_name': ''},                 # HUB nie zarządza OBS
        'wol': {'enabled': False, 'mac': '', 'broadcast_addr': '255.255.255.255:9'},
        'plugins_config': str(BASE / 'hub' / 'config' / 'plugins.json'), 'state_file': str(BASE / 'uslugi.json'),
    }
    (BASE / 'hub.json').write_text(json.dumps(hub_cfg, indent=2, ensure_ascii=False), encoding='utf-8')
    shutil.copy(REPO / 'plugins' / 'timer-plugin' / 'config.json', BASE / 'timer-plugin' / 'config.json')
    obs_cfg = json.loads((REPO / 'plugins' / 'obs-ws-plugin' / 'config.json').read_text(encoding='utf-8-sig'))
    obs_cfg['allowed_requests'] = DOZWOLONE_ZADANIA
    (BASE / 'obs-ws-plugin' / 'config.json').write_text(json.dumps(obs_cfg, indent=2, ensure_ascii=False), encoding='utf-8')
    (BASE / 'uruchom.bat').write_text(BAT_URUCHOM, encoding='ascii', newline='\r\n')
    (BASE / 'zatrzymaj.bat').write_text(BAT_ZATRZYMAJ, encoding='ascii', newline='\r\n')


def zbuduj():
    for name, cwd, target in (('hub.exe', REPO / 'hub', '.'), ('timer-plugin.exe', REPO / 'plugins' / 'timer-plugin', './cmd/timer-plugin'),
                              ('obs-ws-plugin.exe', REPO / 'plugins' / 'obs-ws-plugin', '.')):
        r = subprocess.run(['go', 'build', '-o', str(BASE / name), target], cwd=cwd, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f'Budowanie {name} nie powiodlo sie:\n{r.stderr}')
    # HUB serwuje nakladki z ./overlays wzgledem katalogu roboczego (BASE); specific.js/css modulu kopiujemy tu, nie do hub/overlays w repozytorium
    shutil.copytree(REPO / 'hub' / 'overlays', BASE / 'overlays', dirs_exist_ok=True)
    folder = FOLDER_NAKLADEK[MODULE]
    for rodzaj in ('js', 'css'):
        zrodlo = REPO / 'modules' / MODULE / 'static' / f'specific.{rodzaj}'
        if zrodlo.is_file():
            (BASE / 'overlays' / folder / rodzaj).mkdir(parents=True, exist_ok=True)
            shutil.copy(zrodlo, BASE / 'overlays' / folder / rodzaj / zrodlo.name)


BAT_URUCHOM = r'''@echo off
rem Proba minimum W7d z PRAWDZIWYM OBS (modul na KOPII bazy roboczej). Uruchom: uruchom.bat futsal_nalf   albo   uruchom.bat garbarnia
rem OBS ma byc juz uruchomiony i ustawiony recznie na profil i zbior scen modulu (HUB niczego w OBS nie przelacza).
rem Wersja transmisyjna musi byc wylaczona (porty 8080 i 8081 wolne). Zatrzymanie: zatrzymaj.bat
setlocal
set "BASE=%~dp0"
set "BASE=%BASE:~0,-1%"
for %%I in ("%BASE%\..\..") do set "ROOT=%%~fI"
set "MODULE=%~1"
if "%MODULE%"=="" set "MODULE=futsal_nalf"
if /i "%MODULE%"=="nalf" set "MODULE=futsal_nalf"
set "PY=%ROOT%\modules\.venv\Scripts\python.exe"
echo === Proba W7d z prawdziwym OBS: modul %MODULE% ===
echo [1/5] Sprawdzam porty 8080, 8081, 18099 i procesy...
for %%P in (8080 8081 18099) do (
  netstat -ano | findstr /R /C:":%%P .*LISTENING" >nul && (echo BLAD: port %%P jest zajety. Zamknij wersje transmisyjna albo poprzednia probe ^(zatrzymaj.bat^). & goto :fail)
)
tasklist /FI "IMAGENAME eq hub.exe" | findstr /I "hub.exe" >nul && (echo BLAD: dziala hub.exe. Zamknij go i uruchom ponownie. & goto :fail)
tasklist /FI "IMAGENAME eq obs64.exe" | findstr /I "obs64.exe" >nul || echo UWAGA: OBS nie dziala. Uruchom go recznie na profilu i zbiorze scen modulu; plugin polaczy sie sam.
echo [2/5] Buduje hub.exe, timer-plugin.exe i obs-ws-plugin.exe (tryb ograniczony) w %BASE% ...
"%PY%" "%ROOT%\tests\modules\proba_w7d_obs_setup.py" %MODULE% > "%TEMP%\w7d-setup.txt" 2>&1
if errorlevel 1 (type "%TEMP%\w7d-setup.txt" & echo BLAD: przygotowanie nie powiodlo sie. & goto :fail)
echo [3/5] Przygotowuje KOPIE bazy roboczej (database-proba.db) ...
"%PY%" "%ROOT%\tests\modules\prepare_dry_run.py" %MODULE% > "%TEMP%\w7d-prepare.txt" 2>&1
if errorlevel 1 (type "%TEMP%\w7d-prepare.txt" & echo BLAD: przygotowanie bazy nie powiodlo sie. & goto :fail)
findstr /C:"Gotowa baza testowa" "%TEMP%\w7d-prepare.txt"
set "ROOTFWD=%ROOT:\=/%"
set "DATABASE_URL=sqlite:///%ROOTFWD%/modules/%MODULE%/instance/database-proba.db"
set "BM_REQUIRED_PLUGINS=timer-plugin,obs-ws-plugin"
set "BM_LOGS_DIR=%BASE%\logs"
echo [4/5] Uruchamiam HUB w osobnym oknie (uruchomi modul, timer-plugin i obs-ws-plugin) ...
start "Probe HUB W7d" /D "%BASE%" cmd /k .\hub.exe --config "%BASE%\hub.json"
echo [5/5] Czekam na modul (port 8081) ...
set /a tries=0
:wait_loop
netstat -ano | findstr /R /C:":8081 .*LISTENING" >nul && goto :ready
set /a tries+=1
if %tries% GEQ 120 (echo BLAD: modul nie wystartowal w 120 s. Sprawdz okno "Probe HUB W7d". & goto :fail)
ping -n 2 127.0.0.1 >nul
goto :wait_loop
:ready
echo.
echo ================================================================
echo  Gotowe. Panel: http://localhost:8081      HUB: http://localhost:8080
echo  Logi: %BASE%\logs\  (najnowszy folder; w nim obs-ws-plugin.log pokazuje ZABLOKOWANE zadania)
echo  Zatrzymanie: zatrzymaj.bat
echo ================================================================
pause
exit /b 0
:fail
pause
exit /b 1
'''

BAT_ZATRZYMAJ = r'''@echo off
rem Zatrzymuje probe W7d: konczy procesy uruchomione z folderu probe-w7d-obs (HUB, timer-plugin, obs-ws-plugin) oraz proces modulu na porcie 8081.
rem Rozpoznaje je po SCIEZCE, nie po nazwie. NIE rusza OBS ani zadnych procesow z innych folderow.
setlocal
set "BASE=%~dp0"
set "BASE=%BASE:~0,-1%"
echo Zatrzymuje procesy proby W7d...
powershell -NoProfile -Command "$base = '%BASE%'; Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($base, 'OrdinalIgnoreCase') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Get-NetTCPConnection -State Listen -LocalPort 8081 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }; Get-CimInstance Win32_Process -Filter \"Name='cmd.exe'\" | Where-Object { $_.CommandLine -match 'hub\.exe --config .*probe-w7d-obs' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
ping -n 3 127.0.0.1 >nul
netstat -ano | findstr /R /C:":8080 .*LISTENING" /C:":8081 .*LISTENING" >nul && (echo UWAGA: nadal jest cos na portach 8080/8081.) || echo Porty 8080 i 8081 sa wolne.
pause
'''

if __name__ == '__main__':
    BASE.mkdir(parents=True, exist_ok=True)
    zapisz_konfiguracje()
    if not ONLY_CONFIG:
        zbuduj()
    print(BASE)
