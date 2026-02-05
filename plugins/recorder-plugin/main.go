package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gorilla/websocket"
)

// Message represents a message in the Hub system
type Message struct {
	From    string                 `json:"from"`
	To      string                 `json:"to"`
	Type    string                 `json:"type"`
	Payload map[string]interface{} `json:"payload"`
}

// RecorderPlugin represents the camera recorder plugin
type RecorderPlugin struct {
	PluginID          string
	HubURL            string
	LocalIP           string
	conn              *websocket.Conn
	send              chan *Message
	receive           chan *Message
	connected         bool
	running           bool
	heartbeatInterval time.Duration
	reconnectInterval time.Duration
	maxReconnects     int
}

// Config holds plugin configuration
type Config struct {
	PluginID          string `json:"plugin_id"`
	HubURL            string `json:"hub_url"`
	HeartbeatInterval int    `json:"heartbeat_interval_ms"`
	ReconnectInterval int    `json:"reconnect_interval_ms"`
	MaxReconnects     int    `json:"max_reconnects"`
}

// NewRecorderPlugin creates a new recorder plugin instance
func NewRecorderPlugin(config Config) *RecorderPlugin {
	return &RecorderPlugin{
		PluginID:          config.PluginID,
		HubURL:            config.HubURL,
		send:              make(chan *Message, 256),
		receive:           make(chan *Message, 256),
		heartbeatInterval: time.Duration(config.HeartbeatInterval) * time.Millisecond,
		reconnectInterval: time.Duration(config.ReconnectInterval) * time.Millisecond,
		maxReconnects:     config.MaxReconnects,
	}
}

// Start starts the plugin
func (r *RecorderPlugin) Start() error {
	log.Printf("🚀 Starting Recorder Plugin: %s", r.PluginID)

	// Get local IP
	localIP, err := getLocalIP()
	if err != nil {
		log.Printf("⚠️  Cannot determine local IP: %v", err)
		localIP = "unknown"
	}
	r.LocalIP = localIP
	log.Printf("📍 Local IP: %s", r.LocalIP)

	// Set running flag BEFORE connecting
	r.running = true

	// Try to connect to Hub (non-blocking)
	log.Printf("🔌 Attempting to connect to Hub: %s", r.HubURL)
	if err := r.connect(); err != nil {
		log.Printf("⚠️  Initial connection failed: %v", err)
		log.Printf("🔄 Will retry in background...")
		// Don't return error - let autoReconnect handle it
	} else {
		log.Printf("✅ Connected to Hub on first attempt")
	}

	// Start goroutines (these handle reconnection)
	go r.readPump()
	go r.writePump()
	go r.heartbeat()
	go r.handleMessages()
	go r.autoReconnect()

	log.Printf("✅ Recorder Plugin started successfully")
	log.Printf("   (will connect to Hub when available)")
	return nil
}

// Stop stops the plugin
func (r *RecorderPlugin) Stop() error {
	log.Printf("⏹️  Stopping Recorder Plugin...")

	r.running = false

	if r.conn != nil {
		// Send disconnect message
		r.sendMessage(&Message{
			From: r.PluginID,
			To:   "hub",
			Type: "disconnect",
			Payload: map[string]interface{}{
				"plugin_id": r.PluginID,
			},
		})

		time.Sleep(100 * time.Millisecond) // Give time to send
		r.conn.Close()
	}

	log.Printf("✅ Recorder Plugin stopped")
	return nil
}

// connect establishes connection to the Hub
func (r *RecorderPlugin) connect() error {
	log.Printf("🔌 Connecting to Hub: %s", r.HubURL)

	conn, _, err := websocket.DefaultDialer.Dial(r.HubURL, nil)
	if err != nil {
		return fmt.Errorf("dial error: %w", err)
	}

	r.conn = conn
	r.connected = true

	log.Printf("✅ Connected to Hub")

	// Register with Hub
	r.register()

	return nil
}

// register registers the plugin with the Hub
func (r *RecorderPlugin) register() {
	log.Printf("📝 Registering with Hub...")

	r.sendMessage(&Message{
		From: r.PluginID,
		To:   "hub",
		Type: "register",
		Payload: map[string]interface{}{
			"plugin_id": r.PluginID,
			"ip":        r.LocalIP,
		},
	})
}

// heartbeat sends periodic heartbeat to Hub
func (r *RecorderPlugin) heartbeat() {
	ticker := time.NewTicker(r.heartbeatInterval)
	defer ticker.Stop()

	for r.running {
		<-ticker.C

		if !r.connected {
			continue
		}

		r.sendMessage(&Message{
			From: r.PluginID,
			To:   "hub",
			Type: "heartbeat",
			Payload: map[string]interface{}{
				"plugin_id": r.PluginID,
				"timestamp": time.Now().Unix(),
			},
		})

		// log.Printf("💓 Heartbeat sent")
	}
}

// autoReconnect automatically reconnects on connection loss
func (r *RecorderPlugin) autoReconnect() {
	reconnectCount := 0
	backoff := r.reconnectInterval

	for r.running {
		time.Sleep(backoff)

		if r.connected {
			reconnectCount = 0
			backoff = r.reconnectInterval
			continue
		}

		if r.maxReconnects > 0 && reconnectCount >= r.maxReconnects {
			log.Printf("❌ Max reconnection attempts reached")
			r.running = false
			return
		}

		reconnectCount++
		log.Printf("🔄 Reconnecting to Hub (attempt %d)...", reconnectCount)

		if err := r.connect(); err != nil {
			log.Printf("⚠️  Reconnection failed: %v", err)
			backoff = min(backoff*2, 30*time.Second)
		} else {
			log.Printf("✅ Reconnected successfully")
			reconnectCount = 0
			backoff = r.reconnectInterval
		}
	}
}

// handleMessages handles incoming messages from Hub
func (r *RecorderPlugin) handleMessages() {
	for r.running {
		select {
		case msg := <-r.receive:
			if msg == nil {
				continue
			}

			log.Printf("📨 Received: %s from %s", msg.Type, msg.From)

			switch msg.Type {
			case "registered":
				log.Printf("✅ Plugin registered with Hub")

			case "ping":
				r.handlePing(msg)

			case "start_recording":
				r.handleStartRecording(msg)

			case "stop_recording":
				r.handleStopRecording(msg)

			case "get_status":
				r.handleGetStatus(msg)

			default:
				log.Printf("⚠️  Unknown message type: %s", msg.Type)
			}

		case <-time.After(100 * time.Millisecond):
			// Timeout, continue loop
		}
	}
}

// handlePing handles ping from Hub
func (r *RecorderPlugin) handlePing(msg *Message) {
	r.sendMessage(&Message{
		From: r.PluginID,
		To:   "hub",
		Type: "pong",
		Payload: map[string]interface{}{
			"plugin_id": r.PluginID,
			"timestamp": time.Now().Unix(),
		},
	})
	log.Printf("🏓 Pong sent in response to ping")
}

// handleStartRecording handles start recording command
func (r *RecorderPlugin) handleStartRecording(msg *Message) {
	log.Printf("🎥 Starting recording...")

	// TODO: Implement actual recording logic
	// For now, just acknowledge

	r.sendMessage(&Message{
		From: r.PluginID,
		To:   msg.From,
		Type: "recording_started",
		Payload: map[string]interface{}{
			"plugin_id": r.PluginID,
			"timestamp": time.Now().Unix(),
			"status":    "recording",
		},
	})

	log.Printf("✅ Recording started")
}

// handleStopRecording handles stop recording command
func (r *RecorderPlugin) handleStopRecording(msg *Message) {
	log.Printf("⏹️  Stopping recording...")

	// TODO: Implement actual recording stop logic

	r.sendMessage(&Message{
		From: r.PluginID,
		To:   msg.From,
		Type: "recording_stopped",
		Payload: map[string]interface{}{
			"plugin_id": r.PluginID,
			"timestamp": time.Now().Unix(),
			"status":    "idle",
		},
	})

	log.Printf("✅ Recording stopped")
}

// handleGetStatus handles status request
func (r *RecorderPlugin) handleGetStatus(msg *Message) {
	r.sendMessage(&Message{
		From: r.PluginID,
		To:   msg.From,
		Type: "status_response",
		Payload: map[string]interface{}{
			"plugin_id": r.PluginID,
			"status":    "idle", // TODO: Get actual status
			"ip":        r.LocalIP,
			"timestamp": time.Now().Unix(),
		},
	})
}

// sendMessage sends a message to Hub
func (r *RecorderPlugin) sendMessage(msg *Message) {
	if !r.connected {
		return
	}

	select {
	case r.send <- msg:
	default:
		log.Printf("⚠️  Send buffer full, message dropped")
	}
}

// readPump reads messages from WebSocket
func (r *RecorderPlugin) readPump() {
	defer func() {
		r.connected = false
		if r.conn != nil {
			r.conn.Close()
		}
		log.Printf("❌ Connection closed (read)")
	}()

	for r.running {
		if r.conn == nil {
			time.Sleep(100 * time.Millisecond)
			continue
		}

		_, data, err := r.conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				log.Printf("⚠️  WebSocket read error: %v", err)
			}
			r.connected = false
			return
		}

		var msg Message
		if err := json.Unmarshal(data, &msg); err != nil {
			log.Printf("⚠️  Invalid message format: %v", err)
			continue
		}

		r.receive <- &msg
	}
}

// writePump writes messages to WebSocket
func (r *RecorderPlugin) writePump() {
	ticker := time.NewTicker(54 * time.Second)
	defer func() {
		ticker.Stop()
		if r.conn != nil {
			r.conn.Close()
		}
		log.Printf("❌ Connection closed (write)")
	}()

	for r.running {
		if r.conn == nil {
			time.Sleep(100 * time.Millisecond)
			continue
		}

		select {
		case msg, ok := <-r.send:
			if !ok {
				r.conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}

			data, err := json.Marshal(msg)
			if err != nil {
				log.Printf("⚠️  Error marshaling message: %v", err)
				continue
			}

			r.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := r.conn.WriteMessage(websocket.TextMessage, data); err != nil {
				log.Printf("⚠️  WebSocket write error: %v", err)
				r.connected = false
				return
			}

		case <-ticker.C:
			r.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := r.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				log.Printf("⚠️  Ping error: %v", err)
				r.connected = false
				return
			}
		}
	}
}

// getLocalIP returns the local IP address
func getLocalIP() (string, error) {
	addrs, err := net.InterfaceAddrs()
	if err != nil {
		return "", err
	}

	for _, addr := range addrs {
		if ipnet, ok := addr.(*net.IPNet); ok && !ipnet.IP.IsLoopback() {
			if ipnet.IP.To4() != nil {
				return ipnet.IP.String(), nil
			}
		}
	}

	return "", fmt.Errorf("no non-loopback IP found")
}

func min(a, b time.Duration) time.Duration {
	if a < b {
		return a
	}
	return b
}

// loadConfig loads configuration from file
func loadConfig(filename string) (Config, error) {
	var config Config

	file, err := os.Open(filename)
	if err != nil {
		return config, fmt.Errorf("failed to open config file: %w", err)
	}
	defer file.Close()

	decoder := json.NewDecoder(file)
	if err := decoder.Decode(&config); err != nil {
		return config, fmt.Errorf("failed to decode config: %w", err)
	}

	// Set defaults
	if config.PluginID == "" {
		config.PluginID = "recorder-plugin"
	}
	if config.HubURL == "" {
		config.HubURL = "ws://broadcast-hub.local:8080/ws"
	}
	if config.HeartbeatInterval == 0 {
		config.HeartbeatInterval = 5000 // 5s
	}
	if config.ReconnectInterval == 0 {
		config.ReconnectInterval = 5000 // 5s
	}
	if config.MaxReconnects == 0 {
		config.MaxReconnects = 0 // Infinite
	}

	return config, nil
}

func main() {
	log.Println("🎥 Starting Camera Recorder Plugin...")

	// Parse command line flags
	configFile := flag.String("config", "config.json", "Path to configuration file")
	flag.Parse()

	// Load configuration
	config, err := loadConfig(*configFile)
	if err != nil {
		log.Printf("⚠️  Failed to load config: %v", err)
		log.Printf("Using defaults...")
		config = Config{
			PluginID:          "recorder-plugin",
			HubURL:            "ws://broadcast-hub.local:8080/ws",
			HeartbeatInterval: 5000,
			ReconnectInterval: 5000,
			MaxReconnects:     0,
		}
	}

	// Environment variable overrides
	if hubURL := os.Getenv("HUB_URL"); hubURL != "" {
		log.Printf("Using HUB_URL from environment: %s", hubURL)
		config.HubURL = hubURL
	}

	if pluginID := os.Getenv("PLUGIN_ID"); pluginID != "" {
		log.Printf("Using PLUGIN_ID from environment: %s", pluginID)
		config.PluginID = pluginID
	}

	log.Printf("Configuration:")
	log.Printf("   Plugin ID: %s", config.PluginID)
	log.Printf("   Hub URL:   %s", config.HubURL)

	// Create and start plugin
	plugin := NewRecorderPlugin(config)

	if err := plugin.Start(); err != nil {
		log.Fatalf("❌ Failed to start plugin: %v", err)
	}

	// Setup graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, os.Interrupt, syscall.SIGTERM)

	log.Println("⏱️  Recorder Plugin is running. Press Ctrl+C to stop.")
	log.Println("   Ready to receive commands from Hub")

	// Wait for shutdown signal
	<-quit

	log.Println("🛑 Shutting down Recorder Plugin...")
	if err := plugin.Stop(); err != nil {
		log.Printf("⚠️  Error during shutdown: %v", err)
	}

	log.Println("✅ Recorder Plugin stopped successfully")
}
