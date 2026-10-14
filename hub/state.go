package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// Plik stanu usług (E2d2): run/uslugi.json. HUB zapisuje w nim (atomowo) numer i czas utworzenia procesów, które uruchomił
// (moduł, OBS, pluginy lokalne), ich porty, folder logów uruchomienia oraz ostatni znany status sesji. Po starcie HUB:
//  - przejmuje działające usługi zamiast uruchamiać je ponownie,
//  - kończy pozostałe po awarii pluginy lokalne (rozpoznanie wyłącznie po numerze i czasie utworzenia, z własnego pliku stanu,
//    nigdy po nazwie procesu: obok może działać HUB z innego folderu),
//  - odtwarza ostatni znany status sesji (do czasu pierwszego zgłoszenia przez moduł).
// Plik uszkodzony albo brak pliku: HUB niczego nie kończy, zapisuje to w logu i opiera się na sprawdzeniu portów i procesu OBS.

const stateVersion = 1

// StateEntry opisuje jeden proces uruchomiony przez HUB.
type StateEntry struct {
	ID           string `json:"id"`
	Kind         string `json:"kind"` // "service" albo "plugin"
	PID          int    `json:"pid"`
	CreatedFT    uint64 `json:"created_ft"` // czas utworzenia procesu (FILETIME)
	Address      string `json:"address,omitempty"`
	StartedByHub bool   `json:"started_by_hub"`
	RunDir       string `json:"run_dir,omitempty"` // folder logów uruchomienia, w którym proces prowadzi swoje logi
}

// StateSession to zapamiętany status sesji.
type StateSession struct {
	State     string `json:"state"`
	SessionID int    `json:"session_id"`
	GameID    int    `json:"game_id"`
	At        string `json:"at"`
}

// StateFile to zawartość pliku stanu.
type StateFile struct {
	Version int           `json:"version"`
	HubPID  int           `json:"hub_pid"`
	Updated string        `json:"updated"`
	Entries []StateEntry  `json:"entries"`
	Session *StateSession `json:"session,omitempty"`
}

// StateStore zapisuje i wczytuje plik stanu.
type StateStore struct {
	path string
	mu   sync.Mutex
}

func NewStateStore(path string) *StateStore { return &StateStore{path: path} }

// Save zapisuje plik atomowo: najpierw plik tymczasowy w tym samym folderze, potem zamiana. Czytelnik nigdy nie widzi pliku w połowie zapisu.
func (s *StateStore) Save(f StateFile) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	f.Version = stateVersion
	f.HubPID = os.Getpid()
	f.Updated = time.Now().Format(time.RFC3339)
	data, err := json.MarshalIndent(f, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(s.path), 0o755); err != nil {
		return err
	}
	tmp := s.path + ".tmp"
	file, err := os.OpenFile(tmp, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
	if err != nil {
		return err
	}
	if _, err := file.Write(data); err != nil {
		file.Close()
		os.Remove(tmp)
		return err
	}
	if err := file.Sync(); err != nil {
		file.Close()
		os.Remove(tmp)
		return err
	}
	if err := file.Close(); err != nil {
		os.Remove(tmp)
		return err
	}
	return renameReplace(tmp, s.path)
}

// renameReplace zamienia plik docelowy na tymczasowy. Na Windowsie zamiana kończy się chwilowym "Access is denied", gdy ktoś
// w tej samej chwili czyta plik docelowy bez prawa współdzielenia usuwania, więc kilka krótkich ponowień.
func renameReplace(from, to string) error {
	var err error
	for i := 0; i < 100; i++ {
		if err = os.Rename(from, to); err == nil {
			return nil
		}
		time.Sleep(5 * time.Millisecond)
	}
	return err
}

// Load wczytuje plik stanu. Brak pliku to (nil, nil). Uszkodzony plik to błąd (plik zostaje na miejscu do oględzin).
func (s *StateStore) Load() (*StateFile, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	data, err := os.ReadFile(s.path)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var f StateFile
	if err := json.Unmarshal(data, &f); err != nil {
		return nil, fmt.Errorf("plik stanu %s jest uszkodzony: %v", s.path, err)
	}
	if f.Version != stateVersion {
		return nil, fmt.Errorf("plik stanu %s ma nieznaną wersję %d", s.path, f.Version)
	}
	return &f, nil
}

// find zwraca wpis o danym identyfikatorze i rodzaju.
func (f *StateFile) find(kind, id string) *StateEntry {
	if f == nil {
		return nil
	}
	for i := range f.Entries {
		if f.Entries[i].Kind == kind && f.Entries[i].ID == id {
			return &f.Entries[i]
		}
	}
	return nil
}
