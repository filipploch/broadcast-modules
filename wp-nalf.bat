@echo off
rem WordPress/SportsPress modulu NALF w oknie (WP-1): praca w WP bez aplikacji do transmisji.
rem Parametry (port, baza, szablon) pochodza z modules\...\module.json (blok "wp"), te same co przy starcie przez HUB.
rem Dziala jedna instancja naraz: dzialajaca instancja drugiego modulu zostaje zamknieta. Zatrzymanie: Ctrl+C lub zamkniecie okna.
setlocal
cd /d "%~dp0"
if not exist "hub\hub.exe" (
  echo BLAD: brak hub\hub.exe. Zbuduj go przez hub\build.bat.
  pause
  exit /b 1
)
hub\hub.exe wp nalf
if errorlevel 1 pause
