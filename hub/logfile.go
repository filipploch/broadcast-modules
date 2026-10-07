package main

import (
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

// logRetention to czas, po którym stare pliki logów są usuwane przy starcie.
const logRetention = 30 * 24 * time.Hour

// processOutput to miejsce, dokąd trafia wyjście uruchamianych pluginów lokalnych (konsola + plik logu HUB-a).
var processOutput io.Writer = os.Stdout

// logsDir zwraca folder logów: BM_LOGS_DIR, a bez niego `logs/` w katalogu głównym repozytorium
// (liczonym od położenia pliku wykonywalnego HUB-a, nie od bieżącego folderu).
func logsDir() string {
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

// setupLogFile kieruje log HUB-a i wyjście pluginów lokalnych do konsoli oraz do osobnego pliku tego uruchomienia
// (hub-RRRR-MM-DD_GG-MM-SS.log), a przy okazji usuwa pliki logów starsze niż 30 dni. Zwraca otwarty plik (zamykany przy zakończeniu procesu).
func setupLogFile(dir string, now time.Time) (*os.File, error) {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, err
	}
	removeOldLogs(dir, now)
	path := filepath.Join(dir, fmt.Sprintf("hub-%s.log", now.Format("2006-01-02_15-04-05")))
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return nil, err
	}
	w := io.MultiWriter(os.Stdout, f)
	log.SetOutput(w)
	processOutput = w
	return f, nil
}

// removeOldLogs usuwa pliki *.log (także modułu) starsze niż logRetention; zwraca liczbę usuniętych.
func removeOldLogs(dir string, now time.Time) int {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return 0
	}
	removed := 0
	for _, e := range entries {
		if e.IsDir() || !strings.Contains(e.Name(), ".log") {
			continue
		}
		info, err := e.Info()
		if err != nil || now.Sub(info.ModTime()) <= logRetention {
			continue
		}
		if os.Remove(filepath.Join(dir, e.Name())) == nil {
			removed++
		}
	}
	return removed
}
