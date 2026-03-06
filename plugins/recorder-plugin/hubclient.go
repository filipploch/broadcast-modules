package main

import (
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// Message represents a WebSocket message in the Broadcast-modules system
type Message struct {
	From      string                 `json:"from"`
	To        string                 `json:"to"`
	Type      string                 `json:"type"`
	Payload   map[string]interface{} `json:"payload,omitempty"`
	Timestamp string                 `json:"timestamp,omitempty"`
}

// HubClient manages WebSocket connection to the Hub
type HubClient struct {
	PluginID   string
	PluginName string
	HubURL     string

	conn             *websocket.Conn
	mu               sync.RWMutex
	connected        bool
	reconnectEnabled bool
	stopChan         chan struct{}

	Messages chan *Message // incoming messages from Hub
}

// NewHubClient creates a new Hub client
func NewHubClient(pluginID, pluginName, hubURL string) *HubClient {
	return &HubClient{
		PluginID:         pluginID,
		PluginName:       pluginName,
		HubURL:           hubURL,
		Messages:         make(chan *Message, 256),
		reconnectEnabled: true,
		stopChan:         make(chan struct{}),
	}
}

// Connect establishes connection to the Hub
func (hc *HubClient) Connect() error {
	hc.mu.RLock()
	alreadyConnected := hc.connected
	hc.mu.RUnlock()
	if alreadyConnected {
		return fmt.Errorf("already connected to Hub at %s", hc.HubURL)
	}

	hc.HubURL = strings.TrimSpace(hc.HubURL)
	if hc.HubURL == "" {
		return fmt.Errorf("HubURL is empty")
	}
	if !strings.HasPrefix(hc.HubURL, "ws://") && !strings.HasPrefix(hc.HubURL, "wss://") {
		return fmt.Errorf("invalid URL scheme: %s", hc.HubURL)
	}

	log.Printf("🔌 Connecting to HUB: %s", hc.HubURL)

	dialer := websocket.Dialer{
		HandshakeTimeout: 10 * time.Second,
	}
	conn, _, err := dialer.Dial(hc.HubURL, nil)
	if err != nil {
		return fmt.Errorf("failed to connect to Hub: %w", err)
	}

	hc.mu.Lock()
	hc.conn = conn
	hc.connected = true
	hc.mu.Unlock()

	// Register plugin with Hub
	if err := hc.register(); err != nil {
		conn.Close()
		hc.mu.Lock()
		hc.conn = nil
		hc.connected = false
		hc.mu.Unlock()
		return fmt.Errorf("failed to register with Hub: %w", err)
	}

	log.Printf("✅ Connected to HUB and registered as: %s", hc.PluginID)

	go hc.readMessages()
	go hc.sendHeartbeat()

	return nil
}

// register sends the registration message to Hub
func (hc *HubClient) register() error {
	return hc.Send(&Message{
		From: "recorder-plugin",
		To:   "hub",
		Type: "register",
		Payload: map[string]interface{}{
			"plugin_id":   hc.PluginID,
			"plugin_name": hc.PluginName,
			"plugin_type": "recorder",
			"classes":     []string{"recorder_device"},
		},
	})
}

// Send sends a message to the Hub
func (hc *HubClient) Send(msg *Message) error {
	hc.mu.RLock()
	conn := hc.conn
	connected := hc.connected
	hc.mu.RUnlock()

	if !connected || conn == nil {
		return fmt.Errorf("not connected to Hub")
	}

	if msg.From == "" {
		msg.From = hc.PluginID
	}
	msg.Timestamp = time.Now().Format(time.RFC3339)

	data, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("failed to marshal message: %w", err)
	}

	hc.mu.Lock()
	defer hc.mu.Unlock()

	conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
	if err := conn.WriteMessage(websocket.TextMessage, data); err != nil {
		return fmt.Errorf("failed to send message: %w", err)
	}

	return nil
}

// Subscribe subscribes this plugin to one or more HUB classes.
// Must be called after successful registration.
func (hc *HubClient) Subscribe(classes ...string) error {
	return hc.Send(&Message{
		From: "recorder-plugin",
		To:   "hub",
		Type: "subscribe",
		Payload: map[string]interface{}{
			"class": classes,
		},
	})
}

// Receive returns the channel for incoming messages (read-only)
func (hc *HubClient) Receive() <-chan *Message {
	return hc.Messages
}

// readMessages reads incoming messages from Hub
func (hc *HubClient) readMessages() {
	defer func() {
		hc.mu.Lock()
		hc.connected = false
		if hc.conn != nil {
			hc.conn.Close()
			hc.conn = nil
		}
		hc.mu.Unlock()

		if hc.reconnectEnabled {
			go hc.reconnect()
		}
	}()

	for {
		select {
		case <-hc.stopChan:
			return
		default:
		}

		hc.mu.RLock()
		conn := hc.conn
		hc.mu.RUnlock()

		if conn == nil {
			return
		}

		_, data, err := conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				log.Printf("❌ WebSocket error: %v", err)
			} else {
				log.Printf("⚠️  Connection to HUB lost: %v", err)
			}
			return
		}

		var msg Message
		if err := json.Unmarshal(data, &msg); err != nil {
			log.Printf("⚠️  Failed to parse message: %v", err)
			continue
		}

		select {
		case hc.Messages <- &msg:
		default:
			log.Printf("⚠️  Message channel full, dropping message")
		}
	}
}

// sendHeartbeat sends periodic heartbeat messages to Hub
func (hc *HubClient) sendHeartbeat() {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-hc.stopChan:
			return
		case <-ticker.C:
			hc.mu.RLock()
			connected := hc.connected
			hc.mu.RUnlock()

			if !connected {
				return
			}

			if err := hc.Send(&Message{
				From: "recorder-plugin",
				To:   "hub",
				Type: "heartbeat",
				Payload: map[string]interface{}{
					"status": "alive",
				},
			}); err != nil {
				log.Printf("⚠️  Failed to send heartbeat: %v", err)
			}
		}
	}
}

// reconnect attempts to reconnect to Hub after connection loss
func (hc *HubClient) reconnect() {
	log.Printf("🔄 Attempting to reconnect to HUB...")

	backoff := 1 * time.Second
	maxBackoff := 30 * time.Second

	for {
		select {
		case <-hc.stopChan:
			return
		default:
			if err := hc.Connect(); err == nil {
				log.Printf("✅ Reconnected to HUB")
				return
			}

			log.Printf("⚠️  Reconnect failed, retrying in %v...", backoff)
			time.Sleep(backoff)

			backoff *= 2
			if backoff > maxBackoff {
				backoff = maxBackoff
			}
		}
	}
}

// IsConnected returns true if connected to Hub
func (hc *HubClient) IsConnected() bool {
	hc.mu.RLock()
	defer hc.mu.RUnlock()
	return hc.connected
}

// Close closes the connection to the Hub
func (hc *HubClient) Close() error {
	hc.reconnectEnabled = false
	close(hc.stopChan)

	hc.mu.Lock()
	defer hc.mu.Unlock()

	if hc.conn != nil {
		hc.conn.WriteMessage(
			websocket.CloseMessage,
			websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""),
		)
		hc.conn.Close()
		hc.conn = nil
	}

	hc.connected = false
	log.Printf("🔌 Disconnected from HUB")
	return nil
}

func (hc *HubClient) Done() <-chan struct{} {
	return hc.stopChan
}
