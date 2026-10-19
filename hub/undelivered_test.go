package main

import (
	"encoding/json"
	"testing"
)

func newMainModule(hub *Hub) *Module {
	m := NewModule(hub, nil)
	m.ID = "futsal-nalf"
	m.ComponentType = "main_module"
	m.IsActive = true
	hub.MainModule = m
	return m
}

func readSent(t *testing.T, m *Module) *Message {
	t.Helper()
	select {
	case data := <-m.Send:
		msg, err := FromJSON(data)
		if err != nil {
			t.Fatal(err)
		}
		return msg
	default:
		return nil
	}
}

func TestUndeliveredToMissingPluginIsReportedToMainModule(t *testing.T) {
	hub := NewHub(0, false, false)
	main := newMainModule(hub)

	msg := NewMessage(main.ID, "timer-plugin", "start_timer", map[string]interface{}{"timer_id": "t1"})
	msg.Source = main
	hub.routeMessage(msg)

	got := readSent(t, main)
	if got == nil || got.Type != "undelivered" {
		t.Fatalf("oczekiwano komunikatu 'undelivered', jest %+v", got)
	}
	if got.Payload["plugin_id"] != "timer-plugin" || got.Payload["command"] != "start_timer" {
		t.Fatalf("zły ładunek: %v", got.Payload)
	}
	inner, _ := got.Payload["command_payload"].(map[string]interface{})
	if inner["timer_id"] != "t1" {
		t.Fatalf("brak oryginalnego ładunku polecenia: %v", got.Payload)
	}
	if _, err := json.Marshal(got); err != nil {
		t.Fatal(err)
	}
}

func TestUndeliveredToInactivePluginIsReported(t *testing.T) {
	hub := NewHub(0, false, false)
	main := newMainModule(hub)
	p := NewModule(hub, nil)
	p.ID = "timer-plugin"
	p.IsActive = false
	hub.Plugins[p.ID] = p

	msg := NewMessage(main.ID, "timer-plugin", "pause_timer", nil)
	msg.Source = main
	hub.routeMessage(msg)

	if got := readSent(t, main); got == nil || got.Type != "undelivered" {
		t.Fatalf("oczekiwano 'undelivered', jest %+v", got)
	}
}

func TestDeliveredMessageProducesNoUndeliveredReport(t *testing.T) {
	hub := NewHub(0, false, false)
	main := newMainModule(hub)
	p := NewModule(hub, nil)
	p.ID = "timer-plugin"
	p.IsActive = true
	hub.Plugins[p.ID] = p

	msg := NewMessage(main.ID, "timer-plugin", "start_timer", nil)
	msg.Source = main
	hub.routeMessage(msg)

	if got := readSent(t, main); got != nil {
		t.Fatalf("nie powinno być odpowiedzi, jest %+v", got)
	}
	if readSent(t, p) == nil {
		t.Fatal("plugin nie dostał polecenia")
	}
}

// Plugin piszący do nieobecnego adresata (np. odpowiedź do modułu, którego nie ma) nie dostaje raportu.
func TestUndeliveredIsNotReportedToPlugins(t *testing.T) {
	hub := NewHub(0, false, false)
	newMainModule(hub)
	sender := NewModule(hub, nil)
	sender.ID = "obs-ws-plugin"
	sender.ComponentType = "plugin"
	sender.IsActive = true
	hub.Plugins[sender.ID] = sender

	msg := NewMessage(sender.ID, "replay-plugin", "x", nil)
	msg.Source = sender
	hub.routeMessage(msg)

	if got := readSent(t, sender); got != nil {
		t.Fatalf("plugin nie powinien dostać raportu, jest %+v", got)
	}
}

// Raport sam nie może wywołać kolejnego raportu.
func TestUndeliveredReportDoesNotLoop(t *testing.T) {
	hub := NewHub(0, false, false)
	main := newMainModule(hub)
	msg := NewMessage(main.ID, "nobody", "undelivered", nil)
	msg.Source = main
	hub.routeMessage(msg)
	if got := readSent(t, main); got != nil {
		t.Fatalf("pętla raportów: %+v", got)
	}
}

// Moduł rozłączony w ciągu 200 ms od rejestracji (np. zatrzymany kanałem sterującym zaraz po starcie): opóźnione powiadomienie
// o pluginach nie może wywrócić HUB-a (dawniej: "panic: send on closed channel", wykryte w próbie M4 z E2d3c1).
func TestLateJoinNotificationAfterQuickDisconnectDoesNotPanic(t *testing.T) {
	hub := NewHub(0, false, false)
	p := NewModule(hub, nil)
	p.ID, p.IsActive = "timer-plugin", true
	hub.Plugins[p.ID] = p
	main := newMainModule(hub)
	done := make(chan struct{})
	go func() {
		defer close(done)
		hub.sendCurrentPluginStates(main)
	}()
	hub.mu.Lock()
	main.IsActive = false
	hub.MainModule = nil
	hub.mu.Unlock()
	close(main.Send)
	<-done
}
