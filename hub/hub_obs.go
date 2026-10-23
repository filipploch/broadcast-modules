package main

import (
	"fmt"
	"log"
	"sync"
	"time"
)

// Zamykanie HUB-a a moduł i OBS (E2d2). Reguły:
//   - Sesja otwarta (przygotowanie / na antenie) albo jej status nieznany: HUB NIE zatrzymuje modułu ani OBS. Zatrzymuje tylko pluginy
//     lokalne, zapisuje plik stanu; moduł i OBS pracują dalej, a kolejny HUB je przejmie.
//   - Sesja zamknięta: moduł jest zamykany łagodnie; OBS tylko wtedy, gdy łącznie: HUB sam go uruchomił, obs-ws-plugin jest połączony
//     i w ciągu 3 s odpowiada, że nie trwa stream ani nagrywanie. Brak odpowiedzi, błąd albo stan nieznany liczy się jak trwający stream:
//     OBS zostaje, a przyczyna idzie do logu. Zamknięcie OBS jest łagodne (WM_CLOSE tylko do okna głównego, limit 30 s) i nigdy wymuszone.

const obsQueryBudget = 3 * time.Second

// hubRequests: odpowiedzi pluginów adresowane do samego HUB-a ("to": "hub"), np. na pytanie o stan streamu OBS.
type hubRequests struct {
	mu      sync.Mutex
	seq     int
	pending map[string]*pendingRequest
}

type pendingRequest struct {
	requestType string
	byContext   bool // pytanie z identyfikatorem w kontekście (RequestByContext, control.go); nie pasuje po samym requestType
	ch          chan *Message
}

// RequestPlugin wysyła do pluginu polecenie i czeka na odpowiedź (obs_response / obs_error) adresowaną do HUB-a.
func (h *Hub) RequestPlugin(pluginID, msgType, requestType string, requestData map[string]interface{}, timeout time.Duration) (*Message, error) {
	h.mu.RLock()
	plugin := h.Plugins[pluginID]
	h.mu.RUnlock()
	if plugin == nil || !plugin.IsActive {
		return nil, fmt.Errorf("plugin %s nie jest połączony", pluginID)
	}
	h.requests.mu.Lock()
	if h.requests.pending == nil {
		h.requests.pending = map[string]*pendingRequest{}
	}
	h.requests.seq++
	id := fmt.Sprintf("hub-%d", h.requests.seq)
	req := &pendingRequest{requestType: requestType, ch: make(chan *Message, 1)}
	h.requests.pending[id] = req
	h.requests.mu.Unlock()
	defer func() {
		h.requests.mu.Lock()
		delete(h.requests.pending, id)
		h.requests.mu.Unlock()
	}()

	if requestData == nil {
		requestData = map[string]interface{}{}
	}
	msg := NewMessage("hub", pluginID, msgType, map[string]interface{}{
		"requestType": requestType, "requestData": requestData, "request_id": id,
	})
	h.sendSafely(plugin, msg)
	select {
	case resp := <-req.ch:
		return resp, nil
	case <-time.After(timeout):
		return nil, fmt.Errorf("brak odpowiedzi pluginu %s w %v", pluginID, timeout)
	}
}

// handleHubAddressed przyjmuje odpowiedź pluginu adresowaną do HUB-a. Zwraca true, gdy pasuje do oczekującego pytania.
// obs_response niesie requestID; obs_error ma identyfikator w "command" albo tylko requestType (wtedy pasuje jedyne takie pytanie).
func (h *Hub) handleHubAddressed(msg *Message) bool {
	if h.deliverByContext(msg) {
		return true
	}
	if msg.Type != "obs_response" && msg.Type != "obs_error" {
		return false
	}
	id, _ := msg.Payload["requestID"].(string)
	if id == "" {
		if cmd, ok := msg.Payload["command"].(map[string]interface{}); ok {
			id, _ = cmd["request_id"].(string)
		}
	}
	h.requests.mu.Lock()
	defer h.requests.mu.Unlock()
	if req, ok := h.requests.pending[id]; ok && id != "" {
		select {
		case req.ch <- msg:
		default:
		}
		return true
	}
	rt, _ := msg.Payload["requestType"].(string)
	var match *pendingRequest
	n := 0
	for _, req := range h.requests.pending {
		if rt != "" && !req.byContext && req.requestType == rt {
			match = req
			n++
		}
	}
	if n == 1 {
		select {
		case match.ch <- msg:
		default:
		}
		return true
	}
	return false
}

// obsOutputsIdle pyta obs-ws-plugin o stream i nagrywanie. true tylko, gdy oba wyjścia na pewno nie pracują.
func (h *Hub) obsOutputsIdle(budget time.Duration) (bool, string) {
	deadline := time.Now().Add(budget)
	for _, rt := range []string{"GetStreamStatus", "GetRecordStatus"} {
		left := time.Until(deadline)
		if left <= 0 {
			return false, "upłynął czas na pytanie o stan wyjść OBS"
		}
		resp, err := h.RequestPlugin("obs-ws-plugin", "obs_command", rt, nil, left)
		if err != nil {
			return false, fmt.Sprintf("%s: %v", rt, err)
		}
		if resp.Type != "obs_response" {
			return false, fmt.Sprintf("%s: OBS odpowiedział błędem (%v)", rt, resp.Payload["error"])
		}
		data, _ := resp.Payload["responseData"].(map[string]interface{})
		active, known := data["outputActive"].(bool)
		if !known {
			return false, fmt.Sprintf("%s: odpowiedź bez pola outputActive", rt)
		}
		if active {
			what := "stream"
			if rt == "GetRecordStatus" {
				what = "nagrywanie"
			}
			return false, "trwa " + what
		}
	}
	return true, ""
}

// obsCloseDecision rozstrzyga, czy HUB może zamknąć OBS przy zamykaniu (sesja musi być już uznana za zamkniętą).
func (h *Hub) obsCloseDecision(budget time.Duration) (bool, string) {
	if h.Services == nil || !h.Services.StartedByHub("obs") {
		return false, "OBS nie został uruchomiony przez HUB (obcy proces albo nie działa)"
	}
	if h.SessionStatus().OpenForShutdown() {
		return false, "sesja otwarta albo jej status nieznany"
	}
	idle, reason := h.obsOutputsIdle(budget)
	if !idle {
		return false, "nie można potwierdzić, że stream i nagrywanie nie trwają, traktuję jak trwający stream: " + reason
	}
	return true, ""
}

// shutdownServices zatrzymuje usługi według reguł z komentarza na górze pliku.
func (h *Hub) shutdownServices() {
	if h.Services == nil {
		return
	}
	ids := h.Services.IDs()
	st := h.SessionStatus()
	if st.OpenForShutdown() {
		why := "status sesji nieznany"
		if st.Known {
			why = fmt.Sprintf("sesja %s (nr %d)", st.State, st.SessionID)
		}
		log.Printf("📌 %s: moduł i OBS zostają uruchomione (kolejny HUB je przejmie); zatrzymuję tylko pluginy lokalne", why)
		for _, id := range ids {
			h.Services.Detach(id)
		}
		return
	}
	only := map[string]bool{}
	for _, id := range ids {
		if id != "obs" {
			only[id] = true
		}
	}
	if allow, reason := h.obsCloseDecision(obsQueryBudget); allow {
		only["obs"] = true
	} else if h.Services.Has("obs") {
		log.Printf("📌 OBS zostaje uruchomiony: %s", reason)
		h.Services.Detach("obs")
	}
	h.Services.StopSome(only)
	// Moduł zatrzymany razem z HUB-em: jego WP także (przy otwartej sesji moduł i WP zostają, wyżej)
	if h.wp != nil {
		h.wp.stopForCurrent()
	}
}

// gracefulStopService prosi usługę o zamknięcie się samej. Moduł: komunikat shutdown_module przez WebSocket. OBS: WM_CLOSE do okna
// głównego (jak kliknięcie X). Zwraca false, gdy nie ma jak (moduł niepołączony, brak okna OBS): moduł jest wtedy kończony od razu,
// a OBS zostaje (nigdy nie jest kończony siłą).
func (h *Hub) gracefulStopService(id string) bool {
	switch id {
	case "module":
		h.mu.RLock()
		m := h.MainModule
		h.mu.RUnlock()
		if m == nil || !m.IsActive {
			return false
		}
		h.sendSafely(m, NewMessage("hub", m.ID, "shutdown_module", map[string]interface{}{}))
		return true
	case "obs":
		pid := h.Services.PID(id)
		if pid == 0 {
			return false
		}
		if err := closeMainWindow(pid); err != nil {
			log.Printf("⚠️  OBS: %v", err)
			return false
		}
		log.Printf("📨 OBS: wysłano komunikat zamknięcia do okna głównego (PID %d), czekam do 30 s", pid)
		return true
	}
	return false
}
