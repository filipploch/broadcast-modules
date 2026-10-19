@echo off
rem Zatrzymuje probe E2d2 z atrapa OBS (uruchom-probe-obs.bat): konczy wszystkie procesy uruchomione z folderu wp-local\probe-obs
rem (HUB, timer-plugin, atrapa OBS, falszywy obs-ws-plugin) oraz proces modulu na porcie 8081. Rozpoznaje je po SCIEZCE, nie po nazwie.
rem Nie rusza prawdziwego OBS ani zadnych procesow z innych folderow.
setlocal
set "ROOT=%~dp0"
echo Zatrzymuje procesy proby E2d2...
powershell -NoProfile -Command "$base = '%ROOT%wp-local\probe-obs'; Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($base, 'OrdinalIgnoreCase') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; foreach ($port in 8081) { Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force } }; Get-CimInstance Win32_Process -Filter \"Name='cmd.exe'\" | Where-Object { $_.CommandLine -match 'hub\.exe --config .*probe-obs' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
ping -n 3 127.0.0.1 >nul
netstat -ano | findstr /R /C:":8080 .*LISTENING" /C:":8081 .*LISTENING" /C:":14455 .*LISTENING" >nul && (echo UWAGA: nadal jest cos na portach 8080/8081/14455.) || echo Porty 8080, 8081 i 14455 sa wolne.
if not defined PROBE_NOPAUSE pause
