package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"obs-ws-plugin/internal/hub"
	"obs-ws-plugin/internal/obs"
)

// Config represents the plugin configuration
type Config struct {
	Plugin struct {
		ID      string `json:"id"`
		Name    string `json:"name"`
		Version string `json:"version"`
	} `json:"plugin"`
	OBS     obs.Config `json:"obs"`
	Logging struct {
		Level string `json:"level"`
	} `json:"logging"`
}

// Plugin represents the OBS WebSocket plugin
type Plugin struct {
	config    *Config
	hubClient *hub.HubClient
	obsClient *obs.Client
}

func main() {
	log.SetFlags(log.Ldate | log.Ltime | log.Lmicroseconds)
	log.Println("🎬 OBS WebSocket Plugin starting...")

	// Load configuration
	config, err := loadConfig()
	if err != nil {
		log.Fatalf("❌ Failed to load config: %v", err)
	}

	// Override from environment variables if set
	if pluginID := os.Getenv("PLUGIN_ID"); pluginID != "" {
		config.Plugin.ID = pluginID
	}

	hubURL := os.Getenv("HUB_URL")
	if hubURL == "" {
		hubURL = "ws://localhost:8080/ws"
	}

	// Create plugin instance
	plugin := &Plugin{
		config:    config,
		hubClient: hub.NewHubClient(hubURL, config.Plugin.ID, config.Plugin.Name),
		obsClient: obs.NewClient(&config.OBS),
	}

	// Connect to HUB
	if err := plugin.hubClient.Connect(); err != nil {
		log.Fatalf("❌ Failed to connect to HUB: %v", err)
	}

	// Connect to OBS
	if err := plugin.obsClient.Connect(); err != nil {
		log.Printf("⚠️  Failed to connect to OBS: %v", err)
		log.Printf("    Will retry automatically...")
	}

	// Start message routing
	go plugin.routeHubToOBS()
	go plugin.routeOBSToHub()
	go plugin.monitorOBSStatus()

	log.Println("✅ OBS WebSocket Plugin is running")
	log.Printf("   Plugin ID: %s", config.Plugin.ID)
	log.Printf("   HUB: %s", hubURL)
	log.Printf("   OBS: %s:%d", config.OBS.Host, config.OBS.Port)

	// Wait for shutdown signal
	waitForShutdown(plugin)
}

// loadConfig loads configuration from file
func loadConfig() (*Config, error) {
	data, err := os.ReadFile("config.json")
	if err != nil {
		return nil, fmt.Errorf("failed to read config.json: %w", err)
	}

	var config Config
	if err := json.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse config.json: %w", err)
	}

	return &config, nil
}

// routeHubToOBS routes messages from HUB to OBS
func (p *Plugin) routeHubToOBS() {
	log.Println("🔀 Starting Hub → OBS routing")

	for msg := range p.hubClient.Messages {
		// Only forward obs_command messages
		if msg.Type != "obs_command" {
			continue
		}

		log.Printf("📨 Hub → OBS: %s", msg.Type)

		// Check if OBS is connected
		if !p.obsClient.IsConnected() {
			log.Printf("⚠️  OBS not connected, cannot forward command")
			
			// Send error back to sender
			p.hubClient.Send(&hub.Message{
				From: p.config.Plugin.ID,
				To:   msg.From,
				Type: "obs_error",
				Payload: map[string]interface{}{
					"error":   "OBS not connected",
					"command": msg.Payload,
				},
			})
			continue
		}

		// Forward raw payload to OBS (transparent proxy)
		if err := p.obsClient.SendRaw(msg.Payload); err != nil {
			log.Printf("❌ Failed to send to OBS: %v", err)
			
			// Send error back to sender
			p.hubClient.Send(&hub.Message{
				From: p.config.Plugin.ID,
				To:   msg.From,
				Type: "obs_error",
				Payload: map[string]interface{}{
					"error":   err.Error(),
					"command": msg.Payload,
				},
			})
		}
	}
}

// routeOBSToHub routes events from OBS to HUB
func (p *Plugin) routeOBSToHub() {
	log.Println("🔀 Starting OBS → Hub routing")

	for event := range p.obsClient.Events {
		log.Printf("📨 OBS → Hub: event received")

		// Convert event to map for JSON serialization
		eventData := make(map[string]interface{})
		
		// Marshal and unmarshal to convert to map
		data, err := json.Marshal(event)
		if err != nil {
			log.Printf("⚠️  Failed to marshal OBS event: %v", err)
			continue
		}

		if err := json.Unmarshal(data, &eventData); err != nil {
			log.Printf("⚠️  Failed to unmarshal OBS event: %v", err)
			continue
		}

		// Broadcast to all modules via HUB (transparent proxy)
		p.hubClient.Send(&hub.Message{
			From: p.config.Plugin.ID,
			To:   "broadcast",
			Type: "obs_event",
			Payload: eventData,
		})
	}
}

// monitorOBSStatus monitors OBS connection status and notifies HUB
func (p *Plugin) monitorOBSStatus() {
	log.Println("📡 Starting OBS status monitor")

	for status := range p.obsClient.StatusChanged {
		log.Printf("📊 OBS Status changed: %s", status)

		// Notify HUB about OBS status change
		p.hubClient.Send(&hub.Message{
			From: p.config.Plugin.ID,
			To:   "broadcast",
			Type: "obs_status",
			Payload: map[string]interface{}{
				"status":    status,
				"obs_host":  fmt.Sprintf("%s:%d", p.config.OBS.Host, p.config.OBS.Port),
				"timestamp": time.Now().Unix(),
			},
		})
	}
}

// waitForShutdown waits for shutdown signal and cleanup
func waitForShutdown(plugin *Plugin) {
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	<-sigChan

	log.Println("🛑 Shutdown signal received, cleaning up...")

	// Close connections
	plugin.obsClient.Close()
	plugin.hubClient.Close()

	log.Println("👋 OBS WebSocket Plugin stopped")
	os.Exit(0)
}
