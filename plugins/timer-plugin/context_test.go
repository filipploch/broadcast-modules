package timer

import (
	"encoding/json"
	"path/filepath"
	"testing"
	"time"
)

func newCtxPlugin(t *testing.T) *Plugin {
	t.Helper()
	p := NewPlugin(PluginConfig{PluginID: "timer-plugin", PluginName: "Timer Plugin"})
	p.hubClient = NewHubClient("timer-plugin", "Timer Plugin", "ws://test")
	p.hubClient.connected = true // wysyłka trafia do kanału send, bez prawdziwego połączenia
	return p
}

// sent zwraca wiadomości wysłane do HUB-a od ostatniego wywołania.
func sent(p *Plugin) []*Message {
	var out []*Message
	for {
		select {
		case data := <-p.hubClient.send:
			var m Message
			if err := json.Unmarshal(data, &m); err == nil {
				out = append(out, &m)
			}
		default:
			return out
		}
	}
}

// collect zbiera wiadomości przez krótki czas (zdarzenia zegara wysyłają wątki w tle).
func collect(p *Plugin, wait time.Duration) []*Message {
	time.Sleep(wait)
	return sent(p)
}

func lastOfType(msgs []*Message, typ string) *Message {
	for i := len(msgs) - 1; i >= 0; i-- {
		if msgs[i].Type == typ {
			return msgs[i]
		}
	}
	return nil
}

var gameA = map[string]interface{}{"module": "futsal_nalf", "session_id": float64(7), "game_id": float64(42), "period_id": float64(3)}
var gameB = map[string]interface{}{"module": "futsal_nalf", "session_id": float64(7), "game_id": float64(43), "period_id": float64(5)}

func sameContext(t *testing.T, got, want map[string]interface{}) {
	t.Helper()
	for k, v := range want {
		if got[k] != v {
			t.Fatalf("kontekst %v != oczekiwany %v", got, want)
		}
	}
}

func TestCreateTimerEchoesCommandContext(t *testing.T) {
	p := newCtxPlugin(t)
	p.handleCreateTimer(&Message{From: "main-module", Payload: map[string]interface{}{"timer_id": "t1", "limit": float64(60000)}, Context: gameA})
	created := lastOfType(sent(p), "timer_created")
	if created == nil {
		t.Fatal("brak timer_created")
	}
	sameContext(t, created.Context, gameA)
}

// Zdarzenia zegara niosą kontekst z chwili jego utworzenia, także gdy polecenie startu przyszło z innym kontekstem.
func TestTimerEventsCarryCreationContext(t *testing.T) {
	p := newCtxPlugin(t)
	p.handleCreateTimer(&Message{From: "main-module", Payload: map[string]interface{}{"timer_id": "t1", "limit": float64(60000)}, Context: gameA})
	sent(p)
	t.Cleanup(func() { p.manager.Remove("t1") })

	p.handleStartTimer(&Message{From: "main-module", Payload: map[string]interface{}{"timer_id": "t1"}, Context: gameB})
	p.handlePauseTimer(&Message{From: "main-module", Payload: map[string]interface{}{"timer_id": "t1"}, Context: gameB})
	msgs := collect(p, 300*time.Millisecond)
	for _, typ := range []string{"timer_started", "timer_paused"} {
		m := lastOfType(msgs, typ)
		if m == nil {
			t.Fatalf("brak %s wśród %d wiadomości", typ, len(msgs))
		}
		sameContext(t, m.Context, gameA)
	}
}

func TestEnsureTimerKeepsOriginalContextOfExistingTimer(t *testing.T) {
	p := newCtxPlugin(t)
	p.handleEnsureTimer(&Message{From: "main-module", Payload: map[string]interface{}{"timer_id": "t1"}, Context: gameA})
	p.handleEnsureTimer(&Message{From: "main-module", Payload: map[string]interface{}{"timer_id": "t1"}, Context: gameB})
	ensured := lastOfType(sent(p), "timer_ensured")
	if ensured == nil {
		t.Fatal("brak timer_ensured")
	}
	sameContext(t, ensured.Context, gameA)
}

func TestCommandWithoutTimerGetsCommandContext(t *testing.T) {
	p := newCtxPlugin(t)
	p.handleGetAllTimers(&Message{From: "main-module", Payload: map[string]interface{}{}, Context: gameA})
	all := lastOfType(sent(p), "all_timers")
	if all == nil {
		t.Fatal("brak all_timers")
	}
	sameContext(t, all.Context, gameA)
}

func TestMessagesWithoutAnyContextStayWithoutContext(t *testing.T) {
	p := newCtxPlugin(t)
	p.handleCreateTimer(&Message{From: "main-module", Payload: map[string]interface{}{"timer_id": "t1"}})
	created := lastOfType(sent(p), "timer_created")
	if created == nil || created.Context != nil {
		t.Fatalf("starsza wersja modułu (bez kontekstu) nie może dostać kontekstu: %+v", created)
	}
	data, _ := json.Marshal(created)
	if json.Valid(data) && containsKey(data, "context") {
		t.Fatalf("w JSON nie powinno być klucza context: %s", data)
	}
}

func containsKey(data []byte, key string) bool {
	var m map[string]interface{}
	json.Unmarshal(data, &m)
	_, ok := m[key]
	return ok
}

func TestContextIsHiddenFromTimerMetadataSentToModule(t *testing.T) {
	p := newCtxPlugin(t)
	p.handleCreateTimer(&Message{From: "main-module", Payload: map[string]interface{}{"timer_id": "t1"}, Context: gameA})
	sent(p)
	info, _ := p.manager.GetState("t1")
	converted := p.convertTimerInfo(info, "t1")
	md, _ := converted["metadata"].(map[string]interface{})
	if _, leaked := md[contextMetaKey]; leaked {
		t.Fatalf("wewnętrzny klucz kontekstu wyciekł do metadata: %v", md)
	}
}

// Kontekst przeżywa awarię pluginu: zapisany w pliku stanu, po odtworzeniu zdarzenia zegara dalej go niosą.
func TestContextSurvivesPluginRestartThroughStateFile(t *testing.T) {
	p := newCtxPlugin(t)
	p.handleCreateTimer(&Message{From: "main-module", Payload: map[string]interface{}{"timer_id": "t1", "limit": float64(60000)}, Context: gameA})
	p.handleStartTimer(&Message{From: "main-module", Payload: map[string]interface{}{"timer_id": "t1"}, Context: gameA})
	path := filepath.Join(t.TempDir(), "timers.json")
	if err := WriteStateFile(path, p.manager.Snapshot(time.Now())); err != nil {
		t.Fatal(err)
	}
	p.manager.Remove("t1")

	p2 := newCtxPlugin(t) // "nowy proces"
	now := time.Now().Add(2 * time.Second)
	file, status, err := LoadStateFile(path, now, DefaultStateMaxAge)
	if status != LoadRestored || err != nil {
		t.Fatalf("stan nie został wczytany: %v %v", status, err)
	}
	p2.manager.Restore(file, now, p2.timerCallbacks())
	t.Cleanup(func() { p2.manager.Remove("t1") })

	sameContext(t, p2.timerContext("t1"), gameA)
	p2.handlePauseTimer(&Message{From: "main-module", Payload: map[string]interface{}{"timer_id": "t1"}})
	paused := lastOfType(collect(p2, 300*time.Millisecond), "timer_paused")
	if paused == nil {
		t.Fatal("brak timer_paused po odtworzeniu")
	}
	sameContext(t, paused.Context, gameA)
}

// Mecz ten sam, sesja nowa (zamknięto i otwarto sesję): zdarzenia zegara niosą nowy numer sesji, żeby moduł ich nie odrzucał.
func TestNewerSessionOfSameGameRefreshesTimerContext(t *testing.T) {
	p := newCtxPlugin(t)
	p.handleCreateTimer(&Message{From: "main-module", Payload: map[string]interface{}{"timer_id": "t1", "limit": float64(60000)}, Context: gameA})
	t.Cleanup(func() { p.manager.Remove("t1") })
	sent(p)

	newSession := map[string]interface{}{"module": "futsal_nalf", "session_id": float64(8), "game_id": float64(42), "period_id": float64(3)}
	p.handleMessage(&Message{From: "main-module", Type: "start_timer", Payload: map[string]interface{}{"timer_id": "t1"}, Context: newSession})
	p.handlePauseTimer(&Message{From: "main-module", Payload: map[string]interface{}{"timer_id": "t1"}, Context: newSession})
	started := lastOfType(collect(p, 300*time.Millisecond), "timer_started")
	if started == nil {
		t.Fatal("brak timer_started")
	}
	sameContext(t, started.Context, newSession)
}

// Inny mecz nie odświeża kontekstu: zegar meczu A dalej niesie mecz A (komunikat spóźniony ma zostać odrzucony przez moduł).
func TestCommandOfOtherGameDoesNotRefreshTimerContext(t *testing.T) {
	p := newCtxPlugin(t)
	p.handleCreateTimer(&Message{From: "main-module", Payload: map[string]interface{}{"timer_id": "t1", "limit": float64(60000)}, Context: gameA})
	t.Cleanup(func() { p.manager.Remove("t1") })
	sent(p)

	otherSession := map[string]interface{}{"module": "futsal_nalf", "session_id": float64(8), "game_id": float64(43), "period_id": float64(5)}
	p.handleMessage(&Message{From: "main-module", Type: "start_timer", Payload: map[string]interface{}{"timer_id": "t1"}, Context: otherSession})
	p.handlePauseTimer(&Message{From: "main-module", Payload: map[string]interface{}{"timer_id": "t1"}, Context: otherSession})
	started := lastOfType(collect(p, 300*time.Millisecond), "timer_started")
	if started == nil {
		t.Fatal("brak timer_started")
	}
	sameContext(t, started.Context, gameA)
}
