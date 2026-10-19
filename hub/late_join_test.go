package main

import "testing"

// Modul rozlaczony w ciagu 200 ms od rejestracji: opoznione powiadomienie o pluginach nie moze wywrocic HUB-a
// (dawniej: "panic: send on closed channel" w sendCurrentPluginStates; wykryte w probie M4 etapu E2d3c1).
func TestLateJoinNotificationAfterQuickDisconnectDoesNotPanic(t *testing.T) {
	hub := NewHub(0, false, false)
	p := NewModule(hub, nil)
	p.ID, p.IsActive = "timer-plugin", true
	hub.Plugins[p.ID] = p
	main := NewModule(hub, nil)
	main.ID, main.ComponentType, main.IsActive = "main-module", "main_module", true
	hub.MainModule = main
	done := make(chan struct{})
	go func() {
		defer close(done)
		hub.sendCurrentPluginStates(main)
	}()
	// jak przy rozlaczeniu modulu: pod blokada HUB-a modul przestaje byc glownym, a jego kanal jest zamykany
	hub.mu.Lock()
	main.IsActive = false
	hub.MainModule = nil
	close(main.Send)
	hub.mu.Unlock()
	<-done
}
