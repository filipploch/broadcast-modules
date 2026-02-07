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

// Connect establishes WebSocket connection to HUB
func (c *HubClient) Connect() error {
	log.Printf("🔌 Connecting to HUB: %s", c.URL)

	conn, _, err := websocket.DefaultDialer.Dial(c.URL, nil)
	if err != nil {
		return fmt.Errorf("failed to connect to HUB: %w", err)
	}

	c.mu.Lock()
	c.conn = conn
	c.connected = true
	c.mu.Unlock()

	// Register with HUB
	if err := c.register(); err != nil {
		conn.Close()
		return fmt.Errorf("failed to register with HUB: %w", err)
	}

	log.Printf("✅ Connected to HUB and registered as: %s", c.PluginID)

	// Start message handlers
	go c.readMessages()
	go c.heartbeat()

	return nil
}

// register sends registration message to HUB
func (c *HubClient) register() error {
	msg := &Message{
		From: c.PluginID,
		To:   "hub",
		Type: "register",
		Payload: map[string]interface{}{
			"plugin_id":   c.PluginID,
			"plugin_name": c.PluginName,
			"plugin_type": "obs-websocket",
			"classes":     []string{"obs", "streaming", "recording"},
		},
	}

	return c.Send(msg)
}

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
				From: c.PluginID,
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
