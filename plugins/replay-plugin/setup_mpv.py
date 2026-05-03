#!/usr/bin/env python3
"""
setup_mpv.py — Pobiera portable mpv dla Windows i konfiguruje środowisko.

Uruchom raz przed pierwszym użyciem replay-plugin:
    python setup_mpv.py

Wymaga: pip install requests
"""

import os
import sys
import zipfile
import shutil
import json
from pathlib import Path

try:
    import requests
except ImportError:
    print("Instaluję requests...")
    os.system(f"{sys.executable} -m pip install requests")
    import requests

PLUGIN_DIR = Path(__file__).parent
MPV_EXE    = PLUGIN_DIR / 'mpv.exe'
CONFIG_FILE = PLUGIN_DIR / 'config.json'

# Najnowsza wersja portable mpv dla Windows x86_64
# Sprawdź aktualny link na https://mpv.io/installation/ → Windows → Shinchiro builds
MPV_RELEASE_URL = 'https://github.com/shinchiro/mpv-winbuild-cmake/releases/latest'
MPV_DOWNLOAD_PATTERN = 'mpv-x86_64-*.zip'


def get_latest_mpv_url() -> str:
    """Pobiera URL najnowszego portable mpv z GitHub releases."""
    import re
    print("Szukam najnowszej wersji mpv...")
    api_url = 'https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest'
    r = requests.get(api_url, timeout=15)
    r.raise_for_status()
    data = r.json()
    assets = data.get('assets', [])
    for asset in assets:
        name = asset['name']
        # Szukamy mpv-x86_64-YYYYMMDD-git-HASH.zip (bez -vulkan)
        if re.match(r'mpv-x86_64-\d{8}-git-[a-f0-9]+\.zip', name):
            print(f"Znaleziono: {name}")
            return asset['browser_download_url'], name
    raise RuntimeError("Nie znaleziono odpowiedniego pakietu mpv")


def download_mpv():
    """Pobiera i rozpakowuje mpv.exe."""
    if MPV_EXE.exists():
        print(f"mpv.exe już istnieje: {MPV_EXE}")
        return

    try:
        url, filename = get_latest_mpv_url()
    except Exception as e:
        print(f"Błąd pobierania info o wersji: {e}")
        print("Pobierz ręcznie mpv.exe z https://mpv.io/installation/")
        print(f"i umieść w: {PLUGIN_DIR}")
        return

    zip_path = PLUGIN_DIR / filename
    print(f"Pobieranie {filename}...")
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    total = int(r.headers.get('content-length', 0))
    downloaded = 0
    with open(zip_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded * 100 // total
                print(f"\r  {pct}%", end='', flush=True)
    print()

    print("Rozpakowuję...")
    with zipfile.ZipFile(zip_path, 'r') as z:
        # mpv.exe jest bezpośrednio w archiwum
        for member in z.namelist():
            if member == 'mpv.exe' or member.endswith('/mpv.exe'):
                z.extract(member, PLUGIN_DIR)
                extracted = PLUGIN_DIR / member
                if extracted != MPV_EXE:
                    shutil.move(str(extracted), str(MPV_EXE))
                break
    zip_path.unlink()
    print(f"mpv.exe zainstalowany: {MPV_EXE}")


def create_config():
    """Tworzy domyślny config.json jeśli nie istnieje."""
    if CONFIG_FILE.exists():
        print(f"config.json już istnieje: {CONFIG_FILE}")
        return

    config = {
        "hub_url":       "ws://localhost:8080/ws",
        "mpv_path":      str(MPV_EXE),
        "mpv_pipe":      "\\\\.\\pipe\\mpvsocket",
        "window_geometry": "1920x1080+0+0",
        "default_speed": 0.9,
        "comment": {
            "hub_url": "Adres WebSocket huba",
            "window_geometry": "Rozmiar i pozycja okna mpv: SZEROKOŚĆxWYSOKOŚĆ+X+Y",
            "default_speed": "Domyślna prędkość odtwarzania (0.5 = zwolniony, 1.0 = normalny)"
        }
    }
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    print(f"Utworzono config.json: {CONFIG_FILE}")


def install_dependencies():
    """Instaluje wymagane pakiety Python."""
    packages = ['websocket-client']
    for pkg in packages:
        print(f"Instaluję {pkg}...")
        os.system(f"{sys.executable} -m pip install {pkg} -q")


def create_launcher():
    """Tworzy plik .bat do uruchamiania pluginu."""
    bat_path = PLUGIN_DIR / 'start_replay_plugin.bat'
    bat_content = f"""@echo off
cd /d "{PLUGIN_DIR}"
echo Uruchamianie Replay Plugin...
python replay_plugin.py
pause
"""
    bat_path.write_text(bat_content, encoding='utf-8')
    print(f"Launcher: {bat_path}")


if __name__ == '__main__':
    print("=== Setup Replay Plugin ===\n")

    print("1. Instalacja zależności Python...")
    install_dependencies()

    print("\n2. Pobieranie mpv...")
    download_mpv()

    print("\n3. Tworzenie konfiguracji...")
    create_config()

    print("\n4. Tworzenie launchera...")
    create_launcher()

    print("\n=== Gotowe! ===")
    print(f"Uruchom plugin: start_replay_plugin.bat")
    print(f"lub:            python replay_plugin.py")
    print(f"\nKonfiguracja:   {CONFIG_FILE}")
    print("Dostosuj window_geometry do rozdzielczości swojego ekranu.")
