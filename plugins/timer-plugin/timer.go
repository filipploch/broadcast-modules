package timer

import (
	"fmt"
	"sync"
	"time"
)


// TimerType represents the type of timer
type TimerType string

const (
	TimerTypeIndependent TimerType = "independent"
	TimerTypeDependent   TimerType = "dependent"
)

// State represents timer state
type State string

const (
	StateIdle    State = "idle"
	StateRunning State = "running"
	StatePaused  State = "paused"
	StateStopped State = "stopped"
)

// TimerConfig holds timer configuration
type TimerConfig struct {
	Type           TimerType
	ParentID       string
	InitialTime    time.Duration // Initial time offset (always added to display)
	Limit          time.Duration // 0 = no limit
	PauseAtLimit   bool
	UpdateInterval time.Duration // Tick interval (recommended 50ms)
	Metadata       map[string]interface{}
	Callbacks      *Callbacks
}

// Callbacks for timer events
type Callbacks struct {
	OnSecondTick func(elapsedTime time.Duration, timerID string)
	OnLimit      func(elapsedTime time.Duration, timerID string)
	OnStart      func(elapsedTime time.Duration, timerID string)
	OnPause      func(elapsedTime time.Duration, timerID string)
	OnResume     func(elapsedTime time.Duration, timerID string)
}

// TimerInfo contains timer information
type TimerInfo struct {
	ID              string
	Type            TimerType
	ParentID        string
	ElapsedTime     time.Duration // Current elapsed time (renamed from elapsed_time)
	PauseAtLimit    bool
	InitialTime     time.Duration // Initial time offset (renamed from initial_time)
	State           State
	Limit           time.Duration
	HasReachedLimit bool
	Metadata        map[string]interface{}
}

// timer represents an internal timer
type timer struct {
	id                  string
	timerType           TimerType
	parentID            string
	state               State
	t0                  time.Time     // System time when started/resumed (independent timers only)
	elapsedBase         time.Duration // Stored elapsed from before pause/resume (independent timers only)
	remainderTime       time.Duration // Remainder from last full second
	initialTime         time.Duration // Initial time offset
	limit               time.Duration // 0 = no limit
	pauseAtLimit        bool
	hasReachedLimit     bool
	updateInterval      time.Duration // Tick interval
	lastBroadcastSecond int64         // Last second for which we sent update
	metadata            map[string]interface{}
	callbacks           *Callbacks
	stopChan            chan struct{} // Channel to stop ticker
	mu                  sync.RWMutex

	// Pola dependent timerów (np. kar): elapsed jest WYLICZANY z rodzica,
	// zamiast liczony z własnego zegara systemowego. Dzięki temu dependent
	// automatycznie dziedziczy pauzę/wznowienie rodzica bez osobnej kaskady.
	parentOffset     time.Duration // elapsed rodzica w momencie utworzenia/reset tego timera
	manualAdjustment time.Duration // suma ręcznych korekt (AdjustTime/SetElapsedTime)
}

// Manager manages multiple timers
type Manager struct {
	timers map[string]*timer
	mu     sync.RWMutex
}

// NewManager creates a new timer manager
func NewManager() *Manager {
	return &Manager{
		timers: make(map[string]*timer),
	}
}

// parentElapsed returns the current elapsed time of a parent timer, for
// anchoring a newly created dependent timer. Caller must NOT already hold
// parent.mu (a fresh RLock is taken here).
func (m *Manager) parentElapsed(parent *timer) time.Duration {
	if parent == nil {
		return 0
	}
	parent.mu.RLock()
	defer parent.mu.RUnlock()
	return m.independentElapsed(parent)
}

// Create creates a new timer with the given id.
func (m *Manager) Create(id string, config TimerConfig) {
	updateInterval := config.UpdateInterval
	if updateInterval == 0 {
		updateInterval = 50 * time.Millisecond
	}

	var parentOffset time.Duration
	if config.Type == TimerTypeDependent && config.ParentID != "" {
		m.mu.RLock()
		parent := m.timers[config.ParentID]
		m.mu.RUnlock()
		parentOffset = m.parentElapsed(parent)
	}

	t := &timer{
		id:                  id,
		timerType:           config.Type,
		parentID:            config.ParentID,
		state:               StateIdle,
		elapsedBase:         0,
		remainderTime:       0,
		initialTime:         config.InitialTime,
		limit:               config.Limit,
		pauseAtLimit:        config.PauseAtLimit,
		updateInterval:      updateInterval,
		lastBroadcastSecond: -1,
		metadata:            config.Metadata,
		callbacks:           config.Callbacks,
		stopChan:            make(chan struct{}),
		parentOffset:        parentOffset,
	}

	if t.metadata == nil {
		t.metadata = make(map[string]interface{})
	}

	m.mu.Lock()
	m.timers[id] = t
	m.mu.Unlock()
}

// Ensure creates a timer with the given id only if it does not already exist.
// Returns true if the timer was created, false if it already existed.
func (m *Manager) Ensure(id string, config TimerConfig) bool {
	m.mu.Lock()
	defer m.mu.Unlock()

	if _, exists := m.timers[id]; exists {
		return false
	}

	updateInterval := config.UpdateInterval
	if updateInterval == 0 {
		updateInterval = 50 * time.Millisecond
	}

	var parentOffset time.Duration
	if config.Type == TimerTypeDependent && config.ParentID != "" {
		// m.mu is already held (write lock) — read the map directly instead
		// of calling parentElapsed's RLock path (would deadlock, RWMutex
		// isn't reentrant).
		if parent, exists := m.timers[config.ParentID]; exists {
			parent.mu.RLock()
			parentOffset = m.independentElapsed(parent)
			parent.mu.RUnlock()
		}
	}

	t := &timer{
		id:                  id,
		timerType:           config.Type,
		parentID:            config.ParentID,
		state:               StateIdle,
		elapsedBase:         0,
		remainderTime:       0,
		initialTime:         config.InitialTime,
		limit:               config.Limit,
		pauseAtLimit:        config.PauseAtLimit,
		updateInterval:      updateInterval,
		lastBroadcastSecond: -1,
		metadata:            config.Metadata,
		callbacks:           config.Callbacks,
		stopChan:            make(chan struct{}),
		parentOffset:        parentOffset,
	}

	if t.metadata == nil {
		t.metadata = make(map[string]interface{})
	}

	m.timers[id] = t
	return true
}

// Start starts a timer
func (m *Manager) Start(timerID string) error {
	m.mu.RLock()
	t, exists := m.timers[timerID]
	m.mu.RUnlock()

	if !exists {
		return fmt.Errorf("timer not found: %s", timerID)
	}

	t.mu.Lock()
	defer t.mu.Unlock()

	if t.state == StateRunning {
		return nil // Already running
	}

	// Check if at limit
	if t.limit > 0 && t.pauseAtLimit && t.elapsedBase >= t.limit {
		// return fmt.Errorf("timer is at limit, cannot start")
		go t.callbacks.OnLimit(t.elapsedBase, timerID)
	} else {
		// Set t0 and start
		t.t0 = time.Now()
		t.state = StateRunning

		// Reset stopChan if needed
		select {
		case <-t.stopChan:
			t.stopChan = make(chan struct{})
		default:
		}

		// Calculate last broadcast second based on current elapsed
		t.lastBroadcastSecond = (t.elapsedBase.Milliseconds() / 1000) - 1

		// Start ticker goroutine
		go m.runTimer(timerID)

		// Call OnStart callback
		if t.callbacks != nil && t.callbacks.OnStart != nil {
			go t.callbacks.OnStart(t.elapsedBase, timerID)
		}
	}

	return nil
}

// Pause pauses a running timer
func (m *Manager) Pause(timerID string) error {
	m.mu.RLock()
	t, exists := m.timers[timerID]
	m.mu.RUnlock()

	if !exists {
		return fmt.Errorf("timer not found: %s", timerID)
	}

	t.mu.Lock()
	defer t.mu.Unlock()

	if t.state != StateRunning {
		return fmt.Errorf("timer is not running")
	}

	// Stop ticker
	close(t.stopChan)

	// Calculate current elapsed
	currentElapsed := m.calculateElapsedTime(t)
	t.elapsedBase = currentElapsed
	t.remainderTime = currentElapsed % (1000 * time.Millisecond)
	t.state = StatePaused

	// Call OnPause callback
	if t.callbacks != nil && t.callbacks.OnPause != nil {
		go t.callbacks.OnPause(t.elapsedBase, timerID)
	}

	return nil
}

// Resume resumes a paused timer
func (m *Manager) Resume(timerID string) error {
	return m.Start(timerID)
}

// Reset resets timer to elapsed_time = 0
func (m *Manager) Reset(timerID string) error {
	m.mu.RLock()
	t, exists := m.timers[timerID]
	m.mu.RUnlock()

	if !exists {
		return fmt.Errorf("timer not found: %s", timerID)
	}

	// Dla dependent timera "0" oznacza: od teraz zaczynamy liczyć od nowa
	// względem rodzica — trzeba więc ponownie zakotwiczyć parentOffset na
	// jego aktualnym elapsed (obliczone PRZED zablokowaniem t.mu, żeby
	// zachować kolejność blokad dziecko→rodzic).
	var parentOffset time.Duration
	if t.timerType == TimerTypeDependent && t.parentID != "" {
		m.mu.RLock()
		parent, pexists := m.timers[t.parentID]
		m.mu.RUnlock()
		if pexists {
			parentOffset = m.parentElapsed(parent)
		}
	}

	t.mu.Lock()
	defer t.mu.Unlock()

	t.elapsedBase = 0
	t.remainderTime = 0
	t.state = StateIdle
	t.hasReachedLimit = false
	t.lastBroadcastSecond = -1
	if t.timerType == TimerTypeDependent {
		t.parentOffset = parentOffset
		t.manualAdjustment = 0
	}

	return nil
}

// Remove removes a timer, stopping it first if it is running
func (m *Manager) Remove(timerID string) error {
	m.mu.RLock()
	t, exists := m.timers[timerID]
	m.mu.RUnlock()

	if !exists {
		return fmt.Errorf("timer not found: %s", timerID)
	}

	t.mu.Lock()
	if t.state == StateRunning {
		// Stop the ticker goroutine before removing
		close(t.stopChan)
	}
	t.state = StateStopped
	t.mu.Unlock()

	m.mu.Lock()
	delete(m.timers, timerID)
	m.mu.Unlock()

	return nil
}

// GetState returns the current state of a timer
func (m *Manager) GetState(timerID string) (*TimerInfo, error) {
	m.mu.RLock()
	t, exists := m.timers[timerID]
	m.mu.RUnlock()

	if !exists {
		return nil, fmt.Errorf("timer not found: %s", timerID)
	}

	t.mu.RLock()
	defer t.mu.RUnlock()

	return &TimerInfo{
		ID:              t.id,
		Type:            t.timerType,
		ParentID:        t.parentID,
		ElapsedTime:     m.calculateElapsedTime(t),
		PauseAtLimit:    t.pauseAtLimit,
		InitialTime:     t.initialTime,
		State:           t.state,
		Limit:           t.limit,
		HasReachedLimit: t.hasReachedLimit,
		Metadata:        t.metadata,
	}, nil
}

// GetAllTimers returns information about all timers
func (m *Manager) GetAllTimers() []*TimerInfo {
	m.mu.RLock()
	defer m.mu.RUnlock()

	timers := make([]*TimerInfo, 0, len(m.timers))
	for id := range m.timers {
		if info, err := m.GetState(id); err == nil {
			timers = append(timers, info)
		}
	}

	return timers
}

// AdjustTime adjusts timer by delta
func (m *Manager) AdjustTime(timerID string, delta time.Duration) error {
	m.mu.RLock()
	t, exists := m.timers[timerID]
	m.mu.RUnlock()

	if !exists {
		return fmt.Errorf("timer not found: %s", timerID)
	}

	t.mu.Lock()
	defer t.mu.Unlock()

	if t.state == StateStopped {
		return fmt.Errorf("timer is stopped, cannot adjust")
	}

	// Zapamiętaj PRZED wspólnym blokiem obsługi limitu poniżej — potrzebne,
	// żeby dependent timer (kara) mógł wznowić odliczanie, jeśli korekta
	// cofnie go poniżej limitu po automatycznej pauzie (patrz niżej).
	wasPausedAtLimit := t.hasReachedLimit && t.state == StatePaused

	currentElapsed := m.calculateElapsedTime(t)
	newElapsed := currentElapsed + delta

	// Handle negative elapsed
	if newElapsed < 0 {
		newElapsed = 0
	}

	// Handle limit
	if t.limit > 0 && t.pauseAtLimit && newElapsed >= t.limit {
		newElapsed = t.limit
		t.hasReachedLimit = true

		// If running, we need to pause
		if t.state == StateRunning {
			close(t.stopChan)
			t.state = StatePaused
			t.stopChan = make(chan struct{})
		}
	} else {
		t.hasReachedLimit = false
	}

	if t.timerType == TimerTypeDependent {
		// Elapsed jest wyliczany z rodzica — korekta idzie do manualAdjustment,
		// przeliczonego tak, żeby kolejne wywołanie calculateElapsedTime()
		// dało dokładnie (skorygowane) newElapsed.
		t.manualAdjustment += newElapsed - currentElapsed

		// Kara automatycznie zapauzowana po osiągnięciu limitu (0:00) — jeśli
		// korekta cofnęła ją teraz poniżej limitu, wznów odliczanie. Operator
		// nie ma dziś osobnego przełącznika pauzy per kara, więc
		// "paused-at-limit" zawsze oznacza właśnie automatyczną pauzę, nigdy
		// ręczną — bez tego korekta "ożywiającej" karę zmieniałaby tylko
		// zamrożoną wartość, nigdy nie wznawiając jej odliczania.
		if wasPausedAtLimit && !t.hasReachedLimit {
			t.state = StateRunning
			select {
			case <-t.stopChan:
				t.stopChan = make(chan struct{})
			default:
			}
			go m.runTimer(t.id)
		}

		if t.state != StateRunning {
			t.elapsedBase = newElapsed
			t.remainderTime = newElapsed % (1000 * time.Millisecond)
		} else {
			t.lastBroadcastSecond = (newElapsed.Milliseconds() / 1000) - 1
		}
		return nil
	}

	// Update elapsed base
	if t.state == StateRunning {
		// Adjust t0 to maintain continuity
		diff := newElapsed - currentElapsed
		t.t0 = t.t0.Add(-diff)

		// Recalculate last broadcast second
		t.lastBroadcastSecond = (newElapsed.Milliseconds() / 1000) - 1
	} else {
		t.elapsedBase = newElapsed
		t.remainderTime = newElapsed % (1000 * time.Millisecond)
	}

	return nil
}

// SetElapsedTime sets the exact elapsed time
func (m *Manager) SetElapsedTime(timerID string, newElapsed time.Duration) error {
	currentElapsed := time.Duration(0)

	m.mu.RLock()
	t, exists := m.timers[timerID]
	m.mu.RUnlock()

	if exists {
		t.mu.RLock()
		currentElapsed = m.calculateElapsedTime(t)
		t.mu.RUnlock()
	}

	delta := newElapsed - currentElapsed
	return m.AdjustTime(timerID, delta)
}

// runTimer is the ticker goroutine
func (m *Manager) runTimer(timerID string) {
	m.mu.RLock()
	t, exists := m.timers[timerID]
	m.mu.RUnlock()

	if !exists {
		return
	}

	ticker := time.NewTicker(t.updateInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			t.mu.Lock()
			if t.state != StateRunning {
				t.mu.Unlock()
				return
			}

			currentElapsed := m.calculateElapsedTime(t)
			currentSecond := currentElapsed.Milliseconds() / 1000

			shouldBroadcast := currentSecond > t.lastBroadcastSecond
			if shouldBroadcast {
				t.lastBroadcastSecond = currentSecond
			}

			limit := t.limit
			pauseAtLimit := t.pauseAtLimit
			hasReachedLimit := t.hasReachedLimit
			callbacks := t.callbacks
			t.mu.Unlock()

			if shouldBroadcast && callbacks != nil && callbacks.OnSecondTick != nil {
				// Raw elapsed — BEZ doliczania t.initialTime. initial_time
				// jest już osobnym polem w broadcastowanym payloadzie
				// (plugin.go), więc doliczanie go tutaj powodowało podwójne
				// zliczanie po stronie klienta (overlay/UI dodają
				// initial_time do "elapsed_time", który już je zawierał).
				broadcastTime := time.Duration(currentSecond*1000) * time.Millisecond
				callbacks.OnSecondTick(broadcastTime, timerID)
			}

			if limit > 0 && currentElapsed >= limit && !hasReachedLimit {
				t.mu.Lock()
				t.hasReachedLimit = true

				if pauseAtLimit {
					t.state = StatePaused
					t.elapsedBase = limit
					t.remainderTime = 0
					t.mu.Unlock()

					if callbacks != nil && callbacks.OnLimit != nil {
						go callbacks.OnLimit(limit, timerID)
					}

					return
				}
				t.mu.Unlock()

				if callbacks != nil && callbacks.OnLimit != nil {
					go callbacks.OnLimit(limit, timerID)
				}
			}

		case <-t.stopChan:
			return
		}
	}
}

// calculateElapsedTime calculates current elapsed time.
//
// Dependent timers (kary) nie mają własnego zegara — ich elapsed jest
// wyliczany z rodzica (main timer), więc automatycznie dziedziczą jego
// pauzę/wznowienie bez żadnej kaskady komend. Timer musi być sam w stanie
// Running, żeby w ogóle podążać za rodzicem — jeśli operator jawnie
// zapauzował konkretną karę, zamraża się ona niezależnie od rodzica
// (tak samo jak niezależny timer).
func (m *Manager) calculateElapsedTime(t *timer) time.Duration {
	if t.state != StateRunning {
		return t.elapsedBase
	}

	if t.timerType == TimerTypeDependent && t.parentID != "" {
		m.mu.RLock()
		parent, exists := m.timers[t.parentID]
		m.mu.RUnlock()

		if exists {
			elapsed := m.parentElapsed(parent) - t.parentOffset + t.manualAdjustment
			if elapsed < 0 {
				elapsed = 0
			}
			return elapsed
		}
		// Rodzic zniknął (np. usunięty) — zamroź na ostatniej znanej wartości.
		return t.elapsedBase
	}

	return m.independentElapsed(t)
}

// independentElapsed calculates elapsed time from the timer's own clock
// (t0/elapsedBase), ignoring any parent relationship. Caller must already
// hold t.mu (read or write).
func (m *Manager) independentElapsed(t *timer) time.Duration {
	if t.state != StateRunning {
		return t.elapsedBase
	}
	if t.t0.IsZero() {
		return t.elapsedBase
	}
	return time.Since(t.t0) + t.elapsedBase
}

