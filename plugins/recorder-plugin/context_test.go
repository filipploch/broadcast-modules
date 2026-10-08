package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

// ctxTestHub to serwer WebSocket udający HUB: zbiera wszystko, co wyśle plugin.
func ctxTestHub(t *testing.T) (*HubClient, chan Message) {
	t.Helper()
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
	t.Cleanup(srv.Close)
	hc := NewHubClient("recorder-plugin", "Recorder", "ws"+strings.TrimPrefix(srv.URL, "http"))
	if err := hc.Connect(); err != nil {
		t.Fatal(err)
	}
	return hc, got
}

func ctxWait(t *testing.T, got chan Message, typ string) Message {
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

var ctxA = map[string]interface{}{"module": "futsal_nalf", "session_id": float64(7), "game_id": float64(42), "period_id": float64(3)}

func requireCtx(t *testing.T, m Message, want map[string]interface{}) {
	t.Helper()
	for k, v := range want {
		if m.Context[k] != v {
			t.Fatalf("%s: kontekst %v != %v", m.Type, m.Context, want)
		}
	}
}

// Zdarzenia kamery niosą kontekst polecenia, które uruchomiło jej nagrywanie.
func TestCameraEventsCarryStartCommandContext(t *testing.T) {
	hc, got := ctxTestHub(t)
	rm := &RecorderManager{cameras: map[string]*CameraRecorder{}, hubClient: hc}
	rm.setCameraContext("camera1", ctxA)

	rm.notifyRecordingStopped("camera1")
	requireCtx(t, ctxWait(t, got, "recording_stopped"), ctxA)

	rm.notifyStreamChanged("camera1", true, "")
	requireCtx(t, ctxWait(t, got, "stream_changed"), ctxA)

	rm.notifySegmentRotated("camera1", RecordingMeta{CameraID: "camera1"}, "max_duration")
	requireCtx(t, ctxWait(t, got, "segment_rotated"), ctxA)

	rm.notifyRecordingStarted(RecordingMeta{CameraID: "camera1"})
	requireCtx(t, ctxWait(t, got, "recording_started"), ctxA)
}

func TestCameraWithoutStartContextHasNone(t *testing.T) {
	hc, got := ctxTestHub(t)
	rm := &RecorderManager{cameras: map[string]*CameraRecorder{}, hubClient: hc}
	rm.notifyRecordingStopped("camera2")
	if m := ctxWait(t, got, "recording_stopped"); m.Context != nil {
		t.Fatalf("kamera bez kontekstu nie może go dostać: %v", m.Context)
	}
}

func TestCameraContextIsPerCamera(t *testing.T) {
	hc, got := ctxTestHub(t)
	rm := &RecorderManager{cameras: map[string]*CameraRecorder{}, hubClient: hc}
	rm.setCameraContext("camera1", ctxA)
	rm.setCameraContext("camera2", map[string]interface{}{"game_id": float64(43)})
	rm.notifyRecordingStopped("camera1")
	rm.notifyRecordingStopped("camera2")
	first := ctxWait(t, got, "recording_stopped")
	second := ctxWait(t, got, "recording_stopped")
	if first.Context["game_id"] != float64(42) || second.Context["game_id"] != float64(43) {
		t.Fatalf("konteksty kamer pomieszane: %v / %v", first.Context, second.Context)
	}
}

// Odpowiedź na polecenie nagrywania odsyła kontekst polecenia (także błąd).
func TestRecordingCommandReplyEchoesCommandContext(t *testing.T) {
	hc, got := ctxTestHub(t)
	rm := &RecorderManager{cameras: map[string]*CameraRecorder{}, hubClient: hc}
	rm.handleRecordingCommand(&Message{From: "main-module", Type: "recording_command", Context: ctxA,
		Payload: map[string]interface{}{"requestType": "Nieznane", "cameras": map[string]interface{}{}}}, hc)
	requireCtx(t, ctxWait(t, got, "recording_command_response"), ctxA)
}

func TestRecordingCommandPartialErrorEchoesCommandContext(t *testing.T) {
	hc, got := ctxTestHub(t)
	rm := &RecorderManager{cameras: map[string]*CameraRecorder{}, hubClient: hc}
	rm.handleRecordingCommand(&Message{From: "main-module", Type: "recording_command", Context: ctxA,
		Payload: map[string]interface{}{"requestType": "StartRecord", "cameras": map[string]interface{}{"nie-ma-takiej": true}}}, hc)
	var sawPartial bool
	for i := 0; i < 2; i++ {
		m := ctxWait(t, got, "recording_command_response")
		requireCtx(t, m, ctxA)
		if m.Payload["status"] == "partial_error" {
			sawPartial = true
		}
	}
	if !sawPartial {
		t.Fatal("brak odpowiedzi partial_error")
	}
}
