package main

import (
	"bytes"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
	"time"
)

func TestRemoveOldRunDirsRemovesWholeFolders(t *testing.T) {
	root := t.TempDir()
	now := time.Now()
	mk := func(name string, age time.Duration, withFile bool) string {
		dir := filepath.Join(root, name)
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatal(err)
		}
		if withFile {
			f := filepath.Join(dir, "hub.log")
			os.WriteFile(f, []byte("x"), 0o644)
			os.Chtimes(f, now.Add(-age), now.Add(-age))
		}
		os.Chtimes(dir, now.Add(-age), now.Add(-age))
		return dir
	}
	old := mk("logs-2026-01-01-10-00-00", 31*24*time.Hour, true)
	fresh := mk("logs-2026-10-01-10-00-00", 29*24*time.Hour, true)
	// folder ze starym katalogiem, ale świeżo dopisanym plikiem (długa transmisja) zostaje
	active := mk("logs-2026-08-01-10-00-00", 60*24*time.Hour, false)
	os.WriteFile(filepath.Join(active, "hub.log"), []byte("x"), 0o644)
	other := mk("inny-folder", 90*24*time.Hour, true)

	if n := removeOldRunDirs(root, now); n != 1 {
		t.Fatalf("usunięto %d folderów, oczekiwano 1", n)
	}
	if _, err := os.Stat(old); err == nil {
		t.Error("stary folder powinien zniknąć razem z zawartością")
	}
	for _, keep := range []string{fresh, active, other} {
		if _, err := os.Stat(keep); err != nil {
			t.Errorf("folder %s powinien zostać", keep)
		}
	}
}

func resetLogState(t *testing.T) {
	t.Helper()
	runLogDir = ""
	os.Unsetenv(runDirEnv)
	t.Cleanup(func() {
		runLogDir = ""
		os.Unsetenv(runDirEnv)
		log.SetOutput(os.Stderr)
		log.SetFlags(log.LstdFlags)
	})
}

func TestSetupRunLogsCreatesFolderEnvAndHubLog(t *testing.T) {
	resetLogState(t)
	root := filepath.Join(t.TempDir(), "logs")
	now := time.Date(2026, 10, 8, 12, 30, 5, 0, time.Local)
	dir, closeLogs, err := setupRunLogs(root, now)
	if err != nil {
		t.Fatal(err)
	}
	if filepath.Base(dir) != "logs-2026-10-08-12-30-05" {
		t.Fatalf("nazwa folderu: %s", filepath.Base(dir))
	}
	if os.Getenv(runDirEnv) != dir {
		t.Fatalf("zmienna %s = %q, oczekiwano %q", runDirEnv, os.Getenv(runDirEnv), dir)
	}
	log.Println("pierwszy wiersz huba")
	closeLogs()
	data, err := os.ReadFile(filepath.Join(dir, "hub.log"))
	if err != nil {
		t.Fatal(err)
	}
	re := regexp.MustCompile(`^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} pierwszy wiersz huba\n$`)
	if !re.Match(data) {
		t.Fatalf("zły format wiersza w hub.log: %q", data)
	}
}

func TestPluginSinkWritesFileAndConsoleWithUniformTimestamp(t *testing.T) {
	resetLogState(t)
	runLogDir = t.TempDir()
	var console bytes.Buffer
	s := newSink("timer-plugin", &console, "timer-plugin")
	// plugin w Go wypisuje własny znacznik (bez milisekund) i wiersz może przyjść w kawałkach
	s.Write([]byte("2026/10/08 12:00:00 ✅ Timer sta"))
	s.Write([]byte("rted\ndrugi wiersz bez znacznika\r\n"))
	s.Close()

	file, _ := os.ReadFile(filepath.Join(runLogDir, "timer-plugin.log"))
	lines := strings.Split(strings.TrimSpace(string(file)), "\n")
	if len(lines) != 2 {
		t.Fatalf("wierszy w pliku: %d (%q)", len(lines), file)
	}
	re := regexp.MustCompile(`^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} `)
	for _, l := range lines {
		if !re.MatchString(l) {
			t.Errorf("wiersz bez jednolitego znacznika: %q", l)
		}
	}
	if !strings.HasSuffix(lines[0], " ✅ Timer started") || strings.Contains(lines[0], "2026/10/08") {
		t.Errorf("własny znacznik pluginu nie został zastąpiony: %q", lines[0])
	}
	if !strings.Contains(console.String(), "[timer-plugin] ✅ Timer started") {
		t.Errorf("konsola powinna pokazywać wiersz z etykietą pluginu: %q", console.String())
	}
	if strings.Contains(string(file), "[timer-plugin]") {
		t.Errorf("plik składnika nie powinien mieć etykiety: %q", file)
	}
}

func TestPluginRestartAppendsToSameFileWithSeparator(t *testing.T) {
	resetLogState(t)
	runLogDir = t.TempDir()
	s1 := newSink("obs-ws-plugin", nil, "obs-ws-plugin")
	s1.Write([]byte("przed awarią\n"))
	s1.Close()

	s2 := newSink("obs-ws-plugin", nil, "obs-ws-plugin") // restart pluginu
	s2.Write([]byte("po restarcie\n"))
	s2.Close()

	data, _ := os.ReadFile(filepath.Join(runLogDir, "obs-ws-plugin.log"))
	text := string(data)
	i1, i2, i3 := strings.Index(text, "przed awarią"), strings.Index(text, "ponowne uruchomienie składnika obs-ws-plugin"), strings.Index(text, "po restarcie")
	if !(i1 >= 0 && i2 > i1 && i3 > i2) {
		t.Fatalf("oczekiwano kolejno: wiersz sprzed awarii, separator, wiersz po restarcie; jest:\n%s", text)
	}
	if entries, _ := os.ReadDir(runLogDir); len(entries) != 1 {
		t.Errorf("restart ma dopisywać do tego samego pliku, plików: %d", len(entries))
	}
}

func TestSinkWithoutRunDirWritesOnlyToConsole(t *testing.T) {
	resetLogState(t)
	var console bytes.Buffer
	s := newSink("replay-plugin", &console, "replay-plugin")
	s.Write([]byte("tylko konsola\n"))
	s.Close()
	if !strings.Contains(console.String(), "[replay-plugin] tylko konsola") {
		t.Fatalf("konsola: %q", console.String())
	}
}

func TestRotatingFileKeepsSizeLimit(t *testing.T) {
	path := filepath.Join(t.TempDir(), "x.log")
	r, err := openRotating(path, 100, 2)
	if err != nil {
		t.Fatal(err)
	}
	line := []byte(strings.Repeat("a", 39) + "\n") // 40 B
	for i := 0; i < 10; i++ {
		r.Write(line)
	}
	r.Close()
	for _, p := range []string{path, path + ".1", path + ".2"} {
		info, err := os.Stat(p)
		if err != nil {
			t.Fatalf("brak pliku %s", p)
		}
		if info.Size() > 100 {
			t.Errorf("%s ma %d B, limit 100", p, info.Size())
		}
	}
	if _, err := os.Stat(path + ".3"); err == nil {
		t.Error("powstała kopia ponad limit liczby kopii")
	}
}
