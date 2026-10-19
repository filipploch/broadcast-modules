package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

func writeManifest(t *testing.T, root, folder, body string) {
	t.Helper()
	dir := filepath.Join(root, folder)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "module.json"), []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestCatalogReadsValidManifestsInOrder(t *testing.T) {
	root := t.TempDir()
	writeManifest(t, root, "b", `{"format":1,"id":"beta","button":"BETA","script":"b.py","port":1,"order":20}`)
	writeManifest(t, root, "a", `{"format":1,"id":"alfa","button":"ALFA","script":"a.py","port":2,"order":10,"log_name":"alfa_log"}`)
	writeManifest(t, root, "c", `{"format":1,"id":"gamma","button":"GAMMA","script":"c.py","port":3,"order":10}`)
	os.MkdirAll(filepath.Join(root, "bez-pliku"), 0o755) // folder bez module.json to nie moduł i nie ostrzeżenie
	cat := scanModuleCatalog(root)
	if len(cat.Warnings) != 0 {
		t.Fatalf("nieoczekiwane ostrzeżenia: %v", cat.Warnings)
	}
	if got := strings.Join(cat.IDs(), ","); got != "alfa,gamma,beta" {
		t.Fatalf("kolejność: %s (oczekiwano order, potem id)", got)
	}
	if m, _ := cat.Get("alfa"); m.EffectiveLogName() != "alfa_log" {
		t.Fatalf("log_name: %+v", m)
	}
	if m, _ := cat.Get("beta"); m.EffectiveLogName() != "beta" {
		t.Fatalf("log_name domyślnie id: %+v", m)
	}
	if m, ok := cat.ByLogName("alfa_log"); !ok || m.ID != "alfa" {
		t.Fatalf("rozpoznanie po nazwie z rejestracji: %+v %v", m, ok)
	}
}

func TestCatalogSkipsBrokenIncompleteAndDuplicate(t *testing.T) {
	root := t.TempDir()
	writeManifest(t, root, "ok", `{"format":1,"id":"ok","button":"OK","script":"ok.py","port":1}`)
	writeManifest(t, root, "zly", `{ to nie json`)
	writeManifest(t, root, "niepelny", `{"format":1,"id":"np","script":"np.py"}`)
	writeManifest(t, root, "literowka", `{"format":1,"id":"lit","button":"L","script":"l.py","port":1,"prot":2}`)
	writeManifest(t, root, "format", `{"format":2,"id":"f2","button":"F","script":"f.py","port":1}`)
	writeManifest(t, root, "dup1", `{"format":1,"id":"dup","button":"D1","script":"d1.py","port":1}`)
	writeManifest(t, root, "dup2", `{"format":1,"id":"dup","button":"D2","script":"d2.py","port":1}`)
	cat := scanModuleCatalog(root)
	if got := strings.Join(cat.IDs(), ","); got != "ok" {
		t.Fatalf("poprawny jest tylko moduł ok, jest: %s", got)
	}
	all := strings.Join(cat.Warnings, "\n")
	for _, want := range []string{"zly", "brak pól button, port", "literowka", "nieznany format 2", "dup1", "dup2"} {
		if !strings.Contains(all, want) {
			t.Errorf("brak ostrzeżenia %q w:\n%s", want, all)
		}
	}
}

func TestCatalogMissingFolderIsEmptyWithoutError(t *testing.T) {
	cat := scanModuleCatalog(filepath.Join(t.TempDir(), "nie-ma"))
	if len(cat.Modules) != 0 || len(cat.Warnings) != 0 {
		t.Fatalf("brak folderu: %+v", cat)
	}
}

// Pliki module.json w repozytorium: oba moduły, a log_name równa się MODULE_NAME z config.py (nazwa, pod którą moduł rejestruje się
// w HUB-ie; po niej HUB rozpoznaje moduł uruchomiony ręcznie, bo oba mają wspólny MODULE_ID "main-module" do czasu E2g).
func TestRepoManifestsMatchModuleNames(t *testing.T) {
	cat := scanModuleCatalog(filepath.Join("..", "modules"))
	if len(cat.Warnings) != 0 {
		t.Fatalf("ostrzeżenia dla plików z repozytorium: %v", cat.Warnings)
	}
	re := regexp.MustCompile(`(?m)^\s*MODULE_NAME\s*=\s*'([^']+)'`)
	for _, want := range []struct{ id, folder string }{{"nalf", "futsal_nalf"}, {"garbarnia", "garbarnia"}} {
		m, ok := cat.Get(want.id)
		if !ok {
			t.Fatalf("brak modułu %s w plikach module.json", want.id)
		}
		data, err := os.ReadFile(filepath.Join("..", "modules", want.folder, "config.py"))
		if err != nil {
			t.Fatal(err)
		}
		mm := re.FindSubmatch(data)
		if mm == nil || string(mm[1]) != m.EffectiveLogName() {
			t.Fatalf("%s: log_name %q różni się od MODULE_NAME w config.py (%q)", want.id, m.EffectiveLogName(), mm)
		}
		if _, err := os.Stat(filepath.Join("..", filepath.FromSlash(m.Script))); err != nil {
			t.Fatalf("%s: skrypt %s nie istnieje", want.id, m.Script)
		}
		var raw map[string]interface{}
		data, _ = os.ReadFile(filepath.Join(m.Dir, "module.json"))
		if json.Unmarshal(data, &raw) != nil || raw["button"] == "" {
			t.Fatalf("%s: plik nieczytelny", want.id)
		}
	}
}
