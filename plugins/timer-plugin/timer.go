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
	t0                  time.Time     // System time when started/resumed
	elapsedBase         time.Duration // Stored elapsed from before pause/resume
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

// Create creates a new timer and returns its ID
func (m *Manager) Create(config TimerConfig) string {
	id := generateID()

	updateInterval := config.UpdateInterval
	if updateInterval == 0 {
		updateInterval = 50 * time.Millisecond
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
	}

	if t.metadata == nil {
		t.metadata = make(map[string]interface{})
	}

	m.mu.Lock()
	m.timers[id] = t
	m.mu.Unlock()

	return id
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
		go t.callbacks.OnLimit(t.elapsedBase+t.initialTime, timerID)
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
			go t.callbacks.OnStart(t.elapsedBase+t.initialTime, timerID)
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
		go t.callbacks.OnPause(t.elapsedBase+t.initialTime, timerID)
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

	t.mu.Lock()
	defer t.mu.Unlock()

	if t.state != StatePaused {
		t.state = StatePaused
	}

	t.elapsedBase = 0
	t.remainderTime = 0
	t.state = StateIdle
	t.hasReachedLimit = false
	t.lastBroadcastSecond = -1

	return nil
}

// Remove removes a timer
func (m *Manager) Remove(timerID string) error {
	m.mu.RLock()
	t, exists := m.timers[timerID]
	m.mu.RUnlock()

	if !exists {
		return fmt.Errorf("timer not found: %s", timerID)
	}

	t.mu.Lock()
	if t.state == StateRunning {
		t.mu.Unlock()
		return fmt.Errorf("cannot remove running timer, pause it first")
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
			t.mu.RLock()
			if t.state != StateRunning {
				t.mu.RUnlock()
				return
			}

			currentElapsed := m.calculateElapsedTime(t)
			currentSecond := currentElapsed.Milliseconds() / 1000
			lastBroadcast := t.lastBroadcastSecond
			limit := t.limit
			pauseAtLimit := t.pauseAtLimit
			hasReachedLimit := t.hasReachedLimit
			callbacks := t.callbacks
			t.mu.RUnlock()

			// Check if we've reached a new full second
			if currentSecond > lastBroadcast {
				t.mu.Lock()
				t.lastBroadcastSecond = currentSecond
				t.mu.Unlock()

				// Call OnSecondTick callback
				if callbacks != nil && callbacks.OnSecondTick != nil {
					broadcastTime := time.Duration(currentSecond*1000) * time.Millisecond
					go callbacks.OnSecondTick(broadcastTime+t.initialTime, timerID)
				}
			}

			// Check limit
			if limit > 0 && currentElapsed >= limit && !hasReachedLimit {
				t.mu.Lock()
				t.hasReachedLimit = true

				if pauseAtLimit {
					// Stop ticker and pause
					t.state = StatePaused
					t.elapsedBase = limit
					t.remainderTime = 0
					t.mu.Unlock()

					// Call OnLimit callback
					if callbacks != nil && callbacks.OnLimit != nil {
						go callbacks.OnLimit(limit+t.initialTime, timerID)
					}

					return
				}
				t.mu.Unlock()

				// Call OnLimit callback (non-pausing)
				if callbacks != nil && callbacks.OnLimit != nil {
					go callbacks.OnLimit(limit+t.initialTime, timerID)
				}
			}

		case <-t.stopChan:
			return
		}
	}
}

// calculateElapsedTime calculates current elapsed time
func (m *Manager) calculateElapsedTime(t *timer) time.Duration {
	if t.state != StateRunning {
		return t.elapsedBase
	}

	if t.t0.IsZero() {
		return t.elapsedBase
	}

	elapsed := time.Since(t.t0) + t.elapsedBase
	return elapsed
}

// generateID generates a unique timer ID
func generateID() string {
	return fmt.Sprintf("timer_%d", time.Now().UnixNano())
}
