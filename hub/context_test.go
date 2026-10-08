package main

import (
	"encoding/json"
	"strings"
	"testing"
)

var testContext = map[string]interface{}{"module": "futsal_nalf", "session_id": float64(7), "game_id": float64(42), "period_id": float64(3)}

func TestContextSurvivesJSONRoundTrip(t *testing.T) {
	msg := NewMessage("futsal-nalf", "timer-plugin", "start_timer", map[string]interface{}{"timer_id": "t1"})
	msg.Context = testContext
	data, err := msg.ToJSON()
	if err != nil {
		t.Fatal(err)
	}
	back, err := FromJSON(data)
	if err != nil {
		t.Fatal(err)
	}
	for k, v := range testContext {
		if back.Context[k] != v {
			t.Fatalf("pole %s: %v != %v", k, back.Context[k], v)
		}
	}
}

func TestMessageWithoutContextHasNoContextKey(t *testing.T) {
	data, _ := NewMessage("a", "b", "x", nil).ToJSON()
	if strings.Contains(string(data), "context") {
		t.Fatalf("wiadomość bez kontekstu nie powinna go mieć w JSON: %s", data)
	}
}

// HUB przekazuje kontekst polecenia do pluginu bez zmian (polecenie jest przepisywane przez ToJSON).
func TestRoutedCommandKeepsContext(t *testing.T) {
	hub := NewHub(0, false, false)
	main := newMainModule(hub)
	p := NewModule(hub, nil)
	p.ID, p.IsActive = "timer-plugin", true
	hub.Plugins[p.ID] = p

	msg := NewMessage(main.ID, "timer-plugin", "start_timer", nil)
	msg.Context = testContext
	msg.Source = main
	hub.routeMessage(msg)

	got := readSent(t, p)
	if got == nil || got.Context["game_id"] != float64(42) || got.Context["module"] != "futsal_nalf" {
		t.Fatalf("plugin nie dostał kontekstu: %+v", got)
	}
}

// Odpowiedź plugina, która odsyła kontekst, dociera do modułu z kontekstem.
func TestPluginReplyKeepsContext(t *testing.T) {
	hub := NewHub(0, false, false)
	main := newMainModule(hub)
	reply := NewMessage("timer-plugin", main.ID, "timer_started", map[string]interface{}{"timer_id": "t1"})
	reply.Context = testContext
	hub.routeMessage(reply)

	got := readSent(t, main)
	if got == nil || got.Context["period_id"] != float64(3) {
		t.Fatalf("moduł nie dostał kontekstu odpowiedzi: %+v", got)
	}
}

func TestUndeliveredReportCarriesContext(t *testing.T) {
	hub := NewHub(0, false, false)
	main := newMainModule(hub)
	msg := NewMessage(main.ID, "timer-plugin", "start_timer", nil)
	msg.Context = testContext
	msg.Source = main
	hub.routeMessage(msg)

	got := readSent(t, main)
	if got == nil || got.Type != "undelivered" || got.Context["game_id"] != float64(42) {
		t.Fatalf("raport niedostarczenia bez kontekstu polecenia: %+v", got)
	}
	var raw map[string]interface{}
	data, _ := got.ToJSON()
	json.Unmarshal(data, &raw)
	if raw["context"] == nil {
		t.Fatal("kontekst nie trafił do JSON raportu")
	}
}
