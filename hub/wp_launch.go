package main

import (
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
)

// Wspólna implementacja startu instancji WP (WP-1): polecenie, baza z szablonu i zasady "jedna instancja naraz" są tutaj,
// a wołają je zarówno "hub.exe wp <id>" (pliki .bat), jak i HUB przy starcie modułu (wp_instance.go).

// wpPaths to położenie PHP i WordPressa. Wszystko leży w folderze wp_dir (domyślnie wp-local, poza gitem), jak start-wp.bat.
type wpPaths struct {
	Dir    string // wp-local
	Php    string // php\php.exe
	Cli    string // wp-cli.phar
	Site   string // wordpress (argument --path)
	DbBase string // databases
}

func (c *LoadedHubConfig) wpPaths() wpPaths {
	dir := c.WpDir
	if dir == "" {
		dir = wpDefaultDir
	}
	dir = c.abs(dir)
	return wpPaths{
		Dir:    dir,
		Php:    filepath.Join(dir, "php", "php.exe"),
		Cli:    filepath.Join(dir, "wp-cli.phar"),
		Site:   filepath.Join(dir, "wordpress"),
		DbBase: filepath.Join(dir, "databases"),
	}
}

// check zwraca opis pierwszego brakującego elementu instalacji albo nil.
func (p wpPaths) check() error {
	for _, f := range []struct{ path, what string }{
		{p.Php, "PHP (php\\php.exe)"},
		{p.Cli, "wp-cli.phar"},
		{filepath.Join(p.Site, "wp-config.php"), "WordPress (wordpress\\wp-config.php)"},
	} {
		if _, err := os.Stat(f.path); err != nil {
			return fmt.Errorf("brak %s w %s", f.what, p.Dir)
		}
	}
	return nil
}

// wpCommand to gotowe polecenie startu instancji.
type wpCommand struct {
	Exe  string
	Args []string
	Env  []string // dodatkowe zmienne (do dołączenia do środowiska procesu)
	Dir  string
}

// command składa polecenie startu instancji tak, jak robi to start-wp.bat, z portem i bazą z bloku "wp".
// Baza wybierana jest po zmiennej BM_DB (bm-multidb.php), port po --port; to jedyne miejsce, które je składa.
func (p wpPaths) command(w WpConfig) wpCommand {
	return wpCommand{
		Exe: p.Php,
		Args: []string{
			p.Cli, "--path=" + p.Site, "server", "--host=127.0.0.1", "--port=" + strconv.Itoa(w.Port),
		},
		Env: []string{
			"BM_DB=" + w.EffectiveDB(),
			"BM_PORT=" + strconv.Itoa(w.Port),
		},
		Dir: p.Dir,
	}
}

// String: polecenie do porównań w testach i do logu.
func (c wpCommand) String() string {
	return fmt.Sprintf("%s %s [%s] w %s", c.Exe, strings.Join(c.Args, " "), strings.Join(c.Env, " "), c.Dir)
}

func (c wpCommand) exec() *exec.Cmd {
	cmd := exec.Command(c.Exe, c.Args...)
	cmd.Dir = c.Dir
	cmd.Env = append(os.Environ(), c.Env...)
	return cmd
}

// ensureDB zakłada bazę z szablonu, gdy jej brak. Zwraca true, gdy baza została założona.
func (p wpPaths) ensureDB(w WpConfig) (bool, error) {
	dst := filepath.Join(p.DbBase, w.EffectiveDB())
	if _, err := os.Stat(filepath.Join(dst, ".ht.sqlite")); err == nil {
		return false, nil
	}
	src := filepath.Join(p.DbBase, w.EffectiveTemplate(), ".ht.sqlite")
	if _, err := os.Stat(src); err != nil {
		return false, fmt.Errorf("brak bazy %q i szablonu %q (%s)", w.EffectiveDB(), w.EffectiveTemplate(), src)
	}
	if err := os.MkdirAll(dst, 0o755); err != nil {
		return false, err
	}
	if err := copyFile(src, filepath.Join(dst, ".ht.sqlite")); err != nil {
		return false, fmt.Errorf("kopiowanie szablonu: %v", err)
	}
	// jak w bazach z testu T6: folder bazy nie może być czytany przez serwer WWW
	_ = os.WriteFile(filepath.Join(dst, ".htaccess"), []byte("DENY FROM ALL"), 0o644)
	_ = os.WriteFile(filepath.Join(dst, "index.php"), []byte("<?php // Silence is gold. ?>"), 0o644)
	return true, nil
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	return out.Close()
}

// applyTitle ustawia tytuł strony nowej bazy (odróżnia rozgrywki w panelu WP). Błąd nie przerywa startu.
func (p wpPaths) applyTitle(w WpConfig) error {
	if w.Title == "" {
		return nil
	}
	cmd := exec.Command(p.Php, p.Cli, "--path="+p.Site, "option", "update", "blogname", w.Title)
	cmd.Dir = p.Dir
	cmd.Env = append(os.Environ(), "BM_DB="+w.EffectiveDB(), "BM_PORT="+strconv.Itoa(w.Port))
	if out, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("%v: %s", err, strings.TrimSpace(string(out)))
	}
	return nil
}

// wpOS to zależności systemowe przygotowania startu (podmieniane w testach).
type wpOS struct {
	listenerPID func(port int) (int, bool) // PID procesu nasłuchującego na porcie
	isOurs      func(pid int) bool         // czy to nasz php.exe z folderu WP
	kill        func(pid int) error        // zakończenie drzewa procesów
	portOpen    func(port int) bool
	sleep       func(time.Duration)
}

func (p wpPaths) defaultOS() wpOS {
	return wpOS{
		listenerPID: listenerPIDOnPort,
		isOurs:      func(pid int) bool { return processImageEquals(pid, p.Php) },
		kill:        killTree,
		portOpen:    func(port int) bool { return tcpOpen(net.JoinHostPort("127.0.0.1", strconv.Itoa(port))) },
		sleep:       time.Sleep,
	}
}

// wpPlan to wynik przygotowania startu instancji modułu.
type wpPlan struct {
	Adopt    bool     // właściwa instancja już działa (nasz php.exe): zostaje, bez restartu
	PID      int      // PID przejętej instancji
	Closed   []string // instancje innych modułów zamknięte (do logu): "id (port, PID n)"
	Warnings []string // ostrzeżenia: nie zamknięto obcego procesu na porcie innej instancji itp.
	Err      error    // port instancji modułu zajęty przez obcy proces (start niemożliwy)
}

// prepareWpStart realizuje zasady: zamyka działające instancje INNYCH modułów (tylko nasze php.exe), a jeśli właściwa
// instancja już działa, zostawia ją (przejmuje). Obcego procesu na porcie nie zamyka nigdy.
func prepareWpStart(p wpPaths, cat *ModuleCatalog, m ModuleManifest, sys wpOS) wpPlan {
	var plan wpPlan
	if m.Wp == nil {
		plan.Err = fmt.Errorf("moduł %s nie ma bloku wp w module.json", m.ID)
		return plan
	}
	others := []ModuleManifest{}
	if cat != nil {
		for _, o := range cat.Modules {
			if o.ID != m.ID && o.Wp != nil {
				others = append(others, o)
			}
		}
	}
	sort.SliceStable(others, func(i, j int) bool { return others[i].ID < others[j].ID })
	for _, o := range others {
		pid, listening := sys.listenerPID(o.Wp.Port)
		if !listening {
			continue
		}
		if !sys.isOurs(pid) {
			plan.Warnings = append(plan.Warnings, fmt.Sprintf("port %d (WP modułu %s) zajmuje inny proces (PID %d): nie zamykam go", o.Wp.Port, o.ID, pid))
			continue
		}
		if err := sys.kill(pid); err != nil {
			plan.Warnings = append(plan.Warnings, fmt.Sprintf("nie udało się zamknąć WP modułu %s (PID %d): %v", o.ID, pid, err))
			continue
		}
		if !waitPortClosed(sys, o.Wp.Port) {
			plan.Warnings = append(plan.Warnings, fmt.Sprintf("WP modułu %s (port %d) nadal odpowiada po zamknięciu", o.ID, o.Wp.Port))
			continue
		}
		plan.Closed = append(plan.Closed, fmt.Sprintf("%s (port %d, PID %d)", o.ID, o.Wp.Port, pid))
	}
	if pid, listening := sys.listenerPID(m.Wp.Port); listening {
		if sys.isOurs(pid) {
			plan.Adopt, plan.PID = true, pid
		} else {
			plan.Err = fmt.Errorf("port %d zajmuje inny proces (PID %d), nie WordPress tego programu", m.Wp.Port, pid)
		}
		return plan
	}
	if sys.portOpen(m.Wp.Port) {
		// ktoś nasłuchuje, ale nie umiemy podać właściciela (brak uprawnień): traktujemy jak obcy proces
		plan.Err = fmt.Errorf("port %d jest zajęty przez nieznany proces", m.Wp.Port)
	}
	return plan
}

func waitPortClosed(sys wpOS, port int) bool {
	for i := 0; i < 50; i++ {
		if !sys.portOpen(port) {
			return true
		}
		sys.sleep(100 * time.Millisecond)
	}
	return !sys.portOpen(port)
}

// runWpCommand to "hub.exe wp <id modułu>": uruchamia instancję WP modułu w pierwszym planie (okno .bat), Ctrl+C ją zatrzymuje.
// Zwraca kod wyjścia procesu.
func runWpCommand(args []string, out io.Writer) int {
	cfg, err := loadHubConfig("", "none", "")
	if err != nil {
		fmt.Fprintf(out, "BŁĄD: konfiguracja HUB-a: %v\n", err)
		return 2
	}
	if len(args) != 1 {
		fmt.Fprintf(out, "Użycie: hub.exe wp <moduł>. Moduły z własnym WP: %s\n", strings.Join(wpModuleIDs(cfg.Catalog), ", "))
		return 2
	}
	m, ok := cfg.Catalog.Get(args[0])
	if !ok || m.Wp == nil {
		fmt.Fprintf(out, "BŁĄD: moduł %q nie istnieje albo nie ma bloku wp w module.json. Moduły z własnym WP: %s\n", args[0], strings.Join(wpModuleIDs(cfg.Catalog), ", "))
		return 2
	}
	p := cfg.wpPaths()
	if err := p.check(); err != nil {
		fmt.Fprintf(out, "BŁĄD: %v\n", err)
		return 2
	}
	plan := prepareWpStart(p, cfg.Catalog, m, p.defaultOS())
	for _, c := range plan.Closed {
		fmt.Fprintf(out, "Zamknięto działającą instancję WP modułu %s (jedna instancja naraz).\n", c)
	}
	for _, w := range plan.Warnings {
		fmt.Fprintf(out, "UWAGA: %s\n", w)
	}
	if plan.Err != nil {
		fmt.Fprintf(out, "BŁĄD: %v\n", plan.Err)
		return 1
	}
	url := fmt.Sprintf("http://127.0.0.1:%d/wp-admin/", m.Wp.Port)
	if plan.Adopt {
		fmt.Fprintf(out, "Instancja WP modułu %s już działa (PID %d): %s\n", m.ID, plan.PID, url)
		return 0
	}
	created, err := p.ensureDB(*m.Wp)
	if err != nil {
		fmt.Fprintf(out, "BŁĄD: %v\n", err)
		return 1
	}
	if created {
		fmt.Fprintf(out, "Założono bazę %q z szablonu %q.\n", m.Wp.EffectiveDB(), m.Wp.EffectiveTemplate())
		if err := p.applyTitle(*m.Wp); err != nil {
			fmt.Fprintf(out, "UWAGA: nie ustawiono tytułu strony: %v\n", err)
		}
	}
	cmd := p.command(*m.Wp).exec()
	cmd.Stdout, cmd.Stderr = out, out
	fmt.Fprintf(out, "WP modułu %s: %s (baza %s). Zatrzymanie: Ctrl+C lub zamknięcie okna.\n", m.ID, url, m.Wp.EffectiveDB())
	if err := cmd.Start(); err != nil {
		fmt.Fprintf(out, "BŁĄD: start nie powiódł się: %v\n", err)
		return 1
	}
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	select {
	case <-sig:
		_ = killTree(cmd.Process.Pid)
		<-done
		return 0
	case err := <-done:
		if err != nil {
			fmt.Fprintf(out, "WP zakończył pracę: %v\n", err)
			return 1
		}
		return 0
	}
}

func wpModuleIDs(cat *ModuleCatalog) []string {
	var ids []string
	if cat != nil {
		for _, m := range cat.Modules {
			if m.Wp != nil {
				ids = append(ids, m.ID)
			}
		}
	}
	if len(ids) == 0 {
		return []string{"(brak)"}
	}
	return ids
}
