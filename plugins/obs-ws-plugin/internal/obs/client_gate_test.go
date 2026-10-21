package obs

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

// fakeObsServer to minimalny serwer obs-websocket v5: Hello/Identify/Identified, odpowiada sukcesem na każde żądanie
// i wysyła zdarzenia na polecenie testu.
type fakeObsServer struct {
	srv    *httptest.Server
	mu     sync.Mutex
	conn   *websocket.Conn
	ready  chan struct{}
	reqs   []string
	writeM sync.Mutex
}

func newFakeObsServer(t *testing.T) *fakeObsServer {
	f := &fakeObsServer{ready: make(chan struct{})}
	up := websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }}
	f.srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := up.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close()
		conn.WriteJSON(map[string]interface{}{"op": 0, "d": map[string]interface{}{"obsWebSocketVersion": "5.0.0", "rpcVersion": 1}})
		var identify map[string]interface{}
		if err := conn.ReadJSON(&identify); err != nil {
			return
		}
		conn.WriteJSON(map[string]interface{}{"op": 2, "d": map[string]interface{}{"negotiatedRpcVersion": 1}})
		f.mu.Lock()
		f.conn = conn
		f.mu.Unlock()
		close(f.ready)
		for {
			var m struct {
				Op int                    `json:"op"`
				D  map[string]interface{} `json:"d"`
			}
			if err := conn.ReadJSON(&m); err != nil {
				return
			}
			if m.Op == 6 {
				f.mu.Lock()
				f.reqs = append(f.reqs, m.D["requestType"].(string))
				f.mu.Unlock()
				f.writeM.Lock()
				conn.WriteJSON(map[string]interface{}{"op": 7, "d": map[string]interface{}{
					"requestType": m.D["requestType"], "requestId": m.D["requestId"],
					"requestStatus": map[string]interface{}{"result": true, "code": 100},
					"responseData":  map[string]interface{}{"ok": true},
				}})
				f.writeM.Unlock()
			}
		}
	}))
	t.Cleanup(f.srv.Close)
	return f
}

func (f *fakeObsServer) event(eventType string) {
	f.mu.Lock()
	conn := f.conn
	f.mu.Unlock()
	f.writeM.Lock()
	defer f.writeM.Unlock()
	conn.WriteJSON(map[string]interface{}{"op": 5, "d": map[string]interface{}{"eventType": eventType, "eventIntent": 2}})
}

func (f *fakeObsServer) requests() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]string(nil), f.reqs...)
}

func connectedClient(t *testing.T, f *fakeObsServer) *Client {
	t.Helper()
	port, _ := strconv.Atoi(f.srv.URL[strings.LastIndex(f.srv.URL, ":")+1:])
	c := NewClient(&Config{Host: "127.0.0.1", Port: port, ConnectionTimeoutMs: 1500})
	go func() { // opróżniamy zdarzenia jak robi to plugin
		for range c.Events {
		}
	}()
	if err := c.Connect(); err != nil {
		t.Fatal(err)
	}
	<-f.ready
	t.Cleanup(c.Close)
	return c
}

func TestClientHoldsRequestsDuringSceneCollectionChange(t *testing.T) {
	f := newFakeObsServer(t)
	c := connectedClient(t, f)

	f.event("CurrentSceneCollectionChanging")
	deadline := time.Now().Add(time.Second)
	for !c.Gate.Paused() && time.Now().Before(deadline) {
		time.Sleep(5 * time.Millisecond)
	}
	if !c.Gate.Paused() {
		t.Fatal("Changing powinno zamknąć bramkę")
	}

	done := make(chan error, 1)
	go func() { _, err := c.SendRequest("GetSceneList", nil); done <- err }()
	select {
	case <-done:
		t.Fatal("żądanie nie może wyjść do OBS w trakcie zmiany zbioru scen")
	case <-time.After(150 * time.Millisecond):
	}
	if len(f.requests()) != 0 {
		t.Fatalf("OBS dostał żądanie w trakcie zmiany: %v", f.requests())
	}

	f.event("CurrentSceneCollectionChanged")
	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("po Changed żądanie ma być wykonane: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("żądanie nie zostało wznowione po Changed")
	}
	if got := f.requests(); len(got) != 1 || got[0] != "GetSceneList" {
		t.Fatalf("żądania do OBS: %v", got)
	}
}

// Changed przed Changing (odwrócona kolejność): żądania nie mogą utknąć.
func TestClientChangedBeforeChangingDoesNotStallRequests(t *testing.T) {
	f := newFakeObsServer(t)
	c := connectedClient(t, f)
	f.event("CurrentSceneCollectionChanged")
	f.event("CurrentSceneCollectionChanging")
	time.Sleep(100 * time.Millisecond)
	start := time.Now()
	if _, err := c.SendRequest("GetSceneList", nil); err != nil {
		t.Fatal(err)
	}
	if time.Since(start) > time.Second {
		t.Fatal("żądanie czekało mimo odwróconej kolejności zdarzeń")
	}
}

func TestClientEventsStillReachThePlugin(t *testing.T) {
	f := newFakeObsServer(t)
	port, _ := strconv.Atoi(f.srv.URL[strings.LastIndex(f.srv.URL, ":")+1:])
	c := NewClient(&Config{Host: "127.0.0.1", Port: port, ConnectionTimeoutMs: 1500})
	if err := c.Connect(); err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	<-f.ready
	f.event("CurrentSceneCollectionChanged")
	select {
	case ev := <-c.Events:
		raw, _ := json.Marshal(ev)
		if !strings.Contains(string(raw), "CurrentSceneCollectionChanged") {
			t.Fatalf("zdarzenie: %s", raw)
		}
	case <-time.After(time.Second):
		t.Fatal("zdarzenie zmiany zbioru scen musi dotrzeć do pluginu (odświeżenie mapy scen)")
	}
}
