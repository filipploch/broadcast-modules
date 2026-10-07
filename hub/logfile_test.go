package main

import (
	"log"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestRemoveOldLogs(t *testing.T) {
	dir := t.TempDir()
	now := time.Now()
	mk := func(name string, age time.Duration) {
		p := filepath.Join(dir, name)
		if err := os.WriteFile(p, []byte("x"), 0o644); err != nil {
			t.Fatal(err)
		}
		if err := os.Chtimes(p, now.Add(-age), now.Add(-age)); err != nil {
			t.Fatal(err)
		}
	}
	mk("hub-stary.log", 31*24*time.Hour)
	mk("modul-x-stary.log.1", 45*24*time.Hour)
	mk("hub-nowy.log", 29*24*time.Hour)
	mk("inny.txt", 90*24*time.Hour)

	if n := removeOldLogs(dir, now); n != 2 {
		t.Fatalf("usunieto %d plikow, oczekiwano 2", n)
	}
	for _, keep := range []string{"hub-nowy.log", "inny.txt"} {
		if _, err := os.Stat(filepath.Join(dir, keep)); err != nil {
			t.Errorf("plik %s powinien zostac", keep)
		}
	}
}

func TestSetupLogFileCreatesFileWithDate(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "logs")
	now := time.Date(2026, 10, 8, 12, 30, 5, 0, time.UTC)
	f, err := setupLogFile(dir, now)
	if err != nil {
		t.Fatal(err)
	}
	path := f.Name()
	defer func() {
		log.SetOutput(os.Stderr)
		processOutput = os.Stdout
		f.Close()
	}()
	if filepath.Base(path) != "hub-2026-10-08_12-30-05.log" {
		t.Fatalf("nazwa pliku: %s", filepath.Base(path))
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatal(err)
	}
}
