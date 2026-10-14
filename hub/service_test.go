package main

import (
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"
)

// TestServiceHelper to "usługa" uruchamiana przez testy (ten sam plik wykonywalny co testy).
// Tryby (GO_SERVICE_HELPER): http (serwer + wiersze na stdout), http-with-child (rodzic bez portu, port trzyma potomek),
// sleep (tylko śpi), crash (kończy z kodem HELPER_EXIT), mini-hub (udaje HUB: uruchamia usługę i czeka na zabicie).
func TestServiceHelper(t *testing.T) {
	mode := os.Getenv("GO_SERVICE_HELPER")
	if mode == "" {
		return
	}
	switch mode {
	case "http":
		if ms, _ := strconv.Atoi(os.Getenv("HELPER_DELAY_MS")); ms > 0 {
			time.Sleep(time.Duration(ms) * time.Millisecond)
		}
		ln, err := net.Listen("tcp", "127.0.0.1:"+os.Getenv("HELPER_PORT"))
		if err != nil {
			fmt.Fprintln(os.Stderr, "helper: nie można nasłuchiwać:", err)
			os.Exit(2)
		}
		mux := http.NewServeMux()
		mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("ok")) })
		mux.HandleFunc("/exit", func(w http.ResponseWriter, r *http.Request) {
			code, _ := strconv.Atoi(r.URL.Query().Get("code"))
			go func() { time.Sleep(50 * time.Millisecond); os.Exit(code) }()
		})
		mux.HandleFunc("/quit", func(w http.ResponseWriter, r *http.Request) {
			if os.Getenv("HELPER_IGNORE_QUIT") == "1" {
				return
			}
			go func() { time.Sleep(50 * time.Millisecond); os.Exit(0) }()
		})
		go http.Serve(ln, mux)
		for i := 0; ; i++ {
			fmt.Printf("helper tick %d\n", i)
			time.Sleep(100 * time.Millisecond)
		}
	case "http-with-child":
		child := exec.Command(os.Args[0], "-test.run=TestServiceHelper")
		child.Env = append(os.Environ(), "GO_SERVICE_HELPER=http")
		child.Stdout, child.Stderr = os.Stdout, os.Stderr
		if err := child.Start(); err != nil {
			os.Exit(2)
		}
		child.Wait()
	case "sleep":
		time.Sleep(60 * time.Second)
	case "crash":
		code, _ := strconv.Atoi(os.Getenv("HELPER_EXIT"))
		time.Sleep(30 * time.Millisecond)
		os.Exit(code)
	case "mini-hub":
		var cfg ServiceConfig
		json.Unmarshal([]byte(os.Getenv("MINI_CONFIG")), &cfg)
		runLogDir = os.Getenv("MINI_RUNDIR")
		sm := NewServiceManager()
		sm.Add(cfg)
		if err := sm.Start(cfg.ID); err != nil {
			fmt.Println("MINI_ERR", err)
			os.Exit(3)
		}
		for sm.Status(cfg.ID) != "online" {
			time.Sleep(50 * time.Millisecond)
		}
		sm.mu.Lock()
		pid := sm.services[cfg.ID].pid
		sm.mu.Unlock()
		if p := os.Getenv("MINI_STATE"); p != "" {
			NewStateStore(p).Save(StateFile{Entries: sm.StateEntries()})
		}
		fmt.Println("MINI_READY", pid)
		time.Sleep(60 * time.Second)
	}
	os.Exit(0)
}

func freePort(t *testing.T) int {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()
	return ln.Addr().(*net.TCPAddr).Port
}

func portOpen(port int) bool { return tcpOpen(net.JoinHostPort("127.0.0.1", strconv.Itoa(port))) }

func useRunDir(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	old := runLogDir
	runLogDir = dir
	t.Cleanup(func() { runLogDir = old })
	return dir
}

func svcCfg(id, mode string, port int, extraEnv ...string) ServiceConfig {
	env := append([]string{"GO_SERVICE_HELPER=" + mode, "HELPER_PORT=" + strconv.Itoa(port)}, extraEnv...)
	cfg := ServiceConfig{
		ID: id, Type: "service", ExecutablePath: os.Args[0], Args: []string{"-test.run=TestServiceHelper"},
		Env: env, ReadyTimeoutS: 10, StopGraceS: 1, RestartDelayMs: 10,
	}
	if port > 0 {
		cfg.ReadyURL = fmt.Sprintf("http://127.0.0.1:%d/", port)
	}
	return cfg
}

func newTestSM(t *testing.T) *ServiceManager {
	t.Helper()
	sm := NewServiceManager()
	sm.pollInterval = 20 * time.Millisecond
	sm.followInterval = 20 * time.Millisecond
	sm.killWait = 5 * time.Second
	t.Cleanup(func() {
		sm.StopAll()
		sm.mu.Lock()
		defer sm.mu.Unlock()
		for _, sp := range sm.services { // ostateczne sprzątanie: żaden proces nie zostaje
			if sp.pid > 0 {
				killTree(sp.pid)
			}
		}
	})
	return sm
}

func waitCond(t *testing.T, what string, d time.Duration, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(d)
	for time.Now().Before(deadline) {
		if cond() {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("nie doczekano: %s", what)
}

func httpQuit(port int) {
	if resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/quit", port)); err == nil {
		resp.Body.Close()
	}
}

func TestServiceStartsReadyAndStopsGracefully(t *testing.T) {
	dir := useRunDir(t)
	port := freePort(t)
	sm := newTestSM(t)
	cfg := svcCfg("module", "http", port)
	cfg.OutputFile = "modul-test.wyjscie.log"
	sm.Add(cfg)
	sm.graceful = func(id string) bool { httpQuit(port); return true }
	if err := sm.Start("module"); err != nil {
		t.Fatal(err)
	}
	waitCond(t, "status online", 10*time.Second, func() bool { return sm.Status("module") == "online" })
	snap := sm.Snapshot()["module"].(map[string]interface{})
	if snap["pid"].(int) == 0 || snap["address"] != fmt.Sprintf("127.0.0.1:%d", port) {
		t.Fatalf("snapshot: %v", snap)
	}
	// wyjście procesu trafia prosto do pliku
	waitCond(t, "wyjście w pliku", 5*time.Second, func() bool {
		b, _ := os.ReadFile(filepath.Join(dir, "modul-test.wyjscie.log"))
		return strings.Contains(string(b), "helper tick")
	})
	if err := sm.Stop("module"); err != nil {
		t.Fatal(err)
	}
	if portOpen(port) || sm.Status("module") != "stopped" {
		t.Fatalf("po zatrzymaniu: port otwarty=%v status=%s", portOpen(port), sm.Status("module"))
	}
}

func TestServiceThatIgnoresGracefulStopIsKilledWithItsChildAndPortIsFree(t *testing.T) {
	useRunDir(t)
	port := freePort(t)
	sm := newTestSM(t)
	// rodzic nie trzyma portu; trzyma go potomek: samo zakończenie rodzica nie zwolniłoby portu
	cfg := svcCfg("module", "http-with-child", port, "HELPER_IGNORE_QUIT=1")
	sm.Add(cfg)
	var asked bool
	sm.graceful = func(id string) bool { asked = true; httpQuit(port); return true } // prośba jest ignorowana
	if err := sm.Start("module"); err != nil {
		t.Fatal(err)
	}
	waitCond(t, "status online", 10*time.Second, func() bool { return sm.Status("module") == "online" })
	start := time.Now()
	if err := sm.Stop("module"); err != nil {
		t.Fatal(err)
	}
	if !asked {
		t.Fatal("nie poproszono łagodnie")
	}
	if time.Since(start) < 900*time.Millisecond {
		t.Fatalf("wymuszenie nastąpiło przed upływem czasu łagodnego zatrzymania (%v)", time.Since(start))
	}
	if portOpen(port) {
		t.Fatal("port nadal zajęty: potomek przeżył zakończenie procesu głównego")
	}
}

func TestServiceNeverStartsSecondCopyOnBusyPort(t *testing.T) {
	useRunDir(t)
	port := freePort(t)
	ln, err := net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", port))
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()
	go func() {
		for {
			c, err := ln.Accept()
			if err != nil {
				return
			}
			c.Close()
		}
	}()
	sm := newTestSM(t)
	sm.Add(svcCfg("module", "http", port))
	if err := sm.Start("module"); err == nil || !strings.Contains(err.Error(), "zajęty") {
		t.Fatalf("oczekiwano błędu zajętego portu: %v", err)
	}
	if sm.Status("module") != "error" || sm.Snapshot()["module"].(map[string]interface{})["pid"].(int) != 0 {
		t.Fatalf("stan: %v", sm.Snapshot())
	}
}

func TestServiceCrashRestartsUpToLimitAndExitZeroDoesNot(t *testing.T) {
	useRunDir(t)
	sm := newTestSM(t)
	crash := svcCfg("crash", "crash", 0, "HELPER_EXIT=3")
	crash.RestartOnCrash, crash.MaxRestarts = true, 2
	sm.Add(crash)
	clean := svcCfg("clean", "crash", 0, "HELPER_EXIT=0")
	clean.RestartOnCrash, clean.MaxRestarts = true, 5
	sm.Add(clean)
	sm.Start("crash")
	sm.Start("clean")
	waitCond(t, "limit restartów wyczerpany", 15*time.Second, func() bool {
		s := sm.Snapshot()["crash"].(map[string]interface{})
		return s["restarts"].(int) == 2 && s["status"] == "error"
	})
	time.Sleep(300 * time.Millisecond)
	if r := sm.Snapshot()["crash"].(map[string]interface{})["restarts"].(int); r != 2 {
		t.Fatalf("po wyczerpaniu limitu doszły kolejne restarty: %d", r)
	}
	c := sm.Snapshot()["clean"].(map[string]interface{})
	if c["restarts"].(int) != 0 || c["status"] != "stopped" {
		t.Fatalf("kod 0 nie powinien dawać restartu: %v", c)
	}
}

func TestServiceRestartCounterNeverExceedsLimit(t *testing.T) {
	useRunDir(t)
	sm := newTestSM(t)
	sm.stableAfter = 50 * time.Millisecond
	cfg := svcCfg("crash", "crash", 0, "HELPER_EXIT=3")
	cfg.RestartOnCrash, cfg.MaxRestarts = true, 1
	sm.Add(cfg)
	sm.Start("crash")
	time.Sleep(1500 * time.Millisecond)
	s := sm.Snapshot()["crash"].(map[string]interface{})
	if s["restart_count"].(int) > 1 {
		t.Fatalf("licznik ponad limit: %v", s)
	}
}

func TestStartAfterWaitsForReadinessOfDependency(t *testing.T) {
	useRunDir(t)
	portA := freePort(t)
	sm := newTestSM(t)
	a := svcCfg("a", "http", portA, "HELPER_DELAY_MS=1200")
	b := svcCfg("b", "sleep", 0)
	b.StartAfter = []string{"a"}
	sm.Add(a)
	sm.Add(b)
	sm.StartAll()
	waitCond(t, "a uruchomiona", 5*time.Second, func() bool { return sm.Status("a") == "starting" || sm.Status("a") == "online" })
	if st := sm.Status("b"); st != "stopped" {
		t.Fatalf("b wystartowała przed gotowością a: %s", st)
	}
	waitCond(t, "a gotowa", 10*time.Second, func() bool { return sm.Status("a") == "online" })
	waitCond(t, "b uruchomiona", 10*time.Second, func() bool { return sm.Status("b") == "starting" || sm.Status("b") == "online" })
}

func TestStartAfterStartsAnywayAfterDependencyTimeout(t *testing.T) {
	useRunDir(t)
	portA := freePort(t)
	sm := newTestSM(t)
	a := svcCfg("a", "http", portA, "HELPER_DELAY_MS=60000")
	a.ReadyTimeoutS = 1
	b := svcCfg("b", "sleep", 0)
	b.StartAfter = []string{"a"}
	sm.Add(a)
	sm.Add(b)
	start := time.Now()
	sm.StartAll()
	waitCond(t, "b uruchomiona mimo braku gotowości a", 8*time.Second, func() bool { return sm.Status("b") == "starting" || sm.Status("b") == "online" })
	if d := time.Since(start); d < 900*time.Millisecond {
		t.Fatalf("b wystartowała bez czekania na a (%v)", d)
	}
}

func TestStopAllStopsInReverseOrder(t *testing.T) {
	useRunDir(t)
	sm := newTestSM(t)
	var mu sync.Mutex
	var order []string
	sm.graceful = func(id string) bool { mu.Lock(); order = append(order, id); mu.Unlock(); return false }
	sm.Add(svcCfg("first", "sleep", 0))
	sm.Add(svcCfg("second", "sleep", 0))
	sm.Start("first")
	sm.Start("second")
	sm.StopAll()
	mu.Lock()
	defer mu.Unlock()
	if strings.Join(order, ",") != "second,first" {
		t.Fatalf("kolejność zatrzymywania: %v", order)
	}
}

func TestServicesLoadedFromPluginsJSON(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "plugins.json")
	writeFile(t, path, `{
	  "timer-plugin": {"id":"timer-plugin","type":"local","executable_path":"x"},
	  "moja-usluga": {"type":"service","executable_path":"y","ready_port":12345,"start_after":["module"],"max_restarts":3}
	}`)
	sm := NewServiceManager()
	if err := sm.LoadFromPluginsJSON(path); err != nil {
		t.Fatal(err)
	}
	if len(sm.services) != 1 || sm.services["moja-usluga"] == nil {
		t.Fatalf("usługi: %v", sm.order)
	}
	c := sm.services["moja-usluga"].cfg
	if c.ID != "moja-usluga" || c.ReadyPort != 12345 || c.StartAfter[0] != "module" || c.OutputFile != "moja-usluga.wyjscie.log" {
		t.Fatalf("%+v", c)
	}
	if err := NewServiceManager().LoadFromPluginsJSON(filepath.Join(dir, "brak.json")); err != nil {
		t.Fatalf("brak pliku to nie błąd: %v", err)
	}
}

// Awaria HUB-a: proces HUB-a zabity siłą, usługa żyje dalej i nadal pisze na wyjście (bez potoku przez HUB nie ma błędu zapisu).
func TestServiceSurvivesHubKillAndKeepsWritingOutput(t *testing.T) {
	dir := useRunDir(t)
	port := freePort(t)
	cfg := svcCfg("module", "http", port)
	cfg.OutputFile = "modul-test.wyjscie.log"
	cfgJSON, _ := json.Marshal(cfg)

	hub := exec.Command(os.Args[0], "-test.run=TestServiceHelper")
	hub.Env = append(os.Environ(), "GO_SERVICE_HELPER=mini-hub", "MINI_CONFIG="+string(cfgJSON), "MINI_RUNDIR="+dir)
	stdout, _ := hub.StdoutPipe()
	if err := hub.Start(); err != nil {
		t.Fatal(err)
	}
	var svcPid int
	t.Cleanup(func() {
		if svcPid > 0 {
			killTree(svcPid)
		}
		hub.Process.Kill()
	})
	buf := make([]byte, 256)
	n, _ := stdout.Read(buf)
	if _, err := fmt.Sscanf(strings.TrimSpace(string(buf[:n])), "MINI_READY %d", &svcPid); err != nil || svcPid == 0 {
		t.Fatalf("mini-hub nie zgłosił gotowości: %q (%v)", string(buf[:n]), err)
	}
	outPath := filepath.Join(dir, "modul-test.wyjscie.log")
	sizeBefore := fileSize(outPath)

	// "awaria HUB-a": zabicie procesu HUB-a bez żadnego sprzątania
	if err := exec.Command("taskkill", "/F", "/PID", strconv.Itoa(hub.Process.Pid)).Run(); err != nil {
		t.Fatal(err)
	}
	hub.Wait()

	time.Sleep(1200 * time.Millisecond)
	if !portOpen(port) {
		t.Fatal("usługa przestała odpowiadać po zabiciu HUB-a")
	}
	if after := fileSize(outPath); after <= sizeBefore {
		t.Fatalf("usługa nie pisze na wyjście po zabiciu HUB-a (%d -> %d)", sizeBefore, after)
	}
	b, _ := os.ReadFile(outPath)
	if strings.Contains(string(b), "write error") || strings.Contains(string(b), "broken pipe") {
		t.Fatalf("błąd zapisu w wyjściu usługi: %s", b)
	}
}

func fileSize(p string) int64 {
	if info, err := os.Stat(p); err == nil {
		return info.Size()
	}
	return 0
}

func httpGetQuiet(url string) (*http.Response, error) {
	c := http.Client{Timeout: 3 * time.Second}
	return c.Get(url)
}
