package main

import (
	"log"
	"sync"
	"time"
)

// PluginHealth represents health status of a plugin
type PluginHealth struct {
	PluginID         string
	LastHeartbeat    time.Time
	HeartbeatCount   int
	IsHealthy        bool
	ConsecutiveFails int
	LastCheckTime    time.Time
}

// HealthMonitor monitors plugin health
type HealthMonitor struct {
	hub              *Hub
	pluginHealth     map[string]*PluginHealth
	checkInterval    time.Duration
	heartbeatTimeout time.Duration
	maxFailures      int
	mu               sync.RWMutex
	stopChan         chan struct{}
	running          bool
}

// NewHealthMonitor creates a new health monitor
func NewHealthMonitor(hub *Hub) *HealthMonitor {
	return &HealthMonitor{
		hub:              hub,
		pluginHealth:     make(map[string]*PluginHealth),
		checkInterval:    10 * time.Second, // Check every 10 seconds
		heartbeatTimeout: 30 * time.Second, // Timeout after 30 seconds
		maxFailures:      3,                // Max 3 consecutive failures
		stopChan:         make(chan struct{}),
		running:          false,
	}
}

// Start starts the health monitoring loop
func (hm *HealthMonitor) Start() {
	hm.mu.Lock()
	if hm.running {
		hm.mu.Unlock()
		return
	}
	hm.running = true
	hm.mu.Unlock()

	log.Println("🏥 HealthMonitor started")

	ticker := time.NewTicker(hm.checkInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			hm.checkAllPlugins()
			// ✅ NEW: Broadcast health status to main module
			hm.broadcastHealthStatus()

		case <-hm.stopChan:
			log.Println("🏥 HealthMonitor stopped")
			return
		}
	}
}

// Stop stops the health monitor
func (hm *HealthMonitor) Stop() {
	hm.mu.Lock()
	if !hm.running {
		hm.mu.Unlock()
		return
	}
	hm.running = false
	hm.mu.Unlock()

	close(hm.stopChan)
}

// RegisterPlugin registers a plugin for health monitoring
func (hm *HealthMonitor) RegisterPlugin(pluginID string) {
	hm.mu.Lock()
	defer hm.mu.Unlock()

	hm.pluginHealth[pluginID] = &PluginHealth{
		PluginID:      pluginID,
		LastHeartbeat: time.Now(),
		IsHealthy:     true,
		LastCheckTime: time.Now(),
	}

	log.Printf("🏥 Registered plugin for health monitoring: %s", pluginID)
}

// UnregisterPlugin unregisters a plugin from health monitoring
func (hm *HealthMonitor) UnregisterPlugin(pluginID string) {
	hm.mu.Lock()
	defer hm.mu.Unlock()

	delete(hm.pluginHealth, pluginID)
	log.Printf("🏥 Unregistered plugin from health monitoring: %s", pluginID)
}

// UpdateHeartbeat updates the last heartbeat time for a plugin
func (hm *HealthMonitor) UpdateHeartbeat(pluginID string) {
	hm.mu.Lock()
	defer hm.mu.Unlock()

	health, exists := hm.pluginHealth[pluginID]
	if !exists {
		// Auto-register if not exists
		health = &PluginHealth{
			PluginID:      pluginID,
			IsHealthy:     true,
			LastCheckTime: time.Now(),
		}
		hm.pluginHealth[pluginID] = health
	}

	health.LastHeartbeat = time.Now()
	health.HeartbeatCount++

	// Reset failure count if plugin is back online
	if !health.IsHealthy {
		health.IsHealthy = true
		health.ConsecutiveFails = 0
		log.Printf("✅ Plugin %s is healthy again", pluginID)
	}
}

// RecordHeartbeat is an alias for UpdateHeartbeat
func (hm *HealthMonitor) RecordHeartbeat(pluginID string) {
	hm.UpdateHeartbeat(pluginID)
}

// checkAllPlugins checks health of all registered plugins
func (hm *HealthMonitor) checkAllPlugins() {
	hm.mu.Lock()
	pluginIDs := make([]string, 0, len(hm.pluginHealth))
	for id := range hm.pluginHealth {
		pluginIDs = append(pluginIDs, id)
	}
	hm.mu.Unlock()

	for _, pluginID := range pluginIDs {
		hm.checkPluginHealth(pluginID)
	}
}

// checkPluginHealth checks health of a specific plugin
func (hm *HealthMonitor) checkPluginHealth(pluginID string) {
	hm.mu.Lock()
	health, exists := hm.pluginHealth[pluginID]
	if !exists {
		hm.mu.Unlock()
		return
	}

	health.LastCheckTime = time.Now()
	timeSinceHeartbeat := time.Since(health.LastHeartbeat)
	hm.mu.Unlock()

	// Check if plugin is still in hub
	hm.hub.mu.RLock()
	plugin, pluginExists := hm.hub.Plugins[pluginID]
	isActive := pluginExists && plugin.IsActive
	hm.hub.mu.RUnlock()

	// If plugin disconnected, no need to check heartbeat
	if !isActive {
		return
	}

	// Check heartbeat timeout
	if timeSinceHeartbeat > hm.heartbeatTimeout {
		hm.mu.Lock()
		health.ConsecutiveFails++
		wasHealthy := health.IsHealthy
		health.IsHealthy = false
		hm.mu.Unlock()

		if wasHealthy {
			log.Printf("⚠️  Plugin %s heartbeat timeout (%.0fs since last heartbeat)",
				pluginID, timeSinceHeartbeat.Seconds())
		}

		// Take action if too many failures
		if health.ConsecutiveFails >= hm.maxFailures {
			log.Printf("❌ Plugin %s exceeded max failures (%d), taking action",
				pluginID, hm.maxFailures)
			hm.handleUnhealthyPlugin(pluginID)
		}
	}
}

// handleUnhealthyPlugin handles an unhealthy plugin
func (hm *HealthMonitor) handleUnhealthyPlugin(pluginID string) {
	log.Printf("🔧 Handling unhealthy plugin: %s", pluginID)

	// Check if plugin should be restarted
	hm.hub.mu.RLock()
	isExpected := hm.hub.ExpectedPlugins[pluginID]
	hm.hub.mu.RUnlock()

	if isExpected && hm.hub.PluginManager != nil {
		log.Printf("🔄 Restarting unhealthy plugin: %s", pluginID)

		go func(id string) {
			// Reset consecutive failures
			hm.mu.Lock()
			if health, exists := hm.pluginHealth[id]; exists {
				health.ConsecutiveFails = 0
			}
			hm.mu.Unlock()

			// Restart local plugin only
			if hm.hub.PluginManager.IsLocalPlugin(id) {
				log.Printf("🔄 Attempting to restart plugin: %s", id)
				if err := hm.hub.PluginManager.StopPlugin(id); err != nil {
					log.Printf("⚠️  Failed to stop plugin %s: %v", id, err)
				}
				time.Sleep(1 * time.Second)
				if err := hm.hub.PluginManager.StartPlugin(id); err != nil {
					log.Printf("❌ Failed to restart plugin %s: %v", id, err)
				}
			} else {
				log.Printf("⚠️  Cannot restart external plugin: %s", id)
			}
		}(pluginID)
	}
}

// GetPluginHealth returns health status of a plugin
func (hm *HealthMonitor) GetPluginHealth(pluginID string) *PluginHealth {
	hm.mu.RLock()
	defer hm.mu.RUnlock()

	health, exists := hm.pluginHealth[pluginID]
	if !exists {
		return nil
	}

	// Return a copy
	return &PluginHealth{
		PluginID:         health.PluginID,
		LastHeartbeat:    health.LastHeartbeat,
		HeartbeatCount:   health.HeartbeatCount,
		IsHealthy:        health.IsHealthy,
		ConsecutiveFails: health.ConsecutiveFails,
		LastCheckTime:    health.LastCheckTime,
	}
}

// GetAllHealth returns health status of all plugins
func (hm *HealthMonitor) GetAllHealth() map[string]interface{} {
	hm.mu.RLock()
	defer hm.mu.RUnlock()

	allHealth := make(map[string]interface{})

	for id, health := range hm.pluginHealth {
		allHealth[id] = map[string]interface{}{
			"plugin_id":               health.PluginID,
			"is_healthy":              health.IsHealthy,
			"heartbeat_count":         health.HeartbeatCount,
			"consecutive_fails":       health.ConsecutiveFails,
			"seconds_since_heartbeat": time.Since(health.LastHeartbeat).Seconds(),
			"last_check_time":         health.LastCheckTime.Format(time.RFC3339),
		}
	}

	return allHealth
}

// GetHealthSummary returns a summary of overall health
func (hm *HealthMonitor) GetHealthSummary() map[string]interface{} {
	hm.mu.RLock()
	defer hm.mu.RUnlock()

	total := len(hm.pluginHealth)
	healthy := 0
	unhealthy := 0

	for _, health := range hm.pluginHealth {
		if health.IsHealthy {
			healthy++
		} else {
			unhealthy++
		}
	}

	return map[string]interface{}{
		"total_plugins":             total,
		"healthy_plugins":           healthy,
		"unhealthy_plugins":         unhealthy,
		"check_interval_seconds":    hm.checkInterval.Seconds(),
		"heartbeat_timeout_seconds": hm.heartbeatTimeout.Seconds(),
	}
}

// ✅ NEW: broadcastHealthStatus sends health status to main module via WebSocket
func (hm *HealthMonitor) broadcastHealthStatus() {
	// Get current health data
	allHealth := hm.GetAllHealth()
	summary := hm.GetHealthSummary()

	// Get info about local plugins (from PluginManager)
	localPluginsStatus := make(map[string]interface{}) // ← Zmień nazwę
	if hm.hub.PluginManager != nil {
		for pluginID := range hm.hub.ExpectedPlugins {
			if status, err := hm.hub.PluginManager.GetPluginStatus(pluginID); err == nil {
				localPluginsStatus[pluginID] = status
			}
		}
	}

	// Get info about connected plugins (all - local and external)
	connectedPlugins := make(map[string]interface{})
	hm.hub.mu.RLock()
	for pluginID, plugin := range hm.hub.Plugins {
		connectedPlugins[pluginID] = map[string]interface{}{
			"plugin_id": plugin.ID,
			"name":      plugin.Name,
			"is_active": plugin.IsActive,
		}
	}
	hm.hub.mu.RUnlock()

	// Create message payload
	payload := map[string]interface{}{
		"health_summary":        summary,
		"plugin_health":         allHealth,
		"plugin_manager_status": localPluginsStatus,
		"connected_plugins":     connectedPlugins,
		"timestamp":             time.Now().Unix(),
	}

	// Send to main module if connected
	hm.hub.mu.RLock()
	mainModule := hm.hub.MainModule
	hm.hub.mu.RUnlock()

	if mainModule != nil && mainModule.IsActive {
		msg := &Message{
			From:    "hub",
			To:      mainModule.ID,
			Type:    "health_status",
			Payload: payload,
		}

		// Send message through hub's routing system
		select {
		case hm.hub.Route <- msg:
			// Message sent successfully
		default:
			log.Printf("⚠️  Failed to send health status: route channel full")
		}
	}
}

// SetCheckInterval sets the health check interval
func (hm *HealthMonitor) SetCheckInterval(interval time.Duration) {
	hm.mu.Lock()
	defer hm.mu.Unlock()

	hm.checkInterval = interval
	log.Printf("🏥 Health check interval set to: %v", interval)
}

// SetHeartbeatTimeout sets the heartbeat timeout
func (hm *HealthMonitor) SetHeartbeatTimeout(timeout time.Duration) {
	hm.mu.Lock()
	defer hm.mu.Unlock()

	hm.heartbeatTimeout = timeout
	log.Printf("🏥 Heartbeat timeout set to: %v", timeout)
}
