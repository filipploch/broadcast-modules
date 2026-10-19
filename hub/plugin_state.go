package main

import "log"

// Stan pluginów lokalnych w pliku stanu (E2d2): numer i czas utworzenia procesu każdego uruchomionego pluginu.
// Po awarii HUB-a pluginy zostają jako sieroty; nowy HUB kończy je i uruchamia od nowa (zegar wraca z zapisu na dysku).

func (pm *PluginManager) persistNow() {
	pm.mu.RLock()
	f := pm.persist
	pm.mu.RUnlock()
	if f != nil {
		f()
	}
}

// StateEntries zwraca wpisy uruchomionych pluginów lokalnych do pliku stanu.
func (pm *PluginManager) StateEntries() []StateEntry {
	pm.mu.RLock()
	defer pm.mu.RUnlock()
	var out []StateEntry
	for id, pp := range pm.plugins {
		if pp.Process == nil || pp.Process.Process == nil || pp.createdFT == 0 {
			continue
		}
		if pp.Status == "stopped" || pp.Status == "error" {
			continue
		}
		out = append(out, StateEntry{ID: id, Kind: "plugin", PID: pp.Process.Process.Pid, CreatedFT: pp.createdFT, StartedByHub: true})
	}
	return out
}

// KillOrphans kończy pluginy lokalne pozostałe po poprzednim HUB-ie. Rozpoznanie wyłącznie po parze (numer procesu, czas
// utworzenia) z własnego pliku stanu, nigdy po nazwie procesu: obok może działać HUB z innego folderu (np. wersja transmisyjna).
// Wpis, którego numer został użyty ponownie przez inny proces (inny czas utworzenia), nie jest ruszany. Zwraca numery zakończonych.
func KillOrphans(f *StateFile) []int {
	if f == nil {
		return nil
	}
	var killed []int
	for _, e := range f.Entries {
		if e.Kind != "plugin" {
			continue
		}
		created, ok := processCreationTime(e.PID)
		if !ok {
			continue // proces już nie żyje
		}
		if created != e.CreatedFT {
			log.Printf("ℹ️  Plik stanu: PID %d (plugin %s) należy teraz do innego procesu, nie ruszam", e.PID, e.ID)
			continue
		}
		log.Printf("🧹 Kończę plugin %s (PID %d) pozostały po poprzednim HUB-ie; nowy HUB uruchomi go od nowa", e.ID, e.PID)
		if err := killTree(e.PID); err != nil {
			log.Printf("⚠️  Nie udało się zakończyć pluginu %s (PID %d): %v", e.ID, e.PID, err)
			continue
		}
		killed = append(killed, e.PID)
	}
	return killed
}
