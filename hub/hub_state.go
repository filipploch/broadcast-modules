package main

import (
	"log"
	"sync/atomic"
	"time"
)

// Połączenie HUB-a z plikiem stanu i zdarzeniami usług (E2d2).

// stateReady: plik stanu wolno zapisywać dopiero po przejęciu usług i zakończeniu sierot; wcześniej zapis z pustą listą
// wymazałby wpisy żyjących procesów (a po awarii w tym oknie nie dałoby się ich przejąć).
type stateGate struct{ ready atomic.Bool }

// collectState składa zawartość pliku stanu z usług, pluginów i statusu sesji.
func (h *Hub) collectState() StateFile {
	var f StateFile
	if h.Services != nil {
		f.Entries = append(f.Entries, h.Services.StateEntries()...)
	}
	if h.PluginManager != nil {
		f.Entries = append(f.Entries, h.PluginManager.StateEntries()...)
	}
	if s := h.session.get(); s.Known {
		f.Session = &StateSession{State: s.State, SessionID: s.SessionID, GameID: s.GameID, At: s.At.Format(time.RFC3339)}
	}
	return f
}

// persistState zapisuje plik stanu (jeśli HUB ma store i jest po przejęciu usług). Błąd zapisu tylko loguje.
func (h *Hub) persistState() {
	if h.State == nil || !h.stateReady.ready.Load() {
		return
	}
	if err := h.State.Save(h.collectState()); err != nil {
		log.Printf("⚠️  Nie udało się zapisać pliku stanu: %v", err)
	}
}

// RestoreFromState odtwarza stan po poprzednim HUB-ie: ostatni znany status sesji, kończy sieroty pluginów i przejmuje działające
// usługi. Zwraca identyfikatory usług, których proces już nie żyje (kod wyjścia nieznany). Plik uszkodzony albo brak pliku:
// niczego nie kończy ani nie przejmuje, tylko zapisuje to w logu.
func (h *Hub) RestoreFromState() (dead []string) {
	defer func() {
		h.stateReady.ready.Store(true)
		h.persistState()
	}()
	if h.State == nil {
		return nil
	}
	f, err := h.State.Load()
	if err != nil {
		log.Printf("⚠️  %v; niczego nie kończę ani nie przejmuję, opieram się na sprawdzeniu portów i procesu OBS", err)
		return nil
	}
	if f == nil {
		log.Printf("ℹ️  Brak pliku stanu (%s): to pierwsze uruchomienie albo plik usunięto; opieram się na sprawdzeniu portów i procesu OBS", h.State.path)
		return nil
	}
	log.Printf("📂 Plik stanu z poprzedniego uruchomienia: %d wpisów (poprzedni HUB: PID %d, zapis %s)", len(f.Entries), f.HubPID, f.Updated)
	if f.Session != nil {
		at, _ := time.Parse(time.RFC3339, f.Session.At)
		h.session.restore(SessionStatus{State: f.Session.State, SessionID: f.Session.SessionID, GameID: f.Session.GameID, At: at, Known: true, FromFile: true})
		log.Printf("📋 Ostatni znany status sesji (z pliku stanu): %s (sesja %d)", f.Session.State, f.Session.SessionID)
	}
	KillOrphans(f)
	if h.Services != nil {
		_, dead = h.Services.Adopt(f)
	}
	return dead
}

// prepareModuleAdoption: jeśli plik stanu zapisał działający moduł (z id z module.json), usługa "module" dostaje jego definicję,
// żeby RestoreFromState mógł go przejąć niezależnie od --module (manager uruchamia HUB z --module none). Wpis bez id modułu
// (zapis sprzed E2d3c1) przejmuje tylko moduł z konfiguracji, jak dotąd.
func (h *Hub) prepareModuleAdoption(cfg *LoadedHubConfig) {
	if h.State == nil || h.Services == nil {
		return
	}
	f, err := h.State.Load()
	if err != nil || f == nil {
		return
	}
	for _, e := range f.Entries {
		if e.Kind != "service" || e.ID != "module" {
			continue
		}
		if e.Module == "" {
			if !h.Services.Has("module") {
				log.Printf("ℹ️  Plik stanu: moduł (PID %d) zapisany bez nazwy (sprzed E2d3c1), a HUB nie ma wybranego modułu: nie przejmuję go", e.PID)
			}
			return
		}
		if _, _, cur, _, _, _ := h.Services.Info("module"); cur == e.Module {
			return
		}
		m, ok := cfg.Catalog.Get(e.Module)
		if !ok {
			log.Printf("⚠️  Plik stanu: moduł %s (PID %d) nie ma pliku module.json: nie przejmuję go (jego port pozostaje zajęty)", e.Module, e.PID)
			return
		}
		if err := h.Services.Replace(cfg.moduleServiceFor(m)); err != nil {
			log.Printf("⚠️  Plik stanu: nie można przygotować przejęcia modułu %s: %v", e.Module, err)
			return
		}
		log.Printf("📂 Plik stanu: moduł %s z poprzedniego uruchomienia zostanie przejęty", e.Module)
		return
	}
}

// pluginGate mówi usłudze czekającej na plugin (OBS na obs-ws-plugin): czy moduł już zadeklarował pluginy, czy ten jest wymagany
// i czy jest połączony.
func (h *Hub) pluginGate(id string) (declared, expected, connected bool) {
	h.mu.RLock()
	defer h.mu.RUnlock()
	declared = h.declaredOnce
	expected = h.ExpectedPlugins[id]
	if p, ok := h.Plugins[id]; ok && p.IsActive {
		connected = true
	}
	return
}

// notifyService przekazuje modułowi zdarzenie usługi (pasek w panelu): kind = error, recovered, restarted, gave_up, info.
func (h *Hub) notifyService(id, kind, msg string) {
	h.notifyMainModule("service_status", map[string]interface{}{"service_id": id, "kind": kind, "message": msg})
}
