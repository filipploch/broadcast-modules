package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
)

// Konfiguracja HUB-a (E2d1): hub/config/hub.json (lokalny, poza gitem) z wartościami domyślnymi w hub.example.json (w repozytorium).
// Brak pliku lokalnego: HUB startuje z wartościami z przykładu i zapisuje to w logu. Plik uszkodzony albo wskazany przez
// --config, a nieistniejący: HUB kończy start błędem (nie wraca po cichu do wartości domyślnych).

// ModuleEntry opisuje, jak uruchomić jeden moduł główny.
type ModuleEntry struct {
	Script string   `json:"script"`         // plik startowy Pythona (względem katalogu głównego repozytorium)
	Args   []string `json:"args,omitempty"` // dodatkowe argumenty po skrypcie
	Port   int      `json:"port"`           // port HTTP modułu
	// LogName: nazwa używana przez moduł w nazwach plików logu (modul-<LogName>.log); domyślnie klucz w "modules"
	LogName string `json:"log_name,omitempty"`
}

// ObsConfig: ustawienia OBS (używane od E2d2).
type ObsConfig struct {
	Path        string `json:"path"`
	WsPort      int    `json:"ws_port"`
	ProcessName string `json:"process_name"`
}

// WolConfig: Wake-on-LAN Debiana (używane od E2d3).
type WolConfig struct {
	Enabled       bool   `json:"enabled"`
	Mac           string `json:"mac"`
	BroadcastAddr string `json:"broadcast_addr"`
}

// HubConfig to zawartość hub.json.
type HubConfig struct {
	HubPort             int                    `json:"hub_port"`
	Module              string                 `json:"module"` // "" = HUB nie uruchamia modułu
	Modules             map[string]ModuleEntry `json:"modules"`
	PythonPath          string                 `json:"python_path"`
	ModuleDir           string                 `json:"module_dir"`
	ModuleReadyTimeoutS int                    `json:"module_ready_timeout_s"`
	ModuleStopGraceS    int                    `json:"module_stop_grace_s"`
	// PluginsConfig: plik konfiguracji pluginów (względem katalogu głównego); "" = config/plugins.json względem bieżącego folderu.
	// Próby ręczne wskazują tu plik tylko z pluginami lokalnymi, żeby HUB nie wołał prawdziwych urządzeń (Debian, kamery).
	PluginsConfig string    `json:"plugins_config"`
	Obs           ObsConfig `json:"obs"`
	Wol           WolConfig `json:"wol"`
}

// defaultHubConfig: wartości wbudowane; test pilnuje, żeby były identyczne z hub.example.json.
func defaultHubConfig() HubConfig {
	return HubConfig{
		HubPort: 8080,
		Module:  "nalf",
		Modules: map[string]ModuleEntry{
			"nalf":      {Script: "modules/nalf.py", Port: 8081, LogName: "futsal_nalf"},
			"garbarnia": {Script: "modules/garbarnia.py", Port: 8081, LogName: "garbarnia"},
		},
		PythonPath:          "modules/.venv/Scripts/python.exe",
		ModuleDir:           "modules",
		ModuleReadyTimeoutS: 60,
		ModuleStopGraceS:    10,
		Obs: ObsConfig{
			Path:        `C:\Program Files\obs-studio\bin\64bit\obs64.exe`,
			WsPort:      4455,
			ProcessName: "obs64.exe",
		},
		Wol: WolConfig{Enabled: false, Mac: "", BroadcastAddr: "255.255.255.255:9"},
	}
}

// repoRoot: katalog główny repozytorium liczony od położenia pliku wykonywalnego HUB-a (nie od bieżącego folderu).
func repoRoot() string {
	exeDir := ""
	if exe, err := os.Executable(); err == nil {
		exeDir = filepath.Dir(exe)
	}
	// `go run` buduje plik w folderze tymczasowym: wtedy liczymy od położenia źródeł
	if exeDir == "" || strings.Contains(exeDir, "go-build") {
		if _, file, _, ok := runtime.Caller(0); ok {
			exeDir = filepath.Dir(file)
		}
	}
	return filepath.Dir(exeDir)
}

// defaultConfigDir: hub/config/ liczony od katalogu głównego repozytorium.
func defaultConfigDir() string {
	return filepath.Join(repoRoot(), "hub", "config")
}

// hubConfigDir to folder domyślnej konfiguracji (zmienna, żeby testy mogły go podmienić).
var hubConfigDir = defaultConfigDir

// LoadedHubConfig to wczytana konfiguracja wraz z informacją, skąd pochodzi (do pierwszych wierszy logu).
type LoadedHubConfig struct {
	HubConfig
	Root         string   // katalog, względem którego liczone są ścieżki względne
	ModuleSource string   // "argument --module", "hub.json", "hub.example.json (brak hub.json)", "wartości wbudowane (brak hub.json i hub.example.json)"
	Notes        []string // komunikaty do zapisania w logu po jego założeniu
}

// loadHubConfig wczytuje konfigurację. configPath == "" oznacza hub/config/hub.json (z hub.example.json obok jako zapas).
func loadHubConfig(configPath, moduleArg, root string) (*LoadedHubConfig, error) {
	if root == "" {
		root = repoRoot()
	}
	out := &LoadedHubConfig{Root: root}
	explicit := configPath != ""
	exampleDir := hubConfigDir()
	if explicit {
		exampleDir = filepath.Dir(configPath)
	} else {
		configPath = filepath.Join(exampleDir, "hub.json")
	}

	cfg := defaultHubConfig()
	source := ""
	data, err := os.ReadFile(configPath)
	switch {
	case err == nil:
		if jerr := jsonUnmarshalStrict(data, &cfg); jerr != nil {
			return nil, fmt.Errorf("plik konfiguracji %s jest uszkodzony: %v", configPath, jerr)
		}
		source = filepath.Base(configPath)
		out.Notes = append(out.Notes, fmt.Sprintf("Konfiguracja HUB-a: %s", configPath))
	case os.IsNotExist(err) && explicit:
		return nil, fmt.Errorf("plik konfiguracji %s (z --config) nie istnieje", configPath)
	case os.IsNotExist(err):
		examplePath := filepath.Join(exampleDir, "hub.example.json")
		if edata, eerr := os.ReadFile(examplePath); eerr == nil {
			if jerr := jsonUnmarshalStrict(edata, &cfg); jerr != nil {
				return nil, fmt.Errorf("plik %s jest uszkodzony: %v", examplePath, jerr)
			}
			source = "hub.example.json (brak hub.json)"
			out.Notes = append(out.Notes, fmt.Sprintf("Brak %s: konfiguracja z %s", configPath, examplePath))
		} else {
			source = "wartości wbudowane (brak hub.json i hub.example.json)"
			out.Notes = append(out.Notes, fmt.Sprintf("Brak %s i hub.example.json: wartości wbudowane", configPath))
		}
	default:
		return nil, fmt.Errorf("nie można odczytać %s: %v", configPath, err)
	}

	if moduleArg != "" {
		cfg.Module = moduleArg
		out.ModuleSource = "argument --module"
	} else {
		out.ModuleSource = source
	}
	if cfg.Module != "" {
		if _, ok := cfg.Modules[cfg.Module]; !ok {
			return nil, fmt.Errorf("nieznany moduł %q (źródło: %s); dozwolone: %s",
				cfg.Module, out.ModuleSource, strings.Join(moduleNames(cfg.Modules), ", "))
		}
	}
	if cfg.HubPort <= 0 {
		return nil, fmt.Errorf("hub_port musi być dodatni")
	}
	out.HubConfig = cfg
	return out, nil
}

func moduleNames(m map[string]ModuleEntry) []string {
	names := make([]string, 0, len(m))
	for n := range m {
		names = append(names, n)
	}
	sort.Strings(names)
	return names
}

// abs zamienia ścieżkę względną na bezwzględną względem katalogu głównego repozytorium.
func (c *LoadedHubConfig) abs(p string) string {
	if p == "" || filepath.IsAbs(p) {
		return p
	}
	return filepath.Join(c.Root, filepath.FromSlash(p))
}

// ModuleLabel to nazwa modułu do logu: klucz z konfiguracji i, gdy inna, nazwa używana w plikach logu
// (np. "nalf (futsal_nalf)"), żeby było widać, który moduł naprawdę startuje.
func (c *LoadedHubConfig) ModuleLabel() string {
	e := c.Modules[c.Module]
	if e.LogName != "" && e.LogName != c.Module {
		return fmt.Sprintf("%s (%s)", c.Module, e.LogName)
	}
	return c.Module
}

// moduleService składa usługę modułu głównego z wybranego wpisu "modules". Zwraca false, gdy moduł nie jest wybrany.
func (c *LoadedHubConfig) moduleService() (ServiceConfig, bool) {
	if c.Module == "" {
		return ServiceConfig{}, false
	}
	e := c.Modules[c.Module]
	logName := e.LogName
	if logName == "" {
		logName = c.Module
	}
	return ServiceConfig{
		ID:             "module",
		Name:           "Moduł " + c.Module,
		Type:           "service",
		ExecutablePath: c.abs(c.PythonPath),
		WorkingDir:     c.abs(c.ModuleDir),
		Args:           append([]string{c.abs(e.Script)}, e.Args...),
		Env: []string{
			"BM_HUB_MANAGED=1", // moduł nie pisze na konsolę (tylko do pliku), surowe wyjście idzie do pliku .wyjscie.log
			fmt.Sprintf("BM_HUB_URL=ws://localhost:%d/ws", c.HubPort),
			fmt.Sprintf("BM_MODULE_PORT=%d", e.Port),
			"PYTHONIOENCODING=utf-8",
			"PYTHONUNBUFFERED=1",
		},
		ReadyURL:       fmt.Sprintf("http://127.0.0.1:%d/", e.Port),
		ReadyTimeoutS:  c.ModuleReadyTimeoutS,
		StopGraceS:     c.ModuleStopGraceS,
		RestartOnCrash: true,
		MaxRestarts:    5,
		RestartDelayMs: 3000,
		OutputFile:     "modul-" + logName + ".wyjscie.log",
		FollowFiles:    []string{"modul-" + logName + ".log", "modul-" + logName + ".wyjscie.log"},
		FollowLabel:    "moduł",
	}, true
}

// jsonUnmarshalStrict parsuje JSON, odrzucając nieznane pola (literówka w konfiguracji nie może przejść niezauważona).
func jsonUnmarshalStrict(data []byte, v interface{}) error {
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	return dec.Decode(v)
}
