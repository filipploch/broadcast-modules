@echo off
rem Odswiez wyniki: stan i wynik meczow biezacych rozgrywek modulu ze zrodla (NALF: wyniki rozegranych meczow; Garbarnia: takze mecz w toku z Superscore).
rem   odswiez-wyniki.bat                 -> modul rozpoznany po dzialajacym panelu (8081), liga i sezon z biezacego wyboru rozgrywek modulu
rem   odswiez-wyniki.bat nalf|garbarnia -> gdy modulu nie da sie rozpoznac
rem   odswiez-wyniki.bat --na-sucho     -> tylko podsumowanie, bez zapisu do WP
rem Bezpieczne w trakcie transmisji: nie rusza skladow ani statystyk, pomija mecz transmitowany (flaga "decyduje uzytkownik") i mecze zablokowane.
rem Wymaga dzialajacej instancji WP modulu. Drugi dwuklik w trakcie odswiezania dostaje komunikat zamiast drugiego odswiezania.
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
modules\.venv\Scripts\python.exe tools\import_wp\odswiez.py %*
echo.
pause
