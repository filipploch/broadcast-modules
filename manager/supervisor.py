"""Nadzór HUB-a bez okna: ta sama logika co w broadcast_manager.py (manager/hub_process.py), do prób M5-M6.

    python -m manager.supervisor [--config hub.json] [--hub-exe hub.exe] [--run-seconds N] [--interval S]

Wypisuje zdarzenia nadzoru (start, podłączenie, restart, limit, zatrzymanie celowe) i fazę HUB-a; kończy się po --run-seconds
(HUB działa dalej: manager go nie zatrzymuje)."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import config as mconfig
from .hub_process import Supervisor


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--config")
    p.add_argument("--hub-exe")
    p.add_argument("--run-seconds", type=float, default=0)
    p.add_argument("--interval", type=float, default=1.0)
    a = p.parse_args(argv)
    cfg = mconfig.load(a.config)
    hub_exe = Path(a.hub_exe) if a.hub_exe else cfg.root / "hub" / "hub.exe"
    sup = Supervisor(cfg, hub_exe)
    end = time.monotonic() + a.run_seconds if a.run_seconds else None
    last_phase = None
    try:
        while end is None or time.monotonic() < end:
            sup.tick()
            for e in sup.events:
                print(f"{time.strftime('%H:%M:%S')} [{e.kind}] {e.text}", flush=True)
            sup.events.clear()
            if sup.phase != last_phase:
                print(f"{time.strftime('%H:%M:%S')} [faza] {sup.phase} (nadzorca: {'tak' if sup.supervising else 'nie'})", flush=True)
                last_phase = sup.phase
            time.sleep(a.interval)
    finally:
        sup.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
