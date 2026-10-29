@echo off
rem Numery koszulek ze starej bazy do WP (krok A): pole "number" zawodnika, tylko gdy w WP jest puste; raport oznacza je jako "propozycja ze starej bazy".
rem Wymaga dzialajacej instancji WP modulu (jedna naraz). Zalecany pierwszy przebieg z --na-sucho.
rem   numery-zawodnikow.bat nalf --kopia wp-local\kopie\przed-importem-2026-10-23 --na-sucho
rem   numery-zawodnikow.bat nalf --kopia wp-local\kopie\przed-importem-2026-10-23              (zapis do WP, kopia pliku bazy WP przed zapisem)
rem   numery-zawodnikow.bat nalf --cofnij wp-local
umery-nalf-RRRRMMDD-GGMMSS.json            (usuwa tylko numery zapisane przez narzedzie)
setlocal
cd /d "%~dp0"
modules\.venv\Scripts\python.exe tools\import_wp
umery.py %*
if errorlevel 1 pause
