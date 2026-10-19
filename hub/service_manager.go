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
	"syscall"
	"time"
)

// Usługi (E2d1, E2d2): długo żyjące procesy uruchamiane przez HUB bez połączenia WebSocket i bez heartbeatu: moduł główny
// i OBS. Gotowość i stan sprawdza HUB po porcie (HTTP albo TCP). Proces jest odłączony od konsoli HUB-a i pisze wyjście
// prosto do pliku (bez potoku przez HUB), więc przeżywa awarię HUB-a; po starcie HUB przejmuje działające usługi
// według pliku stanu (service_adopt.go).

// Polityki restartu po awarii (kod wyjścia inny niż 0).
const (
	restartAlways      = ""             // zawsze, do limitu (moduł)
	restartSessionOpen = "session_open" // tylko przy otwartej sesji (OBS)
)

// ServiceConfig opisuje usługę (wpis "type": "service" w plugins.json albo usługa złożona z hub.json).
type ServiceConfig struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	Type string `json:"type"` // "service"

	ModuleID string `json:"module_id,omitempty"` // usługa "module": id modułu z module.json (zapisywane w pliku stanu, do przejęcia po awarii)

	ExecutablePath string   `json:"executable_path"`
	WorkingDir     string   `json:"working_dir"`
	Args           []string `json:"args"`
	Env            []string `json:"env"`

	ReadyURL      string   `json:"ready_url"`       // gotowość = dowolna odpowiedź HTTP
	ReadyPort     int      `json:"ready_port"`      // gotowość = połączenie TCP (gdy brak ready_url)
	ReadyTimeoutS int      `json:"ready_timeout_s"` // po tym czasie zgłaszany jest błąd (nie zabijamy procesu)
	StartAfter    []string `json:"start_after"`     // czeka na gotowość tych usług (najwyżej ich ready_timeout_s)

	// Czekanie na rejestrację pluginu (OBS czeka na obs-ws-plugin): tylko gdy moduł plugin zadeklarował; po upływie startuje mimo to.
	WaitForPlugin  string `json:"wait_for_plugin"`
	WaitForPluginS int    `json:"wait_for_plugin_s"`

	RestartOnCrash bool   `json:"restart_on_crash"` // restart po zakończeniu z kodem innym niż 0
	RestartPolicy  string `json:"restart_policy"`   // "" (zawsze) albo "session_open" (tylko przy otwartej sesji)
	MaxRestarts    int    `json:"max_restarts"`
	RestartDelayMs int    `json:"restart_delay_ms"`
	StableAfterS   int    `json:"stable_after_s"` // po tylu sekundach stabilnej pracy licznik restartów zeruje się (domyślnie 60)
	StopGraceS     int    `json:"stop_grace_s"`   // czas łagodnego zatrzymania przed wymuszeniem
	NeverKill      bool   `json:"never_kill"`     // po czasie łagodnego zatrzymania usługa NIE jest kończona siłą (OBS)

	// Obcy proces: proces o tej nazwie (albo odpowiadający port) uruchomiony nie przez HUB jest "obcy": HUB go nie restartuje,
	// nie zamyka i nie uruchamia drugiej kopii.
	ProcessName string `json:"process_name"`
	ForeignOK   bool   `json:"foreign_ok"`

	// WindowedApp: program okienkowy (OBS): uruchamiany bez ukrytej konsoli (windowedAttr), którą dostają programy konsolowe.
	WindowedApp bool `json:"windowed_app"`

	OutputFile  string   `json:"output_file"`  // plik w folderze uruchomienia, np. "modul-nalf.wyjscie.log"; domyślnie <id>.wyjscie.log
	FollowFiles []string `json:"follow_files"` // pliki z folderu uruchomienia pokazywane na konsoli HUB-a (czytane, nie zapisywane)
	FollowLabel string   `json:"follow_label"`
}

type serviceProc struct {
	cfg          ServiceConfig
	cmd          *exec.Cmd // nil dla przejętego procesu i obcego
	pid          int
	createdFT    uint64 // czas utworzenia procesu (do pliku stanu)
	gen          int    // numer uruchomienia: odróżnia bieżący proces od poprzednich (monitor starego nic nie zmienia)
	status       string // "stopped", "starting", "online", "error", "external"
	lastErr      string
	exitCode     int
	restartCount int // restarty automatyczne z rzędu (zerowane po stabilnej pracy)
	restarts     int // wszystkie ponowne uruchomienia od startu HUB-a
	startedOnce  bool
	startedAt    time.Time
	stopping     bool
	adopted      bool // proces przejęty z pliku stanu (nie uruchomiony przez ten egzemplarz HUB-a)
	autoRestart  bool // bieżące uruchomienie to automatyczny restart po awarii (po gotowości: komunikat dla operatora)
	hadError     bool // był błąd gotowości/startu (po powrocie: komunikat "wrócił")
	runDir       string
	exited       chan struct{}
	followers    []*fileFollower
}

type ServiceManager struct {
	mu       sync.Mutex
	services map[string]*serviceProc
	order    []string

	// graceful prosi usługę o zamknięcie się samej (np. komunikat do modułu); zwraca false, gdy nie ma jak.
	graceful func(id string) bool
	// sessionOpen mówi, czy sesja jest otwarta wedle ostatniego znanego statusu (restart OBS tylko wtedy).
	sessionOpen func() bool
	// pluginGate: czy moduł już zadeklarował pluginy, czy plugin jest wymagany i czy jest połączony.
	pluginGate func(id string) (declared, expected, connected bool)
	// notify przekazuje modułowi zdarzenie usługi do paska w panelu (kind: error, recovered, restarted, gave_up, info).
	notify func(id, kind, msg string)
	// persist zapisuje plik stanu (wołane bez trzymania blokad).
	persist func()
	// procByName zwraca numery procesów o danej nazwie (do wykrywania obcego OBS).
	procByName func(name string) []int

	stableAfter      time.Duration
	pollInterval     time.Duration
	followInterval   time.Duration
	externalInterval time.Duration
	killWait         time.Duration // jak długo czekać na zniknięcie procesu i zwolnienie portu po wymuszeniu
	shuttingDown     bool
	skipStart        map[string]string // usługi, których pierwszego startu nie wykonujemy (powód w logu)
}

func NewServiceManager() *ServiceManager {
	return &ServiceManager{
		services:         make(map[string]*serviceProc),
		stableAfter:      60 * time.Second,
		pollInterval:     250 * time.Millisecond,
		followInterval:   100 * time.Millisecond,
		externalInterval: 5 * time.Second,
		killWait:         5 * time.Second,
		procByName:       findProcessesByName,
	}
}

func (sm *ServiceManager) persistNow() {
	if sm.persist != nil {
		sm.persist()
	}
}

func (sm *ServiceManager) notifyNow(id, kind, msg string) {
	if sm.notify != nil {
		sm.notify(id, kind, msg)
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
	if cfg.WaitForPluginS <= 0 {
		cfg.WaitForPluginS = 15
	}
	if cfg.Name == "" {
		cfg.Name = cfg.ID
	}
	sm.services[cfg.ID] = &serviceProc{cfg: cfg, status: "stopped"}
	sm.order = append(sm.order, cfg.ID)
	return nil
}

// Replace podmienia definicję usługi, której proces nie działa (kanał sterujący: zmiana modułu przy działającym HUB-ie).
// Nieznana usługa jest dodawana. Działającej nie rusza (błąd): wyłączność modułu pilnuje kanał, a to jest druga linia obrony.
func (sm *ServiceManager) Replace(cfg ServiceConfig) error {
	sm.mu.Lock()
	sp := sm.services[cfg.ID]
	if sp == nil {
		sm.mu.Unlock()
		return sm.Add(cfg)
	}
	if sp.exited != nil && !isClosed(sp.exited) {
		sm.mu.Unlock()
		return fmt.Errorf("usługa %s działa (PID %d); najpierw ją zatrzymaj", cfg.ID, sp.pid)
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
	if cfg.WaitForPluginS <= 0 {
		cfg.WaitForPluginS = 15
	}
	if cfg.Name == "" {
		cfg.Name = cfg.ID
	}
	sp.cfg = cfg
	sp.restartCount = 0
	sp.lastErr = ""
	if sp.status == "error" {
		sp.status = "stopped"
	}
	sm.mu.Unlock()
	return nil
}

// Info zwraca stan usługi do kanału sterującego: status, PID (gdy działa), id modułu, ostatni błąd, czy trwa zatrzymywanie.
func (sm *ServiceManager) Info(id string) (status string, pid int, moduleID, lastErr string, stopping, alive bool) {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	sp := sm.services[id]
	if sp == nil {
		return "", 0, "", "", false, false
	}
	alive = sp.exited != nil && !isClosed(sp.exited) && sp.status != "external"
	if alive {
		pid = sp.pid
	}
	return sp.status, pid, sp.cfg.ModuleID, sp.lastErr, sp.stopping, alive
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
// potem startuje mimo to i zapisuje to w logu). Usługi już przejęte z pliku stanu nie są uruchamiane drugi raz.
func (sm *ServiceManager) StartAll() {
	sm.mu.Lock()
	ids := append([]string(nil), sm.order...)
	sm.mu.Unlock()
	for _, id := range ids {
		go func(id string) {
			if reason := sm.skipReason(id); reason != "" {
				log.Printf("ℹ️  Usługa %s: pomijam start: %s", id, reason)
				sm.mu.Lock()
				cfg := sm.services[id].cfg
				sm.mu.Unlock()
				if cfg.ForeignOK {
					sm.detectForeign(id, cfg) // OBS uruchomiony ręcznie mimo to jest rozpoznany jako obcy (bez uruchamiania drugiej kopii)
				}
				return
			}
			sm.waitForDeps(id)
			sm.waitForPlugin(id)
			if err := sm.Start(id); err != nil {
				log.Printf("❌ Usługa %s: nie uruchomiono: %v", id, err)
			}
		}(id)
	}
}

// SkipInitialStart pomija pierwszy start usługi wykonywany przez StartAll (np. OBS zakończył się, gdy HUB nie działał, a sesji nie było).
func (sm *ServiceManager) SkipInitialStart(id, reason string) {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	if sm.skipStart == nil {
		sm.skipStart = map[string]string{}
	}
	sm.skipStart[id] = reason
}

func (sm *ServiceManager) skipReason(id string) string {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	return sm.skipStart[id]
}

// RestartPolicy zwraca politykę restartu usługi ("" gdy usługi nie ma).
func (sm *ServiceManager) RestartPolicy(id string) string {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	if sp := sm.services[id]; sp != nil {
		return sp.cfg.RestartPolicy
	}
	return ""
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
			if st := sm.Status(dep); st == "online" || st == "external" {
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

// waitForPlugin: usługa (OBS) startuje po rejestracji pluginu (obs-ws-plugin), ale czeka najwyżej wait_for_plugin_s i tylko
// wtedy, gdy moduł ten plugin zadeklarował. Po upływie czasu startuje mimo to i zgłasza to modułowi.
func (sm *ServiceManager) waitForPlugin(id string) {
	sm.mu.Lock()
	cfg := sm.services[id].cfg
	gate := sm.pluginGate
	sm.mu.Unlock()
	if cfg.WaitForPlugin == "" || gate == nil {
		return
	}
	deadline := time.Now().Add(time.Duration(cfg.WaitForPluginS) * time.Second)
	for {
		declared, expected, connected := gate(cfg.WaitForPlugin)
		if declared && (!expected || connected) {
			return
		}
		if time.Now().After(deadline) {
			if expected && !connected {
				log.Printf("⚠️  Usługa %s: plugin %s nie zarejestrował się w %d s, startuję mimo to", id, cfg.WaitForPlugin, cfg.WaitForPluginS)
				sm.notifyNow(id, "info", fmt.Sprintf("%s startuje bez zarejestrowanego pluginu %s", cfg.Name, cfg.WaitForPlugin))
			} else {
				log.Printf("ℹ️  Usługa %s: moduł nie zadeklarował pluginu %s w %d s, startuję", id, cfg.WaitForPlugin, cfg.WaitForPluginS)
			}
			return
		}
		time.Sleep(sm.pollInterval)
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
// wersja transmisyjna), nie startuje drugiej kopii i zgłasza błąd. Usługa z foreign_ok (OBS), której proces już działa,
// nie uruchomiona przez ten HUB, jest uznana za obcą: HUB jej nie rusza.
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
	if sm.shuttingDown {
		sm.mu.Unlock()
		log.Printf("⏹️  Usługa %s: HUB się zamyka, pomijam start", id)
		return fmt.Errorf("HUB się zamyka")
	}
	if sp.status == "online" || sp.status == "starting" || sp.status == "external" {
		st := sp.status
		sm.mu.Unlock()
		log.Printf("ℹ️  Usługa %s już działa (%s)", id, st)
		return nil
	}
	cfg := sp.cfg
	sm.mu.Unlock()

	if cfg.ForeignOK && sm.detectForeign(id, cfg) {
		return nil
	}
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
	cmd.SysProcAttr = serviceAttr(cfg)
	if err := cmd.Start(); err != nil {
		out.Close()
		sm.setError(id, fmt.Sprintf("start nie powiódł się: %v", err))
		return err
	}
	out.Close() // proces ma własny uchwyt
	created, _ := processCreationTime(cmd.Process.Pid)

	followers := sm.startFollowersIn(cfg, runLogDir)

	sm.mu.Lock()
	sp.gen++
	gen := sp.gen
	sp.cmd = cmd
	sp.pid = cmd.Process.Pid
	sp.createdFT = created
	sp.status = "starting"
	sp.lastErr = ""
	sp.startedAt = time.Now()
	sp.stopping = false
	sp.adopted = false
	sp.runDir = runLogDir
	sp.exited = make(chan struct{})
	sp.followers = followers
	if sp.startedOnce {
		sp.restarts++
	}
	sp.startedOnce = true
	sp.autoRestart = auto
	if auto {
		sp.restartCount++
	}
	exited := sp.exited
	sm.mu.Unlock()

	log.Printf("▶️  Usługa %s uruchomiona (PID %d), wyjście procesu: %s", id, cmd.Process.Pid, outPath)
	if runLogDir != "" {
		log.Printf("   Logi usługi %s prowadzone w folderze: %s", id, runLogDir)
	}
	go sm.monitor(id, gen, exited, func() (int, error) {
		err := cmd.Wait()
		code := 0
		if cmd.ProcessState != nil {
			code = cmd.ProcessState.ExitCode()
		}
		return code, err
	})
	go sm.watchReady(id, gen, exited)
	sm.persistNow()
	return nil
}

// serviceAttr: atrybuty procesu usługi. Programy konsolowe (moduł) dostają własną ukrytą konsolę, programy okienkowe (OBS) nie.
func serviceAttr(cfg ServiceConfig) *syscall.SysProcAttr {
	if cfg.WindowedApp {
		return windowedAttr()
	}
	return detachedAttr()
}

func (sm *ServiceManager) setError(id, msg string) {
	sm.mu.Lock()
	if sp := sm.services[id]; sp != nil {
		sp.status = "error"
		sp.lastErr = msg
		sp.hadError = true
	}
	sm.mu.Unlock()
	log.Printf("❌ Usługa %s: %s", id, msg)
	sm.notifyNow(id, "error", msg)
}

// openServiceOutput otwiera plik wyjścia usługi w folderze uruchomienia (dopisywanie; przy ponownym uruchomieniu
// wiersz rozdzielający). Bez folderu logów wyjście idzie do NUL.
func openServiceOutput(name string) (*os.File, string, error) {
	if runLogDir == "" {
		f, err := os.OpenFile(os.DevNull, os.O_WRONLY, 0)
		return f, os.DevNull, err
	}
	path := filepath.Join(runLogDir, name)
	rotateIfLarge(path, logMaxBytes, logBackups) // przy (ponownym) starcie; w trakcie pracy procesu plik rośnie tylko surowym wyjściem
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

// rotateIfLarge przesuwa plik większy niż maxBytes do <plik>.1 (starsze do .2, .3), żeby nowy start zaczynał od małego pliku.
func rotateIfLarge(path string, maxBytes int64, backups int) {
	info, err := os.Stat(path)
	if err != nil || info.Size() <= maxBytes {
		return
	}
	os.Remove(fmt.Sprintf("%s.%d", path, backups))
	for i := backups - 1; i >= 1; i-- {
		os.Rename(fmt.Sprintf("%s.%d", path, i), fmt.Sprintf("%s.%d", path, i+1))
	}
	os.Rename(path, path+".1")
}

// startFollowersIn czyta pliki logu usługi z podanego folderu (folder uruchomienia, w którym proces prowadzi logi) na konsolę HUB-a.
func (sm *ServiceManager) startFollowersIn(cfg ServiceConfig, dir string) []*fileFollower {
	if dir == "" || len(cfg.FollowFiles) == 0 {
		return nil
	}
	label := cfg.FollowLabel
	if label == "" {
		label = cfg.ID
	}
	emit := consoleEmit(label)
	var fs []*fileFollower
	for _, name := range cfg.FollowFiles {
		fs = append(fs, startFileFollower(filepath.Join(dir, name), sm.followInterval, emit))
	}
	return fs
}

// watchReady czeka na gotowość usługi. Po ready_timeout_s zgłasza błąd, ale proces zostaje i czeka dalej (wolniej):
// jeśli w końcu odpowie, stan wraca na "online".
func (sm *ServiceManager) watchReady(id string, gen int, exited chan struct{}) {
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
			announce := ""
			if sp.gen == gen && !isClosed(exited) {
				sp.status = "online"
				sp.lastErr = ""
				switch {
				case sp.autoRestart:
					announce = "restarted"
				case sp.hadError:
					announce = "recovered"
				}
				sp.hadError = false
			}
			sm.mu.Unlock()
			log.Printf("✅ Usługa %s gotowa po %.1f s", id, time.Since(started).Seconds())
			if announce != "" {
				sm.notifyNow(id, announce, cfg.Name)
			}
			return
		}
		if !reported && time.Since(started) > time.Duration(cfg.ReadyTimeoutS)*time.Second {
			reported = true
			msg := fmt.Sprintf("brak odpowiedzi po %d s", cfg.ReadyTimeoutS)
			sm.mu.Lock()
			current := false
			if sp := sm.services[id]; sp.gen == gen {
				sp.status = "error"
				sp.lastErr = msg
				sp.hadError = true
				current = true
			}
			sm.mu.Unlock()
			log.Printf("❌ Usługa %s nie odpowiada po %d s (proces działa, sprawdzam dalej)", id, cfg.ReadyTimeoutS)
			if current {
				sm.notifyNow(id, "error", msg)
			}
		}
		time.Sleep(sm.pollInterval)
	}
}

// monitor czeka na zakończenie procesu (wait zwraca kod wyjścia) i podejmuje decyzję o restarcie.
func (sm *ServiceManager) monitor(id string, gen int, exited chan struct{}, wait func() (int, error)) {
	code, err := wait()

	sm.mu.Lock()
	sp := sm.services[id]
	for _, f := range sp.followers {
		f.Stop()
	}
	sp.followers = nil
	superseded := sp.gen != gen
	stoppedByHub := sp.stopping
	cfg := sp.cfg
	stable := sm.stableAfter
	if cfg.StableAfterS > 0 {
		stable = time.Duration(cfg.StableAfterS) * time.Second
	}
	if !superseded {
		sp.exitCode = code
		if time.Since(sp.startedAt) >= stable {
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
	restartCount := sp.restartCount
	shuttingDown := sm.shuttingDown
	sessionOpen := sm.sessionOpen
	sm.mu.Unlock()
	defer sm.persistNow()

	if superseded {
		return
	}
	switch {
	case stoppedByHub:
		log.Printf("⏹️  Usługa %s zatrzymana przez HUB", id)
		return
	case code == 0:
		log.Printf("🔌 Usługa %s zakończyła się normalnie (kod 0), bez restartu", id)
		return
	default:
		log.Printf("❌ Usługa %s zakończyła się z kodem %d (%v)", id, code, err)
	}
	if shuttingDown || !cfg.RestartOnCrash {
		return
	}
	if cfg.RestartPolicy == restartSessionOpen {
		if sessionOpen == nil || !sessionOpen() {
			log.Printf("ℹ️  Usługa %s: sesja nie jest otwarta, bez restartu", id)
			return
		}
	}
	if restartCount >= cfg.MaxRestarts {
		log.Printf("❌ Usługa %s: limit restartów (%d) wyczerpany", id, cfg.MaxRestarts)
		sm.notifyNow(id, "gave_up", fmt.Sprintf("%s: limit automatycznych restartów (%d) wyczerpany", cfg.Name, cfg.MaxRestarts))
		return
	}
	delay := time.Duration(cfg.RestartDelayMs) * time.Millisecond
	log.Printf("🔄 Restart usługi %s za %v (próba %d z %d)", id, delay, restartCount+1, cfg.MaxRestarts)
	time.Sleep(delay)
	if err := sm.start(id, true); err != nil {
		log.Printf("❌ Restart usługi %s nie powiódł się: %v", id, err)
	}
}

func (sm *ServiceManager) isShuttingDown() bool {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	return sm.shuttingDown
}

// Stop zatrzymuje usługę: najpierw łagodnie (graceful, do stop_grace_s), potem wymusza zakończenie całego drzewa
// procesów. Na końcu sprawdza, czy port został zwolniony. Obcego procesu nie rusza.
func (sm *ServiceManager) Stop(id string) error {
	sm.mu.Lock()
	sp := sm.services[id]
	if sp == nil {
		sm.mu.Unlock()
		return fmt.Errorf("nieznana usługa %s", id)
	}
	if sp.status == "external" || sp.exited == nil {
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
		if cfg.NeverKill {
			sm.mu.Lock()
			sp.stopping = false
			sm.mu.Unlock()
			return sm.stopFailed(id, fmt.Sprintf("nie zamknęła się w %d s; zostawiam ją uruchomioną (bez wymuszania)", cfg.StopGraceS))
		}
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

// IDs zwraca identyfikatory usług w kolejności startu.
func (sm *ServiceManager) IDs() []string {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	return append([]string(nil), sm.order...)
}

// Has mówi, czy usługa jest skonfigurowana.
func (sm *ServiceManager) Has(id string) bool {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	return sm.services[id] != nil
}

// PID zwraca numer procesu usługi uruchomionej lub przejętej przez HUB (0, gdy nie działa albo jest obca).
func (sm *ServiceManager) PID(id string) int {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	sp := sm.services[id]
	if sp == nil || sp.exited == nil || isClosed(sp.exited) || sp.status == "external" {
		return 0
	}
	return sp.pid
}

// BeginShutdown blokuje wszystkie starty usług (także zaplanowane restarty po awarii).
func (sm *ServiceManager) BeginShutdown() {
	sm.mu.Lock()
	sm.shuttingDown = true
	sm.mu.Unlock()
}

// StopAll zatrzymuje usługi w kolejności odwrotnej do startu i blokuje ich automatyczne restarty.
func (sm *ServiceManager) StopAll() {
	sm.StopSome(nil)
}

// StopSome zatrzymuje wskazane usługi (nil = wszystkie) w kolejności odwrotnej do startu; pozostałe zostają uruchomione.
func (sm *ServiceManager) StopSome(only map[string]bool) {
	sm.mu.Lock()
	sm.shuttingDown = true
	ids := append([]string(nil), sm.order...)
	sm.mu.Unlock()
	for i := len(ids) - 1; i >= 0; i-- {
		if only != nil && !only[ids[i]] {
			continue
		}
		if err := sm.Stop(ids[i]); err != nil {
			log.Printf("⚠️  Zatrzymanie usługi %s: %v", ids[i], err)
		}
	}
	sm.persistNow()
}

// Detach przestaje obserwować usługę (czytniki logów), ale jej proces zostaje uruchomiony: HUB się zamyka, usługa dalej pracuje.
func (sm *ServiceManager) Detach(id string) {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	if sp := sm.services[id]; sp != nil {
		for _, f := range sp.followers {
			f.Stop()
		}
		sp.followers = nil
	}
}

// Running zwraca, czy proces usługi uruchomiony lub przejęty przez ten HUB jeszcze działa.
func (sm *ServiceManager) Running(id string) bool {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	sp := sm.services[id]
	return sp != nil && sp.exited != nil && !isClosed(sp.exited) && sp.status != "external"
}

// StartedByHub zwraca, czy proces usługi został uruchomiony przez HUB (ten albo poprzedni egzemplarz).
func (sm *ServiceManager) StartedByHub(id string) bool {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	sp := sm.services[id]
	return sp != nil && sp.pid > 0 && sp.status != "external" && sp.exited != nil && !isClosed(sp.exited)
}

// StateEntries zwraca wpisy do pliku stanu: procesy usług uruchomione lub przejęte przez HUB, które jeszcze działają.
func (sm *ServiceManager) StateEntries() []StateEntry {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	var out []StateEntry
	for _, id := range sm.order {
		sp := sm.services[id]
		if sp == nil || sp.pid == 0 || sp.exited == nil || isClosed(sp.exited) || sp.status == "external" {
			continue
		}
		out = append(out, StateEntry{ID: id, Kind: "service", PID: sp.pid, CreatedFT: sp.createdFT,
			Address: readyAddr(sp.cfg), StartedByHub: true, RunDir: sp.runDir, Module: sp.cfg.ModuleID})
	}
	return out
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
		alive := sp.exited != nil && !isClosed(sp.exited)
		if sp.status == "starting" || sp.status == "online" || (sp.status == "error" && alive) {
			m["pid"] = sp.pid
			m["uptime_s"] = int(time.Since(sp.startedAt).Seconds())
		}
		if sp.adopted {
			m["adopted"] = true
		}
		if sp.status == "external" {
			m["external"] = true
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
