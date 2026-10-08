@echo off
rem Zatrzymuje HUB, timer-plugin i modul uruchomione przez uruchom-probe.bat (po portach 8080/8081, nazwie procesu i oknach cmd).
echo Zatrzymuje procesy proby...
for %%P in (8081 8080) do (
  for /f "tokens=5" %%I in ('netstat -ano ^| findstr /R /C:":%%P .*LISTENING"') do taskkill /PID %%I /F /T >nul 2>&1
)
taskkill /IM timer-plugin.exe /F >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='cmd.exe'\" | Where-Object { $_.CommandLine -match 'cmd +/k .*(hub\.exe|nalf\.py|garbarnia\.py)' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
ping -n 3 127.0.0.1 >nul
netstat -ano | findstr /R /C:":8080 .*LISTENING" /C:":8081 .*LISTENING" >nul && (echo UWAGA: nadal jest cos na portach 8080/8081.) || echo Porty 8080 i 8081 sa wolne.
if not defined PROBE_NOPAUSE pause
