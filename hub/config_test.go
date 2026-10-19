package main

import (
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

// Wartości wbudowane w kodzie i hub.example.json muszą być identyczne (E2d1).
func TestDefaultsMatchExampleFile(t *testing.T) {
	data, err := os.ReadFile(filepath.Join("config", "hub.example.json"))
	if err != nil {
		t.Fatal(err)
	}
	// parsujemy do pustej struktury: nic nie może "dojść" z wartości domyślnych
	var fromFile HubConfig
	if err := jsonUnmarshalStrict(data, &fromFile); err != nil {
		t.Fatal(err)
	}
	if def := defaultHubConfig(); !reflect.DeepEqual(fromFile, def) {
		t.Fatalf("hub.example.json różni się od wartości wbudowanych:\nplik:  %+v\nkod:   %+v", fromFile, def)
	}
}

// writeModules zakłada w <root>/modules pliki module.json obu modułów (jak w repozytorium).
func writeModules(t *testing.T, root string) {
	t.Helper()
	for _, m := range []struct{ folder, body string }{
		{"futsal_nalf", `{"format":1,"id":"nalf","button":"FUTSAL NALF","script":"modules/nalf.py","port":8081,"log_name":"futsal_nalf","order":10}`},
		{"garbarnia", `{"format":1,"id":"garbarnia","button":"GARBARNIA","script":"modules/garbarnia.py","port":8081,"log_name":"garbarnia","order":20}`},
	} {
		dir := filepath.Join(root, "modules", m.folder)
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatal(err)
		}
		writeFile(t, filepath.Join(dir, "module.json"), m.body)
	}
}

func withConfigDir(t *testing.T, dir string) {
	old := hubConfigDir
	hubConfigDir = func() string { return dir }
	t.Cleanup(func() { hubConfigDir = old })
}

func TestConfigFromLocalFileAndModuleSource(t *testing.T) {
	dir := t.TempDir()
	withConfigDir(t, dir)
	writeModules(t, dir)
	writeFile(t, filepath.Join(dir, "hub.json"), `{"module":"garbarnia","hub_port":18080}`)
	c, err := loadHubConfig("", "", dir)
	if err != nil {
		t.Fatal(err)
	}
	if c.Module != "garbarnia" || c.ModuleSource != "hub.json" || c.HubPort != 18080 {
		t.Fatalf("%+v", c)
	}
	// wartości pominięte w pliku zostają domyślne
	if c.Obs.WsPort != 4455 || c.ModuleReadyTimeoutS != 60 {
		t.Fatalf("brak wartości domyślnych: %+v", c.HubConfig)
	}
	// argument --module wygrywa
	c, err = loadHubConfig("", "nalf", dir)
	if err != nil || c.Module != "nalf" || c.ModuleSource != "argument --module" {
		t.Fatalf("%+v %v", c, err)
	}
}

func TestConfigFallsBackToExampleThenBuiltin(t *testing.T) {
	dir := t.TempDir()
	withConfigDir(t, dir)
	writeModules(t, dir)
	writeFile(t, filepath.Join(dir, "hub.example.json"), `{"module":"garbarnia"}`)
	c, err := loadHubConfig("", "", dir)
	if err != nil || c.Module != "garbarnia" || !strings.Contains(c.ModuleSource, "hub.example.json") || len(c.Notes) == 0 {
		t.Fatalf("%+v %v", c, err)
	}
	os.Remove(filepath.Join(dir, "hub.example.json"))
	c, err = loadHubConfig("", "", dir)
	if err != nil || c.Module != "nalf" || !strings.Contains(c.ModuleSource, "wbudowane") {
		t.Fatalf("%+v %v", c, err)
	}
}

func TestConfigErrors(t *testing.T) {
	dir := t.TempDir()
	withConfigDir(t, dir)
	writeModules(t, dir)
	writeFile(t, filepath.Join(dir, "hub.json"), `{"module": `)
	if _, err := loadHubConfig("", "", dir); err == nil || !strings.Contains(err.Error(), "uszkodzony") {
		t.Fatalf("uszkodzony plik: %v", err)
	}
	if _, err := loadHubConfig(filepath.Join(dir, "nie-ma.json"), "", dir); err == nil || !strings.Contains(err.Error(), "--config") {
		t.Fatalf("brak pliku z --config: %v", err)
	}
	writeFile(t, filepath.Join(dir, "hub.json"), `{"module":"hokej"}`)
	_, err := loadHubConfig("", "", dir)
	if err == nil || !strings.Contains(err.Error(), "nalf, garbarnia") {
		t.Fatalf("nieznany moduł powinien wypisać dozwolone: %v", err)
	}
	if _, err := loadHubConfig("", "futbol", dir); err == nil {
		t.Fatal("nieznany moduł z argumentu")
	}
	writeFile(t, filepath.Join(dir, "hub.json"), `{"module":"","control_port":8080}`)
	if _, err := loadHubConfig("", "", dir); err == nil || !strings.Contains(err.Error(), "control_port") {
		t.Fatalf("control_port równy hub_port: %v", err)
	}
}

// --module none: HUB bez modułu, nawet gdy konfiguracja wskazuje moduł (manager zleca moduł kanałem sterującym).
func TestModuleNoneArgument(t *testing.T) {
	dir := t.TempDir()
	withConfigDir(t, dir)
	writeModules(t, dir)
	writeFile(t, filepath.Join(dir, "hub.json"), `{"module":"nalf"}`)
	c, err := loadHubConfig("", "none", dir)
	if err != nil {
		t.Fatal(err)
	}
	if c.Module != "" || c.ModuleSource != "argument --module" {
		t.Fatalf("--module none: moduł %q, źródło %q", c.Module, c.ModuleSource)
	}
	if _, ok := c.moduleService(); ok {
		t.Fatal("--module none nie powinien tworzyć usługi modułu")
	}
	if len(c.Catalog.Modules) != 2 {
		t.Fatalf("katalog modułów powinien mieć 2 wpisy: %+v", c.Catalog)
	}
}

// Stary hub.json z listą "modules" (np. w folderze transmisyjnym) wczytuje się, a lista jest pomijana z wpisem w logu.
func TestLegacyModulesListIsIgnoredWithNote(t *testing.T) {
	dir := t.TempDir()
	withConfigDir(t, dir)
	writeModules(t, dir)
	writeFile(t, filepath.Join(dir, "hub.json"), `{"module":"nalf","modules":{"nalf":{"script":"inny.py","port":9999,"log_name":"x"}}}`)
	c, err := loadHubConfig("", "", dir)
	if err != nil {
		t.Fatal(err)
	}
	notes := strings.Join(c.Notes, " | ")
	if !strings.Contains(notes, "pomijana") {
		t.Fatalf("brak wpisu o pominiętej liście modules: %s", notes)
	}
	svc, _ := c.moduleService()
	if !strings.HasSuffix(svc.Args[0], "nalf.py") || svc.ReadyURL != "http://127.0.0.1:8081/" {
		t.Fatalf("moduł powinien pochodzić z module.json, nie z listy w hub.json: %+v", svc)
	}
}

func TestEmptyModuleMeansNoModuleService(t *testing.T) {
	dir := t.TempDir()
	writeFile(t, filepath.Join(dir, "hub.json"), `{"module":""}`)
	c, err := loadHubConfig(filepath.Join(dir, "hub.json"), "", dir)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := c.moduleService(); ok {
		t.Fatal("pusty moduł nie powinien tworzyć usługi")
	}
}

func TestModuleServiceDefinition(t *testing.T) {
	root := t.TempDir()
	c := &LoadedHubConfig{HubConfig: defaultHubConfig(), Root: root}
	c.HubPort = 18080
	svc := c.moduleServiceFor(ModuleManifest{Format: 1, ID: "nalf", Button: "FUTSAL NALF", Script: "modules/nalf.py", Port: 18081, LogName: "futsal_nalf"})
	if svc.ID != "module" || svc.ModuleID != "nalf" {
		t.Errorf("identyfikatory usługi: %s %s", svc.ID, svc.ModuleID)
	}
	env := strings.Join(svc.Env, "|")
	for _, want := range []string{"BM_HUB_MANAGED=1", "BM_HUB_URL=ws://localhost:18080/ws", "BM_MODULE_PORT=18081", "PYTHONUNBUFFERED=1"} {
		if !strings.Contains(env, want) {
			t.Errorf("brak %s w %s", want, env)
		}
	}
	if svc.ReadyURL != "http://127.0.0.1:18081/" {
		t.Errorf("ready_url: %s", svc.ReadyURL)
	}
	if svc.ExecutablePath != filepath.Join(root, "modules", ".venv", "Scripts", "python.exe") || svc.WorkingDir != filepath.Join(root, "modules") {
		t.Errorf("ścieżki: %s %s", svc.ExecutablePath, svc.WorkingDir)
	}
	if len(svc.Args) != 1 || svc.Args[0] != filepath.Join(root, "modules", "nalf.py") {
		t.Errorf("argumenty: %v", svc.Args)
	}
	// nazwy plików zgodne z tym, co zapisuje moduł (modul-<nazwa wewnętrzna>.log)
	if svc.OutputFile != "modul-futsal_nalf.wyjscie.log" || svc.FollowFiles[0] != "modul-futsal_nalf.log" {
		t.Errorf("pliki: %s %v", svc.OutputFile, svc.FollowFiles)
	}
}
