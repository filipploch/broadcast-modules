package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net"
	"time"

	"github.com/gorilla/websocket"
)

// ReverseDiscoveryConfig for external plugins
type ReverseDiscoveryConfig struct {
	Hostname string
	Port     int
	PluginID string
}

// AnnounceToPlugin announces HUB IP to external plugin using reverse discovery
func (h *Hub) AnnounceToPlugin(config ReverseDiscoveryConfig) error {
	log.Printf("🔍 Reverse discovery: Announcing to %s (%s:%d)",
		config.PluginID, config.Hostname, config.Port)

	// Resolve hostname
	ips, err := net.LookupHost(config.Hostname)
	if err != nil {
		return fmt.Errorf("failed to resolve %s: %w", config.Hostname, err)
	}

	if len(ips) == 0 {
		return fmt.Errorf("no IPs found for %s", config.Hostname)
	}

	// Filter for IPv4 only (ignore IPv6)
	var pluginIP string
	for _, ip := range ips {
		// Parse IP to check if it's IPv4
		parsedIP := net.ParseIP(ip)
		if parsedIP != nil && parsedIP.To4() != nil {
			// This is IPv4
			pluginIP = ip
			break
		}
	}

	if pluginIP == "" {
		return fmt.Errorf("no IPv4 address found for %s (only IPv6)", config.Hostname)
	}

	log.Printf("   ✅ Resolved %s → %s (IPv4)", config.Hostname, pluginIP)

	// Get HUB's own IP
	hubIP, err := getHubIP()
	if err != nil {
		return fmt.Errorf("failed to get HUB IP: %w", err)
	}

	log.Printf("   📍 HUB IP: %s", hubIP)

	// Connect to plugin's discovery WebSocket
	url := fmt.Sprintf("ws://%s:%d/discovery", pluginIP, config.Port)
	log.Printf("   🔌 Connecting to: %s", url)

	dialer := websocket.Dialer{
		HandshakeTimeout: 5 * time.Second,
	}

	conn, _, err := dialer.Dial(url, nil)
	if err != nil {
		return fmt.Errorf("failed to connect to plugin: %w", err)
	}
	defer conn.Close()

	// Send announcement
	announcement := map[string]interface{}{
		"type":      "hub_announce",
		"hub_id":    "broadcast-hub",
		"hub_ip":    hubIP,
		"hub_port":  h.Port,
		"hub_url":   fmt.Sprintf("ws://%s:%d/ws", hubIP, h.Port),
		"timestamp": time.Now().Unix(),
	}

	data, _ := json.Marshal(announcement)

	err = conn.WriteMessage(websocket.TextMessage, data)
	if err != nil {
		return fmt.Errorf("failed to send announcement: %w", err)
	}

	log.Printf("   📤 Announcement sent to %s", config.PluginID)

	// Wait for acknowledgment (optional, timeout 2s)
	conn.SetReadDeadline(time.Now().Add(2 * time.Second))
	_, ackData, err := conn.ReadMessage()
	if err == nil {
		var ack map[string]interface{}
		json.Unmarshal(ackData, &ack)
		log.Printf("   ✅ Plugin acknowledged: %v", ack)
	} else {
		log.Printf("   ⚠️  No acknowledgment received (timeout)")
	}

	return nil
}

// getHubIP returns HUB's local IP address
func getHubIP() (string, error) {
	var ips []net.IP

	interfaces, err := net.Interfaces()
	if err != nil {
		return "", err
	}

	for _, iface := range interfaces {
		// Skip loopback and down interfaces
		if iface.Flags&net.FlagLoopback != 0 || iface.Flags&net.FlagUp == 0 {
			continue
		}

		addrs, err := iface.Addrs()
		if err != nil {
			continue
		}

		for _, addr := range addrs {
			var ip net.IP
			switch v := addr.(type) {
			case *net.IPNet:
				ip = v.IP
			case *net.IPAddr:
				ip = v.IP
			}

			// Only IPv4, non-loopback
			if ip != nil && ip.To4() != nil && !ip.IsLoopback() {
				ips = append(ips, ip)
			}
		}
	}

	if len(ips) == 0 {
		return "", fmt.Errorf("no local IPs found")
	}

	return ips[0].String(), nil
}

// StartReverseDiscovery starts reverse discovery for all configured external plugins
func (h *Hub) StartReverseDiscovery() {
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("🔍 Starting reverse discovery for external plugins...")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	if h.PluginManager == nil {
		log.Println("⚠️  PluginManager not initialized, skipping reverse discovery")
		return
	}

	foundPlugins := 0
	configs := h.PluginManager.GetAllConfigs()

	// Read all plugin configs
	for pluginID, config := range configs {
		// Skip if not external plugin
		if config.Type != "external" {
			continue
		}

		// Check if reverse discovery is configured
		if config.DiscoveryMode == "reverse" && config.DiscoveryHostname != "" {
			foundPlugins++
			log.Printf("   📋 Found: %s (hostname: %s, port: %d)",
				pluginID, config.DiscoveryHostname, config.DiscoveryPort)

			// Start announcement in goroutine (non-blocking)
			go func(id string, cfg PluginConfig) {
				// Wait a bit for plugin to be ready
				time.Sleep(2 * time.Second)

				err := h.AnnounceToPlugin(ReverseDiscoveryConfig{
					Hostname: cfg.DiscoveryHostname,
					Port:     cfg.DiscoveryPort,
					PluginID: id,
				})

				if err != nil {
					log.Printf("❌ Reverse discovery failed for %s: %v", id, err)
					log.Printf("   Plugin will need to connect manually or retry")
				} else {
					log.Printf("✅ Reverse discovery complete for %s", id)
				}
			}(pluginID, config)
		}
	}

	if foundPlugins == 0 {
		log.Println("   ℹ️  No plugins configured for reverse discovery")
	} else {
		log.Printf("   🚀 Starting discovery for %d plugin(s)", foundPlugins)
	}

	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
}
