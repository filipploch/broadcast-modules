package main

import (
	"fmt"
	"testing"
)

// Rejestracja ma trafić do połączenia, z którego przyszła, także gdy kilka
// połączeń czeka jednocześnie (wcześniej wybierane było losowe oczekujące).
func TestRegisterBindsToSendingConnection(t *testing.T) {
	for round := 0; round < 200; round++ {
		hub := NewHub(0, false, false)

		names := []string{"timer-plugin", "obs-ws-plugin", "replay-plugin", "recorder-plugin"}
		conns := make(map[string]*Module)
		for _, n := range names {
			m := NewModule(hub, nil)
			conns[n] = m
			hub.PendingModules[m] = true
		}

		for _, n := range names {
			msg := NewMessage("", "hub", "register", map[string]interface{}{
				"plugin_id":      n,
				"component_type": "plugin",
			})
			msg.Source = conns[n]
			hub.handleRegister(msg)
		}

		for _, n := range names {
			got := hub.Plugins[n]
			if got != conns[n] {
				t.Fatalf("runda %d: plugin %s zarejestrowany na cudzym połączeniu (%v)", round, n, describe(got))
			}
			if conns[n].ID != n {
				t.Fatalf("runda %d: połączenie pluginu %s dostało identyfikator %q", round, n, conns[n].ID)
			}
		}
		if len(hub.PendingModules) != 0 {
			t.Fatalf("runda %d: po rejestracji wszystkich zostało %d oczekujących", round, len(hub.PendingModules))
		}
	}
}

// Rejestracja bez znanego źródła albo z połączenia, które nie czeka, nie może zabrać cudzego połączenia.
func TestRegisterWithoutPendingSourceIsIgnored(t *testing.T) {
	hub := NewHub(0, false, false)
	other := NewModule(hub, nil)
	hub.PendingModules[other] = true

	msg := NewMessage("", "hub", "register", map[string]interface{}{"plugin_id": "timer-plugin", "component_type": "plugin"})
	hub.handleRegister(msg) // brak Source

	stranger := NewModule(hub, nil) // nie jest oczekujące
	msg.Source = stranger
	hub.handleRegister(msg)

	if len(hub.Plugins) != 0 || other.ID != "" || !hub.PendingModules[other] {
		t.Fatalf("cudze oczekujące połączenie zostało zajęte: plugins=%d id=%q", len(hub.Plugins), other.ID)
	}
}

func describe(m *Module) string {
	if m == nil {
		return "brak"
	}
	return fmt.Sprintf("id=%q", m.ID)
}
