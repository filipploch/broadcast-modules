package obs

import (
	"sync"
	"time"
)

// RequestGate wstrzymuje żądania do OBS na czas zmiany zbioru scen (E2d3c3). OBS zgłasza CurrentSceneCollectionChanging przed zmianą
// i CurrentSceneCollectionChanged po niej; w tym czasie zbiór scen jest niespójny (żądania o sceny i źródła zwracają błędy albo
// dane poprzedniego zbioru), więc plugin czeka z wysłaniem kolejnych żądań do zdarzenia Changed.
//
// Odporność na kolejność zdarzeń i ich utratę:
//   - Changed, które dotarło PRZED Changing (zdarzenia przetworzone w odwrotnej kolejności), nie zostawia bramki zamkniętej: późne
//     Changing w oknie earlyChangedWindow po Changed jest ignorowane;
//   - jeśli Changed nigdy nie nadejdzie (zdarzenie utracone, rozłączenie), bramka otwiera się sama po maxPause.
type RequestGate struct {
	mu        sync.Mutex
	open      chan struct{} // zamknięty kanał = bramka otwarta
	paused    bool
	gen       uint64
	changedAt time.Time
	maxPause  time.Duration
	earlyWin  time.Duration
	now       func() time.Time
}

const (
	defaultMaxPause        = 15 * time.Second
	defaultEarlyChangedWin = 1500 * time.Millisecond
)

// NewRequestGate tworzy otwartą bramkę.
func NewRequestGate() *RequestGate {
	g := &RequestGate{open: make(chan struct{}), maxPause: defaultMaxPause, earlyWin: defaultEarlyChangedWin, now: time.Now}
	close(g.open)
	return g
}

// Changing: OBS rozpoczyna zmianę zbioru scen — zamyka bramkę (chyba że Changed przyszło tuż przed).
func (g *RequestGate) Changing() {
	g.mu.Lock()
	defer g.mu.Unlock()
	if !g.changedAt.IsZero() && g.now().Sub(g.changedAt) < g.earlyWin {
		return
	}
	if g.paused {
		return
	}
	g.paused = true
	g.open = make(chan struct{})
	g.gen++
	gen := g.gen
	time.AfterFunc(g.maxPause, func() { g.release(gen) })
}

// Changed: zmiana zakończona — otwiera bramkę.
func (g *RequestGate) Changed() {
	g.mu.Lock()
	g.changedAt = g.now()
	g.mu.Unlock()
	g.release(0)
}

// release otwiera bramkę; gen != 0 oznacza zegar bezpieczeństwa (działa tylko dla tej samej pauzy).
func (g *RequestGate) release(gen uint64) {
	g.mu.Lock()
	defer g.mu.Unlock()
	if !g.paused || (gen != 0 && gen != g.gen) {
		return
	}
	g.paused = false
	close(g.open)
}

// Paused: bramka jest zamknięta.
func (g *RequestGate) Paused() bool {
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.paused
}

// Wait czeka do otwarcia bramki; false, gdy nie otworzyła się w timeout.
func (g *RequestGate) Wait(timeout time.Duration) bool {
	g.mu.Lock()
	ch := g.open
	g.mu.Unlock()
	select {
	case <-ch:
		return true
	default:
	}
	select {
	case <-ch:
		return true
	case <-time.After(timeout):
		return false
	}
}
