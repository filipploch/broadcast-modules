"""Konfiguracja HUB-a widziana przez manager: ta sama kolejność co w HUB-ie (hub/config.go): plik wskazany jawnie (--config),
hub/config/hub.json, hub/config/hub.example.json, wartości wbudowane. Manager potrzebuje z niej tylko portów, folderu modułów
i miejsca na swoje pliki (blokada nadzoru, znacznik celowego zatrzymania): folder pliku stanu HUB-a (domyślnie run/)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

DEFAULTS = {"hub_port": 8080, "control_port": 8079, "modules_dir": "modules", "state_file": ""}


@dataclass
class HubConfig:
    root: Path
    config_path: Optional[Path]  # plik, z którego wczytano (None = wartości wbudowane)
    explicit: bool               # wskazany jawnie (wtedy przekazywany HUB-owi jako --config)
    source: str
    hub_port: int
    control_port: int
    modules_dir: Path
    run_dir: Path                # folder plików managera (obok pliku stanu HUB-a)
    error: str = ""              # plik uszkodzony: HUB z nim nie wystartuje


def _abs(root: Path, p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else root / path


def load(config_path: Optional[str] = None, root: Path = ROOT) -> HubConfig:
    explicit = bool(config_path)
    candidates = [Path(config_path)] if explicit else [root / "hub" / "config" / "hub.json", root / "hub" / "config" / "hub.example.json"]
    data, used, source, error = {}, None, "wartości wbudowane", ""
    for i, path in enumerate(candidates):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as e:
            error = f"{path.name} uszkodzony ({e}); HUB z tym plikiem nie wystartuje"
            data = {}
        used = path
        source = path.name if i == 0 or explicit else "hub.example.json (brak hub.json)"
        break
    cfg = {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
    state_file = cfg["state_file"]
    run_dir = _abs(root, state_file).parent if state_file else root / "run"
    return HubConfig(root=root, config_path=used, explicit=explicit, source=source, hub_port=int(cfg["hub_port"]),
                     control_port=int(cfg["control_port"]), modules_dir=_abs(root, cfg["modules_dir"]), run_dir=run_dir, error=error)
