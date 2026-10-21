"""Model widoku managera: ze stanu HUB-a (odpowiedź /state albo jej brak) i katalogu modułów buduje przyciski i paski.
Bez textual, więc w pełni testowalne. Wyłączność modułów wymusza HUB; tu tylko odbijamy jego stan."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import version

STARTING_GRACE_S = 30  # tyle sekund po uruchomieniu brak odpowiedzi HUB-a to "HUB startuje", nie błąd

# fazy HUB-a (z nadzoru): ok (odpowiada), starting, unreachable, stopped (zatrzymany celowo), gave_up (3 restarty), not_started
GREY, GREEN, RED = "grey", "green", "red"


@dataclass
class Button:
    id: str
    text: str
    color: str
    enabled: bool
    action: str  # "start", "stop" albo "" (nieaktywny)


@dataclass
class Banner:
    level: str  # info / warn / error
    text: str


@dataclass
class View:
    buttons: list = field(default_factory=list)
    banners: list = field(default_factory=list)
    hub_text: str = ""
    stop_hub_enabled: bool = False
    start_hub_enabled: bool = False
    hub_button: Optional[Button] = None  # jeden przycisk HUB-a zmieniający stan (jak przyciski modułów)


def hub_button(phase: str, stopping: bool, start_enabled: bool) -> Button:
    """URUCHOM HUB (zielony) / ZATRZYMAJ HUB (czerwony) / stan przejściowy (szary, nieaktywny)."""
    if phase == "ok":
        if stopping:
            return Button("hub", "ZATRZYMYWANIE HUB…", GREY, False, "")
        return Button("hub", "ZATRZYMAJ HUB", RED, True, "stop_hub")
    if phase == "starting":
        return Button("hub", "URUCHAMIANIE HUB…", GREY, False, "")
    if start_enabled:
        return Button("hub", "URUCHOM HUB", GREEN, True, "start_hub")
    return Button("hub", "URUCHOM HUB", GREY, False, "")


def hub_phase(state_ok: bool, seconds_since_start: Optional[float], supervisor_phase: str = "") -> str:
    if state_ok:
        return "ok"
    if supervisor_phase in ("stopped", "gave_up"):
        return supervisor_phase
    if seconds_since_start is not None and seconds_since_start < STARTING_GRACE_S:
        return "starting"
    return "unreachable"


def build(catalog, state: Optional[dict], phase: str, root=None, git=None, supervising: bool = True) -> View:
    """root=None: bez sprawdzania commitu (tylko protokół). supervising=False: ten manager tylko pokazuje stan (nadzoruje inny)."""
    v = View()
    mods = list(catalog.modules)
    for w in catalog.warnings:
        v.banners.append(Banner("warn", "Moduły: " + w))

    if phase != "ok" or state is None:
        v.hub_text = {"starting": "HUB startuje…", "stopped": "HUB zatrzymany celowo", "gave_up": "HUB nie działa (3 restarty po awarii)",
                      "unreachable": "HUB nie odpowiada", "not_started": "HUB nie działa"}.get(phase, "HUB nie odpowiada")
        level = "info" if phase in ("starting", "stopped") else "error"
        v.banners.insert(0, Banner(level, v.hub_text))
        v.start_hub_enabled = supervising and phase in ("stopped", "gave_up", "not_started", "unreachable")
        if not supervising:
            v.banners.append(Banner("info", "HUB nadzoruje inny otwarty manager: ten tylko pokazuje stan"))
        v.buttons = [Button(m.id, f"URUCHOM {m.button}", GREY, False, "") for m in mods]
        v.hub_button = hub_button(phase, False, v.start_hub_enabled)
        return v

    v.hub_text = "HUB działa"
    v.stop_hub_enabled = not (state.get("hub") or {}).get("stopping", False)
    v.hub_button = hub_button("ok", not v.stop_hub_enabled, False)
    if root is None:
        notices = [n for n in version.check(state, None, git=lambda *a: (None, "")) if n.level == "error"]
    else:
        notices = version.check(state, root, git) if git is not None else version.check(state, root)
    blocked = any(n.level == "error" for n in notices)
    for n in notices:
        v.banners.append(Banner(n.level, n.text))
    session = state.get("session") or {}
    if session.get("open"):
        v.banners.append(Banner("info", f"Sesja transmisji otwarta ({session.get('state')}): zatrzymanie modułu i HUB-a zablokowane"))
    elif not session.get("known"):
        v.banners.append(Banner("info", "Stan sesji transmisji nieznany: zatrzymanie modułu i HUB-a zablokowane do zgłoszenia przez moduł"))

    active = state.get("active")
    act_id = (active or {}).get("id")
    _obs_profile_banners(v, mods, state, act_id)
    last = state.get("last_module") or {}
    if active is None and last.get("status") == "error" and last.get("error"):
        m = next((x for x in mods if x.id == last.get("id")), None)
        v.banners.append(Banner("error", f"Moduł {m.button if m else last.get('id')} nie działa: {last['error']} (szczegóły w zakładce Moduł)"))
    known_ids = {m.id for m in mods}
    prof = state.get("obs_profile") or {}
    switching_id = prof.get("module_id") if prof.get("state") == "applying" else None   # HUB przełącza OBS przed startem modułu
    for m in mods:
        if m.id == switching_id and (active is None or act_id == m.id):
            v.buttons.append(Button(m.id, "PRZEŁĄCZANIE OBS…", GREY, False, ""))
        elif active is None:
            v.buttons.append(Button(m.id, f"URUCHOM {m.button}", GREEN if not blocked else GREY, not blocked, "start" if not blocked else ""))
        elif m.id == act_id:
            v.buttons.append(_active_button(active, m.button))
        else:
            v.buttons.append(Button(m.id, f"URUCHOM {m.button}", GREY, False, ""))
    if active is not None and act_id not in known_ids:
        if active.get("state") == "manual_unknown":
            v.banners.append(Banner("error", f"Działa moduł uruchomiony ręcznie spoza listy ({active.get('name')}): starty zablokowane"))
            v.buttons.append(Button("", f"ZATRZYMAJ {active.get('name')} (ręcznie)", RED, True, "stop"))
        else:  # folder działającego modułu zniknął
            v.buttons.append(_active_button(active, active.get("button") or act_id))
    return v


def obs_requirement_text(profile: str, collection: str) -> str:
    """'profil "NALF", zbiór scen "NALF"' albo "" (moduł bez wymagań)."""
    parts = []
    if profile:
        parts.append(f'profil "{profile}"')
    if collection:
        parts.append(f'zbiór scen "{collection}"')
    return ", ".join(parts)


def _obs_profile_banners(v: "View", mods, state: dict, act_id) -> None:
    """Nazwy profilu i zbioru scen OBS aktywnego modułu oraz ostrzeżenie HUB-a o ich realizacji (protokół 2, E2d3c3)."""
    prof = state.get("obs_profile") or {}
    if act_id:
        m = next((x for x in mods if x.id == act_id), None)
        need = obs_requirement_text(prof.get("profile", ""), prof.get("collection", "")) if prof.get("module_id") == act_id else ""
        if not need and m is not None:
            need = obs_requirement_text(m.obs_profile, m.obs_scene_collection)
        if need:
            v.banners.append(Banner("info", f"{(m.button if m else act_id)} → OBS: {need}"))
    level = {"warning": "warn", "error": "error"}.get(prof.get("state", ""))
    if level and prof.get("message"):
        v.banners.append(Banner(level, f"OBS: {prof['message']}"))
    elif prof.get("state") in ("pending", "applying") and prof.get("message"):
        v.banners.append(Banner("info", f"OBS: {prof['message']}"))


def _active_button(active: dict, label: str) -> Button:
    st = active.get("state")
    mid = active.get("id") or ""
    if st == "starting":
        return Button(mid, f"URUCHAMIANIE {label}…", GREY, False, "")
    if st == "stopping":
        return Button(mid, f"ZATRZYMYWANIE {label}…", GREY, False, "")
    suffix = ""
    if st == "manual":
        suffix = " (ręcznie)"
    if active.get("missing"):
        suffix += " (brak folderu)"
    return Button(mid, f"ZATRZYMAJ {label}{suffix}", RED, True, "stop")
