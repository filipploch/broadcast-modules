package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"

	timer "timer-plugin"
)

func main() {
	log.Println("🚀 Starting Timer Plugin...")

	// Parse command line flags
	configFile := flag.String("config", "config.json", "Path to configuration file")
	flag.Parse()

	// Load configuration
	config, err := loadConfig(*configFile)
	if err != nil {
		log.Fatalf("❌ Failed to load config: %v", err)
	}

	// Check for environment variable overrides
	if hubURL := os.Getenv("HUB_URL"); hubURL != "" {
		log.Printf("Using HUB_URL from environment: %s", hubURL)
		config.HubURL = hubURL
	} else if fallbackURL := os.Getenv("HUB_FALLBACK_URL"); fallbackURL != "" && config.HubURL == "" {
		log.Printf("Using HUB_FALLBACK_URL from environment: %s", fallbackURL)
		config.HubURL = fallbackURL
	}

	// Check for PLUGIN_ID override
	if pluginID := os.Getenv("PLUGIN_ID"); pluginID != "" {
		log.Printf("Using PLUGIN_ID from environment: %s", pluginID)
		config.PluginID = pluginID
	}

	log.Printf("Configuration loaded:")
	log.Printf("   Plugin ID:   %s", config.PluginID)
	log.Printf("   Plugin Name: %s", config.PluginName)
	log.Printf("   Hub URL:     %s", config.HubURL)

	// Create and start plugin
	plugin := timer.NewPlugin(config)

	if err := plugin.Start(); err != nil {
		log.Fatalf("❌ Failed to start plugin: %v", err)
	}

	// Setup graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, os.Interrupt, syscall.SIGTERM)

	log.Println("⏱️  Timer Plugin is running. Press Ctrl+C to stop.")

	// Wait for shutdown signal
	<-quit

	log.Println("🛑 Shutting down Timer Plugin...")
	if err := plugin.Stop(); err != nil {
		log.Printf("⚠️  Error during shutdown: %v", err)
	}

	log.Println("✅ Timer Plugin stopped successfully")
}

// loadConfig loads configuration from JSON file
func loadConfig(filename string) (timer.PluginConfig, error) {
	var config timer.PluginConfig

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
		config.PluginID = "timer-plugin"
	}
	if config.PluginName == "" {
		config.PluginName = "Timer Plugin"
	}
	if config.HubURL == "" {
		config.HubURL = "ws://broadcast-hub.local:8080/ws"
	}
	if config.UpdateInterval == 0 {
		config.UpdateInterval = 100 // 100ms default
	}
	if config.HeartbeatInterval == 0 {
		config.HeartbeatInterval = 5000 // 5s default
	}

	return config, nil
}
