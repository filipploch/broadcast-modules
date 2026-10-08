package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"

	"obs-ws-plugin/internal/hub"
	"obs-ws-plugin/internal/obs"
)

// testHub to serwer WebSocket udający HUB: zbiera wszystko, co wyśle plugin.
func testHub(t *testing.T) (url string, got chan hub.Message) {
	t.Helper()
	got = make(chan hub.Message, 100)
	up := websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := up.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close()
		for {
			_, data, err := conn.ReadMessage()
			if err != nil {
				return
			}
			var m hub.Message
			if json.Unmarshal(data, &m) == nil {
				got <- m
			}
		}
	}))
	t.Cleanup(srv.Close)
	return "ws" + strings.TrimPrefix(srv.URL, "http"), got
}

func waitFor(t *testing.T, got chan hub.Message, typ string) hub.Message {
	t.Helper()
	deadline := time.After(3 * time.Second)
	for {
		select {
		case m := <-got:
			if m.Type == typ {
				return m
			}
		case <-deadline:
			t.Fatalf("nie doczekano wiadomości %s", typ)
		}
	}
}

func newTestPlugin(t *testing.T) (*Plugin, chan hub.Message) {
	t.Helper()
	url, got := testHub(t)
	cfg := &Config{}
	cfg.Plugin.ID = "obs-ws-plugin"
	hc := hub.NewHubClient(url, "obs-ws-plugin", "OBS")
	if err := hc.Connect(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(hc.Close)
	return &Plugin{config: cfg, hubClient: hc, obsClient: obs.NewClient(&obs.Config{}), sceneMap: newSceneMap()}, got
}

var testCtx = map[string]interface{}{"module": "futsal_nalf", "session_id": float64(7), "game_id": float64(42), "period_id": float64(3)}

// Odpowiedź na polecenie odsyła kontekst polecenia (tu: błąd, bo OBS nie jest połączony).
func TestObsErrorReplyEchoesCommandContext(t *testing.T) {
	p, got := newTestPlugin(t)
	p.handleObsCommand(&hub.Message{From: "main-module", Type: "obs_command", Context: testCtx,
		Payload: map[string]interface{}{"requestType": "GetVersion"}})
	m := waitFor(t, got, "obs_error")
	for k, v := range testCtx {
		if m.Context[k] != v {
			t.Fatalf("kontekst odpowiedzi %v != %v", m.Context, testCtx)
		}
	}
}

func TestObsErrorReplyWithoutCommandContextHasNone(t *testing.T) {
	p, got := newTestPlugin(t)
	p.handleObsCommand(&hub.Message{From: "main-module", Type: "obs_command",
		Payload: map[string]interface{}{"requestType": "GetVersion"}})
	if m := waitFor(t, got, "obs_error"); m.Context != nil {
		t.Fatalf("starszy moduł (bez kontekstu) nie może dostać kontekstu: %v", m.Context)
	}
}
