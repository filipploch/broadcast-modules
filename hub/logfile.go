package main

import (
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"sync"
	"time"
)

// Logi (E2a): jeden folder na uruchomienie HUB-a, w nim osobny plik na każdy składnik:
//   logs/logs-RRRR-MM-DD-gg-mm-ss/hub.log, modul-<nazwa>.log, timer-plugin.log, obs-ws-plugin.log, ...
// HUB zakłada folder przy starcie i przekazuje jego ścieżkę uruchamianym procesom zmienną środowiskową BM_LOG_RUN_DIR.
// Wyjście każdego pluginu lokalnego trafia do jego pliku i na konsolę HUB-a. Wszystkie wiersze mają ten sam format
// znacznika czasu (z milisekundami): "2006-01-02 15:04:05.000 treść".

const (
	runDirEnv     = "BM_LOG_RUN_DIR"
	runDirPrefix  = "logs-"
	runDirFormat  = "logs-2006-01-02-15-04-05"
	logTimeFormat = "2006-01-02 15:04:05.000"
	logRetention  = 30 * 24 * time.Hour // usuwanie dotyczy całych folderów uruchomień
	logMaxBytes   = 5 * 1024 * 1024     // limit rozmiaru jednego pliku (rotacja: .1, .2, .3)
	logBackups    = 3
)

// runLogDir to folder bieżącego uruchomienia ("" = brak plików logów, tylko konsola).
var runLogDir string

// standardowy znacznik czasu pakietu log (pluginy w Go go wypisują), zastępowany jednolitym znacznikiem HUB-a
var stdLogPrefix = regexp.MustCompile(`^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}(\.\d+)? `)

// logsRoot zwraca folder główny logów: BM_LOGS_DIR, a bez niego `logs/` w katalogu głównym repozytorium
// (liczonym od położenia pliku wykonywalnego HUB-a, nie od bieżącego folderu).
func logsRoot() string {
	if d := os.Getenv("BM_LOGS_DIR"); d != "" {
		return d
	}
	exeDir := ""
	if exe, err := os.Executable(); err == nil {
		exeDir = filepath.Dir(exe)
	}
	// `go run` buduje plik w folderze tymczasowym: wtedy liczymy od położenia źródeł
	if exeDir == "" || strings.Contains(exeDir, "go-build") {
		if _, file, _, ok := runtime.Caller(0); ok {
			exeDir = filepath.Dir(file)
		}
	}
	return filepath.Join(filepath.Dir(exeDir), "logs")
}

// setupRunLogs zakłada folder uruchomienia, usuwa foldery starsze niż 30 dni, ustawia BM_LOG_RUN_DIR dla procesów
// potomnych i kieruje log HUB-a do hub.log oraz na konsolę. Zwraca ścieżkę folderu i funkcję zamykającą pliki.
func setupRunLogs(root string, now time.Time) (string, func(), error) {
	if err := os.MkdirAll(root, 0o755); err != nil {
		return "", func() {}, err
	}
	removeOldRunDirs(root, now)
	dir := filepath.Join(root, now.Format(runDirFormat))
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", func() {}, err
	}
	runLogDir = dir
	os.Setenv(runDirEnv, dir)

	sink := newSink("hub", os.Stdout, "hub")
	log.SetFlags(0)
	log.SetOutput(sink)
	return dir, sink.Close, nil
}

// removeOldRunDirs usuwa całe foldery uruchomień (logs-*), w których nic nie zmieniono od ponad logRetention.
// Zwraca liczbę usuniętych folderów.
func removeOldRunDirs(root string, now time.Time) int {
	entries, err := os.ReadDir(root)
	if err != nil {
		return 0
	}
	removed := 0
	for _, e := range entries {
		if !e.IsDir() || !strings.HasPrefix(e.Name(), runDirPrefix) {
			continue
		}
		dir := filepath.Join(root, e.Name())
		if now.Sub(newestModTime(dir)) <= logRetention {
			continue
		}
		if os.RemoveAll(dir) == nil {
			removed++
		}
	}
	return removed
}

func newestModTime(dir string) time.Time {
	newest := time.Time{}
	if info, err := os.Stat(dir); err == nil {
		newest = info.ModTime()
	}
	files, _ := os.ReadDir(dir)
	for _, f := range files {
		if info, err := f.Info(); err == nil && info.ModTime().After(newest) {
			newest = info.ModTime()
		}
	}
	return newest
}

// ── Wyjście składnika: plik + konsola ─────────────────────────────────────────

// logSink przyjmuje strumień tekstu składnika (log HUB-a albo stdout/stderr pluginu), dzieli go na wiersze, zastępuje
// ewentualny własny znacznik czasu jednolitym i zapisuje wiersz do pliku składnika (bez etykiety) oraz na konsolę (z etykietą).
type logSink struct {
	tag     string
	console io.Writer
	file    *rotatingFile // nil = tylko konsola
	mu      sync.Mutex
	partial []byte
}

// newSink tworzy wyjście składnika; plik <fileBase>.log w folderze uruchomienia (jeśli istnieje) jest dopisywany,
// a przy ponownym uruchomieniu poprzedzany wierszem rozdzielającym.
func newSink(tag string, console io.Writer, fileBase string) *logSink {
	s := &logSink{tag: tag, console: console}
	if runLogDir == "" {
		return s
	}
	path := filepath.Join(runLogDir, fileBase+".log")
	existed := false
	if info, err := os.Stat(path); err == nil && info.Size() > 0 {
		existed = true
	}
	f, err := openRotating(path, logMaxBytes, logBackups)
	if err != nil {
		fmt.Fprintf(console, "%s [%s] ⚠️  nie można otworzyć pliku logu %s: %v\n", time.Now().Format(logTimeFormat), tag, path, err)
		return s
	}
	s.file = f
	if existed {
		s.emit(fmt.Sprintf("──────── ponowne uruchomienie składnika %s ────────", tag))
	}
	return s
}

func (s *logSink) Write(p []byte) (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.partial = append(s.partial, p...)
	for {
		i := strings.IndexByte(string(s.partial), '\n')
		if i < 0 {
			break
		}
		line := string(s.partial[:i])
		s.partial = s.partial[i+1:]
		s.emit(line)
	}
	return len(p), nil
}

func (s *logSink) emit(line string) {
	line = stdLogPrefix.ReplaceAllString(strings.TrimRight(line, "\r"), "")
	ts := time.Now().Format(logTimeFormat)
	if s.file != nil {
		s.file.Write([]byte(ts + " " + line + "\n"))
	}
	if s.console != nil {
		fmt.Fprintf(s.console, "%s [%s] %s\n", ts, s.tag, line)
	}
}

// Close zapisuje niedokończony wiersz i zamyka plik.
func (s *logSink) Close() {
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.partial) > 0 {
		s.emit(string(s.partial))
		s.partial = nil
	}
	if s.file != nil {
		s.file.Close()
		s.file = nil
	}
}

// ── Plik z limitem rozmiaru ───────────────────────────────────────────────────

type rotatingFile struct {
	path     string
	maxBytes int64
	backups  int
	mu       sync.Mutex
	f        *os.File
	size     int64
}

func openRotating(path string, maxBytes int64, backups int) (*rotatingFile, error) {
	r := &rotatingFile{path: path, maxBytes: maxBytes, backups: backups}
	if err := r.open(); err != nil {
		return nil, err
	}
	return r, nil
}

func (r *rotatingFile) open() error {
	f, err := os.OpenFile(r.path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return err
	}
	info, err := f.Stat()
	if err != nil {
		f.Close()
		return err
	}
	r.f, r.size = f, info.Size()
	return nil
}

func (r *rotatingFile) Write(p []byte) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.f == nil {
		return 0, os.ErrClosed
	}
	if r.size+int64(len(p)) > r.maxBytes && r.size > 0 {
		r.rotate()
	}
	n, err := r.f.Write(p)
	r.size += int64(n)
	return n, err
}

func (r *rotatingFile) rotate() {
	r.f.Close()
	for i := r.backups - 1; i >= 1; i-- {
		os.Rename(fmt.Sprintf("%s.%d", r.path, i), fmt.Sprintf("%s.%d", r.path, i+1))
	}
	os.Rename(r.path, r.path+".1")
	if err := r.open(); err != nil {
		r.f = nil
	}
}

func (r *rotatingFile) Close() error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.f == nil {
		return nil
	}
	err := r.f.Close()
	r.f = nil
	return err
}
