package obs

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/gorilla/websocket"
)

// EventSubscription bitmask values for OBS WebSocket v5
// https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md#eventsubscription
const (
	EventSubNone        = 0
	EventSubGeneral     = 1 << 0 // 1
	EventSubConfig      = 1 << 1 // 2
	EventSubScenes      = 1 << 2 // 4
	EventSubInputs      = 1 << 3 // 8
	EventSubTransitions = 1 << 4 // 16
	EventSubFilters     = 1 << 5 // 32
	EventSubOutputs     = 1 << 6 // 64
	EventSubSceneItems  = 1 << 7 // 128
	EventSubMediaInputs = 1 << 8 // 256
	EventSubAll         = (1 << 16) - 1
)

// Config holds OBS connection configuration
type Config struct {
	Host                 string `json:"host"`
	Port                 int    `json:"port"`
	Password             string `json:"password"`
	AutoReconnect        bool   `json:"auto_reconnect"`
	ReconnectIntervalMs  int    `json:"reconnect_interval_ms"`
	MaxReconnectAttempts int    `json:"max_reconnect_attempts"`
	ConnectionTimeoutMs  int    `json:"connection_timeout_ms"`
	EventSubscriptions   int    `json:"event_subscriptions"` // bitmask, 0 = General only (OBS default)
}

// obsMessage represents a raw OBS WebSocket v5 message
type obsMessage struct {
	Op   int                    `json:"op"`
	Data map[string]interface{} `json:"d"`
}

// pendingRequest holds a channel waiting for a specific requestId response
type pendingRequest struct {
	ch chan map[string]interface{}
}

// Client handles connection to OBS WebSocket
type Client struct {
	config        *Config
	conn          *websocket.Conn
	mu            sync.RWMutex
	writeMu       sync.Mutex
	connected     bool
	Events        chan map[string]interface{}
	StatusChanged chan string
	stopChan      chan struct{}
	reconnecting  bool

	pendingMu sync.Mutex
	pending   map[string]*pendingRequest
}

// NewClient creates a new OBS client
func NewClient(config *Config) *Client {
	return &Client{
		config:        config,
		Events:        make(chan map[string]interface{}, 100),
		StatusChanged: make(chan string, 10),
		stopChan:      make(chan struct{}),
		pending:       make(map[string]*pendingRequest),
	}
}

// Connect establishes connection to OBS WebSocket
func (c *Client) Connect() error {
	log.Printf("🎬 Connecting to OBS: %s:%d", c.config.Host, c.config.Port)

	url := fmt.Sprintf("ws://%s:%d", c.config.Host, c.config.Port)
	conn, _, err := websocket.DefaultDialer.Dial(url, nil)
	if err != nil {
		return fmt.Errorf("failed to connect to OBS: %w", err)
	}

	c.mu.Lock()
	c.conn = conn
	c.connected = false
	c.reconnecting = false
	c.mu.Unlock()

	if err := c.handshake(); err != nil {
		conn.Close()
		return fmt.Errorf("OBS handshake failed: %w", err)
	}

	c.mu.Lock()
	c.connected = true
	c.mu.Unlock()

	log.Printf("✅ Connected to OBS WebSocket")

	select {
	case c.StatusChanged <- "connected":
	default:
	}

	go c.readMessages()

	return nil
}

// handshake performs OBS WebSocket v5 protocol handshake
func (c *Client) handshake() error {
	// Read Hello (op=0)
	_, data, err := c.conn.ReadMessage()
	if err != nil {
		return fmt.Errorf("failed to read Hello: %w", err)
	}

	var hello obsMessage
	if err := json.Unmarshal(data, &hello); err != nil {
		return fmt.Errorf("failed to parse Hello: %w", err)
	}

	if hello.Op != 0 {
		return fmt.Errorf("expected Hello op=0, got op=%d", hello.Op)
	}

	// Build Identify (op=1)
	subs := c.config.EventSubscriptions
	if subs == 0 {
		subs = EventSubGeneral // OBS default
	}

	identify := map[string]interface{}{
		"rpcVersion":         1,
		"eventSubscriptions": subs,
	}

	if auth, ok := hello.Data["authentication"].(map[string]interface{}); ok {
		challenge, _ := auth["challenge"].(string)
		salt, _ := auth["salt"].(string)
		if challenge != "" && salt != "" {
			identify["authentication"] = c.buildAuthString(c.config.Password, salt, challenge)
		}
	}

	identifyMsg := obsMessage{Op: 1, Data: identify}
	identifyData, err := json.Marshal(identifyMsg)
	if err != nil {
		return fmt.Errorf("failed to marshal Identify: %w", err)
	}

	if err := c.conn.WriteMessage(websocket.TextMessage, identifyData); err != nil {
		return fmt.Errorf("failed to send Identify: %w", err)
	}

	// Read Identified (op=2)
	_, data, err = c.conn.ReadMessage()
	if err != nil {
		return fmt.Errorf("failed to read Identified: %w", err)
	}

	var identified obsMessage
	if err := json.Unmarshal(data, &identified); err != nil {
		return fmt.Errorf("failed to parse Identified: %w", err)
	}

	if identified.Op != 2 {
		return fmt.Errorf("expected Identified op=2, got op=%d (auth failed?)", identified.Op)
	}

	log.Printf("✅ OBS handshake complete (rpcVersion=%v)", identified.Data["negotiatedRpcVersion"])
	return nil
}

// buildAuthString builds OBS WebSocket v5 authentication string
func (c *Client) buildAuthString(password, salt, challenge string) string {
	h1 := sha256.Sum256([]byte(password + salt))
	secret := base64.StdEncoding.EncodeToString(h1[:])
	h2 := sha256.Sum256([]byte(secret + challenge))
	return base64.StdEncoding.EncodeToString(h2[:])
}

// readMessages reads and dispatches incoming OBS messages
func (c *Client) readMessages() {
	defer func() {
		c.mu.Lock()
		c.connected = false
		c.mu.Unlock()

		// Fail all pending requests
		c.pendingMu.Lock()
		for id, req := range c.pending {
			close(req.ch)
			delete(c.pending, id)
		}
		c.pendingMu.Unlock()

		select {
		case c.StatusChanged <- "disconnected":
		default:
		}

		if c.config.AutoReconnect {
			c.mu.Lock()
			reconnecting := c.reconnecting
			c.mu.Unlock()
			if !reconnecting {
				go c.reconnect()
			}
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
				log.Printf("❌ Error reading from OBS: %v", err)
				return
			}

			var msg obsMessage
			if err := json.Unmarshal(data, &msg); err != nil {
				log.Printf("⚠️  Failed to parse OBS message: %v", err)
				continue
			}

			switch msg.Op {
			case 5: // Event
				select {
				case c.Events <- msg.Data:
				default:
					log.Printf("⚠️  Events channel full, dropping OBS event")
				}

			case 7: // RequestResponse
				requestId, _ := msg.Data["requestId"].(string)
				if requestId == "" {
					continue
				}

				c.pendingMu.Lock()
				req, exists := c.pending[requestId]
				if exists {
					delete(c.pending, requestId)
				}
				c.pendingMu.Unlock()

				if exists {
					req.ch <- msg.Data
				}
			}
		}
	}
}

// SendRequest sends a request to OBS and waits for the response.
//
// requestType: OBS WebSocket request type (e.g. "SetInputMute", "GetSceneList")
// requestData: request fields, can be nil for requests without parameters
//
// Returns responseData on success, or error if OBS returns non-success status or times out.
func (c *Client) SendRequest(requestType string, requestData map[string]interface{}) (map[string]interface{}, error) {
	c.mu.RLock()
	conn := c.conn
	connected := c.connected
	c.mu.RUnlock()

	if !connected || conn == nil {
		return nil, fmt.Errorf("not connected to OBS")
	}

	requestId := uuid.New().String()

	// Register pending BEFORE sending to avoid race condition
	ch := make(chan map[string]interface{}, 1)
	c.pendingMu.Lock()
	c.pending[requestId] = &pendingRequest{ch: ch}
	c.pendingMu.Unlock()

	// Build op=6 Request
	payload := map[string]interface{}{
		"requestType": requestType,
		"requestId":   requestId,
	}
	if requestData != nil {
		payload["requestData"] = requestData
	}

	msg := obsMessage{Op: 6, Data: payload}
	data, err := json.Marshal(msg)
	if err != nil {
		c.pendingMu.Lock()
		delete(c.pending, requestId)
		c.pendingMu.Unlock()
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	c.writeMu.Lock()
	err = conn.WriteMessage(websocket.TextMessage, data)
	c.writeMu.Unlock()

	if err != nil {
		c.pendingMu.Lock()
		delete(c.pending, requestId)
		c.pendingMu.Unlock()
		return nil, fmt.Errorf("failed to send to OBS: %w", err)
	}

	// Wait for response
	timeout := time.Duration(c.config.ConnectionTimeoutMs) * time.Millisecond
	if timeout == 0 {
		timeout = 5 * time.Second
	}

	select {
	case response, ok := <-ch:
		if !ok {
			return nil, fmt.Errorf("connection closed while waiting for OBS response")
		}

		// Check OBS request status
		if status, ok := response["requestStatus"].(map[string]interface{}); ok {
			if result, _ := status["result"].(bool); !result {
				return nil, fmt.Errorf("OBS error: code=%v comment=%v", status["code"], status["comment"])
			}
		}

		// Return responseData if present, otherwise full response
		if responseData, ok := response["responseData"].(map[string]interface{}); ok {
			return responseData, nil
		}
		return response, nil

	case <-time.After(timeout):
		c.pendingMu.Lock()
		delete(c.pending, requestId)
		c.pendingMu.Unlock()
		return nil, fmt.Errorf("timeout waiting for OBS response to %s", requestType)
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

	select {
	case c.StatusChanged <- "reconnecting":
	default:
	}

	attempt := 0
	interval := time.Duration(c.config.ReconnectIntervalMs) * time.Millisecond
	if interval == 0 {
		interval = 3 * time.Second
	}

	for {
		select {
		case <-c.stopChan:
			return
		default:
			attempt++

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

// IsConnected returns true if connected and authenticated to OBS
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

	if c.conn != nil {
		c.conn.Close()
		c.conn = nil
	}
	c.connected = false

	log.Printf("🔌 Disconnected from OBS")
}
