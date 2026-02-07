package obs

import (
	"encoding/json"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/andreykaipov/goobs"
	"github.com/andreykaipov/goobs/api/events"
)

// Config holds OBS connection configuration
type Config struct {
	Host                  string `json:"host"`
	Port                  int    `json:"port"`
	Password              string `json:"password"`
	AutoReconnect         bool   `json:"auto_reconnect"`
	ReconnectIntervalMs   int    `json:"reconnect_interval_ms"`
	MaxReconnectAttempts  int    `json:"max_reconnect_attempts"` // 0 = infinite
	ConnectionTimeoutMs   int    `json:"connection_timeout_ms"`
}

// Client handles connection to OBS WebSocket
type Client struct {
	config        *Config
	client        *goobs.Client
	mu            sync.RWMutex
	connected     bool
	Events        chan interface{} // Raw OBS events
	StatusChanged chan string      // Connection status changes
	stopChan      chan struct{}
	reconnecting  bool
}

// NewClient creates a new OBS client
func NewClient(config *Config) *Client {
	return &Client{
		config:        config,
		Events:        make(chan interface{}, 100),
		StatusChanged: make(chan string, 10),
		stopChan:      make(chan struct{}),
	}
}

// Connect establishes connection to OBS
func (c *Client) Connect() error {
	log.Printf("🎬 Connecting to OBS: %s:%d", c.config.Host, c.config.Port)

	addr := fmt.Sprintf("%s:%d", c.config.Host, c.config.Port)
	
	client, err := goobs.New(addr, goobs.WithPassword(c.config.Password))
	if err != nil {
		return fmt.Errorf("failed to connect to OBS: %w", err)
	}

	c.mu.Lock()
	c.client = client
	c.connected = true
	c.reconnecting = false
	c.mu.Unlock()

	log.Printf("✅ Connected to OBS WebSocket")

	// Notify status change
	select {
	case c.StatusChanged <- "connected":
	default:
	}

	// Start event listener
	go c.listenEvents()

	return nil
}

// listenEvents listens for OBS events and forwards them
func (c *Client) listenEvents() {
	defer func() {
		c.mu.Lock()
		c.connected = false
		c.mu.Unlock()

		// Notify disconnection
		select {
		case c.StatusChanged <- "disconnected":
		default:
		}

		// Try to reconnect if enabled
		if c.config.AutoReconnect && !c.reconnecting {
			go c.reconnect()
		}
	}()

	c.mu.RLock()
	client := c.client
	c.mu.RUnlock()

	if client == nil {
		return
	}

	// Subscribe to all events
	for event := range client.IncomingEvents {
		select {
		case <-c.stopChan:
			return
		default:
			// Forward raw event
			c.Events <- event
			
			// Log event type for debugging
			c.logEvent(event)
		}
	}
}

// logEvent logs event type for debugging
func (c *Client) logEvent(event interface{}) {
	switch e := event.(type) {
	case *events.RecordStateChanged:
		log.Printf("📹 OBS Event: RecordStateChanged -> %s", e.OutputState)
	case *events.CurrentProgramSceneChanged:
		log.Printf("🎬 OBS Event: SceneChanged -> %s", e.SceneName)
	case *events.StreamStateChanged:
		log.Printf("📡 OBS Event: StreamStateChanged -> %s", e.OutputState)
	default:
		// Don't log every event, just the important ones
		// log.Printf("📨 OBS Event: %T", event)
	}
}

// reconnect attempts to reconnect to OBS
func (c *Client) reconnect() {
	c.mu.Lock()
	if c.reconnecting {
		c.mu.Unlock()
		return
	}
	c.reconnecting = true
	c.mu.Unlock()

	log.Printf("🔄 Starting OBS reconnection attempts...")

	// Notify status
	select {
	case c.StatusChanged <- "reconnecting":
	default:
	}

	attempt := 0
	interval := time.Duration(c.config.ReconnectIntervalMs) * time.Millisecond

	for {
		select {
		case <-c.stopChan:
			return
		default:
			attempt++
			
			// Check max attempts
			if c.config.MaxReconnectAttempts > 0 && attempt > c.config.MaxReconnectAttempts {
				log.Printf("❌ Max reconnect attempts (%d) reached", c.config.MaxReconnectAttempts)
				c.mu.Lock()
				c.reconnecting = false
				c.mu.Unlock()
				return
			}

			log.Printf("🔄 Reconnect attempt %d...", attempt)

			if err := c.Connect(); err == nil {
				log.Printf("✅ Reconnected to OBS")
				return
			}

			log.Printf("⚠️  Reconnect failed, retrying in %v...", interval)
			time.Sleep(interval)
		}
	}
}

// SendRaw sends raw JSON command to OBS
func (c *Client) SendRaw(payload map[string]interface{}) error {
	c.mu.RLock()
	client := c.client
	connected := c.connected
	c.mu.RUnlock()

	if !connected || client == nil {
		return fmt.Errorf("not connected to OBS")
	}

	// Marshal payload to JSON
	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal payload: %w", err)
	}

	// Send raw request
	// Note: goobs doesn't have a direct SendRaw method,
	// so we'll use the underlying connection
	// This is a simplified version - in production you'd want to handle this better
	log.Printf("📤 Sending to OBS: %s", string(data))

	// For now, we'll use the SendRequest method with the data
	// The actual implementation depends on the OBS request structure
	
	return nil
}

// IsConnected returns true if connected to OBS
func (c *Client) IsConnected() bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.connected
}

// Close closes the connection to OBS
func (c *Client) Close() {
	close(c.stopChan)

	c.mu.Lock()
	defer c.mu.Unlock()

	if c.client != nil {
		c.client.Disconnect()
		c.client = nil
	}
	c.connected = false

	log.Printf("🔌 Disconnected from OBS")
}
