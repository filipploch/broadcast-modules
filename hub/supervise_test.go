package main

import (
	"bytes"
	"log"
	"os"
	"strings"
	"testing"
	"time"
)

// TestHelperProcess jest "pluginem" uruchamianym przez testy (ten sam plik wykonywalny co testy).
func TestHelperProcess(t *testing.T) {
	switch os.Getenv("GO_WANT_HELPER_PLUGIN") {
	case "sleep":
		time.Sleep(60 * time.Second)
	case "exit":
		os.Exit(1)
	}
}

func newTestPM(t *testing.T, ids ...string) (*Hub, *PluginManager) {
	t.Helper()
	hub := NewHub(0, false, false)
	pm := NewPluginManager(hub)
	hub.PluginManager = pm
	for _, id := range ids {
		pm.plugins[id] = &PluginProcess{
			Status: "stopped",
			Config: PluginConfig{
				ID: id, Type: "local", ExecutablePath: os.Args[0],
				Args: []string{"-test.run=TestHelperProcess"}, Env: []string{"GO_WANT_HELPER_PLUGIN=sleep"},
				RestartOnCrash: true, MaxRestarts: 3, RestartDelay: 10,
			},
		}
		pm.allConfigs[id] = pm.plugins[id].Config
	}
	t.Cleanup(pm.StopAllPlugins)
	return hub, pm
}

func pidOf(pm *PluginManager, id string) int {
	pm.mu.RLock()
	defer pm.mu.RUnlock()
	if p := pm.plugins[id]; p != nil && p.Process != nil && p.Process.Process != nil {
		return p.Process.Process.Pid
	}
	return 0
}

func restartsOf(pm *PluginManager, id string) int {
	pm.mu.RLock()
	defer pm.mu.RUnlock()
	return pm.plugins[id].RestartCount
}

func waitFor(t *testing.T, what string, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if cond() {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("nie doczekano: %s", what)
}

func connect(hub *Hub, pm *PluginManager, id string) {
	m := NewModule(hub, nil)
	m.ID = id
	m.IsActive = true
	hub.mu.Lock()
	hub.Plugins[id] = m
	hub.mu.Unlock()
	pm.UpdatePluginStatus(id, "online")
}

func TestManualRestartIgnoresLimitAndDoesNotCount(t *testing.T) {
	_, pm := newTestPM(t, "timer-plugin")
	if err := pm.StartPlugin("timer-plugin"); err != nil {
		t.Fatal(err)
	}
	pid := pidOf(pm, "timer-plugin")
	for i := 0; i < 5; i++ { // więcej niż max_restarts (3)
		if err := pm.RestartPlugin("timer-plugin", true); err != nil {
			t.Fatalf("restart ręczny %d: %v", i, err)
		}
	}
	if got := pidOf(pm, "timer-plugin"); got == 0 || got == pid {
		t.Fatalf("proces nie został uruchomiony od nowa (pid %d -> %d)", pid, got)
	}
	if n := restartsOf(pm, "timer-plugin"); n != 1 {
		t.Fatalf("restarty ręczne nie mogą zwiększać licznika: %d", n)
	}
}

func TestManualStopDoesNotTriggerAutoRestart(t *testing.T) {
	_, pm := newTestPM(t, "timer-plugin")
	pm.StartPlugin("timer-plugin")
	if err := pm.StopPlugin("timer-plugin"); err != nil {
		t.Fatal(err)
	}
	time.Sleep(300 * time.Millisecond) // dłużej niż restart_delay_ms
	if pidOf(pm, "timer-plugin") != 0 {
		t.Fatal("plugin zatrzymany przez HUB został uruchomiony ponownie przez monitor")
	}
}

func TestSuperviseRestartsPluginThatNeverRegistered(t *testing.T) {
	hub, pm := newTestPM(t, "timer-plugin")
	hub.ExpectedPlugins["timer-plugin"] = true
	pm.StartPlugin("timer-plugin")
	pid := pidOf(pm, "timer-plugin")

	t0 := time.Now()
	pm.superviseOnce(t0)                      // zauważenie kłopotu
	pm.superviseOnce(t0.Add(5 * time.Second)) // jeszcze w czasie na rejestrację
	if pidOf(pm, "timer-plugin") != pid {
		t.Fatal("restart przed upływem czasu na rejestrację")
	}
	pm.superviseOnce(t0.Add(20 * time.Second))
	waitFor(t, "restart po braku rejestracji", func() bool { p := pidOf(pm, "timer-plugin"); return p != 0 && p != pid })
	if n := restartsOf(pm, "timer-plugin"); n != 2 {
		t.Fatalf("samonaprawa liczy się do limitu: oczekiwano 2, jest %d", n)
	}
}

func TestSuperviseRestartsPluginThatRegisteredThenDisconnected(t *testing.T) {
	hub, pm := newTestPM(t, "timer-plugin")
	hub.ExpectedPlugins["timer-plugin"] = true
	pm.StartPlugin("timer-plugin")
	connect(hub, pm, "timer-plugin")
	pid := pidOf(pm, "timer-plugin")

	t0 := time.Now()
	pm.superviseOnce(t0)
	if pidOf(pm, "timer-plugin") != pid {
		t.Fatal("połączony plugin nie może być ruszany")
	}
	hub.mu.Lock()
	delete(hub.Plugins, "timer-plugin") // rozłączył się, proces żyje
	hub.mu.Unlock()
	pm.UpdatePluginStatus("timer-plugin", "offline")

	pm.superviseOnce(t0.Add(time.Second))
	pm.superviseOnce(t0.Add(20 * time.Second))
	waitFor(t, "restart po rozłączeniu", func() bool { p := pidOf(pm, "timer-plugin"); return p != 0 && p != pid })
}

func TestSuperviseStartsRequiredPluginWithoutProcess(t *testing.T) {
	hub, pm := newTestPM(t, "timer-plugin")
	hub.ExpectedPlugins["timer-plugin"] = true

	t0 := time.Now()
	pm.superviseOnce(t0)
	pm.superviseOnce(t0.Add(10 * time.Second))
	waitFor(t, "start pluginu bez procesu", func() bool { return pidOf(pm, "timer-plugin") != 0 })
}

func TestSuperviseIgnoresPluginsNotRequired(t *testing.T) {
	_, pm := newTestPM(t, "replay-plugin")
	t0 := time.Now()
	pm.superviseOnce(t0)
	pm.superviseOnce(t0.Add(time.Minute))
	time.Sleep(100 * time.Millisecond)
	if pidOf(pm, "replay-plugin") != 0 {
		t.Fatal("nadzór uruchomił plugin, którego moduł nie wymaga")
	}
}

func TestSuperviseStopsAtRestartLimit(t *testing.T) {
	hub, pm := newTestPM(t, "timer-plugin")
	hub.ExpectedPlugins["timer-plugin"] = true
	pm.plugins["timer-plugin"].RestartCount = 3 // max_restarts
	t0 := time.Now()
	pm.superviseOnce(t0)
	pm.superviseOnce(t0.Add(time.Minute))
	time.Sleep(100 * time.Millisecond)
	if pidOf(pm, "timer-plugin") != 0 {
		t.Fatal("nadzór przekroczył limit restartów")
	}
}

func TestSuperviseResetsCounterAfterStableRun(t *testing.T) {
	hub, pm := newTestPM(t, "timer-plugin")
	hub.ExpectedPlugins["timer-plugin"] = true
	pm.StartPlugin("timer-plugin")
	connect(hub, pm, "timer-plugin")
	pm.mu.Lock()
	pm.plugins["timer-plugin"].RestartCount = 2
	pm.plugins["timer-plugin"].StartedAt = time.Now().Add(-5 * time.Minute)
	pm.mu.Unlock()
	pm.superviseOnce(time.Now())
	if n := restartsOf(pm, "timer-plugin"); n != 0 {
		t.Fatalf("licznik po stabilnej pracy powinien być zerowy: %d", n)
	}
}

func TestRestartPluginCommandFromMainModule(t *testing.T) {
	hub, _ := newTestPM(t, "timer-plugin")
	main := newMainModule(hub)

	msg := NewMessage(main.ID, "hub", "restart_plugin", map[string]interface{}{"plugin_id": "timer-plugin"})
	msg.Source = main
	hub.handleMessage(msg)
	waitFor(t, "odpowiedź plugin_restart_result", func() bool { return len(main.Send) > 0 })
	got := readSent(t, main)
	if got.Type != "plugin_restart_result" || got.Payload["ok"] != true || got.Payload["plugin_id"] != "timer-plugin" {
		t.Fatalf("zła odpowiedź: %+v", got)
	}

	msg = NewMessage(main.ID, "hub", "restart_plugin", map[string]interface{}{"plugin_id": "stream-overlay"})
	msg.Source = main
	hub.handleMessage(msg)
	waitFor(t, "odpowiedź dla nakładki", func() bool { return len(main.Send) > 0 })
	if got = readSent(t, main); got.Payload["ok"] != false || got.Payload["error"] == "" {
		t.Fatalf("restart nakładki powinien zwrócić błąd: %+v", got)
	}
}

func TestRestartPluginIgnoredFromNonMainModule(t *testing.T) {
	hub, _ := newTestPM(t, "timer-plugin")
	other := NewModule(hub, nil)
	other.ID = "obs-ws-plugin"
	other.ComponentType = "plugin"
	msg := NewMessage(other.ID, "hub", "restart_plugin", map[string]interface{}{"plugin_id": "timer-plugin"})
	msg.Source = other
	hub.handleMessage(msg)
	time.Sleep(100 * time.Millisecond)
	if len(other.Send) != 0 {
		t.Fatal("plugin nie może restartować pluginów")
	}
}

// Brak heartbeatu u pluginu niewymaganego (nakładka w OBS) daje jeden wpis w logu, a nie powtarzany co kontrolę.
func TestHealthMonitorReportsMissingHeartbeatOncePerEpisode(t *testing.T) {
	var buf bytes.Buffer
	log.SetOutput(&buf)
	defer log.SetOutput(os.Stderr)

	hub := NewHub(0, false, true)
	m := NewModule(hub, nil)
	m.ID = "stream-overlay"
	m.IsActive = true
	hub.Plugins[m.ID] = m
	hm := hub.HealthMonitor
	hm.RegisterPlugin(m.ID)
	hm.pluginHealth[m.ID].LastHeartbeat = time.Now().Add(-time.Hour)

	for i := 0; i < 12; i++ {
		hm.checkPluginHealth(m.ID)
	}
	if n := strings.Count(buf.String(), "exceeded max failures"); n != 1 {
		t.Fatalf("raport przekroczenia limitu powinien być jeden, jest %d", n)
	}

	// po powrocie heartbeatu i kolejnym zaniku — nowy epizod, nowy raport
	hm.UpdateHeartbeat(m.ID)
	hm.pluginHealth[m.ID].LastHeartbeat = time.Now().Add(-time.Hour)
	for i := 0; i < 5; i++ {
		hm.checkPluginHealth(m.ID)
	}
	if n := strings.Count(buf.String(), "exceeded max failures"); n != 2 {
		t.Fatalf("nowy epizod powinien dać drugi raport, jest %d", n)
	}
}
