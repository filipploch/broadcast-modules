package timer

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"time"
)

// Zapis stanu zegarów na dysk (E2a). Po awarii i ponownym uruchomieniu pluginu zegary wracają z doliczonym przestojem.
//
// Czas zapisywany jest jako czas ścienny UTC w milisekundach (Unix ms), bo czas monotoniczny (t0) nie przetrwa procesu.
// Dla zegara niezależnego w stanie "running" zapisujemy: czas bazowy (elapsedBase) i chwilę startu odcinka (started_at_ms).
// Upływ po restarcie = czas bazowy + (teraz - started_at_ms). Zegary zależne (kary) zapisują pola wyliczane z rodzica
// (parentOffset, manualAdjustment), więc po odtworzeniu rodzica dziedziczą jego upływ, w tym przestój.

const stateFileVersion = 1

// DefaultStateMaxAge to wiek pliku stanu, powyżej którego jest ignorowany (rozgrywki z poprzedniego dnia nie wracają).
const DefaultStateMaxAge = 12 * time.Hour

// LoadStatus opisuje wynik wczytania pliku stanu (do logu i do odpowiedzi get_all_timers).
type LoadStatus string

const (
	LoadNone     LoadStatus = "none"     // brak pliku: pierwszy start
	LoadRestored LoadStatus = "restored" // plik poprawny i świeży
	LoadStale    LoadStatus = "stale"    // plik starszy niż limit wieku: zignorowany
	LoadCorrupt  LoadStatus = "corrupt"  // plik uszkodzony: odłożony na bok, start bez zegarów
)

// TimerSnapshot to zapisany stan jednego zegara.
type TimerSnapshot struct {
	ID                 string                 `json:"id"`
	Type               TimerType              `json:"type"`
	ParentID           string                 `json:"parent_id,omitempty"`
	State              State                  `json:"state"`
	BaseMs             int64                  `json:"base_ms"`                 // elapsedBase
	StartedAtMs        int64                  `json:"started_at_ms,omitempty"` // Unix ms (UTC) startu odcinka; tylko zegar niezależny w stanie running
	InitialMs          int64                  `json:"initial_ms"`              // initialTime
	LimitMs            int64                  `json:"limit_ms"`
	PauseAtLimit       bool                   `json:"pause_at_limit"`
	HasReachedLimit    bool                   `json:"has_reached_limit"`
	UpdateIntervalMs   int64                  `json:"update_interval_ms"`
	ParentOffsetMs     int64                  `json:"parent_offset_ms,omitempty"`
	ManualAdjustmentMs int64                  `json:"manual_adjustment_ms,omitempty"`
	Metadata           map[string]interface{} `json:"metadata,omitempty"`
}

// StateFile to zawartość pliku stanu.
type StateFile struct {
	Version   int             `json:"version"`
	SavedAtMs int64           `json:"saved_at_ms"` // Unix ms (UTC)
	Timers    []TimerSnapshot `json:"timers"`
}

// persistence trzyma stan zapisu w tle. Zapis jest wyzwalany bez blokad (markDirty), więc można go wołać pod t.mu.
type persistence struct {
	path  string
	dirty chan struct{}
	stop  chan struct{}
	done  chan struct{}
	once  sync.Once
}

func (m *Manager) markDirty() {
	if m.persist == nil {
		return
	}
	select {
	case m.persist.dirty <- struct{}{}:
	default: // zapis już zaplanowany; zobaczy też tę zmianę
	}
}

// EnablePersistence włącza zapis stanu do pliku (zapis atomowy: plik tymczasowy i podmiana) przy każdej zmianie.
func (m *Manager) EnablePersistence(path string) {
	p := &persistence{path: path, dirty: make(chan struct{}, 1), stop: make(chan struct{}), done: make(chan struct{})}
	m.persist = p
	go func() {
		defer close(p.done)
		for {
			select {
			case <-p.dirty:
				if err := WriteStateFile(p.path, m.Snapshot(time.Now())); err != nil {
					log.Printf("❌ Nie udało się zapisać stanu zegarów: %v", err)
				}
			case <-p.stop:
				return
			}
		}
	}()
}

// Close kończy zapis w tle i zapisuje stan po raz ostatni.
func (m *Manager) Close() {
	p := m.persist
	if p == nil {
		return
	}
	p.once.Do(func() {
		close(p.stop)
		<-p.done
		if err := WriteStateFile(p.path, m.Snapshot(time.Now())); err != nil {
			log.Printf("❌ Nie udało się zapisać stanu zegarów przy zamknięciu: %v", err)
		}
	})
}

// Snapshot zwraca zapisywalny stan wszystkich zegarów (lista kopiowana pod m.mu, potem blokady pojedynczych zegarów).
func (m *Manager) Snapshot(now time.Time) StateFile {
	m.mu.RLock()
	timers := make([]*timer, 0, len(m.timers))
	for _, t := range m.timers {
		timers = append(timers, t)
	}
	m.mu.RUnlock()

	nowMs := now.UnixMilli()
	out := StateFile{Version: stateFileVersion, SavedAtMs: nowMs, Timers: make([]TimerSnapshot, 0, len(timers))}
	for _, t := range timers {
		t.mu.RLock()
		s := TimerSnapshot{
			ID: t.id, Type: t.timerType, ParentID: t.parentID, State: t.state,
			BaseMs: t.elapsedBase.Milliseconds(), InitialMs: t.initialTime.Milliseconds(),
			LimitMs: t.limit.Milliseconds(), PauseAtLimit: t.pauseAtLimit, HasReachedLimit: t.hasReachedLimit,
			UpdateIntervalMs: t.updateInterval.Milliseconds(),
			ParentOffsetMs:   t.parentOffset.Milliseconds(), ManualAdjustmentMs: t.manualAdjustment.Milliseconds(),
			Metadata: t.metadata,
		}
		if t.state == StateRunning && t.timerType != TimerTypeDependent && !t.t0.IsZero() {
			s.StartedAtMs = nowMs - time.Since(t.t0).Milliseconds()
		}
		out.Timers = append(out.Timers, s)
		t.mu.RUnlock()
	}
	sort.Slice(out.Timers, func(i, j int) bool { return out.Timers[i].ID < out.Timers[j].ID })
	return out
}

// Restore odtwarza zegary ze stanu. Zegary w stanie running biegną dalej z doliczonym przestojem (czas ścienny).
// Zdarzenia, które przypadły na czas przestoju (osiągnięcie limitu, koniec kary), są emitowane dokładnie raz
// przez cb.OnLimit; zegar z pause_at_limit staje na limicie, bez pause_at_limit biegnie dalej poza limit.
// Zwraca identyfikatory odtworzonych zegarów.
func (m *Manager) Restore(f StateFile, now time.Time, cb *Callbacks) []string {
	nowMs := now.UnixMilli()
	restored := make([]*timer, 0, len(f.Timers))

	m.mu.Lock()
	for _, s := range f.Timers {
		if _, exists := m.timers[s.ID]; exists {
			continue
		}
		interval := time.Duration(s.UpdateIntervalMs) * time.Millisecond
		if interval <= 0 {
			interval = 50 * time.Millisecond
		}
		t := &timer{
			id: s.ID, timerType: s.Type, parentID: s.ParentID, state: s.State,
			elapsedBase:         time.Duration(s.BaseMs) * time.Millisecond,
			remainderTime:       time.Duration(s.BaseMs%1000) * time.Millisecond,
			initialTime:         time.Duration(s.InitialMs) * time.Millisecond,
			limit:               time.Duration(s.LimitMs) * time.Millisecond,
			pauseAtLimit:        s.PauseAtLimit,
			hasReachedLimit:     s.HasReachedLimit,
			updateInterval:      interval,
			lastBroadcastSecond: -1,
			metadata:            s.Metadata,
			callbacks:           cb,
			stopChan:            make(chan struct{}),
			parentOffset:        time.Duration(s.ParentOffsetMs) * time.Millisecond,
			manualAdjustment:    time.Duration(s.ManualAdjustmentMs) * time.Millisecond,
		}
		if t.metadata == nil {
			t.metadata = make(map[string]interface{})
		}
		if t.state == StateRunning && t.timerType != TimerTypeDependent {
			down := nowMs - s.StartedAtMs
			if s.StartedAtMs == 0 || down < 0 {
				down = 0 // brak czasu startu albo zegar systemowy cofnięty: nie doliczamy nic
			}
			t.t0 = time.Now().Add(-time.Duration(down) * time.Millisecond)
		}
		m.timers[s.ID] = t
		restored = append(restored, t)
	}
	m.mu.Unlock()

	// Najpierw zegary niezależne (rodzice), potem zależne: upływ kary wylicza się z rodzica po jego ewentualnym zatrzymaniu na limicie.
	sort.SliceStable(restored, func(i, j int) bool {
		return restored[i].timerType != TimerTypeDependent && restored[j].timerType == TimerTypeDependent
	})

	ids := make([]string, 0, len(restored))
	for _, t := range restored {
		ids = append(ids, t.id)
		t.mu.Lock()
		elapsed := m.calculateElapsedTime(t)
		if t.state == StateRunning && t.limit > 0 && elapsed >= t.limit && !t.hasReachedLimit {
			t.hasReachedLimit = true
			if t.pauseAtLimit {
				t.state = StatePaused
				t.elapsedBase = t.limit
				t.remainderTime = 0
			}
			if cb != nil && cb.OnLimit != nil {
				go cb.OnLimit(t.limit, t.id)
			}
		}
		running := t.state == StateRunning
		if running {
			t.lastBroadcastSecond = elapsed.Milliseconds()/1000 - 1
		}
		t.mu.Unlock()
		if running {
			go m.runTimer(t.id)
		}
	}
	m.markDirty()
	return ids
}

// WriteStateFile zapisuje stan atomowo: do pliku tymczasowego obok, potem podmiana.
func WriteStateFile(path string, f StateFile) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(f, "", "  ")
	if err != nil {
		return err
	}
	tmp := path + ".tmp"
	file, err := os.OpenFile(tmp, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
	if err != nil {
		return err
	}
	if _, err := file.Write(data); err != nil {
		file.Close()
		return err
	}
	if err := file.Sync(); err != nil {
		file.Close()
		return err
	}
	if err := file.Close(); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

// LoadStateFile wczytuje plik stanu. Plik uszkodzony jest odkładany obok (timers.json.bad-<czas>), plik starszy niż
// maxAge jest ignorowany. Zwraca status i, dla LoadRestored, zawartość.
func LoadStateFile(path string, now time.Time, maxAge time.Duration) (StateFile, LoadStatus, error) {
	var f StateFile
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return f, LoadNone, nil
	}
	if err != nil {
		return f, LoadCorrupt, err
	}
	if err := json.Unmarshal(data, &f); err != nil || f.Version != stateFileVersion {
		bad := fmt.Sprintf("%s.bad-%s", path, now.Format("20060102-150405"))
		_ = os.Rename(path, bad)
		if err == nil {
			err = fmt.Errorf("nieznana wersja pliku stanu: %d", f.Version)
		}
		return StateFile{}, LoadCorrupt, err
	}
	if maxAge > 0 && now.Sub(time.UnixMilli(f.SavedAtMs)) > maxAge {
		return StateFile{}, LoadStale, nil
	}
	return f, LoadRestored, nil
}
