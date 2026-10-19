package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// Port obs-websocket jest dziś zapisany w dwóch miejscach: obs.ws_port w konfiguracji HUB-a (HUB po nim sprawdza, czy OBS odpowiada)
// i obs.port w config.json obs-ws-pluginu (plugin łączy się nim z OBS). Różne wartości dają fałszywy błąd „usługa obs nie odpowiada”,
// choć plugin jest połączony z OBS (zgłoszone w próbie E2d3a, 2026-10-19). HUB przy starcie porównuje oba i ostrzega w logu.

// obsPortMismatch zwraca opis rozbieżności albo "" (zgodne, plik nieczytelny albo bez portu: nic nie zgłaszamy).
func obsPortMismatch(hubPort int, pluginWorkingDir string) string {
	if pluginWorkingDir == "" {
		return ""
	}
	path := filepath.Join(pluginWorkingDir, "config.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	var cfg struct {
		Obs struct {
			Port int `json:"port"`
		} `json:"obs"`
	}
	if json.Unmarshal(data, &cfg) != nil || cfg.Obs.Port == 0 || cfg.Obs.Port == hubPort {
		return ""
	}
	return fmt.Sprintf("port obs-websocket w konfiguracji HUB-a (obs.ws_port = %d) różni się od portu w %s (obs.port = %d): "+
		"HUB sprawdza %d i zgłosi, że OBS nie odpowiada, choć obs-ws-plugin jest z nim połączony. Ustaw obie wartości tak samo",
		hubPort, path, cfg.Obs.Port, hubPort)
}
