"""Przygotowanie proby recznej E2d2 z ATRAPA OBS (uruchom-probe-obs.bat): buduje HUB, timer-plugin, atrape OBS i falszywy obs-ws-plugin
do wp-local/probe-obs/ i zapisuje konfiguracje (hub.json, plugins.json) z portami 8080 (HUB), 8081 (modul) i 14455 (port "obs-websocket"
atrapy; inny niz 4455, wiec prawdziwy OBS nie koliduje i nie jest ruszany).

    python tests/modules/probe_obs_setup.py futsal_nalf|garbarnia

Wypisuje sciezki potrzebne skryptowi .bat. Nie dotyka folderu transmisyjnego ani prawdziwego OBS."""
import json, pathlib, shutil, subprocess, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
MODULE = sys.argv[1] if len(sys.argv) > 1 else "futsal_nalf"
SCRIPT = {"futsal_nalf": "nalf.py", "garbarnia": "garbarnia.py"}[MODULE]
BASE = REPO / "wp-local" / "probe-obs"
OBS_BIN = BASE / "obs-bin"
OBS_PORT = 14455


def build():
    BASE.mkdir(parents=True, exist_ok=True)
    OBS_BIN.mkdir(exist_ok=True)
    (BASE / "timer-plugin").mkdir(exist_ok=True)
    shutil.copy(REPO / "plugins" / "timer-plugin" / "config.json", BASE / "timer-plugin" / "config.json")
    for name, cwd, target, outdir in (("hub.exe", REPO / "hub", ".", BASE),
                                      ("timer-plugin.exe", REPO / "plugins" / "timer-plugin", "./cmd/timer-plugin", BASE),
                                      ("obs-atrapa.exe", REPO / "hub", "./cmd/obs-atrapa", OBS_BIN),
                                      ("fake-obs-plugin.exe", REPO / "hub", "./cmd/fake-obs-plugin", BASE)):
        r = subprocess.run(["go", "build", "-o", str(outdir / name), target], cwd=cwd, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"Budowanie {name} nie powiodlo sie:\n{r.stderr}")
    (BASE / "hub" / "config").mkdir(parents=True, exist_ok=True)
    common = {"restart_on_crash": True, "max_restarts": 10, "restart_delay_ms": 3000, "startup_delay_ms": 1000, "health_check_interval": 10,
              "is_critical": False, "auto_start": True, "type": "local", "args": []}
    plugins = {
        "timer-plugin": {**common, "id": "timer-plugin", "name": "Timer Plugin", "executable_path": str(BASE / "timer-plugin.exe"),
                         "working_dir": str(BASE / "timer-plugin"), "env": ["PLUGIN_ID=timer-plugin"]},
        "obs-ws-plugin": {**common, "id": "obs-ws-plugin", "name": "Falszywy obs-ws-plugin (proba)", "executable_path": str(BASE / "fake-obs-plugin.exe"),
                          "working_dir": str(BASE), "env": ["PLUGIN_ID=obs-ws-plugin", f"FAKE_OBS_STATE={BASE / 'fake-obs-state.json'}",
                                                            f"FAKE_OBS_LOG={BASE / 'fake-obs.log'}"]},
    }
    (BASE / "hub" / "config" / "plugins.json").write_text(json.dumps(plugins, indent=2), encoding="utf-8")
    (BASE / "hub" / "config" / "overlays.json").write_text("{}", encoding="utf-8")
    (BASE / "fake-obs-state.json").write_text(json.dumps({"stream": False, "record": False, "silent": False, "fail": False}), encoding="utf-8")
    cfg = {
        "hub_port": 8080, "module": "probe",
        "modules": {"probe": {"script": str(REPO / "modules" / SCRIPT), "port": 8081, "log_name": MODULE}},
        "python_path": str(REPO / "modules" / ".venv" / "Scripts" / "python.exe"), "module_dir": str(REPO / "modules"),
        "obs": {"enabled": True, "path": str(OBS_BIN / "obs-atrapa.exe"), "ws_port": OBS_PORT, "process_name": "obs-atrapa.exe", "ready_timeout_s": 20},
        "wol": {"enabled": False, "mac": "", "broadcast_addr": "255.255.255.255:9"},
        "plugins_config": str(BASE / "hub" / "config" / "plugins.json"),
        "state_file": str(BASE / "uslugi.json"),
    }
    (BASE / "hub.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")


if __name__ == "__main__":
    build()
    print(BASE)
