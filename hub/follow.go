package main

import (
	"bufio"
	"bytes"
	"fmt"
	"io"
	"os"
	"sync"
	"time"
)

// fileFollower czyta (tylko czyta) plik tekstowy zapisywany przez inny proces i przekazuje nowe wiersze do emit.
// Używany do pokazania w konsoli HUB-a logu modułu, który pisze do plików sam (bez potoku przez HUB).
// Rotacja pliku (zmiana nazwy i nowy plik o tej samej ścieżce) jest wykrywana: po dokończeniu starego pliku
// follower otwiera nowy od początku.
type fileFollower struct {
	path string
	emit func(line string)
	stop chan struct{}
	done chan struct{}
	once sync.Once
}

// startFileFollower rusza czytanie w tle. Jeśli plik już istnieje, czytanie zaczyna się od jego końca
// (stara zawartość nie jest wypisywana); plik, który powstanie później, jest czytany od początku.
func startFileFollower(path string, interval time.Duration, emit func(string)) *fileFollower {
	f := &fileFollower{path: path, emit: emit, stop: make(chan struct{}), done: make(chan struct{})}
	_, err := os.Stat(path)
	startAtEnd := err == nil
	go f.run(interval, startAtEnd)
	return f
}

func (f *fileFollower) run(interval time.Duration, startAtEnd bool) {
	defer close(f.done)
	var cur *os.File
	var partial []byte
	defer func() {
		if cur != nil {
			cur.Close()
		}
	}()
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if cur == nil {
			if fh, err := openShared(f.path); err == nil {
				cur = fh
				if startAtEnd {
					cur.Seek(0, io.SeekEnd)
					startAtEnd = false
				}
			}
		}
		if cur != nil {
			partial = f.drain(cur, partial)
			// plik na ścieżce to już inny (rotacja): stary dokończony, przechodzimy na nowy od początku
			if a, err1 := cur.Stat(); err1 == nil {
				if b, err2 := os.Stat(f.path); err2 == nil && !os.SameFile(a, b) {
					partial = f.drain(cur, partial)
					cur.Close()
					cur = nil
					partial = nil
					startAtEnd = false
					continue
				}
			}
		}
		select {
		case <-f.stop:
			return
		case <-ticker.C:
		}
	}
}

// drain czyta wszystko, co dopisano, i emituje kompletne wiersze; niedokończony wiersz wraca jako reszta.
func (f *fileFollower) drain(r io.Reader, partial []byte) []byte {
	br := bufio.NewReader(r)
	for {
		chunk, err := br.ReadBytes('\n')
		partial = append(partial, chunk...)
		if err != nil {
			return partial
		}
		line := string(bytes.TrimRight(partial, "\r\n"))
		partial = partial[:0]
		f.emit(line)
	}
}

// Stop kończy czytanie i czeka na zakończenie gorutyny.
func (f *fileFollower) Stop() {
	f.once.Do(func() { close(f.stop) })
	<-f.done
}

// consoleEmit zwraca funkcję wypisującą wiersz na konsolę HUB-a z etykietą (poza plikiem hub.log: wiersze modułu
// są już w jego własnych plikach).
func consoleEmit(label string) func(string) {
	var mu sync.Mutex
	return func(line string) {
		mu.Lock()
		defer mu.Unlock()
		fmt.Fprintf(os.Stdout, "[%s] %s\n", label, line)
	}
}
