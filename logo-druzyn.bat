@echo off
rem Loga i nazwy 14-znakowe druzyn do WP (etap I4): mapa z kopii starej bazy modulu (kopia z I0). Wymaga dzialajacej instancji WP modulu.
rem   logo-druzyn.bat nalf --kopia wp-local\kopie\przed-importem-2026-10-23              (zapis do WP)
rem   logo-druzyn.bat garbarnia --kopia wp-local\kopie\przed-importem-2026-10-23 --na-sucho   (tylko raport)
rem Pliki logo zostaja w modules\static\images\logos\<modul>\ (poza gitem); do WP trafia tylko sciezka wzgledna (bm_logo) i nazwa 14-znakowa (bm_name14).
setlocal
cd /d "%~dp0"
modules\.venv\Scripts\python.exe tools\import_wp\logo.py %*
if errorlevel 1 pause
