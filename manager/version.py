"""Zgodność managera z HUB-em. Rozstrzyga wersja protokołu kanału z /state (EXPECTED_PROTOCOL): inna wartość blokuje przyciski
modułów. Commit hub.exe (wpisywany przez hub\\build.bat) tylko ostrzega: pusty = wersja nieznana, "-dirty" = zbudowany z niezapisanymi
zmianami, starszy niż ostatnia zmiana w hub/ (sprawdzane gitem, gdy jest) = "przebuduj"; bez gita: "nie można sprawdzić"."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

EXPECTED_PROTOCOL = 1


@dataclass
class Notice:
    level: str   # "error" (blokuje przyciski modułów) albo "warn"
    text: str


def _git(root: Path, *args):
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=5)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None, ""


def check(state: dict, root: Path, git=_git) -> list:
    out = []
    proto = state.get("protocol")
    if proto != EXPECTED_PROTOCOL:
        out.append(Notice("error", f"HUB niezgodny z managerem (protokół {proto}, oczekiwany {EXPECTED_PROTOCOL}): przebuduj hub.exe przez hub\\build.bat"))
    commit = (state.get("hub") or {}).get("commit", "")
    if not commit:
        out.append(Notice("warn", "Wersja HUB-a nieznana (hub.exe zbudowany bez hub\\build.bat)"))
        return out
    base = commit[:-len("-dirty")] if commit.endswith("-dirty") else commit
    if commit.endswith("-dirty"):
        out.append(Notice("warn", f"hub.exe zbudowany z niezapisanymi zmianami w hub\\ (commit {commit})"))
    rc, last = git(root, "log", "-1", "--format=%H", "--", "hub")
    if rc != 0 or not last:
        out.append(Notice("warn", "Nie można sprawdzić, czy hub.exe jest aktualny (brak gita albo repozytorium)"))
        return out
    rc, _ = git(root, "merge-base", "--is-ancestor", last, base)
    if rc == 1:
        out.append(Notice("warn", f"hub.exe ({base}) jest starszy niż ostatnia zmiana w kodzie HUB-a: przebuduj przez hub\\build.bat"))
    elif rc != 0:
        out.append(Notice("warn", f"Nie można sprawdzić, czy hub.exe jest aktualny (commit {base} nieznany w repozytorium)"))
    return out
