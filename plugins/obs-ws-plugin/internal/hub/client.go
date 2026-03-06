package hub

import (
	"encoding/json"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// Message represents a message exchanged with the HUB
type Message struct {
	From    string                 `json:"from"`
	To      string                 `json:"to"`
	Type    string                 `json:"type"`
	Payload map[string]interface{} `json:"payload,omitempty"`
}

// classes that this plugin subscribes to after every successful registration.
// Defined as a package-level constant so it's easy to extend.
var pluginClasses = []string{"obs", "streaming", "recording", "recorder_device"}

// HubClient handles WebSocket connection to the HUB
type HubClient struct {
	URL              string
	PluginID         string
	PluginName       string
	conn             *websocket.Conn
	mu               sync.RWMutex
	Messages         chan *Message
	connected        bool
	reconnectEnabled bool
	stopChan         chan struct{}
	stopOnce         sync.Once
}

// NewHubClient creates a new HUB client
func NewHubClient(url, pluginID, pluginName string) *HubClient {
	return &HubClient{
		URL:              url,
		PluginID:         pluginID,
		PluginName:       pluginName,
		Messages:         make(chan *Message, 100),
		reconnectEnabled: true,
		stopChan:         make(chan struct{}),
	}
}

// Connect establishes WebSocket connection to HUB.
// Safe to call multiple times (e.g. during reconnect).
func (c *HubClient) Connect() error {
	log.Printf("🔌 Connecting to HUB: %s", c.URL)

	conn, _, err := websocket.DefaultDialer.Dial(c.URL, nil)
	if err != nil {
		return fmt.Errorf("failed to connect to HUB: %w", err)
	}

	c.mu.Lock()
	c.conn = conn
	c.connected = true
	// Refresh stopChan for new session — previous one may be spent
	c.stopChan = make(chan struct{})
	c.stopOnce = sync.Once{}
	c.mu.Unlock()

	// Register with HUB
	if err := c.register(); err != nil {
		conn.Close()
		c.mu.Lock()
		c.connected = false
		c.mu.Unlock()
		return fmt.Errorf("failed to register with HUB: %w", err)
	}

	// Subscribe to classes — separate message, hub handles it via handleSubscribe()
	if err := c.subscribe(); err != nil {
		// Non-fatal: plugin is registered, just won't receive class broadcasts.
		// Hub will log the missing subscription; retry happens on next reconnect.
		log.Printf("⚠️  Failed to subscribe to classes: %v", err)
	}

	log.Printf("✅ Connected to HUB and registered as: %s", c.PluginID)
	log.Printf("   Subscribed to classes: %v", pluginClasses)

	// Start message handlers for this session
	go c.readMessages()
	go c.heartbeat()

	return nil
}

// ConnectWithRetry attempts Connect() indefinitely with exponential backoff.
// Use at startup instead of Connect() to avoid Fatalf on temporary hub unavailability.
func (c *HubClient) ConnectWithRetry() {
	backoff := time.Second
	maxBackoff := 30 * time.Second
	attempt := 0

	for {
		attempt++
		log.Printf("🔌 Connecting to HUB (attempt %d): %s", attempt, c.URL)

		if err := c.Connect(); err == nil {
			return
		} else {
			log.Printf("⚠️  HUB connection failed: %v — retrying in %v", err, backoff)
		}

		select {
		case <-c.stopChan:
			log.Printf("⏹️  ConnectWithRetry cancelled")
			return
		case <-time.After(backoff):
		}

		backoff *= 2
		if backoff > maxBackoff {
			backoff = maxBackoff
		}
	}
}

// register sends registration message to HUB.
// Classes are NOT included here — hub ignores them in register payload.
// Use subscribe() separately after registration.
func (c *HubClient) register() error {
	return c.Send(&Message{
		From: c.PluginID,
		To:   "hub",
		Type: "register",
		Payload: map[string]interface{}{
			"id":          c.PluginID,
			"name":        c.PluginName,
			"plugin_type": "obs-websocket",
		},
	})
}

// subscribe sends a subscribe message to HUB so this plugin receives
// broadcast:className messages. Must be called after every successful register().
func (c *HubClient) subscribe() error {
	return c.Send(&Message{
		From: c.PluginID,
		To:   "hub",
		Type: "subscribe",
		Payload: map[string]interface{}{
			"class": pluginClasses,
		},
	})
}

// // Subscribe subscribes this plugin to one or more HUB classes.
// // Must be called after successful registration.
// func (c *HubClient) Subscribe(classes ...string) error {
// 	msg := &Message{
// 		From: "obs-ws-plugin",
// 		To:   "hub",
// 		Type: "subscribe",
// 		Payload: map[string]interface{}{
// 			"class": classes,
// 		},
// 	}
// 	return c.Send(msg)
// }

// readMessages reads incoming messages from HUB
func (c *HubClient) readMessages() {
	defer func() {
		c.mu.Lock()
		c.connected = false
		c.mu.Unlock()

		// Try to reconnect if enabled
		if c.reconnectEnabled {
			go c.reconnect()
		}
	}()

	for {
		select {
		case <-c.stopChan:
			return
		default:
			c.mu.RLock()
			conn := c.conn
			c.mu.RUnlock()

			if conn == nil {
				return
			}

			_, data, err := conn.ReadMessage()
			if err != nil {
				log.Printf("❌ Error reading from HUB: %v", err)
				return
			}

			var msg Message
			if err := json.Unmarshal(data, &msg); err != nil {
				log.Printf("⚠️  Failed to parse message: %v", err)
				continue
			}

			// Send to message channel for processing
			select {
			case c.Messages <- &msg:
			default:
				log.Printf("⚠️  Message channel full, dropping message")
			}
		}
	}
}

// heartbeat sends periodic heartbeat to HUB
func (c *HubClient) heartbeat() {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-c.stopChan:
			return
		case <-ticker.C:
			c.mu.RLock()
			connected := c.connected
			c.mu.RUnlock()

			if !connected {
				return
			}

			msg := &Message{
				From: "obs-ws-plugin",
				To:   "hub",
				Type: "heartbeat",
			}

			if err := c.Send(msg); err != nil {
				log.Printf("⚠️  Failed to send heartbeat: %v", err)
			}
		}
	}
}

// reconnect attempts to reconnect to HUB
func (c *HubClient) reconnect() {
	log.Printf("🔄 Attempting to reconnect to HUB...")

	backoff := time.Second
	maxBackoff := 30 * time.Second

	for {
		select {
		case <-c.stopChan:
			return
		default:
			if err := c.Connect(); err == nil {
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

// Send sends a message to HUB
func (c *HubClient) Send(msg *Message) error {
	c.mu.RLock()
	conn := c.conn
	connected := c.connected
	c.mu.RUnlock()

	if !connected || conn == nil {
		return fmt.Errorf("not connected to HUB")
	}

	data, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("failed to marshal message: %w", err)
	}

	c.mu.Lock()
	defer c.mu.Unlock()

	if err := conn.WriteMessage(websocket.TextMessage, data); err != nil {
		return fmt.Errorf("failed to send message: %w", err)
	}

	return nil
}

// IsConnected returns true if connected to HUB
func (c *HubClient) IsConnected() bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.connected
}

// Close closes the connection to HUB
func (c *HubClient) Close() {
	close(c.stopChan)
	c.reconnectEnabled = false

	c.mu.Lock()
	defer c.mu.Unlock()

	if c.conn != nil {
		c.conn.Close()
		c.conn = nil
	}
	c.connected = false

	log.Printf("🔌 Disconnected from HUB")
}
