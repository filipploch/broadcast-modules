@echo off
rem Raport zgodnosci importu ze strona zrodlowa (etap I3): zrodlo na zywo kontra WP modulu. Niczego nie zapisuje.
rem   porownaj-import.bat nalf                 -> NALF (wymaga wp-nalf.bat)
rem   porownaj-import.bat garbarnia [--kopia wp-local\kopie\przed-importem-RRRR-MM-DD]   -> Garbarnia (wymaga wp-garbarnia.bat)
rem Kod wyjscia 1 = sa rozbieznosci (patrz lista na koncu raportu).
setlocal
cd /d "%~dp0"
modules\.venv\Scripts\python.exe tools\import_wp\porownaj.py %*
if errorlevel 1 pause
