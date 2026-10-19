package main

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"sync"
	"testing"
	"time"
)

// Zamykanie HUB-a a moduł i OBS (E2d2): okno główne OBS, reguły zamykania, zasada "sesja otwarta: nic nie zamykamy".

func TestSelectMainWindowRule(t *testing.T) {
	main := windowInfo{Hwnd: 10, Title: "OBS 31.0.2 - Profil: Bez nazwy - Sceny: Bez nazwy", Class: "Qt6QWindowIcon", Visible: true}
	floatingDock := windowInfo{Hwnd: 11, Title: "Sceny", Class: "Qt6QWindowToolSaveBits", Visible: true, ToolWindow: true}
	ownedDock := windowInfo{Hwnd: 12, Title: "OBS dock", Class: "Qt6QWindowIcon", Visible: true, Owner: 10, ToolWindow: true}
	hidden := windowInfo{Hwnd: 13, Title: "OBS 31.0.2 - Profil: x", Class: "Qt6QWindowIcon", Visible: false}
	dialog := windowInfo{Hwnd: 14, Title: "Ustawienia", Class: "Qt6QWindowIcon", Visible: true}
	cases := []struct {
		name string
		wins []windowInfo
		want uintptr
		ok   bool
	}{
		{"okno główne spośród doków i okien pomocniczych", []windowInfo{floatingDock, ownedDock, hidden, dialog, main}, 10, true},
		{"same doki i okna pomocnicze", []windowInfo{floatingDock, ownedDock, hidden, dialog}, 0, false},
		{"okno z tytułem OBS, ale z właścicielem", []windowInfo{ownedDock}, 0, false},
		{"brak okien", nil, 0, false},
	}
	for _, c := range cases {
		got, ok := selectMainWindow(c.wins)
		if ok != c.ok || got != c.want {
			t.Errorf("%s: (%d, %v), oczekiwano (%d, %v)", c.name, got, ok, c.want, c.ok)
		}
	}
}

// startAtrapa uruchamia atrapę OBS z oknami poza HUB-em; pomija test, gdy okien nie da się utworzyć (brak pulpitu).
func startAtrapa(t *testing.T, port int, markerDir string, extraEnv ...string) *exec.Cmd {
	t.Helper()
	cmd := exec.Command(os.Args[0], "-test.run=TestServiceHelper")
	cmd.Env = append(os.Environ(), "GO_SERVICE_HELPER=window-http", "HELPER_PORT="+strconv.Itoa(port), "HELPER_MARKER_DIR="+markerDir)
	cmd.Env = append(cmd.Env, extraEnv...)
	cmd.SysProcAttr = detachedAttr()
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { killTree(cmd.Process.Pid); cmd.Wait() })
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		if portOpen(port) {
			return cmd
		}
		if _, ok := processCreationTime(cmd.Process.Pid); !ok {
			t.Skip("atrapa OBS nie utworzyła okien (brak pulpitu?)")
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatal("atrapa OBS nie wystartowała")
	return nil
}

func fileExists(p string) bool { _, err := os.Stat(p); return err == nil }

func TestCloseMainWindowSendsWMCloseOnlyToTheMainWindow(t *testing.T) {
	markers := t.TempDir()
	atrapa := startAtrapa(t, freePort(t), markers)
	wins := windowsOfProcess(atrapa.Process.Pid)
	if len(wins) < 3 {
		t.Fatalf("atrapa powinna mieć okno główne i dwa doki, jest %d okien: %+v", len(wins), wins)
	}
	hwnd, ok := selectMainWindow(wins)
	if !ok {
		t.Fatalf("nie rozpoznano okna głównego: %+v", wins)
	}
	for _, w := range wins {
		if w.Hwnd == hwnd && (w.Class != "Qt6QWindowIcon" || w.Owner != 0 || w.ToolWindow) {
			t.Fatalf("wybrano nie to okno: %+v", w)
		}
	}
	if err := closeMainWindow(atrapa.Process.Pid); err != nil {
		t.Fatal(err)
	}
	waitCond(t, "atrapa zamknięta oknem głównym", 10*time.Second, func() bool {
		_, alive := processCreationTime(atrapa.Process.Pid)
		return !alive
	})
	if !fileExists(filepath.Join(markers, "main-got-close")) {
		t.Fatal("okno główne nie dostało WM_CLOSE")
	}
	if m, _ := filepath.Glob(filepath.Join(markers, "dock-got-close-*")); len(m) != 0 {
		t.Fatalf("WM_CLOSE trafił do doku: %v", m)
	}
}

func TestObsIsNeverKilledWhenMainWindowIgnoresClose(t *testing.T) {
	useRunDir(t)
	markers := t.TempDir()
	port := freePort(t)
	sm := newTestSM(t)
	cfg := svcCfg("obs", "window-http", port, "HELPER_MARKER_DIR="+markers, "HELPER_IGNORE_CLOSE=1")
	cfg.StopGraceS = 1
	cfg.NeverKill = true
	sm.Add(cfg)
	sm.graceful = func(id string) bool { return closeMainWindow(sm.PID(id)) == nil }
	if err := sm.Start("obs"); err != nil {
		t.Fatal(err)
	}
	waitCond(t, "atrapa online albo pominięcie", 10*time.Second, func() bool {
		if _, alive := processCreationTime(sm.PID("obs")); !alive && sm.Status("obs") != "starting" {
			t.Skip("atrapa OBS nie utworzyła okien (brak pulpitu?)")
		}
		return sm.Status("obs") == "online"
	})
	pid := sm.PID("obs")
	err := sm.Stop("obs")
	if err == nil {
		t.Fatal("zatrzymanie okna, które ignoruje zamknięcie, nie powinno się udać")
	}
	if _, alive := processCreationTime(pid); !alive {
		t.Fatal("OBS został zakończony siłą")
	}
	if !fileExists(filepath.Join(markers, "main-got-close")) {
		t.Fatal("okno główne nie dostało prośby o zamknięcie")
	}
	if !sm.Running("obs") || sm.Status("obs") == "stopped" {
		t.Fatalf("stan po nieudanym zamknięciu: %s", sm.Status("obs"))
	}
}

// ── fałszywy obs-ws-plugin ───────────────────────────────────────────────────

type fakeObsPlugin struct {
	mu     sync.Mutex
	stream bool
	record bool
	silent bool // nie odpowiada
	fail   bool // odpowiada obs_error ("OBS not connected")
	asked  []string
	stop   chan struct{}
}

func attachFakeObsPlugin(t *testing.T, hub *Hub) *fakeObsPlugin {
	t.Helper()
	f := &fakeObsPlugin{stop: make(chan struct{})}
	m := NewModule(hub, nil)
	m.ID = "obs-ws-plugin"
	m.IsActive = true
	hub.mu.Lock()
	hub.Plugins["obs-ws-plugin"] = m
	hub.mu.Unlock()
	t.Cleanup(func() { close(f.stop) })
	go func() {
		for {
			select {
			case <-f.stop:
				return
			case data := <-m.Send:
				msg, err := FromJSON(data)
				if err != nil {
					continue
				}
				rt, _ := msg.Payload["requestType"].(string)
				f.mu.Lock()
				f.asked = append(f.asked, rt)
				silent, fail, stream, record := f.silent, f.fail, f.stream, f.record
				f.mu.Unlock()
				if silent {
					continue
				}
				var reply *Message
				if fail {
					reply = NewMessage("obs-ws-plugin", "hub", "obs_error", map[string]interface{}{"error": "OBS not connected", "command": msg.Payload})
				} else {
					active := stream
					if rt == "GetRecordStatus" {
						active = record
					}
					reply = NewMessage("obs-ws-plugin", "hub", "obs_response", map[string]interface{}{
						"requestType": rt, "requestID": msg.Payload["request_id"], "responseData": map[string]interface{}{"outputActive": active},
					})
				}
				hub.handleMessage(reply)
			}
		}
	}()
	return f
}

type shutdownRig struct {
	hub      *Hub
	pm       *PluginManager
	sm       *ServiceManager
	markers  string
	modPort  int
	obsPort  int
	plugin   *fakeObsPlugin
	statePth string
}

// newShutdownRig buduje HUB z modułem (usługa pomocnicza), OBS (atrapa z oknami uruchomiona przez HUB), timer-pluginem i fałszywym obs-ws-pluginem.
func newShutdownRig(t *testing.T, withPlugin bool) *shutdownRig {
	t.Helper()
	useRunDir(t)
	hub, pm := newTestPM(t, "timer-plugin")
	sm := newTestSM(t)
	hub.Services = sm
	r := &shutdownRig{hub: hub, pm: pm, sm: sm, markers: t.TempDir(), modPort: freePort(t), obsPort: freePort(t)}
	sm.graceful = hub.gracefulStopService
	r.statePth = filepath.Join(t.TempDir(), "uslugi.json")
	hub.State = NewStateStore(r.statePth)
	sm.persist = hub.persistState
	pm.persist = hub.persistState
	hub.session.onChange = func(SessionStatus) { hub.persistState() }
	hub.RestoreFromState()

	mod := svcCfg("module", "http", r.modPort)
	sm.Add(mod)
	obs := svcCfg("obs", "window-http", r.obsPort, "HELPER_MARKER_DIR="+r.markers)
	obs.StopGraceS = 5
	obs.NeverKill = true
	obs.ForeignOK = true
	sm.Add(obs)

	if err := sm.Start("module"); err != nil {
		t.Fatal(err)
	}
	if err := sm.Start("obs"); err != nil {
		t.Fatal(err)
	}
	waitCond(t, "moduł i OBS online", 15*time.Second, func() bool {
		if _, alive := processCreationTime(sm.PID("obs")); !alive && sm.Status("obs") == "error" {
			t.Skip("atrapa OBS nie utworzyła okien (brak pulpitu?)")
		}
		return sm.Status("module") == "online" && sm.Status("obs") == "online"
	})
	if err := pm.StartPlugin("timer-plugin"); err != nil {
		t.Fatal(err)
	}
	if withPlugin {
		r.plugin = attachFakeObsPlugin(t, hub)
	}
	return r
}

func (r *shutdownRig) session(state string) {
	r.hub.handleMessage(mainModuleMsg(r.hub, map[string]interface{}{"state": state, "session_id": float64(1)}))
}

func (r *shutdownRig) alive(id string) bool {
	_, ok := processCreationTime(r.sm.PID(id))
	return r.sm.PID(id) != 0 && ok
}

func (r *shutdownRig) stateHas(kind, id string) bool {
	f, err := NewStateStore(r.statePth).Load()
	return err == nil && f != nil && f.find(kind, id) != nil
}

func TestShutdownWithOpenSessionLeavesModuleAndObsRunningAndStopsPlugins(t *testing.T) {
	for _, state := range []string{"preparation", "on_air"} {
		t.Run(state, func(t *testing.T) {
			r := newShutdownRig(t, true)
			r.session(state)
			pluginPid := pidOf(r.pm, "timer-plugin")
			modPid, obsPid := r.sm.PID("module"), r.sm.PID("obs")
			r.hub.Shutdown()
			time.Sleep(300 * time.Millisecond)
			if _, ok := processCreationTime(modPid); !ok || !portOpen(r.modPort) {
				t.Fatal("moduł został zatrzymany mimo otwartej sesji")
			}
			if _, ok := processCreationTime(obsPid); !ok || !portOpen(r.obsPort) {
				t.Fatal("OBS został zatrzymany mimo otwartej sesji")
			}
			if fileExists(filepath.Join(r.markers, "main-got-close")) {
				t.Fatal("OBS dostał prośbę o zamknięcie mimo otwartej sesji")
			}
			if _, ok := processCreationTime(pluginPid); ok {
				t.Fatal("plugin lokalny nie został zatrzymany")
			}
			// plik stanu zostaje z wpisami usług (kolejny HUB je przejmie), bez wpisu zatrzymanego pluginu
			if !r.stateHas("service", "module") || !r.stateHas("service", "obs") || r.stateHas("plugin", "timer-plugin") {
				t.Fatal("plik stanu po zamknięciu nie opisuje działających usług")
			}
			if len(r.plugin.asked) != 0 {
				t.Fatalf("HUB pytał obs-ws-plugin o stream mimo otwartej sesji: %v", r.plugin.asked)
			}
		})
	}
}

func TestShutdownWithUnknownSessionStatusLeavesEverythingRunning(t *testing.T) {
	r := newShutdownRig(t, true) // moduł nic nie zgłosił
	modPid, obsPid := r.sm.PID("module"), r.sm.PID("obs")
	r.hub.Shutdown()
	time.Sleep(300 * time.Millisecond)
	if _, ok := processCreationTime(modPid); !ok {
		t.Fatal("moduł zatrzymany przy nieznanym statusie sesji")
	}
	if _, ok := processCreationTime(obsPid); !ok {
		t.Fatal("OBS zatrzymany przy nieznanym statusie sesji")
	}
}

func TestShutdownWithClosedSessionClosesModuleAndObsGracefully(t *testing.T) {
	r := newShutdownRig(t, true)
	r.session("none")
	modPid, obsPid := r.sm.PID("module"), r.sm.PID("obs")
	r.hub.Shutdown()
	for name, pid := range map[string]int{"moduł": modPid, "OBS": obsPid} {
		if _, ok := processCreationTime(pid); ok {
			t.Fatalf("%s nadal działa po zamknięciu HUB-a przy zamkniętej sesji", name)
		}
	}
	if portOpen(r.modPort) || portOpen(r.obsPort) {
		t.Fatal("porty usług nie zostały zwolnione")
	}
	if !fileExists(filepath.Join(r.markers, "main-got-close")) {
		t.Fatal("OBS nie został zamknięty przez okno główne (WM_CLOSE)")
	}
	if m, _ := filepath.Glob(filepath.Join(r.markers, "dock-got-close-*")); len(m) != 0 {
		t.Fatalf("zamknięcie trafiło do doku: %v", m)
	}
	if len(r.plugin.asked) != 2 {
		t.Fatalf("HUB powinien zapytać o stream i nagrywanie: %v", r.plugin.asked)
	}
	if r.stateHas("service", "module") || r.stateHas("service", "obs") {
		t.Fatal("zatrzymane usługi zostały w pliku stanu")
	}
}

func TestShutdownLeavesObsWhenStreamOrRecordingMayBeRunning(t *testing.T) {
	cases := []struct {
		name  string
		setup func(r *shutdownRig)
	}{
		{"trwa stream", func(r *shutdownRig) { r.plugin.stream = true }},
		{"trwa nagrywanie", func(r *shutdownRig) { r.plugin.record = true }},
		{"plugin nie odpowiada", func(r *shutdownRig) { r.plugin.silent = true }},
		{"plugin zgłasza błąd OBS", func(r *shutdownRig) { r.plugin.fail = true }},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			r := newShutdownRig(t, true)
			r.session("none")
			c.setup(r)
			modPid, obsPid := r.sm.PID("module"), r.sm.PID("obs")
			start := time.Now()
			r.hub.Shutdown()
			if _, ok := processCreationTime(obsPid); !ok || !portOpen(r.obsPort) {
				t.Fatal("OBS został zamknięty, choć stream/nagrywanie mogło trwać")
			}
			if fileExists(filepath.Join(r.markers, "main-got-close")) {
				t.Fatal("OBS dostał prośbę o zamknięcie")
			}
			if _, ok := processCreationTime(modPid); ok {
				t.Fatal("moduł powinien zostać zatrzymany (sesja zamknięta)")
			}
			if d := time.Since(start); d > 12*time.Second {
				t.Fatalf("zamykanie trwało zbyt długo: %v", d)
			}
			if !r.stateHas("service", "obs") {
				t.Fatal("OBS zostaje uruchomiony, więc ma zostać w pliku stanu (do przejęcia)")
			}
		})
	}
}

func TestShutdownLeavesObsWhenPluginIsNotConnected(t *testing.T) {
	r := newShutdownRig(t, false) // brak obs-ws-plugin
	r.session("none")
	obsPid := r.sm.PID("obs")
	r.hub.Shutdown()
	if _, ok := processCreationTime(obsPid); !ok {
		t.Fatal("OBS zamknięty bez możliwości sprawdzenia streamu")
	}
}

func TestShutdownNeverClosesForeignObs(t *testing.T) {
	useRunDir(t)
	markers := t.TempDir()
	obsPort := freePort(t)
	foreign := startAtrapa(t, obsPort, markers) // OBS uruchomiony ręcznie, nie przez HUB
	hub, _ := newTestPM(t, "timer-plugin")
	sm := newTestSM(t)
	hub.Services = sm
	sm.graceful = hub.gracefulStopService
	sm.externalInterval = 50 * time.Millisecond
	sm.procByName = func(string) []int { return []int{foreign.Process.Pid} }
	cfg := svcCfg("obs", "window-http", obsPort)
	cfg.ForeignOK = true
	cfg.ProcessName = "obs-atrapa.exe"
	sm.Add(cfg)
	sm.Start("obs")
	if sm.Status("obs") != "external" {
		t.Fatalf("status: %s", sm.Status("obs"))
	}
	attachFakeObsPlugin(t, hub)
	hub.handleMessage(mainModuleMsg(hub, map[string]interface{}{"state": "none"}))
	hub.Shutdown()
	time.Sleep(300 * time.Millisecond)
	if _, ok := processCreationTime(foreign.Process.Pid); !ok {
		t.Fatal("HUB zamknął obcy OBS")
	}
	if fileExists(filepath.Join(markers, "main-got-close")) {
		t.Fatal("obcy OBS dostał prośbę o zamknięcie")
	}
}

func TestHubAddressedResponsesAreMatchedByIdOrByRequestType(t *testing.T) {
	hub := NewHub(0, false, false)
	f := attachFakeObsPlugin(t, hub)
	resp, err := hub.RequestPlugin("obs-ws-plugin", "obs_command", "GetStreamStatus", nil, time.Second)
	if err != nil || resp.Type != "obs_response" {
		t.Fatalf("odpowiedź: %v %v", resp, err)
	}
	f.mu.Lock()
	f.fail = true
	f.mu.Unlock()
	resp, err = hub.RequestPlugin("obs-ws-plugin", "obs_command", "GetRecordStatus", nil, time.Second)
	if err != nil || resp.Type != "obs_error" {
		t.Fatalf("błąd OBS powinien dojść do pytającego (identyfikator w command): %v %v", resp, err)
	}
	f.mu.Lock()
	f.silent = true
	f.mu.Unlock()
	if _, err := hub.RequestPlugin("obs-ws-plugin", "obs_command", "GetStreamStatus", nil, 200*time.Millisecond); err == nil {
		t.Fatal("brak odpowiedzi powinien dać błąd po czasie")
	}
	// plugin niepołączony
	if _, err := hub.RequestPlugin("nie-ma", "obs_command", "GetStreamStatus", nil, 100*time.Millisecond); err == nil {
		t.Fatal("pytanie do niepołączonego pluginu powinno zwrócić błąd")
	}
	// odpowiedź nikomu niezaadresowana nie jest "przyjęta"
	stray := NewMessage("obs-ws-plugin", "hub", "obs_response", map[string]interface{}{"requestType": "GetStreamStatus", "requestID": "hub-999"})
	if hub.handleHubAddressed(stray) {
		t.Fatal("zbłąkana odpowiedź została uznana za odpowiedź na pytanie")
	}
	_ = json.Marshal
}
