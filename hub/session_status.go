package main

import (
	"log"
	"sync"
	"time"
)

// Status sesji transmisji w HUB-ie (E2d2, poprawka C): moduł zgłasza każdą zmianę statusu i ponawia zgłoszenie po każdym
// połączeniu; HUB pamięta ostatni znany status. Od niego zależą restart OBS po awarii i reguła zamykania OBS/modułu.
// HUB nigdy nie pyta o to modułu, więc decyzje nie zależą od tego, czy moduł akurat odpowiada.

const (
	sessionNone        = "none"
	sessionPreparation = "preparation"
	sessionOnAir       = "on_air"
)

// SessionStatus to ostatni znany status sesji.
type SessionStatus struct {
	State     string    `json:"state"` // none / preparation / on_air; "" gdy nic nie zgłoszono
	SessionID int       `json:"session_id"`
	GameID    int       `json:"game_id"`
	At        time.Time `json:"at"`
	Known     bool      `json:"known"`     // czy kiedykolwiek zgłoszono albo odczytano z pliku stanu
	FromFile  bool      `json:"from_file"` // status pochodzi z pliku stanu (moduł jeszcze go nie zgłosił po starcie HUB-a)
}

// IsOpen: sesja otwarta (przygotowanie albo na antenie) i status znany.
func (s SessionStatus) IsOpen() bool {
	return s.Known && (s.State == sessionPreparation || s.State == sessionOnAir)
}

// OpenForShutdown: przy zamykaniu HUB-a brak wiedzy liczy się jak sesja otwarta (bezpieczna strona: nic nie zamykamy).
func (s SessionStatus) OpenForShutdown() bool { return !s.Known || s.IsOpen() }

// OpenForRestart: przy restarcie OBS brak wiedzy liczy się jak brak sesji (bezpieczna strona: nie uruchamiamy OBS bez powodu).
func (s SessionStatus) OpenForRestart() bool { return s.IsOpen() }

type sessionTracker struct {
	mu       sync.RWMutex
	st       SessionStatus
	onChange func(SessionStatus) // np. zapis do pliku stanu
}

func (t *sessionTracker) get() SessionStatus {
	t.mu.RLock()
	defer t.mu.RUnlock()
	return t.st
}

// restore ustawia status odczytany z pliku stanu (bez wywoływania onChange).
func (t *sessionTracker) restore(st SessionStatus) {
	t.mu.Lock()
	t.st = st
	t.mu.Unlock()
}

// set zapisuje nowy status; wywołuje onChange poza blokadą.
func (t *sessionTracker) set(st SessionStatus) {
	t.mu.Lock()
	prev := t.st
	t.st = st
	cb := t.onChange
	t.mu.Unlock()
	if cb != nil && (prev.State != st.State || prev.SessionID != st.SessionID || prev.GameID != st.GameID || !prev.Known || prev.FromFile) {
		cb(st)
	}
}

// SessionStatus zwraca ostatni znany status sesji.
func (h *Hub) SessionStatus() SessionStatus { return h.session.get() }

// handleSessionStatus przyjmuje zgłoszenie statusu sesji. Tylko od modułu głównego; nieznany stan jest ignorowany.
func (h *Hub) handleSessionStatus(msg *Message) {
	if msg.Source == nil || msg.Source.ComponentType != "main_module" {
		log.Printf("⚠️  session_status odrzucone: zgłoszenie tylko od modułu głównego (od: %s)", msg.From)
		return
	}
	state, _ := msg.Payload["state"].(string)
	switch state {
	case sessionNone, sessionPreparation, sessionOnAir:
	default:
		log.Printf("⚠️  session_status: nieznany stan %q, ignoruję", state)
		return
	}
	st := SessionStatus{State: state, At: time.Now(), Known: true}
	if v, ok := msg.Payload["session_id"].(float64); ok {
		st.SessionID = int(v)
	}
	if v, ok := msg.Payload["game_id"].(float64); ok {
		st.GameID = int(v)
	}
	prev := h.session.get()
	h.session.set(st)
	if !prev.Known || prev.State != st.State || prev.SessionID != st.SessionID {
		log.Printf("📋 Status sesji: %s (sesja %d, mecz %d)", state, st.SessionID, st.GameID)
	}
}

// sessionSnapshot: status sesji do /status (z wiekiem zgłoszenia).
func sessionSnapshot(s SessionStatus) map[string]interface{} {
	m := map[string]interface{}{"known": s.Known, "state": s.State, "session_id": s.SessionID, "game_id": s.GameID, "from_file": s.FromFile}
	if s.Known {
		m["age_s"] = int(time.Since(s.At).Seconds())
	}
	return m
}
