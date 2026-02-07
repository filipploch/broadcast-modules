package main

import (
	"log"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

type Module struct {
	ID            string
	Name          string
	Host          string
	Port          string
	ComponentType string
	Type          string
	Owner         *string
	Connection    *websocket.Conn
	Send          chan []byte
	Hub           *Hub
	LastPing      time.Time
	IsActive      bool
	Capabilities  []string
	DeviceInfo    map[string]interface{}
	Subscriptions map[string]bool
	subMu         sync.RWMutex
}

func NewModule(hub *Hub, conn *websocket.Conn) *Module {
	return &Module{
		Hub:           hub,
		Connection:    conn,
		Send:          make(chan []byte, 256),
		LastPing:      time.Now(),
		IsActive:      false,
		Subscriptions: make(map[string]bool),
	}
}

func (m *Module) ReadPump() {
	defer func() {
		m.Hub.Unregister <- m
		m.Connection.Close()
	}()

	m.Connection.SetReadDeadline(time.Now().Add(60 * time.Second))
	m.Connection.SetPongHandler(func(string) error {
		m.Connection.SetReadDeadline(time.Now().Add(60 * time.Second))
		m.LastPing = time.Now()
		return nil
	})

	log.Printf("🔵 ReadPump started for connection") // ← DODAJ

	for {
		log.Printf("🔵 Waiting for message...") // ← DODAJ

		_, message, err := m.Connection.ReadMessage()
		if err != nil {
			log.Printf("🔴 ReadMessage error: %v", err) // ← DODAJ
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				log.Printf("WebSocket error from %s: %v", m.ID, err)
			}
			break
		}

		log.Printf("🟢 Message received! Length: %d bytes", len(message)) // ← DODAJ

		msg, err := FromJSON(message)
		if err != nil {
			log.Printf("Invalid message from %s: %v", m.ID, err)
			continue
		}

		// NIE nadpisuj From jeśli module jeszcze nie ma ID
		if m.ID != "" {
			msg.From = m.ID
		}
		// Dla wiadomości register, From będzie z payload (plugin_id)

		log.Printf("🟡 Parsed: type=%s, from_field=%s", msg.Type, msg.From) // ← DODAJ

		msg.From = m.ID

		log.Printf("🟡 After setting From: type=%s, from=%s", msg.Type, msg.From) // ← DODAJ

		if m.handleSystemMessage(msg) {
			log.Printf("🔴 Handled by system, skipping route") // ← DODAJ
			continue
		}

		log.Printf("🟢 Sending to Route channel...") // ← DODAJ
		m.Hub.Route <- msg
		log.Printf("✅ Sent to Route!") // ← DODAJ
	}

	log.Printf("🔴 ReadPump exiting") // ← DODAJ
}

func (m *Module) WritePump() {
	ticker := time.NewTicker(30 * time.Second)
	defer func() {
		ticker.Stop()
		m.Connection.Close()
	}()

	for {
		select {
		case message, ok := <-m.Send:
			m.Connection.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if !ok {
				m.Connection.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}

			if err := m.Connection.WriteMessage(websocket.TextMessage, message); err != nil {
				return
			}

		case <-ticker.C:
			m.Connection.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := m.Connection.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}

func (m *Module) handleSystemMessage(msg *Message) bool {
	switch msg.Type {
	// ✅ REMOVED: "register" case - let HUB handle it
	// Wiadomość "register" musi trafić do HUB, nie może być obsługiwana lokalnie

	case "ping":
		pong := NewMessage("hub", m.ID, "pong", nil)
		if data, err := pong.ToJSON(); err == nil {
			m.Send <- data
		}
		return true
	}

	return false
}

// Subscribe adds a class subscription
func (m *Module) Subscribe(class string) {
	m.subMu.Lock()
	m.Subscriptions[class] = true
	m.subMu.Unlock()
}

// Unsubscribe removes a class subscription
func (m *Module) Unsubscribe(class string) {
	m.subMu.Lock()
	delete(m.Subscriptions, class)
	m.subMu.Unlock()
}

// IsSubscribedTo checks if subscribed to class
func (m *Module) IsSubscribedTo(class string) bool {
	m.subMu.RLock()
	defer m.subMu.RUnlock()
	return m.Subscriptions[class]
}
