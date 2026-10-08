package main

import (
	"encoding/json"
	"testing"
	"time"
)

func newCtxPlugin(t *testing.T) *Plugin {
	t.Helper()
	cfg := defaultConfig()
	cfg.TransitionLeadMs = 60000 // reset mpv po powtórce nie odpali w trakcie testu
	p := NewPlugin(cfg)
	p.hub = NewHubClient("replay-plugin", "Replay", "ws://test")
	p.hub.connected = true // wysyłka trafia do kanału send, bez prawdziwego połączenia
	return p
}

func nextMessage(t *testing.T, p *Plugin, typ string) *Message {
	t.Helper()
	deadline := time.After(2 * time.Second)
	for {
		select {
		case data := <-p.hub.send:
			var m Message
			if json.Unmarshal(data, &m) == nil && m.Type == typ {
				return &m
			}
		case <-deadline:
			t.Fatalf("nie doczekano wiadomości %s", typ)
		}
	}
}

var testCtx = map[string]interface{}{"module": "futsal_nalf", "session_id": float64(7), "game_id": float64(42), "period_id": float64(3)}

func TestReplayEventsCarryContextOfPlayCommand(t *testing.T) {
	p := newCtxPlugin(t)
	p.setReplayContext(testCtx)
	p.handlePlay(map[string]interface{}{"video_path": "Z:/nie/ma/takiego/pliku.mkv"})
	m := nextMessage(t, p, "replay_error")
	for k, v := range testCtx {
		if m.Context[k] != v {
			t.Fatalf("kontekst %v != %v", m.Context, testCtx)
		}
	}
}

func TestReplayDoneCarriesContextOfActiveReplay(t *testing.T) {
	p := newCtxPlugin(t)
	p.setReplayContext(testCtx)
	p.mu.Lock()
	p.activeReplay = true
	p.mu.Unlock()
	p.finishReplay("controller", nil)
	m := nextMessage(t, p, "replay_done")
	if m.Context["game_id"] != float64(42) {
		t.Fatalf("replay_done bez kontekstu meczu: %v", m.Context)
	}
}

func TestReplayWithoutContextStaysWithoutContext(t *testing.T) {
	p := newCtxPlugin(t)
	p.setReplayContext(nil) // starszy moduł nie przysyła kontekstu
	p.handlePlay(map[string]interface{}{"video_path": "Z:/nie/ma/takiego/pliku.mkv"})
	if m := nextMessage(t, p, "replay_error"); m.Context != nil {
		t.Fatalf("nie powinno być kontekstu: %v", m.Context)
	}
}

// Nowa powtórka z nowym kontekstem zastępuje poprzedni: zdarzenia nie mieszają meczów.
func TestNewPlayReplacesPreviousContext(t *testing.T) {
	p := newCtxPlugin(t)
	p.setReplayContext(testCtx)
	other := map[string]interface{}{"module": "futsal_nalf", "session_id": float64(7), "game_id": float64(43)}
	p.setReplayContext(other)
	p.handlePlay(map[string]interface{}{"video_path": "Z:/nie/ma/takiego/pliku.mkv"})
	if m := nextMessage(t, p, "replay_error"); m.Context["game_id"] != float64(43) {
		t.Fatalf("zdarzenie niesie stary kontekst: %v", m.Context)
	}
}
