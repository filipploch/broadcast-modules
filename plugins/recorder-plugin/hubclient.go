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
	Payload   map[string]interface{} `json:"payload"`
	Timestamp string                 `json:"timestamp"`
}

// HubClient manages WebSocket connection to the Hub
type HubClient struct {
	PluginID   string
	PluginName string
	HubURL     string
	conn       *websocket.Conn
	send       chan []byte
	receive    chan *Message
	reconnect  chan struct{}
	done       chan struct{}
	mu         sync.RWMutex
	connected  bool
}

// NewHubClient creates a new Hub client
func NewHubClient(pluginID, pluginName, hubURL string) *HubClient {
	return &HubClient{
		PluginID:   pluginID,
		PluginName: pluginName,
		HubURL:     hubURL,
		send:       make(chan []byte, 256),
		receive:    make(chan *Message, 256),
		reconnect:  make(chan struct{}, 1),
		done:       make(chan struct{}),
	}
}

// Connect establishes connection to the Hub
func (hc *HubClient) Connect() error {
	// ✅ DODAJ DEBUG
	log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Printf("🔍 DEBUG Connect()")
	log.Printf("   HubURL: '%s'", hc.HubURL)
	log.Printf("   Length: %d", len(hc.HubURL))
	log.Printf("   Type: %T", hc.HubURL)
	log.Printf("   Bytes: %v", []byte(hc.HubURL))
	log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	// Walidacja i czyszczenie
	if hc.HubURL == "" {
		return fmt.Errorf("HubURL is empty")
	}

	// Usuń białe znaki
	hc.HubURL = strings.TrimSpace(hc.HubURL)

	// Sprawdź scheme
	if !strings.HasPrefix(hc.HubURL, "ws://") && !strings.HasPrefix(hc.HubURL, "wss://") {
		return fmt.Errorf("invalid URL scheme: %s", hc.HubURL)
	}

	log.Printf("✅ URL validation passed")

	dialer := websocket.Dialer{
		HandshakeTimeout: 10 * time.Second,
	}

	log.Printf("🔌 Dialing: %s", hc.HubURL)
	conn, _, err := dialer.Dial(hc.HubURL, nil)
	if err != nil {
		log.Printf("❌ Dial failed with error: %v", err)
		return fmt.Errorf("failed to connect to Hub: %w", err)
	}

	hc.mu.Lock()
	hc.conn = conn
	hc.connected = true
	hc.mu.Unlock()

	log.Printf("✅ Connected to Hub at %s", hc.HubURL)

	// Start goroutines for reading and writing
	go hc.readPump()
	go hc.writePump()
	go hc.sendHeartbeat()

	// Register plugin with Hub
	log.Printf("📤 Registering with HUB...")
	log.Printf("   Plugin ID:   %s", hc.PluginID)
	log.Printf("   Plugin Name: %s", hc.PluginName)

	hc.Send(&Message{
		From: hc.PluginID,
		To:   "hub",
		Type: "register",
		Payload: map[string]interface{}{
			"id":      hc.PluginID,   // ✅ Changed from plugin_id to id
			"name":    hc.PluginName, // ✅ Added name field
			"type":    "timer",
			"version": "1.0.0",
		},
	})

	return nil
}

// Send sends a message to the Hub
func (hc *HubClient) Send(msg *Message) error {
	hc.mu.RLock()
	if !hc.connected {
		hc.mu.RUnlock()
		return fmt.Errorf("not connected to Hub")
	}
	hc.mu.RUnlock()

	msg.Timestamp = time.Now().Format(time.RFC3339)
	if msg.From == "" {
		msg.From = hc.PluginID
	}

	data, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("failed to marshal message: %w", err)
	}

	select {
	case hc.send <- data:
		return nil
	case <-time.After(5 * time.Second):
		return fmt.Errorf("send timeout")
	}
}

// Receive returns the channel for receiving messages
func (hc *HubClient) Receive() <-chan *Message {
	return hc.receive
}

// readPump reads messages from the Hub
func (hc *HubClient) readPump() {
	defer func() {
		hc.mu.Lock()
		hc.connected = false
		if hc.conn != nil {
			hc.conn.Close()
		}
		hc.mu.Unlock()

		// Signal reconnect
		select {
		case hc.reconnect <- struct{}{}:
		default:
		}
	}()

	hc.mu.RLock()
	conn := hc.conn
	hc.mu.RUnlock()

	conn.SetReadDeadline(time.Now().Add(60 * time.Second))
	conn.SetPongHandler(func(string) error {
		conn.SetReadDeadline(time.Now().Add(60 * time.Second))
		return nil
	})

	for {
		select {
		case <-hc.done:
			return
		default:
		}

		_, data, err := conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				log.Printf("❌ WebSocket error: %v", err)
			}
			return
		}

		var msg Message
		if err := json.Unmarshal(data, &msg); err != nil {
			log.Printf("⚠️  Failed to parse message: %v", err)
			continue
		}

		select {
		case hc.receive <- &msg:
		case <-time.After(1 * time.Second):
			log.Printf("⚠️  Receive buffer full, dropping message")
		}
	}
}

// writePump writes messages to the Hub
func (hc *HubClient) writePump() {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-hc.done:
			return

		case data, ok := <-hc.send:
			hc.mu.RLock()
			conn := hc.conn
			hc.mu.RUnlock()

			if !ok || conn == nil {
				return
			}

			conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := conn.WriteMessage(websocket.TextMessage, data); err != nil {
				log.Printf("❌ Write error: %v", err)
				return
			}

		case <-ticker.C:
			// Send ping to keep connection alive
			hc.mu.RLock()
			conn := hc.conn
			hc.mu.RUnlock()

			if conn == nil {
				return
			}

			conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}

// Close closes the connection to the Hub
func (hc *HubClient) Close() error {
	hc.mu.Lock()
	defer hc.mu.Unlock()

	close(hc.done)

	if hc.conn != nil {
		// Send close message
		hc.conn.WriteMessage(
			websocket.CloseMessage,
			websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""),
		)
		hc.conn.Close()
		hc.conn = nil
	}

	hc.connected = false
	return nil
}

// IsConnected returns true if connected to Hub
func (hc *HubClient) IsConnected() bool {
	hc.mu.RLock()
	defer hc.mu.RUnlock()
	return hc.connected
}

// AutoReconnect automatically reconnects to Hub if connection is lost
func (hc *HubClient) AutoReconnect(maxAttempts int) {
	attempts := 0
	backoff := 1 * time.Second

	for {
		select {
		case <-hc.reconnect:
			if maxAttempts > 0 && attempts >= maxAttempts {
				log.Printf("❌ Max reconnect attempts (%d) reached", maxAttempts)
				return
			}

			attempts++
			log.Printf("🔄 Reconnecting to Hub (attempt %d/%d)...", attempts, maxAttempts)

			time.Sleep(backoff)

			if err := hc.Connect(); err != nil {
				log.Printf("❌ Reconnect failed: %v", err)
				// Exponential backoff
				backoff *= 2
				if backoff > 30*time.Second {
					backoff = 30 * time.Second
				}

				// Signal reconnect again
				select {
				case hc.reconnect <- struct{}{}:
				default:
				}
			} else {
				log.Printf("✅ Reconnected to Hub")
				attempts = 0
				backoff = 1 * time.Second
			}

		case <-hc.done:
			return
		}
	}
}

// sendHeartbeat sends periodic heartbeat messages
func (hc *HubClient) sendHeartbeat() {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-hc.done:
			return

		case <-ticker.C:
			hc.mu.RLock()
			connected := hc.connected
			hc.mu.RUnlock()

			if !connected {
				return
			}

			err := hc.Send(&Message{
				From: hc.PluginID,
				To:   "hub",
				Type: "heartbeat",
				Payload: map[string]interface{}{
					"status": "alive",
				},
			})

			if err != nil {
				log.Printf("⚠️  Failed to send heartbeat: %v", err)
			}
		}
	}
}
