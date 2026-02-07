package main

import (
	"encoding/json"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"
)

// Config structure
type Config struct {
	HubURL         string `json:"hub_url"`         // Fallback URL (optional)
	DiscoveryPort  int    `json:"discovery_port"`  // Port for reverse discovery
	DiscoveryRetry bool   `json:"discovery_retry"` // Retry discovery if fails
	PluginID       string `json:"plugin_id"`
	PluginName     string `json:"plugin_name"`
}

func main() {
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("📹 Camera Recorder Plugin")
	log.Println("   Version: 2.0.0")
	log.Println("   Mode: Reverse Discovery")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	// Load config
	config := loadConfig()

	// Start discovery server FIRST
	discoveryPort := config.DiscoveryPort
	if discoveryPort == 0 {
		discoveryPort = 9999 // Default
	}

	discoveryServer := NewDiscoveryServer(discoveryPort)

	var hubURL string
	discoveryDone := make(chan bool, 1)

	err := discoveryServer.Start(func(url string) {
		hubURL = url
		log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
		log.Printf("🎯 HUB URL RECEIVED: %s", hubURL)
		log.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
		discoveryDone <- true
	})

	if err != nil {
		log.Fatalf("❌ Failed to start discovery server: %v", err)
	}

	// Wait for discovery (with timeout)
	log.Println("")
	log.Println("⏳ Waiting for HUB announcement...")
	log.Println("   Timeout: 60 seconds")
	log.Println("")

	select {
	case <-discoveryDone:
		log.Println("✅ Discovery complete!")

	case <-time.After(60 * time.Second):
		log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
		log.Println("⚠️  No HUB announcement received after 60s")

		// Check if we have fallback URL in config
		if config.HubURL != "" {
			log.Printf("   Using fallback URL from config: %s", config.HubURL)
			hubURL = config.HubURL
		} else {
			log.Println("   No fallback URL configured")
			log.Println("   Will retry discovery every 30s...")
			log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

			// Keep running discovery server and retry periodically
			if config.DiscoveryRetry {
				go retryDiscovery(discoveryServer, &hubURL, discoveryDone)
			}
		}
	}

	// If we have HUB URL, connect
	if hubURL != "" {
		connectToHub(hubURL, config)
	} else {
		log.Println("⏳ Running in discovery-only mode...")
		log.Println("   Waiting for HUB to announce...")
	}

	// Wait for discovery callback if still waiting
	if hubURL == "" {
		<-discoveryDone
		if hubURL != "" {
			connectToHub(hubURL, config)
		}
	}

	// Handle graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	log.Println("")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("✅ Recorder Plugin is running")
	log.Println("   Press Ctrl+C to stop")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	<-sigChan

	log.Println("")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("⏹️  Shutting down...")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	discoveryServer.Stop()

	log.Println("✅ Recorder Plugin stopped")
}

func retryDiscovery(ds *DiscoveryServer, hubURL *string, done chan bool) {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		if ds.IsDiscovered() {
			*hubURL = ds.GetHubURL()
			log.Printf("✅ Discovery successful on retry: %s", *hubURL)
			done <- true
			return
		}
		log.Println("🔄 Still waiting for HUB announcement...")
	}
}

func connectToHub(hubURL string, config Config) {
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Printf("🔌 Connecting to HUB: %s", hubURL)
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	// ✅ POPRAWIONA KOLEJNOŚĆ!
	hubClient := NewHubClient(
		config.PluginID,   // ← pluginID (first param)
		config.PluginName, // ← pluginName (second param)
		hubURL,            // ← hubURL (third param)
	)

	err := hubClient.Connect()
	if err != nil {
		log.Fatalf("❌ Failed to connect to HUB: %v", err)
	}

	log.Println("✅ Connected to HUB!")

	log.Println("✅ HUB connection initialized")
	log.Printf("   Plugin ID:   %s", config.PluginID)
	log.Printf("   Plugin Name: %s", config.PluginName)
	log.Printf("   HUB URL:     %s", hubURL)
}

func loadConfig() Config {
	// Try to load config from file
	configPath := "config.json"
	if envPath := os.Getenv("CONFIG_PATH"); envPath != "" {
		configPath = envPath
	}

	data, err := os.ReadFile(configPath)
	if err != nil {
		log.Printf("⚠️  Config file not found: %s", configPath)
		log.Println("   Using default config")
		return Config{
			DiscoveryPort:  9999,
			DiscoveryRetry: true,
			PluginID:       "recorder-plugin",
			PluginName:     "Camera Recorder Plugin",
		}
	}

	var config Config
	if err := json.Unmarshal(data, &config); err != nil {
		log.Fatalf("❌ Failed to parse config: %v", err)
	}

	// Set defaults if not specified
	if config.DiscoveryPort == 0 {
		config.DiscoveryPort = 9999
	}
	if config.PluginID == "" {
		config.PluginID = "recorder-plugin"
	}
	if config.PluginName == "" {
		config.PluginName = "Camera Recorder Plugin"
	}

	log.Printf("✅ Config loaded from: %s", configPath)
	log.Printf("   Discovery Port: %d", config.DiscoveryPort)
	log.Printf("   Discovery Retry: %v", config.DiscoveryRetry)
	if config.HubURL != "" {
		log.Printf("   Fallback URL: %s", config.HubURL)
	}

	return config
}
