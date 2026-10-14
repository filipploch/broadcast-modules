package main

import (
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

// Usługa OBS (E2d2): start po module i pluginie, obcy proces, restart po awarii tylko przy otwartej sesji, limit 3 i reset.

type notices struct {
	mu   sync.Mutex
	list []string
}

func (n *notices) add(id, kind, msg string) {
	n.mu.Lock()
	n.list = append(n.list, id+":"+kind)
	n.mu.Unlock()
}
func (n *notices) has(s string) bool {
	n.mu.Lock()
	defer n.mu.Unlock()
	for _, x := range n.list {
		if x == s {
			return true
		}
	}
	return false
}
func (n *notices) count(s string) int {
	n.mu.Lock()
	defer n.mu.Unlock()
	c := 0
	for _, x := range n.list {
		if x == s {
			c++
		}
	}
	return c
}

// obsLikeCfg: usługa jak OBS (polityka restartu zależna od sesji), ale z procesem pomocniczym testów.
func obsLikeCfg(port int, extraEnv ...string) ServiceConfig {
	cfg := svcCfg("obs", "http", port, extraEnv...)
	cfg.RestartOnCrash = true
	cfg.RestartPolicy = restartSessionOpen
	cfg.MaxRestarts = 3
	cfg.RestartDelayMs = 10
	cfg.ForeignOK = true
	cfg.ProcessName = "obs-atrapa.exe"
	return cfg
}

func crashObs(t *testing.T, port, code int) {
	t.Helper()
	if resp, err := httpGetQuiet(fmt.Sprintf("http://127.0.0.1:%d/exit?code=%d", port, code)); err == nil {
		resp.Body.Close()
	}
}

func obsPid(sm *ServiceManager) int {
	return sm.Snapshot()["obs"].(map[string]interface{})["pid"].(int)
}

func TestObsIsRestartedAfterCrashWhenSessionIsOpenAndModuleIsNotified(t *testing.T) {
	useRunDir(t)
	port := freePort(t)
	sm := newTestSM(t)
	n := &notices{}
	sm.notify = n.add
	sm.sessionOpen = func() bool { return true }
	sm.Add(obsLikeCfg(port))
	if err := sm.Start("obs"); err != nil {
		t.Fatal(err)
	}
	waitCond(t, "OBS online", 10*time.Second, func() bool { return sm.Status("obs") == "online" })
	first := obsPid(sm)
	crashObs(t, port, 3)
	waitCond(t, "OBS uruchomiony ponownie", 15*time.Second, func() bool {
		return sm.Status("obs") == "online" && obsPid(sm) != first && obsPid(sm) != 0
	})
	snap := sm.Snapshot()["obs"].(map[string]interface{})
	if snap["restarts"].(int) != 1 || snap["restart_count"].(int) != 1 {
		t.Fatalf("liczniki: %v", snap)
	}
	// moduł dostaje informację o ponownym uruchomieniu (z niej powstaje pasek "wznów stream i nagrywanie")
	waitCond(t, "komunikat o restarcie", 5*time.Second, func() bool { return n.has("obs:restarted") })
	// zwykły start nie jest "restartem"
	if n.count("obs:restarted") != 1 {
		t.Fatalf("komunikaty: %v", n.list)
	}
}

func TestObsIsNotRestartedOutsideSessionOrAfterExitCodeZero(t *testing.T) {
	useRunDir(t)
	for _, tc := range []struct {
		name string
		open bool
		code int
	}{{"poza sesją", false, 3}, {"sesja otwarta, kod 0", true, 0}} {
		t.Run(tc.name, func(t *testing.T) {
			port := freePort(t)
			sm := newTestSM(t)
			sm.sessionOpen = func() bool { return tc.open }
			sm.Add(obsLikeCfg(port))
			if err := sm.Start("obs"); err != nil {
				t.Fatal(err)
			}
			waitCond(t, "OBS online", 10*time.Second, func() bool { return sm.Status("obs") == "online" })
			crashObs(t, port, tc.code)
			waitCond(t, "OBS zakończony", 10*time.Second, func() bool { return !sm.Running("obs") })
			time.Sleep(400 * time.Millisecond) // czas, w którym restart (opóźnienie 10 ms) już by się wykonał
			if sm.Running("obs") {
				t.Fatal("OBS został uruchomiony ponownie")
			}
			if r := sm.Snapshot()["obs"].(map[string]interface{})["restarts"].(int); r != 0 {
				t.Fatalf("restarty: %d", r)
			}
		})
	}
}

func TestObsGivesUpAfterThreeRestartsInARowAndTellsTheModule(t *testing.T) {
	useRunDir(t)
	port := freePort(t)
	sm := newTestSM(t)
	n := &notices{}
	sm.notify = n.add
	sm.sessionOpen = func() bool { return true }
	sm.Add(obsLikeCfg(port))
	sm.Start("obs")
	for i := 0; i < 4; i++ { // pierwsza awaria + 3 awarie po restartach
		waitCond(t, fmt.Sprintf("OBS online (%d)", i), 15*time.Second, func() bool { return sm.Status("obs") == "online" })
		crashObs(t, port, 3)
		if i < 3 {
			waitCond(t, "OBS zakończony", 10*time.Second, func() bool { return sm.Status("obs") != "online" })
		}
	}
	waitCond(t, "limit wyczerpany", 10*time.Second, func() bool { return n.has("obs:gave_up") })
	time.Sleep(300 * time.Millisecond)
	if sm.Running("obs") {
		t.Fatal("po wyczerpaniu limitu OBS nie powinien wracać")
	}
	if r := sm.Snapshot()["obs"].(map[string]interface{})["restarts"].(int); r != 3 {
		t.Fatalf("restarty: %d (oczekiwano 3)", r)
	}
	if n.count("obs:restarted") != 3 {
		t.Fatalf("komunikaty: %v", n.list)
	}
}

func TestObsRestartCounterResetsAfterStableRun(t *testing.T) {
	useRunDir(t)
	port := freePort(t)
	sm := newTestSM(t)
	sm.stableAfter = 100 * time.Millisecond // "5 minut stabilnej pracy" w skali testu
	sm.sessionOpen = func() bool { return true }
	sm.Add(obsLikeCfg(port))
	sm.Start("obs")
	for i := 0; i < 5; i++ { // więcej awarii niż limit 3, ale każda po stabilnej pracy
		waitCond(t, "OBS online", 15*time.Second, func() bool { return sm.Status("obs") == "online" })
		time.Sleep(250 * time.Millisecond)
		first := obsPid(sm)
		crashObs(t, port, 3)
		waitCond(t, "nowy OBS", 15*time.Second, func() bool { return sm.Status("obs") == "online" && obsPid(sm) != first })
	}
	if rc := sm.Snapshot()["obs"].(map[string]interface{})["restart_count"].(int); rc > 1 {
		t.Fatalf("licznik nie zerował się po stabilnej pracy: %d", rc)
	}
}

func TestObsInitialStartIsSkippedWhenItDiedWhileHubWasDownAndSessionWasNotOpen(t *testing.T) {
	useRunDir(t)
	port := freePort(t)
	sm := newTestSM(t)
	sm.Add(obsLikeCfg(port))
	sm.SkipInitialStart("obs", "zakończył się, gdy HUB nie działał")
	sm.StartAll()
	time.Sleep(500 * time.Millisecond)
	if sm.Status("obs") != "stopped" || portOpen(port) {
		t.Fatalf("OBS został uruchomiony mimo pominięcia: %s", sm.Status("obs"))
	}
	if sm.RestartPolicy("obs") != restartSessionOpen {
		t.Fatal("polityka restartu")
	}
}

// ── obcy OBS ─────────────────────────────────────────────────────────────────

func TestForeignObsWithOpenPortIsLeftAloneAndNeverStopped(t *testing.T) {
	useRunDir(t)
	port := freePort(t)
	foreign := spawnHTTPHelper(t, port) // "OBS uruchomiony ręcznie": nie przez HUB
	sm := newTestSM(t)
	sm.externalInterval = 50 * time.Millisecond
	sm.procByName = func(name string) []int { return []int{foreign.Process.Pid} }
	sm.Add(obsLikeCfg(port))
	if err := sm.Start("obs"); err != nil {
		t.Fatal(err)
	}
	if sm.Status("obs") != "external" {
		t.Fatalf("status obcego procesu: %s", sm.Status("obs"))
	}
	if sm.StartedByHub("obs") {
		t.Fatal("obcy proces nie jest 'uruchomiony przez HUB'")
	}
	if entries := sm.StateEntries(); len(entries) != 0 {
		t.Fatalf("obcy proces nie trafia do pliku stanu: %v", entries)
	}
	if err := sm.Stop("obs"); err != nil {
		t.Fatal(err)
	}
	sm.StopAll()
	time.Sleep(200 * time.Millisecond)
	if _, ok := processCreationTime(foreign.Process.Pid); !ok || !portOpen(port) {
		t.Fatal("HUB zamknął obcy proces")
	}
	// StartAll/Start po raz drugi też nie uruchamia drugiej kopii
	sm2 := newTestSM(t)
	sm2.procByName = sm.procByName
	sm2.Add(obsLikeCfg(port))
	sm2.Start("obs")
	if sm2.Status("obs") != "external" {
		t.Fatalf("drugi menedżer: %s", sm2.Status("obs"))
	}
}

func TestForeignObsIsNotRestartedAfterItExits(t *testing.T) {
	useRunDir(t)
	port := freePort(t)
	foreign := spawnHTTPHelper(t, port)
	var alive = true
	var mu sync.Mutex
	sm := newTestSM(t)
	sm.externalInterval = 50 * time.Millisecond
	sm.sessionOpen = func() bool { return true }
	sm.procByName = func(name string) []int {
		mu.Lock()
		defer mu.Unlock()
		if alive {
			return []int{foreign.Process.Pid}
		}
		return nil
	}
	sm.Add(obsLikeCfg(port))
	sm.Start("obs")
	if sm.Status("obs") != "external" {
		t.Fatalf("status: %s", sm.Status("obs"))
	}
	killTree(foreign.Process.Pid)
	mu.Lock()
	alive = false
	mu.Unlock()
	waitCond(t, "obcy proces zakończony", 5*time.Second, func() bool { return sm.Status("obs") == "stopped" })
	time.Sleep(300 * time.Millisecond)
	if sm.Running("obs") || portOpen(port) {
		t.Fatal("HUB uruchomił OBS po zakończeniu obcego procesu")
	}
}

func TestObsProcessRunningButPortSilentReportsErrorWithoutSecondCopyAndRecovers(t *testing.T) {
	useRunDir(t)
	port := freePort(t)
	sm := newTestSM(t)
	n := &notices{}
	sm.notify = n.add
	sm.externalInterval = 50 * time.Millisecond
	sm.procByName = func(name string) []int { return []int{424242} } // proces jest, ale port milczy
	sm.Add(obsLikeCfg(port))
	if err := sm.Start("obs"); err != nil {
		t.Fatal(err)
	}
	if sm.Status("obs") != "error" {
		t.Fatalf("status: %s", sm.Status("obs"))
	}
	snap := sm.Snapshot()["obs"].(map[string]interface{})
	if snap["pid"].(int) != 0 || !strings.Contains(snap["last_error"].(string), "nie odpowiada") {
		t.Fatalf("snapshot: %v", snap)
	}
	if !n.has("obs:error") {
		t.Fatalf("moduł nie dostał błędu: %v", n.list)
	}
	time.Sleep(300 * time.Millisecond)
	if portOpen(port) || sm.Running("obs") {
		t.Fatal("uruchomiono drugą kopię mimo działającego procesu OBS")
	}
	// port zaczyna odpowiadać (OBS dokończył ładowanie): błąd znika
	ln, err := net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", port))
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()
	go http.Serve(ln, http.NotFoundHandler())
	waitCond(t, "powrót do stanu obcego", 5*time.Second, func() bool { return sm.Status("obs") == "external" })
	if !n.has("obs:recovered") {
		t.Fatalf("brak komunikatu o powrocie: %v", n.list)
	}
}

// ── czekanie na obs-ws-plugin ────────────────────────────────────────────────

type fakeGate struct {
	mu                            sync.Mutex
	declared, expected, connected bool
}

func (g *fakeGate) set(d, e, c bool) {
	g.mu.Lock()
	g.declared, g.expected, g.connected = d, e, c
	g.mu.Unlock()
}
func (g *fakeGate) get(string) (bool, bool, bool) {
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.declared, g.expected, g.connected
}

func startedSoon(sm *ServiceManager, within time.Duration) bool {
	deadline := time.Now().Add(within)
	for time.Now().Before(deadline) {
		if st := sm.Status("obs"); st == "starting" || st == "online" {
			return true
		}
		time.Sleep(20 * time.Millisecond)
	}
	return false
}

func TestObsWaitsForPluginRegistrationOnlyWhenModuleDeclaredIt(t *testing.T) {
	useRunDir(t)
	port := freePort(t)
	sm := newTestSM(t)
	g := &fakeGate{}
	sm.pluginGate = g.get
	cfg := obsLikeCfg(port)
	cfg.WaitForPlugin = "obs-ws-plugin"
	cfg.WaitForPluginS = 5
	sm.Add(cfg)
	sm.StartAll()
	if startedSoon(sm, 600*time.Millisecond) {
		t.Fatal("OBS wystartował, zanim moduł zadeklarował pluginy")
	}
	g.set(true, true, false) // plugin wymagany, jeszcze niezarejestrowany
	if startedSoon(sm, 600*time.Millisecond) {
		t.Fatal("OBS wystartował przed rejestracją obs-ws-plugin")
	}
	g.set(true, true, true)
	if !startedSoon(sm, 3*time.Second) {
		t.Fatal("OBS nie wystartował po rejestracji obs-ws-plugin")
	}
}

func TestObsStartsImmediatelyWhenModuleDidNotDeclareThePlugin(t *testing.T) {
	useRunDir(t)
	port := freePort(t)
	sm := newTestSM(t)
	g := &fakeGate{}
	g.set(true, false, false) // moduł zadeklarował pluginy, ale nie obs-ws-plugin
	sm.pluginGate = g.get
	sm.Add(obsLikeCfg(port))
	sm.StartAll()
	if !startedSoon(sm, 2*time.Second) {
		t.Fatal("OBS powinien wystartować bez czekania na plugin, którego moduł nie wymaga")
	}
}

func TestObsStartsAnywayAfterWaitTimeoutAndTellsTheModule(t *testing.T) {
	useRunDir(t)
	port := freePort(t)
	sm := newTestSM(t)
	n := &notices{}
	sm.notify = n.add
	g := &fakeGate{}
	g.set(true, true, false) // plugin wymagany i nigdy się nie rejestruje
	sm.pluginGate = g.get
	cfg := obsLikeCfg(port)
	cfg.WaitForPlugin = "obs-ws-plugin"
	cfg.WaitForPluginS = 1
	sm.Add(cfg)
	start := time.Now()
	sm.StartAll()
	if !startedSoon(sm, 5*time.Second) {
		t.Fatal("OBS nie wystartował po upływie czasu czekania")
	}
	if d := time.Since(start); d < 900*time.Millisecond {
		t.Fatalf("OBS wystartował bez czekania (%v)", d)
	}
	waitCond(t, "komunikat dla modułu", 3*time.Second, func() bool { return n.has("obs:info") })
}

func TestObsServiceDefinitionFromConfig(t *testing.T) {
	root := t.TempDir()
	c := &LoadedHubConfig{HubConfig: defaultHubConfig(), Root: root}
	c.Module = "nalf"
	c.Obs.Path = filepath.Join(root, "obs", "bin", "64bit", "obs64.exe")
	c.Obs.WsPort = 4466
	svc, ok := c.obsService()
	if !ok {
		t.Fatal("brak usługi OBS")
	}
	if svc.ExecutablePath != c.Obs.Path || svc.WorkingDir != filepath.Dir(c.Obs.Path) {
		t.Errorf("ścieżka i katalog roboczy (OBS szuka plików językowych względem katalogu roboczego): %s | %s", svc.ExecutablePath, svc.WorkingDir)
	}
	if len(svc.Args) != 1 || svc.Args[0] != "--disable-shutdown-check" {
		t.Errorf("argumenty: %v", svc.Args)
	}
	if svc.ReadyPort != 4466 || svc.ProcessName != "obs64.exe" || !svc.ForeignOK {
		t.Errorf("gotowość i obcy proces: %+v", svc)
	}
	if svc.RestartPolicy != restartSessionOpen || svc.MaxRestarts != 3 || svc.StableAfterS != 300 || !svc.RestartOnCrash {
		t.Errorf("polityka restartu: %+v", svc)
	}
	if svc.WaitForPlugin != "obs-ws-plugin" || svc.WaitForPluginS != 15 || len(svc.StartAfter) != 1 || svc.StartAfter[0] != "module" {
		t.Errorf("kolejność startu: %+v", svc)
	}
	// bez modułu OBS nie czeka na nic; wyłączony OBS nie tworzy usługi
	c.Module = ""
	if svc, _ := c.obsService(); len(svc.StartAfter) != 0 {
		t.Errorf("start_after bez modułu: %v", svc.StartAfter)
	}
	c.Obs.Enabled = false
	if _, ok := c.obsService(); ok {
		t.Error("wyłączony OBS nie powinien tworzyć usługi")
	}
}

// spawnHTTPHelper uruchamia proces pomocniczy poza menedżerem usług (jak OBS uruchomiony ręcznie) i czeka na jego port.
func spawnHTTPHelper(t *testing.T, port int) *exec.Cmd {
	t.Helper()
	cmd := exec.Command(os.Args[0], "-test.run=TestServiceHelper")
	cmd.Env = append(os.Environ(), "GO_SERVICE_HELPER=http", "HELPER_PORT="+strconv.Itoa(port))
	cmd.SysProcAttr = detachedAttr()
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { killTree(cmd.Process.Pid); cmd.Wait() })
	waitCond(t, "obcy proces nasłuchuje", 10*time.Second, func() bool { return portOpen(port) })
	return cmd
}
