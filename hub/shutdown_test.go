package main

import (
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func pidAlive(pid int) bool {
	out, _ := exec.Command("tasklist", "/FI", "PID eq "+strconv.Itoa(pid), "/NH").Output()
	return strings.Contains(string(out), strconv.Itoa(pid))
}

// E2d1: od początku zamykania HUB nie planuje ani nie wykonuje żadnych restartów. Plugin kończy się sam w trakcie zamykania
// (Ctrl+C z konsoli trafia do całej grupy procesów), moduł zamyka się 5 s; po zamknięciu nie ma procesu pluginu.
func TestShutdownDoesNotRestartPluginKilledWhileServiceIsStopping(t *testing.T) {
	useRunDir(t)
	hub, pm := newTestPM(t, "timer-plugin")
	sm := newTestSM(t)
	hub.Services = sm
	slow := svcCfg("module", "sleep", 0)
	slow.StopGraceS = 5 // usługa ignoruje prośbę o zamknięcie: zatrzymanie trwa 5 s, potem wymuszenie
	sm.Add(slow)
	sm.graceful = func(id string) bool { return true }

	if err := sm.Start("module"); err != nil {
		t.Fatal(err)
	}
	if err := pm.StartPlugin("timer-plugin"); err != nil {
		t.Fatal(err)
	}
	waitFor(t, "plugin działa", func() bool { return pidOf(pm, "timer-plugin") != 0 })
	pluginPid := pidOf(pm, "timer-plugin")

	done := make(chan struct{})
	go func() { hub.Shutdown(); close(done) }()
	time.Sleep(300 * time.Millisecond) // zamykanie trwa (moduł jeszcze się zatrzymuje)

	// plugin kończy się sam, jakby dostał Ctrl+C z konsoli, zanim HUB zdążył go zatrzymać
	pm.mu.RLock()
	proc := pm.plugins["timer-plugin"].Process
	pm.mu.RUnlock()
	proc.Process.Kill()

	select {
	case <-done:
	case <-time.After(20 * time.Second):
		t.Fatal("zamykanie HUB-a trwa zbyt długo")
	}
	time.Sleep(500 * time.Millisecond) // czas, w którym zaplanowany restart (RestartDelay 10 ms) mógłby się wykonać

	pm.mu.RLock()
	restarts := pm.plugins["timer-plugin"].Restarts
	cur := pm.plugins["timer-plugin"].Process
	pm.mu.RUnlock()
	if restarts != 0 {
		t.Fatalf("plugin został uruchomiony ponownie w trakcie zamykania (Restarts=%d)", restarts)
	}
	if pidAlive(pluginPid) {
		t.Fatalf("proces pluginu %d żyje po zamknięciu HUB-a", pluginPid)
	}
	if cur != nil && cur.Process != nil && cur.Process.Pid != pluginPid && pidAlive(cur.Process.Pid) {
		t.Fatalf("po zamknięciu HUB-a żyje nowy proces pluginu %d", cur.Process.Pid)
	}
	if pidAlive(sm.services["module"].pid) {
		t.Fatal("moduł (usługa) nadal żyje")
	}
}

func TestStartsAreRefusedAfterBeginShutdown(t *testing.T) {
	useRunDir(t)
	_, pm := newTestPM(t, "timer-plugin")
	sm := newTestSM(t)
	sm.Add(svcCfg("module", "sleep", 0))
	pm.BeginShutdown()
	sm.BeginShutdown()
	if err := pm.StartPlugin("timer-plugin"); err == nil {
		t.Fatal("start pluginu po rozpoczęciu zamykania powinien być odrzucony")
	}
	if err := pm.RestartPlugin("timer-plugin", true); err == nil {
		t.Fatal("ręczny restart pluginu po rozpoczęciu zamykania powinien być odrzucony")
	}
	if pidOf(pm, "timer-plugin") != 0 {
		t.Fatal("powstał proces pluginu")
	}
	if err := sm.Start("module"); err == nil {
		t.Fatal("start usługi po rozpoczęciu zamykania powinien być odrzucony")
	}
}

func TestOutputFileIsRotatedWhenLargeAtStart(t *testing.T) {
	dir := useRunDir(t)
	path := filepath.Join(dir, "modul-x.wyjscie.log")
	big := make([]byte, logMaxBytes+10)
	writeFile(t, path, string(big))
	f, _, err := openServiceOutput("modul-x.wyjscie.log")
	if err != nil {
		t.Fatal(err)
	}
	f.Close()
	if fileSize(path) > 1024 {
		t.Fatalf("nowy plik wyjścia nie jest mały: %d", fileSize(path))
	}
	if fileSize(path+".1") != int64(len(big)) {
		t.Fatalf("poprzedni plik nie został przesunięty do .1: %d", fileSize(path+".1"))
	}
}

func TestModuleLabelShowsLogName(t *testing.T) {
	c := &LoadedHubConfig{HubConfig: defaultHubConfig()}
	c.Module = "nalf"
	if got := c.ModuleLabel(); got != "nalf (futsal_nalf)" {
		t.Fatalf("etykieta: %q", got)
	}
	c.Module = "garbarnia"
	if got := c.ModuleLabel(); got != "garbarnia" {
		t.Fatalf("etykieta: %q", got)
	}
}
