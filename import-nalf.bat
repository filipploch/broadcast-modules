@echo off
rem Import danych NALF z API nalffutsal.pl do WP/SportsPressa modulu NALF (etap I1). Wymaga dzialajacej instancji WP (wp-nalf.bat).
rem   import-nalf.bat                -> import sezonu z tools\import_wp\zrodla.json
rem   import-nalf.bat --na-sucho     -> tylko raport, bez zapisu do WP
rem   import-nalf.bat --sezon 59     -> inny sezon (59 = Wiosna 2026)
rem Odczyt strony z przerwa 1 s miedzy zapytaniami; import jest powtarzalny (drugie uruchomienie nie dubluje).
setlocal
cd /d "%~dp0"
netstat -ano | findstr /R /C:":8091 .*LISTENING" >nul
if errorlevel 1 (
  echo BLAD: WP modulu NALF nie dziala na porcie 8091. Uruchom najpierw wp-nalf.bat.
  pause
  exit /b 1
)
modules\.venv\Scripts\python.exe tools\import_wp\importuj.py nalf %*
if errorlevel 1 pause
