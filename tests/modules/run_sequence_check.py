"""Proba reczna wedlug instrukcji (docs/proba-na-sucho-E1.md): HUB + modul startowany Z FOLDERU modules\\ na bazie testowej,
potem wywolanie jednej sekwencji przez socket.io (tak jak robi to panel).

    modules\\.venv\\Scripts\\python.exe tests\\modules\\run_sequence_check.py garbarnia [nazwa_sekwencji]

Wymaga wczesniej zbudowanego wp-local/dryrun (uruchom raz tests\\modules\\dry_run_zegary.py) i przygotowanej bazy testowej.
Do logu wp-local/tests-out/sekwencja_<modul>.log zapisuje log modulu.
"""
import os
import pathlib
import socket
import subprocess
import sys
import threading
import time

import socketio as sio_lib

REPO = pathlib.Path(__file__).resolve().parents[2]
MODULE = sys.argv[1] if len(sys.argv) > 1 else "garbarnia"
SEQUENCE = sys.argv[2] if len(sys.argv) > 2 else "halftime_start"
ENTRY = "nalf.py" if MODULE == "futsal_nalf" else "garbarnia.py"
DRY = REPO / "wp-local" / "dryrun"
LOG = REPO / "wp-local" / "tests-out" / f"sekwencja_{MODULE}.log"


def busy(p):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", p)) == 0


def main():
    for p in (8080, 8081):
        if busy(p):
            sys.exit(f"Port {p} zajety")
    db = REPO / "modules" / MODULE / "instance" / "database-proba.db"
    if not db.exists() or not (DRY / "hub.exe").exists():
        sys.exit("Brak bazy testowej albo wp-local/dryrun (patrz opis na gorze pliku)")
    hub = subprocess.Popen([str(DRY / "hub.exe")], cwd=DRY / "hub", stdout=open(DRY / "logs" / "hub.log", "w"), stderr=subprocess.STDOUT)
    mod = None
    try:
        for _ in range(40):
            if busy(8080):
                break
            time.sleep(0.25)
        # dokladnie jak w instrukcji: folder modules\, zmienna DATABASE_URL, plik startowy modulu (BM_REQUIRED_PLUGINS tylko zawęża pluginy startowane przez HUB)
        env = {**os.environ, "DATABASE_URL": "sqlite:///" + db.as_posix(), "BM_REQUIRED_PLUGINS": "timer-plugin", "PYTHONIOENCODING": "utf-8"}
        mod = subprocess.Popen([str(REPO / "modules" / ".venv" / "Scripts" / "python.exe"), ENTRY], cwd=REPO / "modules", env=env,
                               stdout=open(LOG, "w", encoding="utf-8"), stderr=subprocess.STDOUT)
        client = sio_lib.Client()
        got = threading.Event()
        started = {}

        @client.on("sequence_started")
        def _(data):
            started.update(data or {})
            got.set()

        errors = []
        client.on("error", lambda d: errors.append(d))
        for _ in range(120):
            try:
                client.connect("http://127.0.0.1:8081")
                break
            except Exception:
                time.sleep(0.5)
        else:
            sys.exit("Modul nie wystartowal; patrz " + str(LOG))
        time.sleep(3)                                             # managery startuja w tle
        client.emit("trigger_sequence", {"sequence": SEQUENCE, "context": {}})
        ok = got.wait(10)
        time.sleep(4)                                             # kroki sekwencji
        print(f"sekwencja '{SEQUENCE}': sequence_started={'TAK ' + str(started) if ok else 'NIE'}; zdarzenia 'error' z modulu: {errors}")
    finally:
        for pr in (mod, hub):
            if pr:
                pr.terminate()
        subprocess.run(["taskkill", "/F", "/IM", "timer-plugin.exe"], capture_output=True)
    text = LOG.read_text(encoding="utf-8", errors="replace")
    print("FileNotFoundError w logu modulu:", "FileNotFoundError" in text)
    print("fragment logu o sekwencji:")
    for line in text.splitlines():
        if "equence" in line or "sekwenc" in line.lower():
            print("  ", line[:170].encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()
