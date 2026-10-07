package timer

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// limitCounter liczy wywołania OnLimit per zegar.
type limitCounter struct {
	mu     sync.Mutex
	counts map[string]int
}

func newLimitCounter() *limitCounter { return &limitCounter{counts: map[string]int{}} }

func (c *limitCounter) callbacks() *Callbacks {
	cb := noopCallbacks()
	cb.OnLimit = func(_ time.Duration, id string) {
		c.mu.Lock()
		c.counts[id]++
		c.mu.Unlock()
	}
	return cb
}

func (c *limitCounter) get(id string) int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.counts[id]
}

// crash symuluje awarię: stan zapisany w chwili `at`, nowy proces (nowy Manager) startuje w chwili `restartAt`.
func crash(t *testing.T, m *Manager, at time.Time, restartAt time.Time, cb *Callbacks) *Manager {
	t.Helper()
	snap := m.Snapshot(at)
	// przez JSON, jak z pliku: sprawdza też, że wszystkie pola się serializują
	data, err := json.Marshal(snap)
	if err != nil {
		t.Fatal(err)
	}
	var loaded StateFile
	if err := json.Unmarshal(data, &loaded); err != nil {
		t.Fatal(err)
	}
	m2 := NewManager()
	m2.Restore(loaded, restartAt, cb)
	return m2
}

func elapsedOf(t *testing.T, m *Manager, id string) (time.Duration, State) {
	t.Helper()
	info, err := m.GetState(id)
	if err != nil {
		t.Fatalf("GetState(%s): %v", id, err)
	}
	return info.ElapsedTime, info.State
}

func TestRestoreRunningTimerAddsDowntime(t *testing.T) {
	m := NewManager()
	m.Create("main", TimerConfig{Type: TimerTypeIndependent, InitialTime: 20 * time.Minute, Limit: 20 * time.Minute, UpdateInterval: 20 * time.Millisecond, Callbacks: noopCallbacks()})
	m.Start("main")
	time.Sleep(200 * time.Millisecond)

	now := time.Now()
	m2 := crash(t, m, now, now.Add(7*time.Second), noopCallbacks()) // 7 s przestoju

	el, st := elapsedOf(t, m2, "main")
	if st != StateRunning {
		t.Fatalf("stan po odtworzeniu: %s", st)
	}
	// ~0.2 s sprzed awarii + 7 s przestoju
	if !almostEqual(el, 7200*time.Millisecond, 150*time.Millisecond) {
		t.Fatalf("upływ po odtworzeniu = %v, oczekiwano ok. 7.2s", el)
	}
	info, _ := m2.GetState("main")
	if info.InitialTime != 20*time.Minute || info.Limit != 20*time.Minute {
		t.Fatalf("initial/limit nie wróciły: %v %v", info.InitialTime, info.Limit)
	}
	// zegar biegnie dalej
	time.Sleep(200 * time.Millisecond)
	el2, _ := elapsedOf(t, m2, "main")
	if el2-el < 150*time.Millisecond {
		t.Fatalf("zegar po odtworzeniu nie biegnie: %v -> %v", el, el2)
	}
}

func TestRestorePausedTimerStaysPausedWithSameElapsed(t *testing.T) {
	m := NewManager()
	m.Create("main", TimerConfig{Type: TimerTypeIndependent, UpdateInterval: 20 * time.Millisecond, Callbacks: noopCallbacks()})
	m.Start("main")
	time.Sleep(300 * time.Millisecond)
	m.Pause("main")
	before, _ := elapsedOf(t, m, "main")

	now := time.Now()
	m2 := crash(t, m, now, now.Add(time.Hour), noopCallbacks())
	el, st := elapsedOf(t, m2, "main")
	if st != StatePaused {
		t.Fatalf("zegar w pauzie wrócił jako %s", st)
	}
	if el.Milliseconds() != before.Milliseconds() { // zapis ma dokładność do 1 ms
		t.Fatalf("upływ w pauzie zmienił się: %v -> %v", before, el)
	}
}

// Poprawka (a): zegar bez pause_at_limit po odtworzeniu biegnie dalej poza limit, a zdarzenie limitu jest raz.
func TestRestoreWithoutPauseAtLimitRunsPastLimitAndEmitsLimitOnce(t *testing.T) {
	cnt := newLimitCounter()
	m := NewManager()
	m.Create("main", TimerConfig{Type: TimerTypeIndependent, Limit: 1 * time.Second, PauseAtLimit: false, UpdateInterval: 20 * time.Millisecond, Callbacks: cnt.callbacks()})
	m.Start("main")
	time.Sleep(100 * time.Millisecond)

	now := time.Now()
	cnt2 := newLimitCounter()
	m2 := crash(t, m, now, now.Add(3*time.Second), cnt2.callbacks()) // limit 1 s minął w czasie przestoju

	el, st := elapsedOf(t, m2, "main")
	if st != StateRunning {
		t.Fatalf("zegar bez pause_at_limit powinien biec, jest %s", st)
	}
	if el <= 1*time.Second || !almostEqual(el, 3100*time.Millisecond, 150*time.Millisecond) {
		t.Fatalf("upływ = %v, oczekiwano ok. 3.1s (powyżej limitu 1s)", el)
	}
	time.Sleep(300 * time.Millisecond) // kilka tyknięć: zdarzenie nie może się powtórzyć
	el2, st2 := elapsedOf(t, m2, "main")
	if st2 != StateRunning || el2 <= el {
		t.Fatalf("zegar nie biegnie poza limit: %v -> %v (%s)", el, el2, st2)
	}
	if n := cnt2.get("main"); n != 1 {
		t.Fatalf("zdarzenie limitu wyemitowane %d razy, oczekiwano 1", n)
	}
}

// Poprawka (b): kara, która skończyła się w czasie przestoju, zatrzymuje się na limicie i zgłasza koniec raz.
func TestRestorePenaltyEndedDuringDowntimeEmitsLimitOnceAndStops(t *testing.T) {
	m := NewManager()
	m.Create("main", TimerConfig{Type: TimerTypeIndependent, UpdateInterval: 20 * time.Millisecond, Callbacks: noopCallbacks()})
	m.Start("main")
	m.Create("kara", TimerConfig{Type: TimerTypeDependent, ParentID: "main", Limit: 2 * time.Second, PauseAtLimit: true, UpdateInterval: 20 * time.Millisecond, Callbacks: noopCallbacks()})
	m.Start("kara")
	time.Sleep(200 * time.Millisecond)

	now := time.Now()
	cnt := newLimitCounter()
	m2 := crash(t, m, now, now.Add(5*time.Second), cnt.callbacks()) // kara (2 s) skończyła się w przestoju

	time.Sleep(300 * time.Millisecond)
	el, st := elapsedOf(t, m2, "kara")
	if st != StatePaused || el != 2*time.Second {
		t.Fatalf("kara po odtworzeniu: stan=%s upływ=%v, oczekiwano paused na 2s", st, el)
	}
	if n := cnt.get("kara"); n != 1 {
		t.Fatalf("koniec kary wyemitowany %d razy, oczekiwano 1", n)
	}
	if n := cnt.get("main"); n != 0 {
		t.Fatalf("zegar główny bez limitu nie powinien emitować limitu, jest %d", n)
	}
	mainEl, mainSt := elapsedOf(t, m2, "main")
	if mainSt != StateRunning || mainEl < 5*time.Second {
		t.Fatalf("zegar główny: stan=%s upływ=%v", mainSt, mainEl)
	}
}

func TestRestorePenaltyFollowsParentWithDowntime(t *testing.T) {
	m := NewManager()
	m.Create("main", TimerConfig{Type: TimerTypeIndependent, UpdateInterval: 20 * time.Millisecond, Callbacks: noopCallbacks()})
	m.Start("main")
	time.Sleep(150 * time.Millisecond)
	m.Create("kara", TimerConfig{Type: TimerTypeDependent, ParentID: "main", Limit: 2 * time.Minute, PauseAtLimit: true, UpdateInterval: 20 * time.Millisecond, Callbacks: noopCallbacks()})
	m.Start("kara")
	time.Sleep(150 * time.Millisecond)

	now := time.Now()
	m2 := crash(t, m, now, now.Add(10*time.Second), noopCallbacks())
	el, st := elapsedOf(t, m2, "kara")
	if st != StateRunning || !almostEqual(el, 10150*time.Millisecond, 200*time.Millisecond) {
		t.Fatalf("kara: stan=%s upływ=%v, oczekiwano running ok. 10.15s", st, el)
	}
}

func TestRestorePenaltyWithPausedParentDoesNotAdvance(t *testing.T) {
	m := NewManager()
	m.Create("main", TimerConfig{Type: TimerTypeIndependent, UpdateInterval: 20 * time.Millisecond, Callbacks: noopCallbacks()})
	m.Start("main")
	m.Create("kara", TimerConfig{Type: TimerTypeDependent, ParentID: "main", Limit: 2 * time.Minute, PauseAtLimit: true, UpdateInterval: 20 * time.Millisecond, Callbacks: noopCallbacks()})
	m.Start("kara")
	time.Sleep(300 * time.Millisecond)
	m.Pause("main")
	before, _ := elapsedOf(t, m, "kara")

	now := time.Now()
	m2 := crash(t, m, now, now.Add(time.Minute), noopCallbacks())
	el, _ := elapsedOf(t, m2, "kara")
	if !almostEqual(el, before, 50*time.Millisecond) {
		t.Fatalf("kara przy zatrzymanym rodzicu poszła do przodu: %v -> %v", before, el)
	}
	mainEl, mainSt := elapsedOf(t, m2, "main")
	if mainSt != StatePaused || mainEl == 0 {
		t.Fatalf("rodzic: %s %v", mainSt, mainEl)
	}
}

func TestRestoreDoesNotEmitLimitAlreadyReported(t *testing.T) {
	m := NewManager()
	m.Create("main", TimerConfig{Type: TimerTypeIndependent, Limit: 200 * time.Millisecond, PauseAtLimit: false, UpdateInterval: 20 * time.Millisecond, Callbacks: noopCallbacks()})
	m.Start("main")
	time.Sleep(400 * time.Millisecond) // limit osiągnięty przed awarią

	now := time.Now()
	cnt := newLimitCounter()
	crash(t, m, now, now.Add(time.Second), cnt.callbacks())
	time.Sleep(200 * time.Millisecond)
	if n := cnt.get("main"); n != 0 {
		t.Fatalf("limit zgłoszony przed awarią został wyemitowany ponownie (%d)", n)
	}
}

func TestRestoreIgnoresWallClockMovedBack(t *testing.T) {
	m := NewManager()
	m.Create("main", TimerConfig{Type: TimerTypeIndependent, UpdateInterval: 20 * time.Millisecond, Callbacks: noopCallbacks()})
	m.Start("main")
	time.Sleep(200 * time.Millisecond)
	now := time.Now()
	m2 := crash(t, m, now, now.Add(-time.Hour), noopCallbacks()) // zegar systemowy cofnięty
	el, _ := elapsedOf(t, m2, "main")
	if el < 0 || el > time.Second {
		t.Fatalf("upływ po cofnięciu zegara systemowego: %v", el)
	}
}

// Poprawka (c): czas startu zapisany jako Unix ms (UTC), niezależnie od strefy czasowej.
func TestSnapshotUsesUnixMillisecondsUTC(t *testing.T) {
	m := NewManager()
	m.Create("main", TimerConfig{Type: TimerTypeIndependent, UpdateInterval: 20 * time.Millisecond, Callbacks: noopCallbacks()})
	m.Start("main")
	time.Sleep(100 * time.Millisecond)

	loc := time.FixedZone("UTC+13", 13*3600)
	now := time.Now().In(loc)
	snap := m.Snapshot(now)
	if snap.SavedAtMs != now.UnixMilli() {
		t.Fatalf("saved_at_ms=%d, oczekiwano %d", snap.SavedAtMs, now.UnixMilli())
	}
	s := snap.Timers[0]
	if s.StartedAtMs > snap.SavedAtMs || snap.SavedAtMs-s.StartedAtMs > 1000 {
		t.Fatalf("started_at_ms=%d poza saved_at_ms=%d", s.StartedAtMs, snap.SavedAtMs)
	}
	data, _ := json.Marshal(snap)
	if !strings.Contains(string(data), `"started_at_ms":`) || strings.Contains(string(data), "T") && strings.Contains(string(data), "+13") {
		t.Fatalf("zapis nie wygląda na Unix ms: %s", data)
	}
}

func TestPersistenceWritesFileOnChangesAndOnClose(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state", "timers.json")
	m := NewManager()
	m.EnablePersistence(path)
	m.Create("main", TimerConfig{Type: TimerTypeIndependent, Limit: time.Minute, UpdateInterval: 20 * time.Millisecond, Callbacks: noopCallbacks()})
	m.Start("main")

	waitFor(t, 2*time.Second, func() bool {
		f, st, err := LoadStateFile(path, time.Now(), DefaultStateMaxAge)
		return err == nil && st == LoadRestored && len(f.Timers) == 1 && f.Timers[0].State == StateRunning && f.Timers[0].StartedAtMs > 0
	})
	m.Pause("main")
	waitFor(t, 2*time.Second, func() bool {
		f, _, _ := LoadStateFile(path, time.Now(), DefaultStateMaxAge)
		return len(f.Timers) == 1 && f.Timers[0].State == StatePaused
	})
	m.Remove("main")
	waitFor(t, 2*time.Second, func() bool {
		f, st, _ := LoadStateFile(path, time.Now(), DefaultStateMaxAge)
		return st == LoadRestored && len(f.Timers) == 0
	})
	m.Close()
	if _, err := os.Stat(path + ".tmp"); err == nil {
		t.Fatal("po zapisie został plik tymczasowy")
	}
}

func TestPersistenceSavesLimitPauseFromTicker(t *testing.T) {
	path := filepath.Join(t.TempDir(), "timers.json")
	m := NewManager()
	m.EnablePersistence(path)
	defer m.Close()
	m.Create("kara", TimerConfig{Type: TimerTypeIndependent, Limit: 200 * time.Millisecond, PauseAtLimit: true, UpdateInterval: 20 * time.Millisecond, Callbacks: noopCallbacks()})
	m.Start("kara")
	waitFor(t, 3*time.Second, func() bool {
		f, _, _ := LoadStateFile(path, time.Now(), DefaultStateMaxAge)
		return len(f.Timers) == 1 && f.Timers[0].State == StatePaused && f.Timers[0].HasReachedLimit
	})
}

func TestLoadStateFileStatuses(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "timers.json")
	now := time.Now()

	if _, st, err := LoadStateFile(path, now, DefaultStateMaxAge); st != LoadNone || err != nil {
		t.Fatalf("brak pliku: %s %v", st, err)
	}

	fresh := StateFile{Version: stateFileVersion, SavedAtMs: now.Add(-time.Hour).UnixMilli(), Timers: []TimerSnapshot{{ID: "a", State: StatePaused}}}
	if err := WriteStateFile(path, fresh); err != nil {
		t.Fatal(err)
	}
	if f, st, _ := LoadStateFile(path, now, DefaultStateMaxAge); st != LoadRestored || len(f.Timers) != 1 {
		t.Fatalf("świeży plik: %s %d", st, len(f.Timers))
	}

	stale := StateFile{Version: stateFileVersion, SavedAtMs: now.Add(-13 * time.Hour).UnixMilli(), Timers: []TimerSnapshot{{ID: "a"}}}
	WriteStateFile(path, stale)
	if f, st, _ := LoadStateFile(path, now, DefaultStateMaxAge); st != LoadStale || len(f.Timers) != 0 {
		t.Fatalf("przeterminowany plik: %s %d", st, len(f.Timers))
	}

	os.WriteFile(path, []byte("{to nie jest json"), 0o644)
	if _, st, err := LoadStateFile(path, now, DefaultStateMaxAge); st != LoadCorrupt || err == nil {
		t.Fatalf("uszkodzony plik: %s %v", st, err)
	}
	if _, err := os.Stat(path); err == nil {
		t.Fatal("uszkodzony plik powinien zostać odłożony na bok")
	}
	bad, _ := filepath.Glob(path + ".bad-*")
	if len(bad) != 1 {
		t.Fatalf("oczekiwano 1 pliku .bad-*, jest %d", len(bad))
	}
}

func TestRestoreTwiceDoesNotDuplicateTimers(t *testing.T) {
	m := NewManager()
	m.Create("main", TimerConfig{Type: TimerTypeIndependent, UpdateInterval: 20 * time.Millisecond, Callbacks: noopCallbacks()})
	snap := m.Snapshot(time.Now())
	var calls int32
	cb := noopCallbacks()
	cb.OnLimit = func(time.Duration, string) { atomic.AddInt32(&calls, 1) }
	if ids := m.Restore(snap, time.Now(), cb); len(ids) != 0 {
		t.Fatalf("istniejący zegar nie powinien być odtworzony ponownie: %v", ids)
	}
}

func waitFor(t *testing.T, d time.Duration, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(d)
	for time.Now().Before(deadline) {
		if cond() {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatal("warunek nie został spełniony w czasie")
}
