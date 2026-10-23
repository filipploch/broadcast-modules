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

func TestCatalogReadsWpBlock(t *testing.T) {
	root := t.TempDir()
	writeManifest(t, root, "a", `{"format":1,"id":"alfa","button":"ALFA","script":"a.py","port":8081,"wp":{"port":8091}}`)
	writeManifest(t, root, "b", `{"format":1,"id":"beta","button":"BETA","script":"b.py","port":8081,"wp":{"port":8092,"db":"beta-db","template":"szablon_b","title":"Beta"}}`)
	writeManifest(t, root, "c", `{"format":1,"id":"gamma","button":"GAMMA","script":"c.py","port":8081}`)
	cat := scanModuleCatalog(root)
	if len(cat.Warnings) != 0 {
		t.Fatalf("nieoczekiwane ostrzeżenia: %v", cat.Warnings)
	}
	a, _ := cat.Get("alfa")
	if a.Wp == nil || a.Wp.Port != 8091 || a.Wp.EffectiveDB() != "p8091" || a.Wp.EffectiveTemplate() != "_szablon" {
		t.Fatalf("wartości domyślne bloku wp: %+v", a.Wp)
	}
	b, _ := cat.Get("beta")
	if b.Wp == nil || b.Wp.EffectiveDB() != "beta-db" || b.Wp.EffectiveTemplate() != "szablon_b" || b.Wp.Title != "Beta" {
		t.Fatalf("jawne wartości bloku wp: %+v", b.Wp)
	}
	if g, _ := cat.Get("gamma"); g.Wp != nil {
		t.Fatalf("moduł bez bloku wp nie ma mieć WP: %+v", g.Wp)
	}
	if w, ok := b.manifestJSON()["wp"].(map[string]interface{}); !ok || w["port"] != 8092 || w["db"] != "beta-db" {
		t.Fatalf("manifestJSON wp: %v", b.manifestJSON()["wp"])
	}
}

func TestCatalogDropsBadWpBlockButKeepsModule(t *testing.T) {
	root := t.TempDir()
	writeManifest(t, root, "a", `{"format":1,"id":"alfa","button":"A","script":"a.py","port":8081,"wp":{"port":8091}}`)
	writeManifest(t, root, "b", `{"format":1,"id":"beta","button":"B","script":"b.py","port":8081,"wp":{"port":8091}}`)     // ten sam port
	writeManifest(t, root, "c", `{"format":1,"id":"gamma","button":"C","script":"c.py","port":8081,"wp":{"port":8081}}`)    // port modułu
	writeManifest(t, root, "d", `{"format":1,"id":"delta","button":"D","script":"d.py","port":8081,"wp":{"port":8093,"db":"../x"}}`) // zła nazwa
	writeManifest(t, root, "e", `{"format":1,"id":"eps","button":"E","script":"e.py","port":8081,"wp":{"port":8094,"db":"p8091"}}`)   // ta sama baza co alfa
	writeManifest(t, root, "f", `{"format":1,"id":"zeta","button":"F","script":"f.py","port":8081,"wp":{"port":80}}`)       // port zarezerwowany
	cat := scanModuleCatalog(root)
	if len(cat.Modules) != 6 {
		t.Fatalf("błędny blok wp nie może usuwać modułu: %v", cat.IDs())
	}
	wantWp := map[string]bool{"alfa": true}
	for _, m := range cat.Modules {
		if (m.Wp != nil) != wantWp[m.ID] {
			t.Fatalf("moduł %s: wp=%+v, oczekiwano obecności %v", m.ID, m.Wp, wantWp[m.ID])
		}
	}
	if len(cat.Warnings) != 5 {
		t.Fatalf("oczekiwano 5 ostrzeżeń, jest %d: %v", len(cat.Warnings), cat.Warnings)
	}
}

func TestRepoManifestsHaveDistinctWpInstances(t *testing.T) {
	cat := scanModuleCatalog(filepath.Join(repoRoot(), "modules"))
	if len(cat.Warnings) != 0 {
		t.Fatalf("ostrzeżenia katalogu: %v", cat.Warnings)
	}
	want := map[string]int{"nalf": 8091, "garbarnia": 8092}
	for id, port := range want {
		m, ok := cat.Get(id)
		if !ok || m.Wp == nil || m.Wp.Port != port {
			t.Fatalf("moduł %s: oczekiwano bloku wp z portem %d, jest %+v", id, port, m.Wp)
		}
	}
}
