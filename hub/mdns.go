package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"time"

	"github.com/grandcat/zeroconf"
)

// MDNSService represents the mDNS/Bonjour service for the hub
type MDNSService struct {
	serviceName string
	port        int
	server      *zeroconf.Server
	hostname    string
}

// NewMDNSService creates a new mDNS service
func NewMDNSService(port int) *MDNSService {
	return &MDNSService{
		serviceName: "broadcast-hub",
		port:        port,
	}
}

// Start registers the hub with mDNS/Bonjour
func (m *MDNSService) Start() error {
	// Get local IP addresses
	ips, err := getLocalIPs()
	if err != nil {
		return fmt.Errorf("failed to get local IPs: %w", err)
	}

	if len(ips) == 0 {
		return fmt.Errorf("no local IP addresses found")
	}

	log.Printf("🔍 Starting mDNS service with IPs: %v", ips)

	// Convert []net.IP to []string for RegisterProxy
	ipStrings := make([]string, len(ips))
	for i, ip := range ips {
		ipStrings[i] = ip.String()
	}

	// Register the service with FORCED hostname
	// This will make it available as:
	// - broadcast-hub.local (A record) ← FORCED!
	// - _broadcast-hub._tcp.local (SRV record)
	server, err := zeroconf.RegisterProxy(
		m.serviceName,         // Instance name: "broadcast-hub"
		"_broadcast-hub._tcp", // Service type
		"local.",              // Domain
		m.port,                // Port
		m.serviceName,         // Host: "broadcast-hub" ← FORCED HOSTNAME!
		ipStrings,             // IPs as strings
		[]string{ // TXT records (metadata)
			"version=2.1",
			"type=hub",
			"protocol=websocket",
			"path=/ws",
		},
		nil, // Use all network interfaces
	)

	if err != nil {
		return fmt.Errorf("failed to register mDNS service: %w", err)
	}

	m.server = server

	log.Printf("✅ mDNS/Bonjour service registered:")
	log.Printf("   📍 Hostname: %s.local", m.serviceName)
	log.Printf("   🔌 Service: _broadcast-hub._tcp.local")
	log.Printf("   🌐 Port: %d", m.port)
	log.Printf("   📡 IPs: %v", ips)
	log.Printf("")
	log.Printf("   🚀 Access via:")
	log.Printf("      • ws://%s.local:%d/ws", m.serviceName, m.port)
	log.Printf("      • ws://%s:%d/ws (direct IP)", ips[0], m.port)
	log.Printf("")
	log.Printf("   💡 Test resolution:")
	log.Printf("      Windows: ping %s.local", m.serviceName)
	log.Printf("      Linux:   ping %s.local", m.serviceName)
	log.Printf("      macOS:   ping %s.local", m.serviceName)

	return nil
}

// Stop shuts down the mDNS service
func (m *MDNSService) Stop() {
	if m.server != nil {
		log.Println("⏹️  Stopping mDNS service...")
		m.server.Shutdown()
		m.server = nil
		log.Println("✅ mDNS service stopped")
	}
}

// GetServiceURL returns the WebSocket URL for this service
func (m *MDNSService) GetServiceURL() string {
	return fmt.Sprintf("ws://%s.local:%d/ws", m.serviceName, m.port)
}

// GetServiceName returns the mDNS service name
func (m *MDNSService) GetServiceName() string {
	return fmt.Sprintf("%s.local", m.serviceName)
}

// getLocalIPs returns all local non-loopback IP addresses
func getLocalIPs() ([]net.IP, error) {
	var ips []net.IP

	interfaces, err := net.Interfaces()
	if err != nil {
		return nil, err
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

			// Only add IPv4 addresses (mDNS works better with IPv4)
			if ip != nil && ip.To4() != nil && !ip.IsLoopback() {
				ips = append(ips, ip)
			}
		}
	}

	return ips, nil
}

// DiscoverHub discovers broadcast-hub services on the network
// This is useful for clients to find the hub
func DiscoverHub(timeout time.Duration) ([]string, error) {
	resolver, err := zeroconf.NewResolver(nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create resolver: %w", err)
	}

	entries := make(chan *zeroconf.ServiceEntry)
	var urls []string

	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	// Collect results
	go func() {
		for entry := range entries {
			for _, ipv4 := range entry.AddrIPv4 {
				url := fmt.Sprintf("ws://%s:%d/ws", ipv4.String(), entry.Port)
				urls = append(urls, url)
				log.Printf("🔍 Discovered hub: %s (at %s)", entry.Instance, url)
			}
		}
	}()

	// Start discovery
	err = resolver.Browse(ctx, "_broadcast-hub._tcp", "local.", entries)
	if err != nil {
		return nil, fmt.Errorf("browse failed: %w", err)
	}

	<-ctx.Done()

	return urls, nil
}

// DiscoverHubByName discovers hub by exact name (e.g., "broadcast-hub")
func DiscoverHubByName(name string, timeout time.Duration) (string, error) {
	resolver, err := zeroconf.NewResolver(nil)
	if err != nil {
		return "", fmt.Errorf("failed to create resolver: %w", err)
	}

	entries := make(chan *zeroconf.ServiceEntry)
	var foundURL string

	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	// Collect results
	go func() {
		for entry := range entries {
			if entry.Instance == name || entry.HostName == name+".local." {
				if len(entry.AddrIPv4) > 0 {
					foundURL = fmt.Sprintf("ws://%s:%d/ws", entry.AddrIPv4[0].String(), entry.Port)
					log.Printf("🔍 Found hub '%s' at %s", name, foundURL)
					cancel() // Found it, stop searching
					return
				}
			}
		}
	}()

	// Start discovery
	err = resolver.Browse(ctx, "_broadcast-hub._tcp", "local.", entries)
	if err != nil {
		return "", fmt.Errorf("browse failed: %w", err)
	}

	<-ctx.Done()

	if foundURL == "" {
		return "", fmt.Errorf("hub '%s' not found on network", name)
	}

	return foundURL, nil
}

// TestMDNSResolution tests if mDNS hostname resolution works
func TestMDNSResolution(hostname string) error {
	log.Printf("🧪 Testing mDNS resolution for: %s", hostname)

	// Try to resolve the hostname
	ips, err := net.LookupHost(hostname)
	if err != nil {
		return fmt.Errorf("DNS lookup failed: %w", err)
	}

	if len(ips) == 0 {
		return fmt.Errorf("no IPs found for %s", hostname)
	}

	log.Printf("✅ Resolution successful: %s → %v", hostname, ips)
	return nil
}
