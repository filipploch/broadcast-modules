package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// Katalog modułów (E2d3c1): każdy moduł opisuje plik module.json we własnym folderze (modules/<folder>/module.json).
// HUB i broadcast_manager.py czytają te same pliki tą samą zasadą, więc lista przycisków w managerze i lista modułów,
// które HUB umie uruchomić, nie rozjadą się. Lista "modules" w hub.json przestała być źródłem (HUB ją pomija z wpisem w logu).
// Po scaleniu modułów (E2g) zostanie jeden folder z jednym plikiem: ani HUB, ani manager nie mają w kodzie nazw modułów.

const moduleManifestFormat = 1

// ModuleManifest to zawartość module.json.
type ModuleManifest struct {
	Format  int      `json:"format"`
	ID      string   `json:"id"`     // nazwa w poleceniach kanału sterującego i w --module
	Button  string   `json:"button"` // tekst przycisku w managerze (URUCHOM <button> / ZATRZYMAJ <button>)
	Script  string   `json:"script"` // plik startowy Pythona, względem katalogu głównego (albo ścieżka bezwzględna)
	Args    []string `json:"args,omitempty"`
	Port    int      `json:"port"`
	LogName string   `json:"log_name,omitempty"` // nazwa w plikach logu i przy rejestracji modułu w HUB-ie (MODULE_NAME); domyślnie id
	Order   int      `json:"order,omitempty"`

	// Profil i zbiór scen OBS tego modułu (E2d3c3): dwa niezależne pola, nazwy dokładnie jak w OBS. Puste = bez wymagania.
	// Pola przejściowe: po E2g/E2h przejdą do profilu rozgrywek.
	ObsProfile         string `json:"obs_profile,omitempty"`
	ObsSceneCollection string `json:"obs_scene_collection,omitempty"`

	// Instancja WordPressa/SportsPressa tego modułu (WP-1): port, baza i szablon w jednym miejscu dla obu sposobów startu
	// (plik .bat przez "hub.exe wp <id>" i uruchamianie przez HUB). Brak bloku = moduł nie ma własnej instancji WP.
	Wp *WpConfig `json:"wp,omitempty"`

	Dir string `json:"-"` // folder, z którego pochodzi plik (do komunikatów)
}

// EffectiveLogName: nazwa używana w plikach logu i przy rejestracji (log_name albo id).
func (m ModuleManifest) EffectiveLogName() string {
	if m.LogName != "" {
		return m.LogName
	}
	return m.ID
}

// ModuleCatalog to wynik przeglądu folderu modułów.
type ModuleCatalog struct {
	Dir      string
	Modules  []ModuleManifest // poprawne, posortowane wg order, potem id
	Warnings []string         // pliki pominięte (uszkodzone, niepełne, powtórzone id)
}

// Get zwraca moduł o danym id.
func (c *ModuleCatalog) Get(id string) (ModuleManifest, bool) {
	if c == nil {
		return ModuleManifest{}, false
	}
	for _, m := range c.Modules {
		if m.ID == id {
			return m, true
		}
	}
	return ModuleManifest{}, false
}

// ByLogName zwraca moduł, który rejestruje się w HUB-ie pod daną nazwą (rozpoznanie modułu uruchomionego ręcznie).
// Dziś oba moduły mają wspólny MODULE_ID (main-module), więc rozróżnia je wyłącznie nazwa; wspólny identyfikator znika po E2g.
func (c *ModuleCatalog) ByLogName(name string) (ModuleManifest, bool) {
	if c == nil || name == "" {
		return ModuleManifest{}, false
	}
	for _, m := range c.Modules {
		if m.EffectiveLogName() == name {
			return m, true
		}
	}
	return ModuleManifest{}, false
}

// IDs: identyfikatory modułów (do komunikatów o błędzie).
func (c *ModuleCatalog) IDs() []string {
	if c == nil {
		return nil
	}
	out := make([]string, 0, len(c.Modules))
	for _, m := range c.Modules {
		out = append(out, m.ID)
	}
	return out
}

// scanModuleCatalog przegląda <dir>/*/module.json. Brak folderu to pusty katalog (bez błędu: HUB bez modułów to poprawny stan).
func scanModuleCatalog(dir string) *ModuleCatalog {
	cat := &ModuleCatalog{Dir: dir}
	entries, err := os.ReadDir(dir)
	if err != nil {
		if !os.IsNotExist(err) {
			cat.Warnings = append(cat.Warnings, fmt.Sprintf("nie można przejrzeć folderu modułów %s: %v", dir, err))
		}
		return cat
	}
	var found []ModuleManifest
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		path := filepath.Join(dir, e.Name(), "module.json")
		data, err := os.ReadFile(path)
		if err != nil {
			if !os.IsNotExist(err) {
				cat.Warnings = append(cat.Warnings, fmt.Sprintf("%s: nie można odczytać (%v)", path, err))
			}
			continue
		}
		var m ModuleManifest
		if err := jsonUnmarshalStrict(data, &m); err != nil {
			cat.Warnings = append(cat.Warnings, fmt.Sprintf("%s: plik uszkodzony (%v), moduł pominięty", path, err))
			continue
		}
		if missing := m.missingFields(); len(missing) > 0 {
			cat.Warnings = append(cat.Warnings, fmt.Sprintf("%s: brak pól %s, moduł pominięty", path, strings.Join(missing, ", ")))
			continue
		}
		if m.Format != moduleManifestFormat {
			cat.Warnings = append(cat.Warnings, fmt.Sprintf("%s: nieznany format %d (obsługiwany: %d), moduł pominięty", path, m.Format, moduleManifestFormat))
			continue
		}
		m.Dir = filepath.Join(dir, e.Name())
		found = append(found, m)
	}
	// Powtórzone id: odrzucamy wszystkie pliki z tym id (nie wiadomo, który jest właściwy)
	count := map[string]int{}
	for _, m := range found {
		count[m.ID]++
	}
	for _, m := range found {
		if count[m.ID] > 1 {
			cat.Warnings = append(cat.Warnings, fmt.Sprintf("%s: id %q występuje w %d plikach module.json, moduł pominięty", m.Dir, m.ID, count[m.ID]))
			continue
		}
		cat.Modules = append(cat.Modules, m)
	}
	sort.SliceStable(cat.Modules, func(i, j int) bool {
		if cat.Modules[i].Order != cat.Modules[j].Order {
			return cat.Modules[i].Order < cat.Modules[j].Order
		}
		return cat.Modules[i].ID < cat.Modules[j].ID
	})
	cat.validateWp()
	sort.Strings(cat.Warnings)
	return cat
}

// validateWp sprawdza bloki "wp": błędny blok jest zerowany z ostrzeżeniem (moduł nadal działa, tylko bez własnego WP).
// Port i nazwa bazy muszą być różne w całym katalogu (działa jedna instancja naraz, ale ta sama baza dla dwóch modułów to pomyłka).
func (c *ModuleCatalog) validateWp() {
	ports := map[int]string{}
	dbs := map[string]string{}
	for i := range c.Modules {
		m := &c.Modules[i]
		if m.Wp == nil {
			continue
		}
		if msg := m.Wp.problem(m.Port); msg != "" {
			c.Warnings = append(c.Warnings, fmt.Sprintf("%s: blok wp: %s, moduł działa bez WP", m.Dir, msg))
			m.Wp = nil
			continue
		}
		if other, dup := ports[m.Wp.Port]; dup {
			c.Warnings = append(c.Warnings, fmt.Sprintf("%s: blok wp: port %d ma już moduł %s, moduł działa bez WP", m.Dir, m.Wp.Port, other))
			m.Wp = nil
			continue
		}
		if other, dup := dbs[m.Wp.EffectiveDB()]; dup {
			c.Warnings = append(c.Warnings, fmt.Sprintf("%s: blok wp: baza %q ma już moduł %s, moduł działa bez WP", m.Dir, m.Wp.EffectiveDB(), other))
			m.Wp = nil
			continue
		}
		ports[m.Wp.Port] = m.ID
		dbs[m.Wp.EffectiveDB()] = m.ID
	}
}

func (m ModuleManifest) missingFields() []string {
	var out []string
	if m.Format == 0 {
		out = append(out, "format")
	}
	if m.ID == "" {
		out = append(out, "id")
	}
	if m.Button == "" {
		out = append(out, "button")
	}
	if m.Script == "" {
		out = append(out, "script")
	}
	if m.Port <= 0 {
		out = append(out, "port")
	}
	return out
}

// manifestJSON: opis modułu do odpowiedzi /state (bez pól wewnętrznych).
func (m ModuleManifest) manifestJSON() map[string]interface{} {
	out := map[string]interface{}{
		"id":       m.ID,
		"button":   m.Button,
		"port":     m.Port,
		"log_name": m.EffectiveLogName(),
		"order":    m.Order,
		"folder":   filepath.Base(m.Dir),

		"obs_profile":          m.ObsProfile,
		"obs_scene_collection": m.ObsSceneCollection,
	}
	if m.Wp != nil {
		out["wp"] = map[string]interface{}{"port": m.Wp.Port, "db": m.Wp.EffectiveDB(), "template": m.Wp.EffectiveTemplate(), "title": m.Wp.Title}
	}
	return out
}
