package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"sync"

	"github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		return true // Accept all origins (local network only)
	},
}

// DiscoveryServer handles reverse discovery from HUB
type DiscoveryServer struct {
	Port         int
	HubIP        string
	HubPort      int
	HubURL       string
	mu           sync.RWMutex
	onDiscovered func(hubURL string)
	server       *http.Server
}

// NewDiscoveryServer creates discovery server
func NewDiscoveryServer(port int) *DiscoveryServer {
	return &DiscoveryServer{
		Port: port,
	}
}

// Start starts the discovery WebSocket server
func (ds *DiscoveryServer) Start(onDiscovered func(hubURL string)) error {
	ds.onDiscovered = onDiscovered

	mux := http.NewServeMux()
	mux.HandleFunc("/discovery", ds.handleDiscovery)

	addr := fmt.Sprintf(":%d", ds.Port)
	ds.server = &http.Server{
		Addr:    addr,
		Handler: mux,
	}

	log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Printf("🔍 Discovery server starting...")
	log.Printf("   Port: %d", ds.Port)
	log.Printf("   Endpoint: ws://0.0.0.0:%d/discovery", ds.Port)
	log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Printf("⏳ Waiting for HUB announcement...")
	log.Printf("   (HUB will connect to us when it starts)")
	log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	go func() {
		err := ds.server.ListenAndServe()
		if err != nil && err != http.ErrServerClosed {
			log.Printf("❌ Discovery server error: %v", err)
		}
	}()

	return nil
}

// handleDiscovery handles incoming HUB announcements
func (ds *DiscoveryServer) handleDiscovery(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("❌ WebSocket upgrade failed: %v", err)
		return
	}
	defer conn.Close()

	log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Printf("📞 Discovery connection received")
	log.Printf("   From: %s", r.RemoteAddr)
	log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	// Read announcement
	_, data, err := conn.ReadMessage()
	if err != nil {
		log.Printf("❌ Failed to read announcement: %v", err)
		return
	}

	var announcement map[string]interface{}
	if err := json.Unmarshal(data, &announcement); err != nil {
		log.Printf("❌ Failed to parse announcement: %v", err)
		return
	}

	log.Printf("📨 Received announcement:")
	announcementJSON, _ := json.MarshalIndent(announcement, "   ", "  ")
	log.Printf("   %s", string(announcementJSON))

	// Validate and extract HUB info
	if announcement["type"] == "hub_announce" {
		hubIP, ok1 := announcement["hub_ip"].(string)
		hubPort, ok2 := announcement["hub_port"].(float64)
		hubURL, ok3 := announcement["hub_url"].(string)

		if !ok1 || !ok2 || !ok3 {
			log.Printf("❌ Invalid announcement format")
			return
		}

		ds.mu.Lock()
		ds.HubIP = hubIP
		ds.HubPort = int(hubPort)
		ds.HubURL = hubURL
		ds.mu.Unlock()

		log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
		log.Printf("✅ HUB DISCOVERED!")
		log.Printf("   HUB IP:   %s", ds.HubIP)
		log.Printf("   HUB Port: %d", ds.HubPort)
		log.Printf("   HUB URL:  %s", ds.HubURL)
		log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

		// Send acknowledgment
		ack := map[string]interface{}{
			"type":      "ack",
			"status":    "discovered",
			"plugin_id": "recorder-plugin",
		}
		ackData, _ := json.Marshal(ack)
		conn.WriteMessage(websocket.TextMessage, ackData)

		log.Printf("📤 Acknowledgment sent to HUB")

		// Trigger callback
		if ds.onDiscovered != nil {
			log.Printf("🚀 Triggering connection to HUB...")
			go ds.onDiscovered(ds.HubURL)
		}
	} else {
		log.Printf("⚠️  Unknown message type: %v", announcement["type"])
	}
}

// GetHubURL returns discovered HUB URL (thread-safe)
func (ds *DiscoveryServer) GetHubURL() string {
	ds.mu.RLock()
	defer ds.mu.RUnlock()
	return ds.HubURL
}

// IsDiscovered returns true if HUB has been discovered
func (ds *DiscoveryServer) IsDiscovered() bool {
	ds.mu.RLock()
	defer ds.mu.RUnlock()
	return ds.HubURL != ""
}

// Stop stops the discovery server
func (ds *DiscoveryServer) Stop() error {
	if ds.server != nil {
		log.Println("⏹️  Stopping discovery server...")
		return ds.server.Close()
	}
	return nil
}
