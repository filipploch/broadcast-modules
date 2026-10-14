package main

import (
	"encoding/json"
	"net/http/httptest"
	"testing"
)

func mainModuleMsg(hub *Hub, payload map[string]interface{}) *Message {
	src := NewModule(hub, nil)
	src.ComponentType = "main_module"
	src.ID = "main-module"
	m := NewMessage("main-module", "hub", "session_status", payload)
	m.Source = src
	return m
}

func TestSessionStatusUnknownUntilReportedAndSafeDefaults(t *testing.T) {
	hub := NewHub(0, false, false)
	s := hub.SessionStatus()
	if s.Known || s.IsOpen() {
		t.Fatalf("przed zgłoszeniem status ma być nieznany: %+v", s)
	}
	// przy zamykaniu brak wiedzy = sesja otwarta (nic nie zamykamy); przy restarcie OBS brak wiedzy = brak sesji (nie startujemy)
	if !s.OpenForShutdown() || s.OpenForRestart() {
		t.Fatalf("reguły bezpiecznej strony: shutdown=%v restart=%v", s.OpenForShutdown(), s.OpenForRestart())
	}
}

func TestSessionStatusAcceptedFromMainModuleOnly(t *testing.T) {
	hub := NewHub(0, false, false)
	hub.handleMessage(mainModuleMsg(hub, map[string]interface{}{"state": "on_air", "session_id": float64(7), "game_id": float64(42)}))
	s := hub.SessionStatus()
	if !s.Known || s.State != sessionOnAir || s.SessionID != 7 || s.GameID != 42 || !s.IsOpen() || !s.OpenForRestart() || !s.OpenForShutdown() {
		t.Fatalf("status: %+v", s)
	}

	// plugin ani nieznany nadawca nie ustawia statusu sesji
	plugin := NewModule(hub, nil)
	plugin.ComponentType = "plugin"
	fake := NewMessage("timer-plugin", "hub", "session_status", map[string]interface{}{"state": "none"})
	fake.Source = plugin
	hub.handleMessage(fake)
	noSrc := NewMessage("x", "hub", "session_status", map[string]interface{}{"state": "none"})
	hub.handleMessage(noSrc)
	if hub.SessionStatus().State != sessionOnAir {
		t.Fatal("status zmieniony przez nadawcę, który nie jest modułem głównym")
	}

	// nieznany stan jest ignorowany
	hub.handleMessage(mainModuleMsg(hub, map[string]interface{}{"state": "dziwny"}))
	if hub.SessionStatus().State != sessionOnAir {
		t.Fatal("nieznany stan zmienił status")
	}
}

func TestSessionStatusNoneMeansClosedForBothRules(t *testing.T) {
	hub := NewHub(0, false, false)
	hub.handleMessage(mainModuleMsg(hub, map[string]interface{}{"state": "none"}))
	s := hub.SessionStatus()
	if !s.Known || s.IsOpen() || s.OpenForShutdown() || s.OpenForRestart() {
		t.Fatalf("po zgłoszeniu 'none' sesja jest zamknięta dla obu reguł: %+v", s)
	}
	hub.handleMessage(mainModuleMsg(hub, map[string]interface{}{"state": "preparation", "session_id": float64(1)}))
	if s := hub.SessionStatus(); !s.IsOpen() || !s.OpenForRestart() {
		t.Fatalf("przygotowanie to sesja otwarta (decyzja A): %+v", s)
	}
}

func TestSessionStatusCallbackOnlyOnChange(t *testing.T) {
	hub := NewHub(0, false, false)
	var calls []SessionStatus
	hub.session.onChange = func(s SessionStatus) { calls = append(calls, s) }
	msg := func(state string) *Message {
		return mainModuleMsg(hub, map[string]interface{}{"state": state, "session_id": float64(3)})
	}
	hub.handleMessage(msg("preparation"))
	hub.handleMessage(msg("preparation")) // ponowne zgłoszenie po połączeniu: bez zapisu
	hub.handleMessage(msg("on_air"))
	if len(calls) != 2 || calls[0].State != sessionPreparation || calls[1].State != sessionOnAir {
		t.Fatalf("wywołania zapisu: %+v", calls)
	}
}

func TestStatusEndpointShowsSession(t *testing.T) {
	hub := NewHub(0, false, false)
	hub.handleMessage(mainModuleMsg(hub, map[string]interface{}{"state": "on_air", "session_id": float64(5)}))
	rec := httptest.NewRecorder()
	serveStatus(hub, rec, httptest.NewRequest("GET", "/status", nil))
	var out map[string]interface{}
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatal(err)
	}
	sess, _ := out["session"].(map[string]interface{})
	if sess == nil || sess["state"] != "on_air" || sess["known"] != true || sess["session_id"] != float64(5) {
		t.Fatalf("/status session: %v", out["session"])
	}
}
