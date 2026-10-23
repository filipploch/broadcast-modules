package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

// wpFixture to tymczasowe repozytorium z dwoma modułami (z blokiem wp) i kompletną (pustą) instalacją WP.
type wpFixture struct {
	t     *testing.T
	root  string
	cfg   *LoadedHubConfig
	mgr   *wpManager
	fake  *fakeWpOS
	mu    sync.Mutex
	notes []string
	// uruchomione procesy: pid -> kanał zakończenia
	procs    map[int]chan error
	launched []wpCommand
	nextPID  int
	failNext error
}

func newWpFixture(t *testing.T) *wpFixture {
	t.Helper()
	root := t.TempDir()
	f := &wpFixture{t: t, root: root, procs: map[int]chan error{}, nextPID: 1000,
		fake: &fakeWpOS{listeners: map[int]int{}, ours: map[int]bool{}}}
	writeManifest(t, filepath.Join(root, "modules"), "nalf", `{"format":1,"id":"nalf","button":"NALF","script":"n.py","port":8081,"wp":{"port":8091}}`)
	writeManifest(t, filepath.Join(root, "modules"), "garb", `{"format":1,"id":"garbarnia","button":"GARB","script":"g.py","port":8081,"wp":{"port":8092}}`)
	writeManifest(t, filepath.Join(root, "modules"), "bez", `{"format":1,"id":"bezwp","button":"BEZ","script":"b.py","port":8081}`)
	p := wpPaths{Dir: filepath.Join(root, "wp-local")}
	p.Php, p.Cli, p.Site, p.DbBase = filepath.Join(p.Dir, "php", "php.exe"), filepath.Join(p.Dir, "wp-cli.phar"),
		filepath.Join(p.Dir, "wordpress"), filepath.Join(p.Dir, "databases")
	os.MkdirAll(filepath.Dir(p.Php), 0o755)
	os.WriteFile(p.Php, nil, 0o644)
	os.WriteFile(p.Cli, nil, 0o644)
	os.MkdirAll(p.Site, 0o755)
	os.WriteFile(filepath.Join(p.Site, "wp-config.php"), nil, 0o644)
	os.MkdirAll(filepath.Join(p.DbBase, "_szablon"), 0o755)
	os.WriteFile(filepath.Join(p.DbBase, "_szablon", ".ht.sqlite"), []byte("szablon"), 0o644)
	f.cfg = &LoadedHubConfig{Root: root}
	f.cfg.HubConfig = defaultHubConfig()
	f.mgr = newWpManager(f.cfg, func(kind, msg string) {
		f.mu.Lock()
		f.notes = append(f.notes, kind+": "+msg)
		f.mu.Unlock()
	})
	f.mgr.sysFor = func(wpPaths) wpOS { return f.fake.os() }
	f.mgr.readyWait = 2 * time.Second
	f.mgr.delay = 10 * time.Millisecond
	f.mgr.launch = f.launch
	return f
}

// launch udaje start procesu: zajmuje port z polecenia (jako nasz php.exe) i czeka na zakończenie.
func (f *wpFixture) launch(c wpCommand, outName string) (*wpProc, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.failNext != nil {
		err := f.failNext
		f.failNext = nil
		return nil, err
	}
	f.nextPID++
	pid := f.nextPID
	var port int
	for _, a := range c.Args {
		if strings.HasPrefix(a, "--port=") {
			fmt.Sscanf(a, "--port=%d", &port)
		}
	}
	f.fake.listeners[port] = pid
	f.fake.ours[pid] = true
	ch := make(chan error, 1)
	f.procs[pid] = ch
	f.launched = append(f.launched, c)
	return &wpProc{pid: pid, wait: func() error { return <-ch }}, nil
}

// crash: proces WP kończy się sam (awaria).
func (f *wpFixture) crash(pid int) {
	f.mu.Lock()
	for port, p := range f.fake.listeners {
		if p == pid {
			delete(f.fake.listeners, port)
		}
	}
	ch := f.procs[pid]
	f.mu.Unlock()
	ch <- fmt.Errorf("exit status 255")
}

func (f *wpFixture) notices() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]string(nil), f.notes...)
}

func (f *wpFixture) launchCount() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return len(f.launched)
}

func TestWpEnsureStartsInstanceWithBlockParameters(t *testing.T) {
	f := newWpFixture(t)
	f.mgr.ensureFor("nalf")
	if f.launchCount() != 1 {
		t.Fatalf("uruchomień: %d, powiadomienia %v", f.launchCount(), f.notices())
	}
	paths := f.cfg.wpPaths()
	m, _ := f.mgr.catalog().Get("nalf")
	// to samo polecenie, które składa plik .bat (hub.exe wp nalf): jedna funkcja command
	if got, want := f.launched[0].String(), paths.command(*m.Wp).String(); got != want {
		t.Fatalf("polecenie HUB-a różni się od polecenia .bat:\nHUB: %s\n.bat: %s", got, want)
	}
	if _, err := os.Stat(filepath.Join(paths.DbBase, "p8091", ".ht.sqlite")); err != nil {
		t.Fatalf("baza z szablonu nie powstała: %v", err)
	}
	v := f.mgr.view()
	if v.ModuleID != "nalf" || v.Port != 8091 || v.PID == 0 || v.Adopted || len(f.notices()) != 1 || f.notices()[0] != "recovered: " {
		t.Fatalf("widok %+v, powiadomienia %v", v, f.notices())
	}
}

func TestWpEnsureAdoptsRunningOwnInstanceAndStopKillsIt(t *testing.T) {
	f := newWpFixture(t)
	f.fake.listeners[8091], f.fake.ours[400] = 400, true
	f.mgr.ensureFor("nalf")
	if f.launchCount() != 0 {
		t.Fatal("właściwa instancja ma zostać bez restartu")
	}
	if v := f.mgr.view(); !v.Adopted || v.PID != 400 {
		t.Fatalf("widok: %+v", v)
	}
	f.mgr.stopFor("nalf")
	if len(f.fake.killed) != 1 || f.fake.killed[0] != 400 {
		t.Fatalf("zatrzymanie modułu ma zamknąć przejętą instancję: %v", f.fake.killed)
	}
}

func TestWpEnsureClosesOtherModulesInstanceThenStarts(t *testing.T) {
	f := newWpFixture(t)
	f.fake.listeners[8092], f.fake.ours[500] = 500, true
	f.mgr.ensureFor("nalf")
	if len(f.fake.killed) != 1 || f.fake.killed[0] != 500 || f.launchCount() != 1 {
		t.Fatalf("zamknięto %v, uruchomień %d", f.fake.killed, f.launchCount())
	}
}

func TestWpEnsureWarnsButNeverFails(t *testing.T) {
	// moduł bez bloku wp: nic się nie dzieje
	f := newWpFixture(t)
	f.mgr.ensureFor("bezwp")
	if f.launchCount() != 0 {
		t.Fatal("moduł bez bloku wp nie uruchamia WP")
	}
	// brak instalacji
	f = newWpFixture(t)
	os.Remove(f.cfg.wpPaths().Php)
	f.mgr.ensureFor("nalf")
	if f.launchCount() != 0 || !strings.Contains(strings.Join(f.notices(), "|"), "warning: WP modułu nalf nie wystartuje") {
		t.Fatalf("brak PHP: %v", f.notices())
	}
	// obcy proces na własnym porcie
	f = newWpFixture(t)
	f.fake.listeners[8091] = 777
	f.mgr.ensureFor("nalf")
	if f.launchCount() != 0 || len(f.fake.killed) != 0 || !strings.Contains(strings.Join(f.notices(), "|"), "warning") {
		t.Fatalf("obcy proces: uruchomień %d, zamknięto %v, %v", f.launchCount(), f.fake.killed, f.notices())
	}
	// błąd startu procesu
	f = newWpFixture(t)
	f.failNext = fmt.Errorf("brak uprawnień")
	f.mgr.ensureFor("nalf")
	if !strings.Contains(strings.Join(f.notices(), "|"), "warning: WP modułu nalf nie wystartował: brak uprawnień") {
		t.Fatalf("błąd startu: %v", f.notices())
	}
	// brak szablonu i bazy
	f = newWpFixture(t)
	os.Remove(filepath.Join(f.cfg.wpPaths().DbBase, "_szablon", ".ht.sqlite"))
	f.mgr.ensureFor("nalf")
	if f.launchCount() != 0 || !strings.Contains(strings.Join(f.notices(), "|"), "warning") {
		t.Fatalf("brak szablonu: %v", f.notices())
	}
}

func TestWpRestartsAfterCrashThenGivesUp(t *testing.T) {
	f := newWpFixture(t)
	f.mgr.ensureFor("nalf")
	for i := 1; i <= wpMaxRestarts; i++ {
		f.mu.Lock()
		pid := f.fake.listeners[8091]
		f.mu.Unlock()
		f.crash(pid)
		waitWp(t, func() bool { return f.launchCount() == i+1 }, "restart po awarii")
	}
	f.mu.Lock()
	pid := f.fake.listeners[8091]
	f.mu.Unlock()
	f.crash(pid)
	waitWp(t, func() bool { return strings.Contains(strings.Join(f.notices(), "|"), "error: WP modułu nalf przestał działać") }, "komunikat o limicie")
	if f.launchCount() != wpMaxRestarts+1 {
		t.Fatalf("uruchomień: %d", f.launchCount())
	}
}

func TestWpStopDoesNotRestart(t *testing.T) {
	f := newWpFixture(t)
	f.mgr.ensureFor("nalf")
	f.mu.Lock()
	pid := f.fake.listeners[8091]
	f.mu.Unlock()
	f.mgr.stopFor("nalf")
	f.crash(pid) // proces kończy się po zabiciu
	time.Sleep(150 * time.Millisecond)
	if f.launchCount() != 1 {
		t.Fatalf("zamierzone zatrzymanie nie może wywołać restartu: %d uruchomień", f.launchCount())
	}
	// obcy proces na porcie nie jest zamykany przy zatrzymaniu
	f2 := newWpFixture(t)
	f2.fake.listeners[8091] = 888
	f2.mgr.stopFor("nalf")
	if len(f2.fake.killed) != 0 {
		t.Fatalf("obcy proces zamknięty: %v", f2.fake.killed)
	}
}

func TestWpReplayRepeatsWarning(t *testing.T) {
	f := newWpFixture(t)
	f.fake.listeners[8091] = 777
	f.mgr.ensureFor("nalf")
	n := len(f.notices())
	f.mgr.replay()
	if len(f.notices()) != n+1 || !strings.HasPrefix(f.notices()[n], "warning:") {
		t.Fatalf("powtórzenie ostrzeżenia dla modułu łączącego się po starcie: %v", f.notices())
	}
}

func waitWp(t *testing.T, cond func() bool, what string) {
	t.Helper()
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		if cond() {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("nie doczekano: %s", what)
}
