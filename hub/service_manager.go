package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"sync"
	"time"
)

// Usługi (E2d1): długo żyjące procesy uruchamiane przez HUB bez połączenia WebSocket i bez heartbeatu: moduł główny
// (później OBS). Gotowość i stan sprawdza HUB po porcie (HTTP albo TCP). Proces jest odłączony od konsoli HUB-a
// i pisze wyjście prosto do pliku (bez potoku przez HUB), więc przeżywa awarię HUB-a i nie dostaje błędu zapisu.

// ServiceConfig opisuje usługę (wpis "type": "service" w plugins.json albo usługa złożona z hub.json).
type ServiceConfig struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	Type string `json:"type"` // "service"

	ExecutablePath string   `json:"executable_path"`
	WorkingDir     string   `json:"working_dir"`
	Args           []string `json:"args"`
	Env            []string `json:"env"`

	ReadyURL      string   `json:"ready_url"`       // gotowość = dowolna odpowiedź HTTP
	ReadyPort     int      `json:"ready_port"`      // gotowość = połączenie TCP (gdy brak ready_url)
	ReadyTimeoutS int      `json:"ready_timeout_s"` // po tym czasie zgłaszany jest błąd (nie zabijamy procesu)
	StartAfter    []string `json:"start_after"`     // czeka na gotowość tych usług (najwyżej ich ready_timeout_s)

	RestartOnCrash bool `json:"restart_on_crash"` // restart po zakończeniu z kodem innym niż 0
	MaxRestarts    int  `json:"max_restarts"`
	RestartDelayMs int  `json:"restart_delay_ms"`
	StopGraceS     int  `json:"stop_grace_s"` // czas łagodnego zatrzymania przed wymuszeniem

	OutputFile  string   `json:"output_file"`  // plik w folderze uruchomienia, np. "modul-nalf.wyjscie.log"; domyślnie <id>.wyjscie.log
	FollowFiles []string `json:"follow_files"` // pliki z folderu uruchomienia pokazywane na konsoli HUB-a (czytane, nie zapisywane)
	FollowLabel string   `json:"follow_label"`
}

type serviceProc struct {
	cfg          ServiceConfig
	cmd          *exec.Cmd
	pid          int
	status       string // "stopped", "starting", "online", "error"
	lastErr      string
	exitCode     int
	restartCount int // restarty automatyczne z rzędu (zerowane po stabilnej pracy)
	restarts     int // wszystkie ponowne uruchomienia od startu HUB-a
	startedOnce  bool
	startedAt    time.Time
	stopping     bool
	exited       chan struct{}
	followers    []*fileFollower
}

type ServiceManager struct {
	mu       sync.Mutex
	services map[string]*serviceProc
	order    []string

	// graceful prosi usługę o zamknięcie się samej (np. komunikat do modułu); zwraca false, gdy nie ma jak.
	graceful func(id string) bool

	stableAfter    time.Duration
	pollInterval   time.Duration
	followInterval time.Duration
	killWait       time.Duration // jak długo czekać na zniknięcie procesu i zwolnienie portu po wymuszeniu
	shuttingDown   bool
}

func NewServiceManager() *ServiceManager {
	return &ServiceManager{
		services:       make(map[string]*serviceProc),
		stableAfter:    60 * time.Second,
		pollInterval:   250 * time.Millisecond,
		followInterval: 300 * time.Millisecond,
		killWait:       5 * time.Second,
	}
}

// Add rejestruje usługę (nie uruchamia jej).
func (sm *ServiceManager) Add(cfg ServiceConfig) error {
	if cfg.ID == "" {
		return fmt.Errorf("usługa bez identyfikatora")
	}
	sm.mu.Lock()
	defer sm.mu.Unlock()
	if _, ok := sm.services[cfg.ID]; ok {
		return fmt.Errorf("usługa %s jest już zarejestrowana", cfg.ID)
	}
	if cfg.OutputFile == "" {
		cfg.OutputFile = cfg.ID + ".wyjscie.log"
	}
	if cfg.ReadyTimeoutS <= 0 {
		cfg.ReadyTimeoutS = 60
	}
	if cfg.StopGraceS <= 0 {
		cfg.StopGraceS = 10
	}
	if cfg.Name == "" {
		cfg.Name = cfg.ID
	}
	sm.services[cfg.ID] = &serviceProc{cfg: cfg, status: "stopped"}
	sm.order = append(sm.order, cfg.ID)
	return nil
}

// LoadFromPluginsJSON dodaje usługi ("type": "service") z pliku konfiguracji pluginów. Brak pliku to nie błąd.
func (sm *ServiceManager) LoadFromPluginsJSON(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(data, &raw); err != nil {
		return err
	}
	ids := make([]string, 0, len(raw))
	for id := range raw {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		var probe struct {
			Type string `json:"type"`
		}
		if json.Unmarshal(raw[id], &probe) != nil || probe.Type != "service" {
			continue
		}
		var cfg ServiceConfig
		if err := json.Unmarshal(raw[id], &cfg); err != nil {
			return fmt.Errorf("usługa %s: %w", id, err)
		}
		cfg.ID = id
		if err := sm.Add(cfg); err != nil {
			return err
		}
		log.Printf("   🛠  Loaded SERVICE: %s", id)
	}
	return nil
}

// StartAll uruchamia wszystkie usługi w tle; każda czeka na gotowość usług z start_after (najwyżej ich ready_timeout_s,
// potem startuje mimo to i zapisuje to w logu).
func (sm *ServiceManager) StartAll() {
	sm.mu.Lock()
	ids := append([]string(nil), sm.order...)
	sm.mu.Unlock()
	for _, id := range ids {
		go func(id string) {
			sm.waitForDeps(id)
			if err := sm.Start(id); err != nil {
				log.Printf("❌ Usługa %s: nie uruchomiono: %v", id, err)
			}
		}(id)
	}
}

func (sm *ServiceManager) waitForDeps(id string) {
	sm.mu.Lock()
	sp := sm.services[id]
	deps := append([]string(nil), sp.cfg.StartAfter...)
	sm.mu.Unlock()
	for _, dep := range deps {
		sm.mu.Lock()
		d := sm.services[dep]
		sm.mu.Unlock()
		if d == nil {
			log.Printf("⚠️  Usługa %s: zależność %s nie istnieje, pomijam", id, dep)
			continue
		}
		deadline := time.Now().Add(time.Duration(d.cfg.ReadyTimeoutS) * time.Second)
		for {
			if sm.Status(dep) == "online" {
				break
			}
			if time.Now().After(deadline) {
				log.Printf("⚠️  Usługa %s: %s nie jest gotowa po %d s, startuję mimo to", id, dep, d.cfg.ReadyTimeoutS)
				break
			}
			time.Sleep(sm.pollInterval)
		}
	}
}

// Status zwraca stan usługi ("" gdy nie istnieje).
func (sm *ServiceManager) Status(id string) string {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	if sp := sm.services[id]; sp != nil {
		return sp.status
	}
	return ""
}

// readyAddr: adres TCP do sprawdzania gotowości ("" gdy usługa go nie ma).
func readyAddr(cfg ServiceConfig) string {
	if cfg.ReadyURL != "" {
		if u, err := url.Parse(cfg.ReadyURL); err == nil && u.Host != "" {
			return u.Host
		}
	}
	if cfg.ReadyPort > 0 {
		return net.JoinHostPort("127.0.0.1", strconv.Itoa(cfg.ReadyPort))
	}
	return ""
}

func tcpOpen(addr string) bool {
	c, err := net.DialTimeout("tcp", addr, 500*time.Millisecond)
	if err != nil {
		return false
	}
	c.Close()
	return true
}

func isReady(cfg ServiceConfig) bool {
	if cfg.ReadyURL != "" {
		client := http.Client{Timeout: 2 * time.Second}
		resp, err := client.Get(cfg.ReadyURL)
		if err != nil {
			return false
		}
		resp.Body.Close()
		return true
	}
	if addr := readyAddr(cfg); addr != "" {
		return tcpOpen(addr)
	}
	return true
}

// Start uruchamia usługę. Gdy jej port odpowiada już u kogoś innego (np. moduł z poprzedniego uruchomienia albo
// wersja transmisyjna), nie startuje drugiej kopii i zgłasza błąd.
func (sm *ServiceManager) Start(id string) error {
	return sm.start(id, false)
}

func (sm *ServiceManager) start(id string, auto bool) error {
	sm.mu.Lock()
	sp := sm.services[id]
	if sp == nil {
		sm.mu.Unlock()
		return fmt.Errorf("nieznana usługa %s", id)
	}
	if sp.status == "online" || sp.status == "starting" {
		sm.mu.Unlock()
		log.Printf("ℹ️  Usługa %s już działa (%s)", id, sp.status)
		return nil
	}
	cfg := sp.cfg
	sm.mu.Unlock()

	if addr := readyAddr(cfg); addr != "" && tcpOpen(addr) {
		msg := fmt.Sprintf("adres %s jest już zajęty (inny proces, np. z poprzedniego uruchomienia albo wersja transmisyjna); nie uruchamiam drugiej kopii", addr)
		sm.setError(id, msg)
		return fmt.Errorf("%s", msg)
	}
	execPath := cfg.ExecutablePath
	if !filepath.IsAbs(execPath) {
		if abs, err := filepath.Abs(execPath); err == nil {
			execPath = abs
		}
	}
	if _, err := os.Stat(execPath); err != nil {
		sm.setError(id, fmt.Sprintf("nie znaleziono pliku %s", execPath))
		return fmt.Errorf("nie znaleziono pliku %s", execPath)
	}

	out, outPath, err := openServiceOutput(cfg.OutputFile)
	if err != nil {
		sm.setError(id, fmt.Sprintf("nie można otworzyć pliku wyjścia: %v", err))
		return err
	}
	cmd := exec.Command(execPath, cfg.Args...)
	cmd.Dir = cfg.WorkingDir
	cmd.Env = append(os.Environ(), cfg.Env...)
	cmd.Stdin = nil
	cmd.Stdout = out // uchwyt pliku przekazany procesowi: HUB nie pośredniczy, więc awaria HUB-a nie psuje zapisu
	cmd.Stderr = out
	cmd.SysProcAttr = detachedAttr()
	if err := cmd.Start(); err != nil {
		out.Close()
		sm.setError(id, fmt.Sprintf("start nie powiódł się: %v", err))
		return err
	}
	out.Close() // proces ma własny uchwyt

	followers := sm.startFollowers(cfg)

	sm.mu.Lock()
	sp.cmd = cmd
	sp.pid = cmd.Process.Pid
	sp.status = "starting"
	sp.lastErr = ""
	sp.startedAt = time.Now()
	sp.stopping = false
	sp.exited = make(chan struct{})
	sp.followers = followers
	if sp.startedOnce {
		sp.restarts++
	}
	sp.startedOnce = true
	if auto {
		sp.restartCount++
	}
	exited := sp.exited
	sm.mu.Unlock()

	log.Printf("▶️  Usługa %s uruchomiona (PID %d), wyjście procesu: %s", id, cmd.Process.Pid, outPath)
	if runLogDir != "" {
		log.Printf("   Logi usługi %s prowadzone w folderze: %s", id, runLogDir)
	}
	go sm.monitor(id, cmd, exited)
	go sm.watchReady(id, cmd, exited)
	return nil
}

func (sm *ServiceManager) setError(id, msg string) {
	sm.mu.Lock()
	if sp := sm.services[id]; sp != nil {
		sp.status = "error"
		sp.lastErr = msg
	}
	sm.mu.Unlock()
	log.Printf("❌ Usługa %s: %s", id, msg)
}

// openServiceOutput otwiera plik wyjścia usługi w folderze uruchomienia (dopisywanie; przy ponownym uruchomieniu
// wiersz rozdzielający). Bez folderu logów wyjście idzie do NUL.
func openServiceOutput(name string) (*os.File, string, error) {
	if runLogDir == "" {
		f, err := os.OpenFile(os.DevNull, os.O_WRONLY, 0)
		return f, os.DevNull, err
	}
	path := filepath.Join(runLogDir, name)
	existed := false
	if info, err := os.Stat(path); err == nil && info.Size() > 0 {
		existed = true
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return nil, path, err
	}
	if existed {
		fmt.Fprintf(f, "%s ──────── ponowne uruchomienie usługi ────────\n", time.Now().Format(logTimeFormat))
	}
	return f, path, nil
}

func (sm *ServiceManager) startFollowers(cfg ServiceConfig) []*fileFollower {
	if runLogDir == "" || len(cfg.FollowFiles) == 0 {
		return nil
	}
	label := cfg.FollowLabel
	if label == "" {
		label = cfg.ID
	}
	emit := consoleEmit(label)
	var fs []*fileFollower
	for _, name := range cfg.FollowFiles {
		fs = append(fs, startFileFollower(filepath.Join(runLogDir, name), sm.followInterval, emit))
	}
	return fs
}

// watchReady czeka na gotowość usługi. Po ready_timeout_s zgłasza błąd, ale proces zostaje i czeka dalej (wolniej):
// jeśli w końcu odpowie, stan wraca na "online".
func (sm *ServiceManager) watchReady(id string, cmd *exec.Cmd, exited chan struct{}) {
	sm.mu.Lock()
	cfg := sm.services[id].cfg
	started := time.Now()
	sm.mu.Unlock()
	reported := false
	for {
		select {
		case <-exited:
			return
		default:
		}
		if isReady(cfg) {
			sm.mu.Lock()
			sp := sm.services[id]
			if sp.cmd == cmd && !isClosed(exited) {
				sp.status = "online"
				sp.lastErr = ""
			}
			sm.mu.Unlock()
			log.Printf("✅ Usługa %s gotowa po %.1f s", id, time.Since(started).Seconds())
			return
		}
		if !reported && time.Since(started) > time.Duration(cfg.ReadyTimeoutS)*time.Second {
			reported = true
			sm.mu.Lock()
			if sp := sm.services[id]; sp.cmd == cmd {
				sp.status = "error"
				sp.lastErr = fmt.Sprintf("brak odpowiedzi po %d s", cfg.ReadyTimeoutS)
			}
			sm.mu.Unlock()
			log.Printf("❌ Usługa %s nie odpowiada po %d s (proces działa, sprawdzam dalej)", id, cfg.ReadyTimeoutS)
		}
		time.Sleep(sm.pollInterval)
	}
}

func (sm *ServiceManager) monitor(id string, cmd *exec.Cmd, exited chan struct{}) {
	err := cmd.Wait()
	code := 0
	if cmd.ProcessState != nil {
		code = cmd.ProcessState.ExitCode()
	}

	sm.mu.Lock()
	sp := sm.services[id]
	for _, f := range sp.followers {
		f.Stop()
	}
	sp.followers = nil
	superseded := sp.cmd != cmd
	stoppedByHub := sp.stopping
	if !superseded {
		sp.exitCode = code
		if time.Since(sp.startedAt) >= sm.stableAfter {
			sp.restartCount = 0
		}
		if stoppedByHub || code == 0 {
			sp.status = "stopped"
		} else {
			sp.status = "error"
			sp.lastErr = fmt.Sprintf("zakończona z kodem %d", code)
		}
	}
	close(exited)
	shouldRestart := !superseded && !sm.shuttingDown && !stoppedByHub && code != 0 &&
		sp.cfg.RestartOnCrash && sp.restartCount < sp.cfg.MaxRestarts
	delay := time.Duration(sp.cfg.RestartDelayMs) * time.Millisecond
	cfg := sp.cfg
	restartCount := sp.restartCount
	sm.mu.Unlock()

	switch {
	case superseded:
		return
	case stoppedByHub:
		log.Printf("⏹️  Usługa %s zatrzymana przez HUB", id)
	case code == 0:
		log.Printf("🔌 Usługa %s zakończyła się normalnie (kod 0), bez restartu", id)
	default:
		log.Printf("❌ Usługa %s zakończyła się z kodem %d (%v)", id, code, err)
	}
	if shouldRestart {
		log.Printf("🔄 Restart usługi %s za %v (próba %d z %d)", id, delay, restartCount+1, cfg.MaxRestarts)
		time.Sleep(delay)
		if err := sm.start(id, true); err != nil {
			log.Printf("❌ Restart usługi %s nie powiódł się: %v", id, err)
		}
	} else if !stoppedByHub && code != 0 && cfg.RestartOnCrash && !sm.isShuttingDown() {
		log.Printf("❌ Usługa %s: limit restartów (%d) wyczerpany", id, cfg.MaxRestarts)
	}
}

func (sm *ServiceManager) isShuttingDown() bool {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	return sm.shuttingDown
}

// Stop zatrzymuje usługę: najpierw łagodnie (graceful, do stop_grace_s), potem wymusza zakończenie całego drzewa
// procesów. Na końcu sprawdza, czy port został zwolniony.
func (sm *ServiceManager) Stop(id string) error {
	sm.mu.Lock()
	sp := sm.services[id]
	if sp == nil {
		sm.mu.Unlock()
		return fmt.Errorf("nieznana usługa %s", id)
	}
	if sp.cmd == nil || sp.exited == nil {
		sm.mu.Unlock()
		return nil
	}
	select {
	case <-sp.exited:
		sm.mu.Unlock()
		return nil
	default:
	}
	sp.stopping = true
	exited := sp.exited
	pid := sp.pid
	cfg := sp.cfg
	graceful := sm.graceful
	sm.mu.Unlock()

	log.Printf("⏹️  Zatrzymuję usługę %s (PID %d)", id, pid)
	if graceful != nil && graceful(id) {
		select {
		case <-exited:
			log.Printf("✅ Usługa %s zamknęła się sama po prośbie HUB-a", id)
		case <-time.After(time.Duration(cfg.StopGraceS) * time.Second):
			log.Printf("⚠️  Usługa %s nie zamknęła się w %d s, kończę drzewo procesów", id, cfg.StopGraceS)
		}
	}
	select {
	case <-exited:
	default:
		if err := killTree(pid); err != nil {
			log.Printf("⚠️  Kończenie drzewa procesów usługi %s: %v", id, err)
		}
		select {
		case <-exited:
		case <-time.After(sm.killWait):
			return sm.stopFailed(id, "proces nie zakończył się po wymuszeniu")
		}
	}
	if addr := readyAddr(cfg); addr != "" {
		deadline := time.Now().Add(sm.killWait)
		for tcpOpen(addr) {
			if time.Now().After(deadline) {
				return sm.stopFailed(id, fmt.Sprintf("adres %s nadal zajęty po zatrzymaniu (trzyma go inny proces)", addr))
			}
			time.Sleep(100 * time.Millisecond)
		}
	}
	return nil
}

func (sm *ServiceManager) stopFailed(id, msg string) error {
	log.Printf("❌ Usługa %s: %s", id, msg)
	return fmt.Errorf("%s", msg)
}

// StopAll zatrzymuje usługi w kolejności odwrotnej do startu i blokuje ich automatyczne restarty.
func (sm *ServiceManager) StopAll() {
	sm.mu.Lock()
	sm.shuttingDown = true
	ids := append([]string(nil), sm.order...)
	sm.mu.Unlock()
	for i := len(ids) - 1; i >= 0; i-- {
		if err := sm.Stop(ids[i]); err != nil {
			log.Printf("⚠️  Zatrzymanie usługi %s: %v", ids[i], err)
		}
	}
}

// Snapshot: stan usług do /status.
func (sm *ServiceManager) Snapshot() map[string]interface{} {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	out := make(map[string]interface{}, len(sm.services))
	for id, sp := range sm.services {
		m := map[string]interface{}{
			"status":        sp.status,
			"pid":           0,
			"restarts":      sp.restarts,
			"restart_count": sp.restartCount,
		}
		if sp.status == "starting" || sp.status == "online" || (sp.status == "error" && sp.cmd != nil && sp.exited != nil && !isClosed(sp.exited)) {
			m["pid"] = sp.pid
			m["uptime_s"] = int(time.Since(sp.startedAt).Seconds())
		}
		if sp.lastErr != "" {
			m["last_error"] = sp.lastErr
		}
		if addr := readyAddr(sp.cfg); addr != "" {
			m["address"] = addr
		}
		out[id] = m
	}
	return out
}

func isClosed(c chan struct{}) bool {
	select {
	case <-c:
		return true
	default:
		return false
	}
}
