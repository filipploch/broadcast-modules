package main

import (
	"bytes"
	"strconv"
	"strings"
	"sync"
	"time"
)

// progressTracker czyta strumień `-progress pipe:1` z ffmpeg (linie klucz=wartość, co ok. sekundę) i pamięta, ile klatek
// przetworzył proces i kiedy licznik ostatnio wzrósł. To podstawa watchdogu: proces, który żyje, ale nie produkuje klatek
// (kamera zamarła, urządzenie pośrednie bez piszącego), da się odróżnić od procesu, który po prostu pracuje.
type progressTracker struct {
	mu          sync.Mutex
	buf         []byte
	frame       int64
	started     time.Time
	lastAdvance time.Time
	now         func() time.Time // w testach podmieniane
}

func newProgressTracker() *progressTracker {
	p := &progressTracker{now: time.Now}
	p.started = p.now()
	p.lastAdvance = p.started
	return p
}

// progressArgs to globalne opcje ffmpeg włączające raport postępu na standardowym wyjściu.
func progressArgs() []string {
	return []string{"-nostats", "-progress", "pipe:1", "-stats_period", "1"}
}

// Write implementuje io.Writer: wystarczy podpiąć jako cmd.Stdout.
func (p *progressTracker) Write(b []byte) (int, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.buf = append(p.buf, b...)
	for {
		i := bytes.IndexByte(p.buf, '\n')
		if i < 0 {
			break
		}
		line := strings.TrimSpace(string(p.buf[:i]))
		p.buf = p.buf[i+1:]
		if rest, ok := strings.CutPrefix(line, "frame="); ok {
			if n, err := strconv.ParseInt(strings.TrimSpace(rest), 10, 64); err == nil && n > p.frame {
				p.frame = n
				p.lastAdvance = p.now()
			}
		}
	}
	if len(p.buf) > 4096 { // zabezpieczenie przed linią bez końca
		p.buf = nil
	}
	return len(b), nil
}

// Frames: liczba klatek zgłoszona przez proces.
func (p *progressTracker) Frames() int64 {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.frame
}

// SinceAdvance: czas od ostatniego wzrostu licznika klatek (albo od startu, gdy żadnej klatki jeszcze nie było).
func (p *progressTracker) SinceAdvance() time.Duration {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.now().Sub(p.lastAdvance)
}

// SinceStart: czas od uruchomienia procesu.
func (p *progressTracker) SinceStart() time.Duration {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.now().Sub(p.started)
}
