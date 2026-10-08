package main

import (
	"encoding/json"
	"time"
)

type Message struct {
	From      string                 `json:"from"`
	To        string                 `json:"to"`
	Type      string                 `json:"type"`
	Payload   map[string]interface{} `json:"payload,omitempty"`
	Timestamp string                 `json:"timestamp"`

	// Context to kontekst transmisji (module, session_id, game_id, period_id). HUB go tylko przekazuje:
	// polecenie niesie go do pluginu, a plugin odsyła ten sam kontekst w odpowiedzi.
	Context map[string]interface{} `json:"context,omitempty"`

	// Source to połączenie, z którego wiadomość przyszła (ustawiane przez HUB, nie przesyłane).
	Source *Module `json:"-"`
}

func NewMessage(from, to, msgType string, payload map[string]interface{}) *Message {
	return &Message{
		From:      from,
		To:        to,
		Type:      msgType,
		Payload:   payload,
		Timestamp: time.Now().Format(time.RFC3339),
	}
}

func (m *Message) ToJSON() ([]byte, error) {
	return json.Marshal(m)
}

func FromJSON(data []byte) (*Message, error) {
	var msg Message
	err := json.Unmarshal(data, &msg)
	return &msg, err
}
