package main

import (
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

type collector struct {
	mu    sync.Mutex
	lines []string
}

func (c *collector) add(s []string) { c.mu.Lock(); c.lines = append(c.lines, s...); c.mu.Unlock() }
func (c *collector) get() string    { c.mu.Lock(); defer c.mu.Unlock(); return strings.Join(c.lines, "|") }

func appendTo(t *testing.T, path, text string) {
	t.Helper()
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		t.Fatal(err)
	}
	f.WriteString(text)
	f.Close()
}

func TestFollowerSkipsOldContentAndReadsNewLines(t *testing.T) {
	path := filepath.Join(t.TempDir(), "modul.log")
	appendTo(t, path, "stary wiersz\n")
	var c collector
	f := startFileFollower(path, 10*time.Millisecond, c.add)
	defer f.Stop()
	time.Sleep(60 * time.Millisecond)
	appendTo(t, path, "nowy 1\nnowy 2 (niedokoń")
	waitCond(t, "nowe wiersze", 3*time.Second, func() bool { return c.get() == "nowy 1" })
	appendTo(t, path, "czony)\n")
	waitCond(t, "dokończony wiersz", 3*time.Second, func() bool { return c.get() == "nowy 1|nowy 2 (niedokończony)" })
}

func TestFollowerReadsFileCreatedLaterFromStart(t *testing.T) {
	path := filepath.Join(t.TempDir(), "modul.log")
	var c collector
	f := startFileFollower(path, 10*time.Millisecond, c.add)
	defer f.Stop()
	time.Sleep(50 * time.Millisecond)
	appendTo(t, path, "pierwszy\n")
	waitCond(t, "wiersz z nowego pliku", 3*time.Second, func() bool { return c.get() == "pierwszy" })
}

// Rotacja po stronie zapisującego (zmiana nazwy pliku w trakcie czytania) nie może się nie udać przez czytnik
// (FILE_SHARE_DELETE) i musi przejść na nowy plik od początku.
func TestFollowerAllowsRotationByWriterAndSwitchesToNewFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "modul.log")
	appendTo(t, path, "")
	var c collector
	f := startFileFollower(path, 10*time.Millisecond, c.add)
	defer f.Stop()
	time.Sleep(60 * time.Millisecond)
	appendTo(t, path, "przed rotacją\n")
	waitCond(t, "wiersz przed rotacją", 3*time.Second, func() bool { return c.get() == "przed rotacją" })
	if err := os.Rename(path, path+".1"); err != nil {
		t.Fatalf("zmiana nazwy pliku zablokowana przez czytnik: %v", err)
	}
	appendTo(t, path, "po rotacji\n")
	waitCond(t, "wiersz po rotacji", 3*time.Second, func() bool { return c.get() == "przed rotacją|po rotacji" })
}

// Wiersze zapisane razem (np. traceback) trafiają do konsoli jedną paczką, nie przecięte wierszami z innego pliku.
func TestFollowerEmitsLinesWrittenTogetherAsOneBatch(t *testing.T) {
	path := filepath.Join(t.TempDir(), "wyjscie.log")
	appendTo(t, path, "")
	var mu sync.Mutex
	var batches [][]string
	f := startFileFollower(path, 10*time.Millisecond, func(lines []string) {
		mu.Lock()
		batches = append(batches, lines)
		mu.Unlock()
	})
	defer f.Stop()
	time.Sleep(60 * time.Millisecond)
	appendTo(t, path, "Traceback (most recent call last):\n  File \"a.py\", line 1\n    boom()\nValueError: x\n")
	waitCond(t, "paczka", 3*time.Second, func() bool { mu.Lock(); defer mu.Unlock(); return len(batches) > 0 })
	mu.Lock()
	defer mu.Unlock()
	if len(batches) != 1 || len(batches[0]) != 4 {
		t.Fatalf("oczekiwano jednej paczki 4 wierszy: %v", batches)
	}
}
