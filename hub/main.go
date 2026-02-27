package main

import (
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("🚀 BROADCAST HUB STARTING")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	// Configuration
	port := 8080
	enablePluginManager := true
	enableHealthMonitor := true

	// Create Hub
	hub := NewHub(port, enablePluginManager, enableHealthMonitor)

	// Load plugin configurations
	if hub.PluginManager != nil {
		if err := hub.PluginManager.LoadConfig(); err != nil {
			log.Fatalf("❌ Failed to load plugin config: %v", err)
		}

		// Auto-start local plugins
		configs := hub.PluginManager.GetAllConfigs()
		for id, config := range configs {
			if config.Type == "local" && config.AutoStart {
				go func(pluginID string) {
					log.Printf("🚀 Auto-starting local plugin: %s", pluginID)
					if err := hub.PluginManager.StartPlugin(pluginID); err != nil {
						log.Printf("❌ Failed to auto-start plugin %s: %v", pluginID, err)
					}
				}(id)
			}
		}
	}

	// Start hub event loop
	// Initialize FallbackWriter
	hub.FallbackWriter = NewFallbackWriter(hub, fallbackRules())
	log.Println("✅ FallbackWriter initialized")

	// Start hub event loop
	go hub.Run()

	// Setup HTTP server
	http.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		serveWs(hub, w, r)
	})

	http.HandleFunc("/status", func(w http.ResponseWriter, r *http.Request) {
		serveStatus(hub, w, r)
	})

	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		serveHealth(hub, w, r)
	})

	// Start HTTP server using setupHTTPServer
	log.Printf("🌐 Starting HTTP server on port %d", port)
	server := setupHTTPServer(hub)

	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("❌ HTTP server error: %v", err)
		}
	}()

	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("✅ HUB IS READY!")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Printf("   HTTP:      http://0.0.0.0:%d", port)
	log.Printf("   WebSocket: ws://0.0.0.0:%d/ws", port)
	log.Printf("   Status:    http://0.0.0.0:%d/status", port)
	log.Printf("   Health:    http://0.0.0.0:%d/health", port)
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("")
	log.Println("Features enabled:")
	log.Printf("   PluginManager:   %v", enablePluginManager)
	log.Printf("   HealthMonitor:   %v", enableHealthMonitor)
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	// Start reverse discovery for external plugins
	hub.StartReverseDiscovery()

	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	<-sigChan

	log.Println("")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("⏹️  Shutting down gracefully...")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	hub.Shutdown()

	log.Println("✅ Shutdown complete. Goodbye!")
}
