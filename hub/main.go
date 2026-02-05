package main

import (
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
)

func main() {
	// Command line flags
	host := flag.String("host", "0.0.0.0", "Host address")
	port := flag.String("port", "8080", "Port number")
	enableMDNS := flag.Bool("mdns", true, "Enable mDNS service discovery")
	enablePluginManager := flag.Bool("plugins", true, "Enable plugin manager")
	enableHealthMonitor := flag.Bool("health", true, "Enable health monitor")
	pluginConfigPath := flag.String("plugin-config", "config/plugins.json", "Path to plugin configuration")
	flag.Parse()

	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("🚀 BROADCAST HUB STARTING")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	// Create Hub with optional features
	hub := NewHub(*enablePluginManager, *enableHealthMonitor)
	
	// Load plugin configurations if plugin manager is enabled
	if hub.PluginManager != nil {
		hub.PluginManager.configPath = *pluginConfigPath
		if err := hub.PluginManager.LoadConfig(); err != nil {
			log.Printf("⚠️  Warning: Failed to load plugin config: %v", err)
		}
	}
	
	// Start Hub
	go hub.Run()

	// Setup HTTP handlers
	http.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		serveWs(hub, w, r)
	})
	http.HandleFunc("/", serveHome)
	http.HandleFunc("/status", func(w http.ResponseWriter, r *http.Request) {
		serveStatus(hub, w, r)
	})
	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		serveHealth(hub, w, r)
	})

	// Start HTTP server
	addr := *host + ":" + *port
	log.Printf("🌐 Starting HTTP server on %s", addr)
	
	go func() {
		if err := http.ListenAndServe(addr, nil); err != nil {
			log.Fatal("❌ ListenAndServe error:", err)
		}
	}()

	// Start mDNS service if enabled
	if *enableMDNS {
		portNum, err := strconv.Atoi(*port)
		if err != nil {
			log.Printf("⚠️  Warning: Invalid port number for mDNS: %v", err)
		} else {
			mdnsService := NewMDNSService(portNum)
			if err := mdnsService.Start(); err != nil {
				log.Printf("⚠️  Warning: Failed to start mDNS: %v", err)
				log.Printf("   Hub will still be accessible via %s", addr)
			} else {
				hub.MDNSService = mdnsService
			}
		}
	}

	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("✅ HUB IS READY!")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Printf("   HTTP:      http://%s", addr)
	log.Printf("   WebSocket: ws://%s/ws", addr)
	log.Printf("   Status:    http://%s/status", addr)
	log.Printf("   Health:    http://%s/health", addr)
	if hub.MDNSService != nil {
		log.Printf("   mDNS:      ws://broadcast-hub.local:%s/ws", *port)
	}
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("")
	log.Println("Features enabled:")
	log.Printf("   PluginManager:   %v", *enablePluginManager)
	log.Printf("   HealthMonitor:   %v", *enableHealthMonitor)
	log.Printf("   mDNS Discovery:  %v", *enableMDNS)
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	// Wait for interrupt signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	
	log.Println("")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("🛑 SHUTDOWN SIGNAL RECEIVED")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	
	// Graceful shutdown
	hub.Shutdown()
	
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("✅ HUB STOPPED GRACEFULLY")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
}
