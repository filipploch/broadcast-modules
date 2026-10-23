package main

import (
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"
)

func testWpPaths(t *testing.T) wpPaths {
	t.Helper()
	dir := t.TempDir()
	return wpPaths{
		Dir:    dir,
		Php:    filepath.Join(dir, "php", "php.exe"),
		Cli:    filepath.Join(dir, "wp-cli.phar"),
		Site:   filepath.Join(dir, "wordpress"),
		DbBase: filepath.Join(dir, "databases"),
	}
}

func TestWpCommandUsesBlockFields(t *testing.T) {
	p := testWpPaths(t)
	c := p.command(WpConfig{Port: 8091, DB: "baza-x"})
	if c.Exe != p.Php || c.Dir != p.Dir {
		t.Fatalf("exe/dir: %+v", c)
	}
	want := []string{p.Cli, "--path=" + p.Site, "server", "--host=127.0.0.1", "--port=8091"}
	if !reflect.DeepEqual(c.Args, want) {
		t.Fatalf("argumenty: %v, oczekiwano %v", c.Args, want)
	}
	if !reflect.DeepEqual(c.Env, []string{"BM_DB=baza-x", "BM_PORT=8091"}) {
		t.Fatalf("środowisko: %v", c.Env)
	}
	// domyślna baza p<port>
	if env := p.command(WpConfig{Port: 8092}).Env; env[0] != "BM_DB=p8092" {
		t.Fatalf("domyślna baza: %v", env)
	}
}

func TestWpPathsFromConfig(t *testing.T) {
	root := t.TempDir()
	lc := &LoadedHubConfig{Root: root}
	lc.HubConfig = defaultHubConfig()
	p := lc.wpPaths()
	if p.Dir != filepath.Join(root, "wp-local") || p.Php != filepath.Join(root, "wp-local", "php", "php.exe") {
		t.Fatalf("ścieżki: %+v", p)
	}
	lc.WpDir = "inny"
	if lc.wpPaths().Dir != filepath.Join(root, "inny") {
		t.Fatalf("wp_dir: %+v", lc.wpPaths())
	}
}

func TestWpCheckReportsMissingPieces(t *testing.T) {
	p := testWpPaths(t)
	if err := p.check(); err == nil || !strings.Contains(err.Error(), "PHP") {
		t.Fatalf("brak PHP: %v", err)
	}
	os.MkdirAll(filepath.Dir(p.Php), 0o755)
	os.WriteFile(p.Php, nil, 0o644)
	os.WriteFile(p.Cli, nil, 0o644)
	if err := p.check(); err == nil || !strings.Contains(err.Error(), "WordPress") {
		t.Fatalf("brak WordPressa: %v", err)
	}
	os.MkdirAll(p.Site, 0o755)
	os.WriteFile(filepath.Join(p.Site, "wp-config.php"), nil, 0o644)
	if err := p.check(); err != nil {
		t.Fatalf("kompletna instalacja: %v", err)
	}
}

func TestWpEnsureDBCopiesTemplateOnce(t *testing.T) {
	p := testWpPaths(t)
	w := WpConfig{Port: 8091}
	if _, err := p.ensureDB(w); err == nil {
		t.Fatal("brak szablonu powinien dać błąd")
	}
	os.MkdirAll(filepath.Join(p.DbBase, "_szablon"), 0o755)
	os.WriteFile(filepath.Join(p.DbBase, "_szablon", ".ht.sqlite"), []byte("szablon"), 0o644)
	created, err := p.ensureDB(w)
	if err != nil || !created {
		t.Fatalf("pierwsze założenie: %v %v", created, err)
	}
	got, _ := os.ReadFile(filepath.Join(p.DbBase, "p8091", ".ht.sqlite"))
	if string(got) != "szablon" {
		t.Fatalf("zawartość bazy: %q", got)
	}
	for _, f := range []string{".htaccess", "index.php"} {
		if _, err := os.Stat(filepath.Join(p.DbBase, "p8091", f)); err != nil {
			t.Fatalf("brak %s: %v", f, err)
		}
	}
	// istniejąca baza nie jest nadpisywana
	os.WriteFile(filepath.Join(p.DbBase, "p8091", ".ht.sqlite"), []byte("dane operatora"), 0o644)
	created, err = p.ensureDB(w)
	if err != nil || created {
		t.Fatalf("drugie wywołanie: %v %v", created, err)
	}
	got, _ = os.ReadFile(filepath.Join(p.DbBase, "p8091", ".ht.sqlite"))
	if string(got) != "dane operatora" {
		t.Fatalf("baza nadpisana: %q", got)
	}
}

// fakeWpOS: porty -> PID; ours: PID-y naszego php.exe; killed: zamknięte.
type fakeWpOS struct {
	listeners map[int]int
	ours      map[int]bool
	killed    []int
	killErr   error
	stuck     bool // proces po zabiciu nadal trzyma port
}

func (f *fakeWpOS) os() wpOS {
	return wpOS{
		listenerPID: func(port int) (int, bool) { pid, ok := f.listeners[port]; return pid, ok },
		isOurs:      func(pid int) bool { return f.ours[pid] },
		kill: func(pid int) error {
			if f.killErr != nil {
				return f.killErr
			}
			f.killed = append(f.killed, pid)
			if !f.stuck {
				for port, p := range f.listeners {
					if p == pid {
						delete(f.listeners, port)
					}
				}
			}
			return nil
		},
		portOpen: func(port int) bool { _, ok := f.listeners[port]; return ok },
		sleep:    func(time.Duration) {},
	}
}

func twoModuleCatalog() (*ModuleCatalog, ModuleManifest, ModuleManifest) {
	a := ModuleManifest{ID: "nalf", Port: 8081, Wp: &WpConfig{Port: 8091}}
	b := ModuleManifest{ID: "garbarnia", Port: 8081, Wp: &WpConfig{Port: 8092}}
	return &ModuleCatalog{Modules: []ModuleManifest{a, b}}, a, b
}

func TestPrepareWpStartClosesOtherModulesInstance(t *testing.T) {
	cat, nalf, _ := twoModuleCatalog()
	f := &fakeWpOS{listeners: map[int]int{8092: 500}, ours: map[int]bool{500: true}}
	plan := prepareWpStart(testWpPaths(t), cat, nalf, f.os())
	if plan.Err != nil || plan.Adopt || len(plan.Warnings) != 0 {
		t.Fatalf("plan: %+v", plan)
	}
	if !reflect.DeepEqual(f.killed, []int{500}) || len(plan.Closed) != 1 || !strings.Contains(plan.Closed[0], "garbarnia") {
		t.Fatalf("zamknięto %v, plan %+v", f.killed, plan)
	}
}

func TestPrepareWpStartKeepsOwnInstance(t *testing.T) {
	cat, nalf, _ := twoModuleCatalog()
	f := &fakeWpOS{listeners: map[int]int{8091: 400}, ours: map[int]bool{400: true}}
	plan := prepareWpStart(testWpPaths(t), cat, nalf, f.os())
	if !plan.Adopt || plan.PID != 400 || plan.Err != nil || len(f.killed) != 0 {
		t.Fatalf("właściwa instancja ma zostać bez restartu: %+v, zamknięto %v", plan, f.killed)
	}
}

func TestPrepareWpStartClosesOtherButKeepsOwn(t *testing.T) {
	cat, nalf, _ := twoModuleCatalog()
	f := &fakeWpOS{listeners: map[int]int{8091: 400, 8092: 500}, ours: map[int]bool{400: true, 500: true}}
	plan := prepareWpStart(testWpPaths(t), cat, nalf, f.os())
	if !plan.Adopt || !reflect.DeepEqual(f.killed, []int{500}) {
		t.Fatalf("plan %+v, zamknięto %v", plan, f.killed)
	}
}

func TestPrepareWpStartNeverKillsForeignProcess(t *testing.T) {
	cat, nalf, _ := twoModuleCatalog()
	// obcy proces na porcie innej instancji: ostrzeżenie, bez zamykania
	f := &fakeWpOS{listeners: map[int]int{8092: 600}, ours: map[int]bool{}}
	plan := prepareWpStart(testWpPaths(t), cat, nalf, f.os())
	if len(f.killed) != 0 || len(plan.Warnings) != 1 || plan.Err != nil {
		t.Fatalf("obcy proces na porcie innego modułu: %+v, zamknięto %v", plan, f.killed)
	}
	// obcy proces na własnym porcie: błąd startu, bez zamykania
	f = &fakeWpOS{listeners: map[int]int{8091: 601}, ours: map[int]bool{}}
	plan = prepareWpStart(testWpPaths(t), cat, nalf, f.os())
	if len(f.killed) != 0 || plan.Err == nil || plan.Adopt {
		t.Fatalf("obcy proces na własnym porcie: %+v, zamknięto %v", plan, f.killed)
	}
}

func TestPrepareWpStartReportsKillFailureAndStuckPort(t *testing.T) {
	cat, nalf, _ := twoModuleCatalog()
	f := &fakeWpOS{listeners: map[int]int{8092: 500}, ours: map[int]bool{500: true}, killErr: fmt.Errorf("odmowa")}
	plan := prepareWpStart(testWpPaths(t), cat, nalf, f.os())
	if len(plan.Warnings) != 1 || plan.Err != nil {
		t.Fatalf("błąd zamknięcia: %+v", plan)
	}
	f = &fakeWpOS{listeners: map[int]int{8092: 500}, ours: map[int]bool{500: true}, stuck: true}
	plan = prepareWpStart(testWpPaths(t), cat, nalf, f.os())
	if len(plan.Warnings) != 1 || len(plan.Closed) != 0 {
		t.Fatalf("port nadal zajęty po zamknięciu: %+v", plan)
	}
}

func TestPrepareWpStartIdleWhenNothingRuns(t *testing.T) {
	cat, nalf, _ := twoModuleCatalog()
	f := &fakeWpOS{listeners: map[int]int{}, ours: map[int]bool{}}
	plan := prepareWpStart(testWpPaths(t), cat, nalf, f.os())
	if plan.Adopt || plan.Err != nil || len(plan.Closed) != 0 || len(plan.Warnings) != 0 {
		t.Fatalf("plan: %+v", plan)
	}
	if p := prepareWpStart(testWpPaths(t), cat, ModuleManifest{ID: "x"}, f.os()); p.Err == nil {
		t.Fatal("moduł bez bloku wp powinien dać błąd")
	}
}

// Moduł dostaje od HUB-a folder WP (dane logowania do WP leżą obok instalacji, z której HUB uruchamia WordPressa).
func TestModuleServicePassesWpDir(t *testing.T) {
	root := t.TempDir()
	lc := &LoadedHubConfig{Root: root}
	lc.HubConfig = defaultHubConfig()
	svc := lc.moduleServiceFor(ModuleManifest{ID: "nalf", Script: "modules/nalf.py", Port: 8081})
	want := "BM_WP_DIR=" + filepath.Join(root, "wp-local")
	found := false
	for _, e := range svc.Env {
		if e == want {
			found = true
		}
	}
	if !found {
		t.Fatalf("brak %s w środowisku modułu: %v", want, svc.Env)
	}
}
