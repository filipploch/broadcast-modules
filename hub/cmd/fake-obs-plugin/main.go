// Program pomocniczy prób (nie wchodzi do wersji transmisyjnej): udaje obs-ws-plugin bez OBS. Rejestruje się w HUB-ie jak plugin,
// wysyła heartbeaty i odpowiada na pytania o stan streamu i nagrywania według pliku FAKE_OBS_STATE (JSON), który próba może zmieniać
// w trakcie pracy: {"stream": false, "record": false, "silent": false, "fail": false}.
//   - silent: plugin nie odpowiada na polecenia (jak zawieszony),
//   - fail:   plugin odpowiada obs_error ("OBS not connected").
//
// Zmienne: HUB_URL (ustawia HUB), PLUGIN_ID (domyślnie obs-ws-plugin), FAKE_OBS_STATE, FAKE_OBS_LOG (dziennik zdarzeń).
// Po zerwaniu połączenia próbuje łączyć się ponownie (jak prawdziwe pluginy po awarii HUB-a).
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

type message struct {
	From      string                 `json:"from"`
	To        string                 `json:"to"`
	Type      string                 `json:"type"`
	Payload   map[string]interface{} `json:"payload,omitempty"`
	Timestamp string                 `json:"timestamp"`
	Context   map[string]interface{} `json:"context,omitempty"`
}

type fakeState struct {
	Stream bool `json:"stream"`
	Record bool `json:"record"`
	Silent bool `json:"silent"`
	Fail   bool `json:"fail"`
}

func readState() fakeState {
	var s fakeState
	if p := os.Getenv("FAKE_OBS_STATE"); p != "" {
		if data, err := os.ReadFile(p); err == nil {
			json.Unmarshal(data, &s)
		}
	}
	return s
}

func journal(format string, args ...interface{}) {
	line := fmt.Sprintf(format, args...)
	log.Println(line)
	if p := os.Getenv("FAKE_OBS_LOG"); p != "" {
		if f, err := os.OpenFile(p, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644); err == nil {
			fmt.Fprintf(f, "%s %s\n", time.Now().Format("15:04:05.000"), line)
			f.Close()
		}
	}
}

func main() {
	id := os.Getenv("PLUGIN_ID")
	if id == "" {
		id = "obs-ws-plugin"
	}
	url := os.Getenv("HUB_URL")
	if url == "" {
		url = "ws://localhost:8080/ws"
	}
	for {
		run(id, url)
		time.Sleep(2 * time.Second)
	}
}

func run(id, url string) {
	conn, _, err := websocket.DefaultDialer.Dial(url, nil)
	if err != nil {
		return
	}
	defer conn.Close()
	var mu sync.Mutex
	send := func(m *message) {
		m.Timestamp = time.Now().Format(time.RFC3339)
		mu.Lock()
		defer mu.Unlock()
		conn.WriteJSON(m)
	}
	send(&message{From: id, To: "hub", Type: "register", Payload: map[string]interface{}{"plugin_id": id, "name": "Fake OBS WS plugin"}})
	journal("zarejestrowano w HUB-ie (%s)", url)
	stop := make(chan struct{})
	defer close(stop)
	go func() {
		t := time.NewTicker(5 * time.Second)
		defer t.Stop()
		for {
			select {
			case <-stop:
				return
			case <-t.C:
				send(&message{From: id, To: "hub", Type: "heartbeat"})
			}
		}
	}()
	for {
		var m message
		if err := conn.ReadJSON(&m); err != nil {
			journal("połączenie z HUB-em zerwane: %v", err)
			return
		}
		if m.Type != "obs_command" {
			continue
		}
		rt, _ := m.Payload["requestType"].(string)
		s := readState()
		journal("polecenie %s od %s (stream=%v record=%v silent=%v fail=%v)", rt, m.From, s.Stream, s.Record, s.Silent, s.Fail)
		if s.Silent {
			continue
		}
		if s.Fail {
			send(&message{From: id, To: m.From, Type: "obs_error", Context: m.Context,
				Payload: map[string]interface{}{"error": "OBS not connected", "command": m.Payload}})
			continue
		}
		data := map[string]interface{}{}
		switch rt {
		case "GetStreamStatus":
			data["outputActive"] = s.Stream
		case "GetRecordStatus":
			data["outputActive"] = s.Record
		}
		send(&message{From: id, To: m.From, Type: "obs_response", Context: m.Context,
			Payload: map[string]interface{}{"requestType": rt, "requestID": m.Payload["request_id"], "responseData": data}})
	}
}
