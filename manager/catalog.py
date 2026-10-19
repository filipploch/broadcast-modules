"""Katalog modułów z plików modules/<folder>/module.json: te same zasady co w HUB-ie (hub/module_catalog.go), żeby lista
przycisków w managerze i lista modułów, które HUB umie uruchomić, się nie rozjechały. Manager czyta pliki sam, więc przyciski
są widoczne (na szaro) także wtedy, gdy HUB jeszcze nie odpowiada."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

FORMAT = 1
FIELDS = {"format", "id", "button", "script", "args", "port", "log_name", "order"}
REQUIRED = ("format", "id", "button", "script", "port")


@dataclass
class Module:
    id: str
    button: str
    port: int
    log_name: str
    order: int
    folder: str


@dataclass
class Catalog:
    modules: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def get(self, mid):
        return next((m for m in self.modules if m.id == mid), None)


def scan(modules_dir: Path) -> Catalog:
    cat = Catalog()
    try:
        folders = sorted(p for p in Path(modules_dir).iterdir() if p.is_dir())
    except FileNotFoundError:
        return cat
    except OSError as e:
        cat.warnings.append(f"nie można przejrzeć folderu modułów {modules_dir}: {e}")
        return cat
    found = []
    for folder in folders:
        path = folder / "module.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as e:
            cat.warnings.append(f"{path}: plik uszkodzony ({e}), moduł pominięty")
            continue
        if not isinstance(data, dict):
            cat.warnings.append(f"{path}: plik uszkodzony (to nie obiekt JSON), moduł pominięty")
            continue
        unknown = sorted(set(data) - FIELDS)
        if unknown:
            cat.warnings.append(f"{path}: plik uszkodzony (nieznane pola {', '.join(unknown)}), moduł pominięty")
            continue
        missing = [k for k in REQUIRED if not data.get(k) or (k == "port" and not isinstance(data.get(k), int))]
        if missing:
            cat.warnings.append(f"{path}: brak pól {', '.join(missing)}, moduł pominięty")
            continue
        if data["format"] != FORMAT:
            cat.warnings.append(f"{path}: nieznany format {data['format']} (obsługiwany: {FORMAT}), moduł pominięty")
            continue
        found.append(Module(id=data["id"], button=data["button"], port=data["port"], log_name=data.get("log_name") or data["id"],
                            order=int(data.get("order", 0)), folder=folder.name))
    counts = Counter(m.id for m in found)
    for m in found:
        if counts[m.id] > 1:
            cat.warnings.append(f"{Path(modules_dir) / m.folder}: id \"{m.id}\" występuje w {counts[m.id]} plikach module.json, moduł pominięty")
        else:
            cat.modules.append(m)
    cat.modules.sort(key=lambda m: (m.order, m.id))
    cat.warnings.sort()
    return cat
