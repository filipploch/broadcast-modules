package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestStateSaveLoadRoundTripAndMissingFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "run", "uslugi.json")
	st := NewStateStore(path)
	if f, err := st.Load(); f != nil || err != nil {
		t.Fatalf("brak pliku to (nil, nil): %v %v", f, err)
	}
	in := StateFile{
		Entries: []StateEntry{{ID: "module", Kind: "service", PID: 123, CreatedFT: 456, Address: "127.0.0.1:8081", StartedByHub: true, RunDir: `C:\logs\x`}},
		Session: &StateSession{State: "on_air", SessionID: 9, GameID: 4, At: "2026-10-14T10:00:00+02:00"},
	}
	if err := st.Save(in); err != nil {
		t.Fatal(err)
	}
	out, err := st.Load()
	if err != nil || out == nil {
		t.Fatal(err)
	}
	if out.Version != stateVersion || out.HubPID != os.Getpid() || out.Updated == "" {
		t.Fatalf("metadane: %+v", out)
	}
	if e := out.find("service", "module"); e == nil || e.PID != 123 || e.CreatedFT != 456 || e.RunDir != `C:\logs\x` || out.Session.State != "on_air" {
		t.Fatalf("zawartość: %+v", out)
	}
	if out.find("plugin", "module") != nil {
		t.Fatal("find nie rozróżnia rodzaju")
	}
}

func TestStateCorruptOrUnknownVersionIsAnErrorAndLeavesFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "uslugi.json")
	st := NewStateStore(path)
	writeFile(t, path, `{"version": 1, "entries": [`)
	if _, err := st.Load(); err == nil || !strings.Contains(err.Error(), "uszkodzony") {
		t.Fatalf("uszkodzony plik: %v", err)
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatal("uszkodzony plik powinien zostać na miejscu do oględzin")
	}
	writeFile(t, path, `{"version": 99}`)
	if _, err := st.Load(); err == nil || !strings.Contains(err.Error(), "wersj") {
		t.Fatalf("nieznana wersja: %v", err)
	}
}

// Zapis jest atomowy: czytelnik nigdy nie widzi pliku w połowie zapisu (plik tymczasowy + zamiana).
func TestStateSaveIsAtomicUnderConcurrentReads(t *testing.T) {
	path := filepath.Join(t.TempDir(), "uslugi.json")
	st := NewStateStore(path)
	entries := make([]StateEntry, 200) // duży plik: zapis nie mieści się w jednym zapisie systemowym
	for i := range entries {
		entries[i] = StateEntry{ID: fmt.Sprintf("p%d", i), Kind: "plugin", PID: i + 1, CreatedFT: uint64(i)}
	}
	if err := st.Save(StateFile{Entries: entries}); err != nil {
		t.Fatal(err)
	}
	stop := make(chan struct{})
	var wg sync.WaitGroup
	var bad []string
	var mu sync.Mutex
	wg.Add(1)
	go func() { // czytelnik BEZ blokady sklepu: czyta plik jak inny proces
		defer wg.Done()
		for {
			select {
			case <-stop:
				return
			default:
			}
			data, err := os.ReadFile(path)
			if err != nil {
				continue
			}
			var f StateFile
			if err := json.Unmarshal(data, &f); err != nil || len(f.Entries) != 200 {
				mu.Lock()
				bad = append(bad, fmt.Sprintf("%d B: %v", len(data), err))
				mu.Unlock()
			}
		}
	}()
	for i := 0; i < 150; i++ {
		if err := st.Save(StateFile{Entries: entries}); err != nil {
			t.Fatal(err)
		}
	}
	close(stop)
	wg.Wait()
	if len(bad) > 0 {
		t.Fatalf("czytelnik zobaczył niepełny plik %d razy, np. %s", len(bad), bad[0])
	}
	if _, err := os.Stat(path + ".tmp"); err == nil {
		t.Fatal("plik tymczasowy został po zapisie")
	}
}

func TestLeftoverTmpFileIsIgnored(t *testing.T) {
	path := filepath.Join(t.TempDir(), "uslugi.json")
	st := NewStateStore(path)
	writeFile(t, path+".tmp", `śmieci z przerwanego zapisu`)
	if f, err := st.Load(); f != nil || err != nil {
		t.Fatalf("sam plik tymczasowy nie jest plikiem stanu: %v %v", f, err)
	}
}

// ── sieroty pluginów ─────────────────────────────────────────────────────────

func spawnSleeper(t *testing.T) *exec.Cmd {
	t.Helper()
	cmd := exec.Command(os.Args[0], "-test.run=TestServiceHelper")
	cmd.Env = append(os.Environ(), "GO_SERVICE_HELPER=sleep")
	cmd.SysProcAttr = detachedAttr()
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { killTree(cmd.Process.Pid); cmd.Wait() })
	return cmd
}

func TestKillOrphansUsesPidAndCreationTimeOnly(t *testing.T) {
	orphan := spawnSleeper(t)    // wpis zgodny: sierota po poprzednim HUB-ie, ma zostać zakończona
	reused := spawnSleeper(t)    // numer ten sam, ale inny czas utworzenia (numer użyty ponownie): nie ruszać
	bystander := spawnSleeper(t) // proces takiego samego pliku bez wpisu w pliku stanu (np. HUB z folderu main): nie ruszać
	waitCond(t, "procesy żyją", 5*time.Second, func() bool {
		_, a := processCreationTime(orphan.Process.Pid)
		_, b := processCreationTime(reused.Process.Pid)
		_, c := processCreationTime(bystander.Process.Pid)
		return a && b && c
	})
	oc, _ := processCreationTime(orphan.Process.Pid)
	rc, _ := processCreationTime(reused.Process.Pid)
	f := &StateFile{Entries: []StateEntry{
		{ID: "timer-plugin", Kind: "plugin", PID: orphan.Process.Pid, CreatedFT: oc},
		{ID: "replay-plugin", Kind: "plugin", PID: reused.Process.Pid, CreatedFT: rc + 12345},
		{ID: "martwy", Kind: "plugin", PID: 999999, CreatedFT: 1},
		{ID: "module", Kind: "service", PID: bystander.Process.Pid, CreatedFT: 1}, // usługi nie są kończone jako sieroty
	}}
	killed := KillOrphans(f)
	if len(killed) != 1 || killed[0] != orphan.Process.Pid {
		t.Fatalf("zakończone: %v", killed)
	}
	waitCond(t, "sierota zakończona", 5*time.Second, func() bool { _, ok := processCreationTime(orphan.Process.Pid); return !ok })
	for name, c := range map[string]*exec.Cmd{"numer użyty ponownie": reused, "proces bez wpisu": bystander} {
		if _, ok := processCreationTime(c.Process.Pid); !ok {
			t.Fatalf("%s został zakończony", name)
		}
	}
}

func TestRestoreFromStateCorruptOrMissingKillsNothing(t *testing.T) {
	useRunDir(t)
	bystander := spawnSleeper(t)
	waitCond(t, "żyje", 5*time.Second, func() bool { _, ok := processCreationTime(bystander.Process.Pid); return ok })
	path := filepath.Join(t.TempDir(), "uslugi.json")

	hub := NewHub(0, false, false)
	hub.State = NewStateStore(path)
	hub.Services = NewServiceManager()
	hub.Services.Add(svcCfg("module", "sleep", 0))
	// brak pliku
	if dead := hub.RestoreFromState(); dead != nil {
		t.Fatalf("brak pliku: %v", dead)
	}
	// uszkodzony plik (wpis wskazuje na żywy proces: gdyby został wczytany, zostałby przejęty lub zakończony)
	corrupt := fmt.Sprintf(`{"version":1,"entries":[{"id":"x","kind":"plugin","pid":%d,"created_ft":1`, bystander.Process.Pid)
	writeFile(t, path, corrupt)
	hub2 := NewHub(0, false, false)
	hub2.State = NewStateStore(path)
	hub2.Services = NewServiceManager()
	hub2.Services.persist = hub2.persistState
	if dead := hub2.RestoreFromState(); dead != nil {
		t.Fatalf("uszkodzony plik: %v", dead)
	}
	if _, ok := processCreationTime(bystander.Process.Pid); !ok {
		t.Fatal("proces został zakończony mimo uszkodzonego pliku stanu")
	}
}

func TestRestoreFromStateRestoresSessionStatusAndWritesOnlyAfterRestore(t *testing.T) {
	useRunDir(t)
	path := filepath.Join(t.TempDir(), "uslugi.json")
	st := NewStateStore(path)
	st.Save(StateFile{Session: &StateSession{State: "on_air", SessionID: 3, GameID: 8, At: time.Now().Format(time.RFC3339)}})

	hub := NewHub(0, false, false)
	hub.State = NewStateStore(path)
	hub.Services = NewServiceManager()
	hub.Services.persist = hub.persistState
	hub.session.onChange = func(SessionStatus) { hub.persistState() }

	before, _ := os.ReadFile(path)
	hub.persistState() // przed przywróceniem stanu zapis jest zablokowany
	after, _ := os.ReadFile(path)
	if string(before) != string(after) {
		t.Fatal("zapis przed zakończeniem przejmowania nadpisał plik")
	}
	hub.RestoreFromState()
	s := hub.SessionStatus()
	if !s.Known || !s.FromFile || s.State != sessionOnAir || s.SessionID != 3 || !s.OpenForRestart() {
		t.Fatalf("status z pliku: %+v", s)
	}
	// po zgłoszeniu przez moduł status przestaje być "z pliku"
	hub.handleMessage(mainModuleMsg(hub, map[string]interface{}{"state": "preparation", "session_id": float64(3)}))
	if s := hub.SessionStatus(); s.FromFile || s.State != sessionPreparation {
		t.Fatalf("po zgłoszeniu: %+v", s)
	}
	f, err := st.Load()
	if err != nil || f.Session == nil || f.Session.State != "preparation" {
		t.Fatalf("plik po zgłoszeniu: %+v %v", f, err)
	}
}

// ── przejmowanie usług po awarii HUB-a ───────────────────────────────────────

// startServiceInMiniHub uruchamia usługę przez osobny proces "HUB-a" (zapisuje plik stanu), po czym zabija ten proces
// jak awaria. Zwraca numer procesu usługi.
func startServiceInMiniHub(t *testing.T, cfg ServiceConfig, runDir, statePath string) int {
	t.Helper()
	cfgJSON, _ := json.Marshal(cfg)
	hub := exec.Command(os.Args[0], "-test.run=TestServiceHelper")
	hub.Env = append(os.Environ(), "GO_SERVICE_HELPER=mini-hub", "MINI_CONFIG="+string(cfgJSON), "MINI_RUNDIR="+runDir, "MINI_STATE="+statePath)
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
	sc := bufio.NewScanner(stdout)
	for sc.Scan() { // czytniki logów mini-HUB-a też piszą na jego wyjście: szukamy wiersza z gotowością
		if _, err := fmt.Sscanf(strings.TrimSpace(sc.Text()), "MINI_READY %d", &svcPid); err == nil && svcPid != 0 {
			break
		}
	}
	if svcPid == 0 {
		t.Fatal("mini-hub nie zgłosił gotowości")
	}
	go io.Copy(io.Discard, stdout) // dalsze wiersze nie mogą zablokować mini-HUB-a przed zabiciem
	if err := exec.Command("taskkill", "/F", "/PID", strconv.Itoa(hub.Process.Pid)).Run(); err != nil {
		t.Fatal(err)
	}
	hub.Wait()
	return svcPid
}

func TestAdoptTakesOverRunningServiceAndKnowsItsExitCode(t *testing.T) {
	dir := useRunDir(t)
	port := freePort(t)
	statePath := filepath.Join(t.TempDir(), "uslugi.json")
	cfg := svcCfg("module", "http", port)
	cfg.OutputFile = "modul-test.wyjscie.log"
	cfg.FollowFiles = []string{"modul-test.wyjscie.log"}
	svcPid := startServiceInMiniHub(t, cfg, dir, statePath)

	// "nowy HUB": wczytuje plik stanu i przejmuje usługę zamiast uruchamiać drugą
	f, err := NewStateStore(statePath).Load()
	if err != nil || f == nil {
		t.Fatalf("plik stanu: %v", err)
	}
	if e := f.find("service", "module"); e == nil || e.PID != svcPid || e.RunDir != dir || e.CreatedFT == 0 {
		t.Fatalf("wpis w pliku stanu: %+v", e)
	}
	sm := newTestSM(t)
	sm.Add(cfg)
	adopted, dead := sm.Adopt(f)
	if len(adopted) != 1 || len(dead) != 0 {
		t.Fatalf("przejęte %v, martwe %v", adopted, dead)
	}
	waitCond(t, "usługa online po przejęciu", 10*time.Second, func() bool { return sm.Status("module") == "online" })
	snap := sm.Snapshot()["module"].(map[string]interface{})
	if snap["pid"].(int) != svcPid || snap["adopted"] != true {
		t.Fatalf("snapshot: %v", snap)
	}
	if err := sm.Start("module"); err != nil { // StartAll po przejęciu nie uruchamia drugiej kopii
		t.Fatal(err)
	}
	if sm.Snapshot()["module"].(map[string]interface{})["pid"].(int) != svcPid {
		t.Fatal("po przejęciu uruchomiono drugą kopię")
	}
	// przejęta usługa kończy się z kodem 7: HUB zna ten kod (trzyma uchwyt procesu)
	if resp, err := httpGetQuiet(fmt.Sprintf("http://127.0.0.1:%d/exit?code=7", port)); err == nil {
		resp.Body.Close()
	}
	waitCond(t, "usługa zakończona", 10*time.Second, func() bool { return sm.Status("module") == "error" })
	sm.mu.Lock()
	code := sm.services["module"].exitCode
	msg := sm.services["module"].lastErr
	sm.mu.Unlock()
	if code != 7 || !strings.Contains(msg, "kodem 7") {
		t.Fatalf("kod wyjścia przejętej usługi: %d (%s)", code, msg)
	}
}

func TestAdoptRefusesProcessWithDifferentCreationTimeAndReportsDeadOnes(t *testing.T) {
	dir := useRunDir(t)
	port := freePort(t)
	statePath := filepath.Join(t.TempDir(), "uslugi.json")
	cfg := svcCfg("module", "http", port)
	svcPid := startServiceInMiniHub(t, cfg, dir, statePath)
	f, _ := NewStateStore(statePath).Load()
	e := f.find("service", "module")

	sm := newTestSM(t)
	sm.Add(cfg)
	sm.Add(svcCfg("martwa", "sleep", 0))
	f.Entries = []StateEntry{
		{ID: "module", Kind: "service", PID: svcPid, CreatedFT: e.CreatedFT + 777, RunDir: dir}, // numer użyty ponownie
		{ID: "martwa", Kind: "service", PID: 999998, CreatedFT: 5},
	}
	adopted, dead := sm.Adopt(f)
	if len(adopted) != 0 || len(dead) != 2 {
		t.Fatalf("przejęte %v, martwe %v", adopted, dead)
	}
	// proces o innym czasie utworzenia nie został przejęty, więc HUB widzi zajęty port i nie uruchamia drugiej kopii
	if err := sm.Start("module"); err == nil || !strings.Contains(err.Error(), "zajęty") {
		t.Fatalf("oczekiwano odmowy startu przy zajętym porcie: %v", err)
	}
}

func TestCollectStateGathersServicesPluginsAndSession(t *testing.T) {
	useRunDir(t)
	hub, pm := newTestPM(t, "timer-plugin")
	sm := newTestSM(t)
	hub.Services = sm
	sm.Add(svcCfg("module", "sleep", 0))
	hub.State = NewStateStore(filepath.Join(t.TempDir(), "uslugi.json"))
	sm.persist = hub.persistState
	pm.persist = hub.persistState
	hub.session.onChange = func(SessionStatus) { hub.persistState() }
	hub.RestoreFromState() // brak pliku: odblokowuje zapis
	if err := sm.Start("module"); err != nil {
		t.Fatal(err)
	}
	if err := pm.StartPlugin("timer-plugin"); err != nil {
		t.Fatal(err)
	}
	hub.handleMessage(mainModuleMsg(hub, map[string]interface{}{"state": "on_air", "session_id": float64(2)}))
	var f *StateFile
	waitCond(t, "plik stanu z usługą, pluginem i sesją", 5*time.Second, func() bool {
		f, _ = hub.State.Load()
		return f != nil && f.find("service", "module") != nil && f.find("plugin", "timer-plugin") != nil && f.Session != nil && f.Session.State == "on_air"
	})
	if e := f.find("plugin", "timer-plugin"); e.PID != pidOf(pm, "timer-plugin") || e.CreatedFT == 0 {
		t.Fatalf("wpis pluginu: %+v", e)
	}
	// po zatrzymaniu wpisy znikają
	sm.StopAll()
	pm.StopAllPlugins()
	waitCond(t, "wpisy usunięte po zatrzymaniu", 5*time.Second, func() bool {
		f, _ = hub.State.Load()
		return f != nil && f.find("service", "module") == nil && f.find("plugin", "timer-plugin") == nil
	})
}
