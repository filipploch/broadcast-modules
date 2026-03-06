package main

import (
	"encoding/json"
	"log"
	"os"
	"os/signal"
	"syscall"
)

// Config holds full plugin configuration loaded from config.json.
type Config struct {
	// Hub / discovery
	HubURL         string `json:"hub_url"`        // fallback URL (optional)
	DiscoveryPort  int    `json:"discovery_port"` // port for reverse discovery
	DiscoveryRetry bool   `json:"discovery_retry"`
	PluginID       string `json:"plugin_id"`
	PluginName     string `json:"plugin_name"`

	// Recording
	OutputDir string         `json:"output_dir"` // e.g. /srv/samba/public/recorder
	Cameras   []CameraConfig `json:"cameras"`
}

func main() {
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("📹 Camera Recorder Plugin")
	log.Println("   Version: 2.0.0")
	log.Println("   Mode: Reverse Discovery")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	config := loadConfig()

	// Build recorder manager — owns all CameraRecorders
	recorder := NewRecorderManager(config)

	// Discovery
	discoveryPort := config.DiscoveryPort
	if discoveryPort == 0 {
		discoveryPort = 9999
	}

	discoveryServer := NewDiscoveryServer(discoveryPort)

	err := discoveryServer.Start(func(hubURL string) {
		log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
		log.Printf("🎯 HUB URL RECEIVED: %s", hubURL)
		log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
		go connectToHub(hubURL, config, discoveryServer, recorder)
	})

	if err != nil {
		log.Fatalf("❌ Failed to start discovery server: %v", err)
	}

	log.Println("")
	log.Println("⏳ Waiting for HUB announcement...")
	log.Println("   (HUB will connect to us when it starts)")
	log.Println("")

	// Graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("✅ Recorder Plugin is running")
	log.Println("   Press Ctrl+C to stop")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	<-sigChan

	log.Println("")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("⏹️  Shutting down...")

	recorder.StopAll()
	discoveryServer.Stop()

	log.Println("✅ Recorder Plugin stopped")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
}

// connectToHub establishes and maintains the WebSocket connection to the hub.
// Blocks until the connection is lost (Messages channel is drained), then
// resets the discovery server so a new hub_announce can trigger reconnection.
func connectToHub(hubURL string, config Config, ds *DiscoveryServer, recorder *RecorderManager) {
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Printf("🔌 Connecting to HUB: %s", hubURL)
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	hubClient := NewHubClient(config.PluginID, config.PluginName, hubURL)

	if err := hubClient.Connect(); err != nil {
		log.Printf("❌ Failed to connect to HUB: %v", err)
		ds.Reset()
		return
	}

	log.Println("✅ Connected to HUB!")
	log.Printf("   Plugin ID:   %s", config.PluginID)
	log.Printf("   Plugin Name: %s", config.PluginName)
	log.Printf("   HUB URL:     %s", hubURL)

	// Udostępnij hubClient recorderowi — od teraz będzie wysyłał notyfikacje do main_module
	recorder.SetHubClient(hubClient)
	defer recorder.SetHubClient(nil)

	// Process incoming messages.
	// hubClient.reconnectEnabled = true, więc po zerwaniu połączenia readMessages()
	// uruchomi go reconnect() wewnętrznie — Messages nigdy nie jest zamykany.
	// Pętla kończy się dopiero gdy wywołamy hubClient.Close() (stopChan).
	for {
		select {
		case msg, ok := <-hubClient.Receive():
			if !ok {
				// kanał zamknięty — Close() został wywołany
				log.Println("⚠️  HUB Messages channel closed")
				ds.Reset()
				return
			}
			handleMessage(msg, hubClient, recorder)

		case <-hubClient.Done():
			// Close() wywołany z zewnątrz (np. Ctrl+C)
			log.Println("⏹️  HUB client stopped")
			ds.Reset()
			return
		}
	}
}

// handleMessage routes a single message from the hub.
func handleMessage(msg *Message, hubClient *HubClient, recorder *RecorderManager) {
	switch msg.Type {
	case "registered":
		log.Printf("✅ Registered in HUB as: %s", msg.To)
		if err := recorder.hubClient.Subscribe("recorder_device"); err != nil {
			log.Printf("⚠️  Failed to subscribe to recorder_device: %v", err)
		} else {
			log.Printf("✅ Subscribed to class: recorder_device")
		}
		_ = recorder.hubClient.Send(&Message{
			To:   "main_module",
			Type: "recording_status_response",
			Payload: map[string]interface{}{
				"cameras": recorder.Status(),
			},
		})

	case "heartbeat_ack":
		// nothing to do

	case "start_recording", "stop_recording", "stop_all", "recording_status":
		recorder.HandleHubMessage(msg, hubClient)

	case "recording_command":
		recorder.handleRecordingCommand(msg, hubClient)

	default:
		log.Printf("📨 Unhandled message type: %s (from: %s)", msg.Type, msg.From)
	}
}

// loadConfig reads and validates config.json.
func loadConfig() Config {
	configPath := "config.json"
	if envPath := os.Getenv("CONFIG_PATH"); envPath != "" {
		configPath = envPath
	}

	data, err := os.ReadFile(configPath)
	if err != nil {
		log.Printf("⚠️  Config file not found: %s — using defaults", configPath)
		return defaultConfig()
	}

	var config Config
	if err := json.Unmarshal(data, &config); err != nil {
		log.Fatalf("❌ Failed to parse config: %v", err)
	}

	applyDefaults(&config)

	log.Printf("✅ Config loaded from: %s", configPath)
	log.Printf("   Discovery Port: %d", config.DiscoveryPort)
	log.Printf("   Output Dir:     %s", config.OutputDir)
	log.Printf("   Cameras:        %d configured", len(config.Cameras))
	if config.HubURL != "" {
		log.Printf("   Fallback URL:   %s", config.HubURL)
	}

	return config
}

func defaultConfig() Config {
	return Config{
		PluginID:       "recorder-plugin",
		PluginName:     "Camera Recorder Plugin",
		DiscoveryPort:  9999,
		DiscoveryRetry: true,
		OutputDir:      "/srv/samba/public/recorder",
		Cameras: []CameraConfig{
			{ID: "camera1", DeviceName: "camera1", ServiceName: "recorder-camera1.service", Enabled: true},
			{ID: "camera2", DeviceName: "camera2", ServiceName: "recorder-camera2.service", Enabled: true},
			{ID: "camera3", DeviceName: "camera3", ServiceName: "recorder-camera3.service", Enabled: true},
			{ID: "camera4", DeviceName: "camera4", ServiceName: "recorder-camera4.service", Enabled: true},
		},
	}
}

func applyDefaults(c *Config) {
	if c.DiscoveryPort == 0 {
		c.DiscoveryPort = 9999
	}
	if c.PluginID == "" {
		c.PluginID = "recorder-plugin"
	}
	if c.PluginName == "" {
		c.PluginName = "Camera Recorder Plugin"
	}
	if c.OutputDir == "" {
		c.OutputDir = "/srv/samba/public/recorder"
	}
}
