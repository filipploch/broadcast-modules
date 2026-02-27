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

	config, err := loadConfig()
	if err != nil {
		log.Fatalf("❌ Failed to load config: %v", err)
	}

	if pluginID := os.Getenv("PLUGIN_ID"); pluginID != "" {
		config.Plugin.ID = pluginID
	}

	hubURL := os.Getenv("HUB_URL")
	if hubURL == "" {
		hubURL = "ws://localhost:8080/ws"
	}

	plugin := &Plugin{
		config:    config,
		hubClient: hub.NewHubClient(hubURL, config.Plugin.ID, config.Plugin.Name),
		obsClient: obs.NewClient(&config.OBS),
	}

	if err := plugin.hubClient.Connect(); err != nil {
		log.Fatalf("❌ Failed to connect to HUB: %v", err)
	}

	if err := plugin.obsClient.Connect(); err != nil {
		log.Printf("⚠️  Failed to connect to OBS: %v", err)
		log.Printf("    Will retry automatically...")
	}

	go plugin.routeHubToOBS()
	go plugin.routeOBSToHub()
	go plugin.monitorOBSStatus()

	log.Println("✅ OBS WebSocket Plugin is running")
	log.Printf("   Plugin ID: %s", config.Plugin.ID)
	log.Printf("   HUB: %s", hubURL)
	log.Printf("   OBS: %s:%d", config.OBS.Host, config.OBS.Port)

	waitForShutdown(plugin)
}

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

// routeHubToOBS routes obs_command messages from HUB to OBS and sends response back
func (p *Plugin) routeHubToOBS() {
	log.Println("🔀 Starting Hub → OBS routing")

	for msg := range p.hubClient.Messages {
		if msg.Type != "obs_command" {
			continue
		}

		log.Printf("📨 Hub → OBS: %s from %s", msg.Type, msg.From)

		if !p.obsClient.IsConnected() {
			log.Printf("⚠️  OBS not connected, cannot forward command")
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

		// Extract requestType and requestData from payload
		requestType, ok := msg.Payload["requestType"].(string)
		if !ok || requestType == "" {
			log.Printf("⚠️  obs_command missing requestType")
			p.hubClient.Send(&hub.Message{
				From: p.config.Plugin.ID,
				To:   msg.From,
				Type: "obs_error",
				Payload: map[string]interface{}{
					"error": "obs_command payload must contain requestType",
				},
			})
			continue
		}

		var requestData map[string]interface{}
		if rd, ok := msg.Payload["requestData"].(map[string]interface{}); ok {
			requestData = rd
		}

		// Send to OBS and wait for response
		responseData, err := p.obsClient.SendRequest(requestType, requestData)
		if err != nil {
			log.Printf("❌ OBS request failed (%s): %v", requestType, err)
			p.hubClient.Send(&hub.Message{
				From: p.config.Plugin.ID,
				To:   msg.From,
				Type: "obs_error",
				Payload: map[string]interface{}{
					"error":       err.Error(),
					"requestType": requestType,
				},
			})
			continue
		}

		log.Printf("✅ OBS response received for %s", requestType)

		// Send response back to requester
		p.hubClient.Send(&hub.Message{
			From: p.config.Plugin.ID,
			To:   msg.From,
			Type: "obs_response",
			Payload: map[string]interface{}{
				"requestType":  requestType,
				"responseData": responseData,
			},
		})
	}
}

// routeOBSToHub broadcasts OBS events to all HUB subscribers
func (p *Plugin) routeOBSToHub() {
	log.Println("🔀 Starting OBS → Hub routing")

	for event := range p.obsClient.Events {
		log.Printf("📨 OBS → Hub: event received")

		p.hubClient.Send(&hub.Message{
			From:    p.config.Plugin.ID,
			To:      "broadcast:obs_messages_receiver",
			Type:    "obs_event",
			Payload: event,
		})
	}
}

// monitorOBSStatus monitors OBS connection status and notifies HUB
func (p *Plugin) monitorOBSStatus() {
	log.Println("📡 Starting OBS status monitor")

	for status := range p.obsClient.StatusChanged {
		log.Printf("📊 OBS Status changed: %s", status)

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

func waitForShutdown(plugin *Plugin) {
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	<-sigChan

	log.Println("🛑 Shutdown signal received, cleaning up...")

	plugin.obsClient.Close()
	plugin.hubClient.Close()

	log.Println("👋 OBS WebSocket Plugin stopped")
	os.Exit(0)
}
