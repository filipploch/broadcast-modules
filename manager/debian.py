"""Debian w managerze: stan według pingu (niezależnie od HUB-a i modułu), wybór okna potwierdzenia wyłączenia, wyłączenie przez SSH.

Stany pingu:
  up          system działa (odpowiedź z TTL)
  down        wyłączony (nazwa nieznana w sieci albo "host docelowy nieosiągalny" zgłoszony przez ten komputer: brak hosta w sieci lokalnej)
  unreachable nieosiągalny / przekroczony limit (brak odpowiedzi w czasie, inne błędy)
  no_host     brak adresu Debiana (pusty DEBIAN_SSH_HOST w .env): to nie znaczy, że Debian jest wyłączony
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

LABELS = {
    "up": "system działa",
    "down": "wyłączony",
    "unreachable": "nieosiągalny / przekroczony limit",
    "no_host": "brak adresu Debiana (DEBIAN_SSH_HOST w .env)",
}

_NOT_FOUND = ("could not find host", "nie może znaleźć hosta", "nie może znaleźć hosta", "nie mozna znalezc hosta")
_HOST_UNREACHABLE = ("destination host unreachable", "host docelowy jest nieosi", "host docelowy nieosi")
_TIMEOUT = ("request timed out", "limit czasu", "general failure")


def classify(returncode: int, output: str) -> str:
    """Wynik polecenia ping (Windows, wersja polska albo angielska) -> stan."""
    text = output.lower()
    if returncode == 0 and "ttl=" in text:
        return "up"
    if any(s in text for s in _NOT_FOUND):
        return "down"
    if any(s in text for s in _HOST_UNREACHABLE):
        return "down"
    return "unreachable"


def _run_ping(host: str):
    try:
        r = subprocess.run(["ping", "-n", "1", "-w", "1000", host], capture_output=True, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)
    raw = r.stdout + r.stderr
    for enc in ("oem", "cp852", "utf-8"):
        try:
            return r.returncode, raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return r.returncode, raw.decode("ascii", "replace")


def ping(host: str, runner=_run_ping) -> str:
    if not host:
        return "no_host"
    rc, out = runner(host)
    return classify(rc, out)


@dataclass
class ConfirmVariant:
    warnings: list = field(default_factory=list)
    confirmations: int = 1   # 1 = zwykłe potwierdzenie, 2 = ostrzeżenie i drugie, osobne potwierdzenie


def confirm_variant(recorder_state: str, session_open, session_known: bool) -> ConfirmVariant:
    """recorder_state: recording / not_recording / unknown (także: recorder rozłączony, HUB bez odpowiedzi).
    Zwykłe potwierdzenie wyłącznie przy pozytywnym "nie nagrywa" i znanej, zamkniętej sesji."""
    v = ConfirmVariant()
    if recorder_state == "recording":
        v.warnings.append("Trwa nagrywanie na Debianie — wyłączenie przerwie nagranie")
    elif recorder_state != "not_recording":
        v.warnings.append("Nie można sprawdzić, czy trwa nagrywanie")
    if not session_known:
        v.warnings.append("Nie można sprawdzić, czy sesja transmisji jest otwarta")
    elif session_open:
        v.warnings.append("Sesja transmisji jest otwarta")
    if v.warnings:
        v.confirmations = 2
    return v


def shutdown(host: str, user: str, runner=None):
    """Wyłącza Debiana przez SSH (jak dotąd). Zwraca (ok, komunikat)."""
    if not host or not user:
        return False, "Brak DEBIAN_SSH_HOST / DEBIAN_SSH_USER w .env"
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5", f"{user}@{host}", "sudo shutdown -h now"]
    try:
        r = (runner or (lambda c: subprocess.run(c, capture_output=True, text=True, timeout=15)))(cmd)
    except FileNotFoundError:
        return False, "Nie znaleziono 'ssh'. Zainstaluj OpenSSH."
    except subprocess.TimeoutExpired:
        return False, "SSH: brak odpowiedzi w 15 s"
    if r.returncode == 0:
        return True, "Debian wyłącza się"
    return False, f"SSH: kod {r.returncode} {(r.stdout or '') + (r.stderr or '')}".strip()
