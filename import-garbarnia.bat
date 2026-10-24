@echo off
rem Import danych Garbarni z API Superscore do WP/SportsPressa modulu Garbarnia (etap I2). Wymaga dzialajacej instancji WP (wp-garbarnia.bat).
rem   import-garbarnia.bat                -> import sezonu z tools\import_wp\zrodla.json
rem   import-garbarnia.bat --na-sucho     -> tylko raport, bez zapisu do WP
rem Odczyt strony z przerwa 1 s miedzy zapytaniami (terminarz + kadra kazdej druzyny); import jest powtarzalny.
setlocal
cd /d "%~dp0"
netstat -ano | findstr /R /C:":8092 .*LISTENING" >nul
if errorlevel 1 (
  echo BLAD: WP modulu Garbarnia nie dziala na porcie 8092. Uruchom najpierw wp-garbarnia.bat.
  pause
  exit /b 1
)
modules\.venv\Scripts\python.exe tools\import_wp\importuj.py garbarnia %*
if errorlevel 1 pause
