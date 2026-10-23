package main

import (
	"fmt"
	"log"
	"net"
	"strconv"
	"sync"
	"time"
)

// Instancja WP uruchamiana przez HUB razem z modułem (WP-1, krok W3). Zasady (decyzje właściciela):
//   - działa jedna instancja naraz: działająca instancja INNEGO modułu jest zamykana bez ostrzeżeń (tylko nasz php.exe);
//   - jeśli działa już właściwa instancja (np. z pliku .bat), zostaje bez restartu i jest przejęta;
//   - brak albo awaria WP nie blokuje startu modułu (żółte ostrzeżenie w panelu);
//   - zatrzymanie modułu zatrzymuje WP uruchomiony przez HUB i przejęty z .bat.
// Instancja nie jest usługą z pliku stanu: po awarii HUB-a proces WP zostaje (jest odłączony) i przy następnym starcie albo
// zatrzymaniu modułu jest znajdowany po porcie.

const (
	wpServiceID        = "wp" // identyfikator w service_status (pasek w panelu modułu)
	wpReadyTimeout     = 30 * time.Second
	wpMaxRestarts      = 3
	wpRestartDelay     = 3 * time.Second
	wpOutputFilePrefix = "wp-"
)

// wpProc to uruchomiony proces WP: PID i funkcja czekająca na jego zakończenie.
type wpProc struct {
	pid  int
	wait func() error
}

type wpNotice struct {
	Kind string // warning | error | recovered
	Msg  string
}

type wpManager struct {
	cfg    *LoadedHubConfig
	notify func(kind, msg string)

	// podmieniane w testach
	sysFor    func(p wpPaths) wpOS
	launch    func(cmd wpCommand, outName string) (*wpProc, error)
	readyWait time.Duration
	delay     time.Duration

	mu       sync.Mutex
	moduleID string // moduł, dla którego działa (uruchomiona lub przejęta) instancja
	pid      int
	adopted  bool
	gen      int
	stopping bool
	restarts int
	last     wpNotice
}

func newWpManager(cfg *LoadedHubConfig, notify func(kind, msg string)) *wpManager {
	return &wpManager{cfg: cfg, notify: notify, readyWait: wpReadyTimeout, delay: wpRestartDelay,
		sysFor: func(p wpPaths) wpOS { return p.defaultOS() }, launch: launchWpProcess}
}

func (w *wpManager) catalog() *ModuleCatalog { return scanModuleCatalog(w.cfg.abs(w.cfg.ModulesDir)) }

func (w *wpManager) say(kind, msg string) {
	w.mu.Lock()
	w.last = wpNotice{Kind: kind, Msg: msg}
	w.mu.Unlock()
	if w.notify != nil {
		w.notify(kind, msg)
	}
}

// replay przekazuje modułowi bieżące ostrzeżenie (moduł łączy się z HUB-em po starcie instancji).
func (w *wpManager) replay() {
	w.mu.Lock()
	n := w.last
	w.mu.Unlock()
	if (n.Kind == "warning" || n.Kind == "error") && w.notify != nil {
		w.notify(n.Kind, n.Msg)
	}
}

// ensureFor przygotowuje WP przed startem modułu. Nigdy nie zwraca błędu: wszystkie problemy to ostrzeżenia, a moduł startuje dalej.
func (w *wpManager) ensureFor(moduleID string) {
	w.say("recovered", "")
	cat := w.catalog()
	m, ok := cat.Get(moduleID)
	if !ok || m.Wp == nil {
		log.Printf("ℹ️  WP: moduł %s nie ma bloku wp w module.json, nie uruchamiam WordPressa", moduleID)
		return
	}
	paths := w.cfg.wpPaths()
	if err := paths.check(); err != nil {
		log.Printf("⚠️  WP: %v", err)
		w.say("warning", fmt.Sprintf("WP modułu %s nie wystartuje: %v", moduleID, err))
		return
	}
	sys := w.sysFor(paths)
	plan := prepareWpStart(paths, cat, m, sys)
	for _, c := range plan.Closed {
		log.Printf("🔁 WP: zamknięto działającą instancję WP modułu %s (jedna instancja naraz)", c)
	}
	for _, warn := range plan.Warnings {
		log.Printf("⚠️  WP: %s", warn)
	}
	if plan.Err != nil {
		log.Printf("⚠️  WP: %v", plan.Err)
		w.say("warning", fmt.Sprintf("WP modułu %s nie wystartował: %v", moduleID, plan.Err))
		return
	}
	w.mu.Lock()
	w.gen++ // unieważnia nadzór poprzedniej instancji
	gen := w.gen
	w.moduleID, w.stopping, w.restarts = moduleID, false, 0
	w.mu.Unlock()
	if plan.Adopt {
		w.mu.Lock()
		w.pid, w.adopted = plan.PID, true
		w.mu.Unlock()
		log.Printf("📂 WP: instancja modułu %s już działa (PID %d, port %d): zostaje bez restartu", moduleID, plan.PID, m.Wp.Port)
		return
	}
	if created, err := paths.ensureDB(*m.Wp); err != nil {
		log.Printf("⚠️  WP: %v", err)
		w.say("warning", fmt.Sprintf("WP modułu %s nie wystartował: %v", moduleID, err))
		return
	} else if created {
		log.Printf("🆕 WP: założono bazę %q z szablonu %q", m.Wp.EffectiveDB(), m.Wp.EffectiveTemplate())
		if err := paths.applyTitle(*m.Wp); err != nil {
			log.Printf("⚠️  WP: nie ustawiono tytułu strony: %v", err)
		}
	}
	w.startProcess(gen, moduleID, paths, *m.Wp, sys)
}

// startProcess uruchamia proces WP, czeka na gotowość (najwyżej readyWait) i oddaje nadzór goroutine'ie.
func (w *wpManager) startProcess(gen int, moduleID string, paths wpPaths, cfg WpConfig, sys wpOS) {
	proc, err := w.launch(paths.command(cfg), wpOutputFilePrefix+moduleID+".wyjscie.log")
	if err != nil {
		log.Printf("⚠️  WP: start nie powiódł się: %v", err)
		w.say("warning", fmt.Sprintf("WP modułu %s nie wystartował: %v", moduleID, err))
		return
	}
	w.mu.Lock()
	w.pid, w.adopted = proc.pid, false
	w.mu.Unlock()
	log.Printf("▶️  WP: uruchomiono instancję modułu %s (PID %d, port %d, baza %s)", moduleID, proc.pid, cfg.Port, cfg.EffectiveDB())
	exited := make(chan error, 1)
	go func() { exited <- proc.wait() }()
	ready := make(chan bool, 1)
	go func() {
		deadline := time.Now().Add(w.readyWait)
		for time.Now().Before(deadline) {
			if sys.portOpen(cfg.Port) {
				ready <- true
				return
			}
			time.Sleep(100 * time.Millisecond)
		}
		ready <- false
	}()
	select {
	case ok := <-ready:
		if !ok {
			log.Printf("⚠️  WP: instancja modułu %s nie odpowiada na porcie %d po %s", moduleID, cfg.Port, w.readyWait)
			w.say("warning", fmt.Sprintf("WP modułu %s nie odpowiada na porcie %d", moduleID, cfg.Port))
		} else {
			log.Printf("✅ WP: instancja modułu %s gotowa: http://127.0.0.1:%d/", moduleID, cfg.Port)
		}
	case err := <-exited:
		w.onExit(gen, moduleID, paths, cfg, sys, err)
		return
	}
	go func() { w.onExit(gen, moduleID, paths, cfg, sys, <-exited) }()
}

// onExit: proces WP zakończył się. Zamierzone zatrzymanie nic nie robi; w pozostałych przypadkach restart do wpMaxRestarts razy.
func (w *wpManager) onExit(gen int, moduleID string, paths wpPaths, cfg WpConfig, sys wpOS, err error) {
	w.mu.Lock()
	if w.gen != gen || w.stopping {
		w.mu.Unlock()
		return
	}
	w.pid = 0
	w.restarts++
	n := w.restarts
	w.mu.Unlock()
	if n > wpMaxRestarts {
		log.Printf("❌ WP: instancja modułu %s przestała działać (%v); limit restartów wyczerpany", moduleID, err)
		w.say("error", fmt.Sprintf("WP modułu %s przestał działać (limit restartów)", moduleID))
		return
	}
	log.Printf("⚠️  WP: instancja modułu %s zakończyła się (%v); restart %d/%d", moduleID, err, n, wpMaxRestarts)
	w.say("warning", fmt.Sprintf("WP modułu %s zatrzymał się, uruchamiam ponownie (%d/%d)", moduleID, n, wpMaxRestarts))
	time.Sleep(w.delay)
	w.mu.Lock()
	stop := w.gen != gen || w.stopping
	w.mu.Unlock()
	if stop {
		return
	}
	w.startProcess(gen, moduleID, paths, cfg, sys)
}

// stopFor zatrzymuje instancję WP modułu: uruchomioną przez HUB i przejętą z .bat (po porcie, więc działa też po restarcie HUB-a).
// Obcego procesu na porcie nie zamyka.
func (w *wpManager) stopFor(moduleID string) {
	m, ok := w.catalog().Get(moduleID)
	if !ok || m.Wp == nil {
		return
	}
	paths := w.cfg.wpPaths()
	sys := w.sysFor(paths)
	w.mu.Lock()
	if w.moduleID == moduleID {
		w.stopping = true
		w.gen++
	}
	w.mu.Unlock()
	pid, listening := sys.listenerPID(m.Wp.Port)
	if !listening {
		return
	}
	if !sys.isOurs(pid) {
		log.Printf("⚠️  WP: port %d zajmuje inny proces (PID %d): nie zamykam go", m.Wp.Port, pid)
		return
	}
	if err := sys.kill(pid); err != nil {
		log.Printf("⚠️  WP: nie udało się zamknąć instancji modułu %s (PID %d): %v", moduleID, pid, err)
		return
	}
	waitPortClosed(sys, m.Wp.Port)
	log.Printf("⏹️  WP: zatrzymano instancję modułu %s (PID %d)", moduleID, pid)
	w.mu.Lock()
	if w.moduleID == moduleID {
		w.pid, w.adopted = 0, false
	}
	w.mu.Unlock()
	w.say("recovered", "")
}

// stopForCurrent zatrzymuje WP modułu, dla którego HUB go przygotował (zamykanie HUB-a przy zamkniętej sesji).
func (w *wpManager) stopForCurrent() {
	w.mu.Lock()
	id := w.moduleID
	w.mu.Unlock()
	if id != "" {
		w.stopFor(id)
	}
}

// view: opis do /state kanału sterującego.
type wpView struct {
	ModuleID string `json:"module_id"`
	Port     int    `json:"port"`
	PID      int    `json:"pid"`
	Adopted  bool   `json:"adopted"`
	Running  bool   `json:"running"`
	Warning  string `json:"warning"`
}

func (w *wpManager) view() wpView {
	w.mu.Lock()
	v := wpView{ModuleID: w.moduleID, PID: w.pid, Adopted: w.adopted}
	if w.last.Kind == "warning" || w.last.Kind == "error" {
		v.Warning = w.last.Msg
	}
	w.mu.Unlock()
	if v.ModuleID != "" {
		if m, ok := w.catalog().Get(v.ModuleID); ok && m.Wp != nil {
			v.Port = m.Wp.Port
			v.Running = tcpOpen(net.JoinHostPort("127.0.0.1", strconv.Itoa(m.Wp.Port)))
		}
	}
	return v
}
