package timer

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

// Po Start() plugin musi regularnie wysyłać heartbeat do HUB-a. Wcześniej pętla heartbeatu startowała, zanim ustawiono
// p.running, i kończyła się od razu (po E2a, gdy między nimi doszło odtwarzanie stanu): HUB uznawał plugin za martwego
// i restartował go co minutę, aż wyczerpał limit restartów.
func TestStartSendsHeartbeats(t *testing.T) {
	got := make(chan Message, 100)
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
			var m Message
			if json.Unmarshal(data, &m) == nil {
				got <- m
			}
		}
	}))
	defer srv.Close()

	p := NewPlugin(PluginConfig{
		PluginID: "timer-plugin", PluginName: "Timer Plugin",
		HubURL:            "ws" + strings.TrimPrefix(srv.URL, "http"),
		HeartbeatInterval: 50,
		StateDir:          filepath.Join(t.TempDir(), "state"),
	})
	if err := p.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { p.Stop() })

	deadline := time.After(2 * time.Second)
	beats := 0
	for beats < 2 {
		select {
		case m := <-got:
			if m.Type == "heartbeat" {
				beats++
			}
		case <-deadline:
			t.Fatalf("po Start() plugin nie wysyła heartbeatów (otrzymano %d)", beats)
		}
	}
}
