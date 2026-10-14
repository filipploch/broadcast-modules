package main

import (
	"fmt"
	"log"
	"time"
)

// Przejmowanie usług po awarii HUB-a i obsługa obcych procesów (E2d2).

// Adopt przejmuje usługi z pliku stanu: proces o zgodnym numerze i czasie utworzenia, który żyje, staje się usługą uruchomioną
// (bez nowego startu). HUB trzyma uchwyt tego procesu, więc po jego zakończeniu zna kod wyjścia. Zwraca identyfikatory
// przejętych usług oraz tych, których proces już nie żyje (kod wyjścia nieznany).
func (sm *ServiceManager) Adopt(f *StateFile) (adopted, dead []string) {
	if f == nil {
		return nil, nil
	}
	for _, e := range f.Entries {
		if e.Kind != "service" {
			continue
		}
		sm.mu.Lock()
		sp := sm.services[e.ID]
		sm.mu.Unlock()
		if sp == nil {
			log.Printf("ℹ️  Plik stanu: usługa %s nie jest już skonfigurowana, pomijam wpis", e.ID)
			continue
		}
		h, err := openProcessIdentity(e.PID, e.CreatedFT)
		if err != nil {
			log.Printf("ℹ️  Usługa %s z pliku stanu (PID %d) nie działa już (%v); kod wyjścia nieznany", e.ID, e.PID, err)
			dead = append(dead, e.ID)
			continue
		}
		followers := sm.startFollowersIn(sp.cfg, e.RunDir)
		sm.mu.Lock()
		sp.gen++
		gen := sp.gen
		sp.cmd = nil
		sp.pid = e.PID
		sp.createdFT = e.CreatedFT
		sp.status = "starting"
		sp.lastErr = ""
		sp.startedAt = time.Now()
		sp.stopping = false
		sp.adopted = true
		sp.autoRestart = false
		sp.runDir = e.RunDir
		sp.exited = make(chan struct{})
		sp.followers = followers
		sp.startedOnce = true
		exited := sp.exited
		sm.mu.Unlock()

		log.Printf("🤝 Przejęto usługę %s (PID %d) uruchomioną przez poprzedni HUB", e.ID, e.PID)
		if e.RunDir != "" {
			log.Printf("   Logi usługi %s prowadzone w folderze: %s", e.ID, e.RunDir)
		}
		go sm.monitor(e.ID, gen, exited, func() (int, error) {
			defer h.close()
			return h.wait()
		})
		go sm.watchReady(e.ID, gen, exited)
		adopted = append(adopted, e.ID)
	}
	sm.persistNow()
	return adopted, dead
}

// detectForeign sprawdza, czy usługa z foreign_ok (OBS) już działa poza HUB-em. Zwraca true, gdy HUB ma jej nie uruchamiać:
//   - port odpowiada: proces obcy, stan "external" (HUB go nie restartuje ani nie zamyka);
//   - proces działa, ale port milczy: błąd "brak odpowiedzi portu" (bez drugiej kopii); stan jest sprawdzany dalej i wraca, gdy port odpowie.
func (sm *ServiceManager) detectForeign(id string, cfg ServiceConfig) bool {
	addr := readyAddr(cfg)
	portOpen := addr != "" && tcpOpen(addr)
	var pids []int
	if cfg.ProcessName != "" && sm.procByName != nil {
		pids = sm.procByName(cfg.ProcessName)
	}
	if !portOpen && len(pids) == 0 {
		return false
	}
	sm.mu.Lock()
	sp := sm.services[id]
	sp.gen++
	gen := sp.gen
	sp.pid = 0
	sp.adopted = false
	sp.exited = nil
	if portOpen {
		sp.status = "external"
		sp.lastErr = ""
	} else {
		sp.status = "error"
		sp.lastErr = fmt.Sprintf("proces %s działa (PID %v), ale %s nie odpowiada", cfg.ProcessName, pids, addr)
		sp.hadError = true
	}
	msg := sp.lastErr
	status := sp.status
	sm.mu.Unlock()
	if status == "external" {
		log.Printf("ℹ️  Usługa %s: %s już działa poza HUB-em (obcy proces); HUB go nie uruchamia, nie restartuje i nie zamyka", id, cfg.Name)
	} else {
		log.Printf("❌ Usługa %s: %s; nie uruchamiam drugiej kopii", id, msg)
		sm.notifyNow(id, "error", msg)
	}
	go sm.watchExternal(id, gen, cfg)
	return true
}

// watchExternal pilnuje obcego procesu: stan "external" (port odpowiada), "error" (proces jest, port milczy) albo koniec
// (proces zniknął i port milczy). Niczego nie uruchamia ani nie zatrzymuje.
func (sm *ServiceManager) watchExternal(id string, gen int, cfg ServiceConfig) {
	addr := readyAddr(cfg)
	for {
		time.Sleep(sm.externalInterval)
		sm.mu.Lock()
		sp := sm.services[id]
		stop := sm.shuttingDown || sp.gen != gen
		sm.mu.Unlock()
		if stop {
			return
		}
		portOpen := addr != "" && tcpOpen(addr)
		var pids []int
		if cfg.ProcessName != "" && sm.procByName != nil {
			pids = sm.procByName(cfg.ProcessName)
		}
		sm.mu.Lock()
		sp = sm.services[id]
		if sp.gen != gen {
			sm.mu.Unlock()
			return
		}
		prev := sp.status
		announce := ""
		switch {
		case portOpen:
			sp.status = "external"
			sp.lastErr = ""
			if prev == "error" {
				announce = "recovered"
			}
			sp.hadError = false
		case len(pids) > 0:
			sp.status = "error"
			if sp.lastErr == "" {
				sp.lastErr = fmt.Sprintf("proces %s działa (PID %v), ale %s nie odpowiada", cfg.ProcessName, pids, addr)
				announce = "error"
			}
		default:
			sp.status = "stopped"
			sp.lastErr = ""
			sm.mu.Unlock()
			log.Printf("ℹ️  Usługa %s: obcy proces zakończył się", id)
			return
		}
		msg := sp.lastErr
		sm.mu.Unlock()
		if announce != "" {
			if announce == "recovered" {
				msg = cfg.Name
			}
			sm.notifyNow(id, announce, msg)
		}
	}
}
