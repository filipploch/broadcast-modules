package main

import (
	"log"
	"strings"
	"sync"
	"time"
)

// ExternalPlugin represents an external plugin (not managed by PluginManager)
type ExternalPlugin struct {
	PluginID      string
	IP            string
	Module        *Module // Reference to connected module
	Status        string  // "connected" | "disconnected"
	LastHeartbeat time.Time
	ConnectedAt   time.Time
	mu            sync.RWMutex
}

// Hub is the central message router and plugin manager
type Hub struct {
	MainModule      *Module
	Plugins         map[string]*Module
	ExpectedPlugins map[string]bool

	// ✅ NEW: External Plugins Registry
	ExternalPlugins map[string]*ExternalPlugin

	// ✅ Track all connected modules before registration
	PendingModules map[*Module]bool

	Register   chan *Module
	Unregister chan *Module
	Route      chan *Message

	PluginManager *PluginManager
	HealthMonitor *HealthMonitor
	MDNSService   *MDNSService

	mu       sync.RWMutex
	shutdown chan struct{}

	// ✅ NEW: External plugin monitoring config
	heartbeatTimeout  time.Duration
	heartbeatInterval time.Duration
	pingInterval      time.Duration
}

// NewHub creates a new Hub instance
func NewHub(enablePluginManager bool, enableHealthMonitor bool) *Hub {
	hub := &Hub{
		Plugins:           make(map[string]*Module),
		ExpectedPlugins:   make(map[string]bool),
		ExternalPlugins:   make(map[string]*ExternalPlugin), // ✅ NEW
		PendingModules:    make(map[*Module]bool),
		Register:          make(chan *Module),
		Unregister:        make(chan *Module),
		Route:             make(chan *Message, 256),
		shutdown:          make(chan struct{}),
		heartbeatTimeout:  15 * time.Second, // ✅ NEW
		heartbeatInterval: 5 * time.Second,  // ✅ NEW
		pingInterval:      10 * time.Second, // ✅ NEW
	}

	// Initialize PluginManager if enabled
	if enablePluginManager {
		hub.PluginManager = NewPluginManager(hub)
		log.Println("✅ PluginManager initialized")
	}

	// Initialize HealthMonitor if enabled
	if enableHealthMonitor {
		hub.HealthMonitor = NewHealthMonitor(hub)
		log.Println("✅ HealthMonitor initialized")
	}

	return hub
}

// Run starts the hub's main event loop
func (h *Hub) Run() {
	log.Println("🚀 Hub is running...")

	// Start health monitoring if available
	if h.HealthMonitor != nil {
		go h.HealthMonitor.Start()
	}

	// ✅ NEW: Start external plugin monitor
	go h.monitorExternalPlugins()

	for {
		select {
		case module := <-h.Register:
			// ✅ Track module as pending until registered
			h.mu.Lock()
			h.PendingModules[module] = true
			h.mu.Unlock()

			go module.ReadPump()
			go module.WritePump()

		case module := <-h.Unregister:
			h.handleUnregister(module)

		case message := <-h.Route:
			h.handleMessage(message)

		case <-h.shutdown:
			log.Println("🛑 Hub shutdown")
			return
		}
	}
}

// handleMessage routes messages based on type
func (h *Hub) handleMessage(msg *Message) {
	// ✅ DEBUG: Log incoming messages for troubleshooting
	if msg.Type == "register" || msg.Type == "heartbeat" {
		log.Printf("📬 Incoming: type=%s from=%s", msg.Type, msg.From)
	}

	switch msg.Type {
	case "register":
		h.handleRegister(msg)
	case "register_external_plugin": // ✅ NEW
		h.handleExternalPluginRegister(msg)
	case "declare_required_plugins":
		h.handleDeclareRequiredPlugins(msg)
	case "heartbeat":
		h.handleHeartbeat(msg)
	case "external_plugin_heartbeat": // ✅ NEW
		h.handleExternalPluginHeartbeat(msg)
	case "get_external_plugin_status": // ✅ NEW
		h.handleGetExternalPluginStatus(msg)
	case "identify_main_module": // ✅ NEW
		h.handleIdentifyMainModule(msg)
	case "subscribe":
		h.handleSubscribe(msg)
	case "unsubscribe":
		h.handleUnsubscribe(msg)
	default:
		h.routeMessage(msg)
	}
}

// ✅ MODIFIED: handleRegister - supports both standard and external plugin registration
func (h *Hub) handleRegister(msg *Message) {
	// Extract registration data
	id, _ := msg.Payload["id"].(string)
	name, _ := msg.Payload["name"].(string)
	moduleType, _ := msg.Payload["type"].(string)
	host, _ := msg.Payload["host"].(string)
	port, _ := msg.Payload["port"].(string)
	componentType, _ := msg.Payload["component_type"].(string)

	// ✅ NEW: Check if this is an external plugin (uses "plugin_id" instead of "id")
	pluginID, hasPluginID := msg.Payload["plugin_id"].(string)

	if hasPluginID && id == "" {
		// This is an external plugin registration
		log.Printf("📝 External plugin registration detected: %s (from: %s)", pluginID, msg.From)
		h.handleExternalPluginRegister(msg)
		return
	}

	// ✅ DEBUG: Log standard registration
	log.Printf("📝 Standard registration: id=%s, component_type=%s", id, componentType)

	// ✅ Find the pending module that sent this message
	h.mu.Lock()
	var module *Module
	for m := range h.PendingModules {
		if m.ID == "" || m.ID == id {
			// This is the module sending registration
			module = m
			delete(h.PendingModules, m)
			break
		}
	}
	h.mu.Unlock()

	if module == nil {
		log.Printf("⚠️  Cannot find pending module for registration: %s", id)
		return
	}

	// Update module info
	module.ID = id
	module.Name = name
	module.Type = moduleType
	module.Host = host
	module.Port = port
	module.IsActive = true

	// Handle based on component type
	if componentType == "main_module" {
		h.handleMainModuleRegister(module)
	} else {
		h.handlePluginRegister(module)
	}
}

// ✅ NEW: handleExternalPluginRegister handles external plugin registration
func (h *Hub) handleExternalPluginRegister(msg *Message) {
	pluginID, ok := msg.Payload["plugin_id"].(string)
	if !ok {
		log.Printf("⚠️  External plugin registration missing plugin_id")
		return
	}

	ip, _ := msg.Payload["ip"].(string)

	log.Printf("🔍 handleExternalPluginRegister: plugin_id=%s, ip=%s, from=%s", pluginID, ip, msg.From)

	// Find the module that sent this message
	h.mu.Lock()
	log.Printf("🔍 Searching for module: PendingModules=%d, Plugins=%d",
		len(h.PendingModules), len(h.Plugins))

	var module *Module
	for m := range h.PendingModules {
		log.Printf("🔍 PendingModule: ID='%s', checking against from='%s'", m.ID, msg.From)
		if m.ID == "" || m.ID == msg.From {
			module = m
			delete(h.PendingModules, m)
			log.Printf("✅ Found in PendingModules")
			break
		}
	}

	if module == nil {
		log.Printf("🔍 Not found in PendingModules, searching Plugins...")
		// Try to find in existing connections
		for _, plugin := range h.Plugins {
			if plugin.ID == msg.From {
				module = plugin
				log.Printf("✅ Found in Plugins")
				break
			}
		}
	}

	if module == nil {
		log.Printf("❌ Cannot find module for external plugin: %s (from: %s)", pluginID, msg.From)
		log.Printf("   PendingModules count: %d", len(h.PendingModules))
		log.Printf("   Plugins count: %d", len(h.Plugins))
		h.mu.Unlock()
		return
	}

	log.Printf("✅ Module found, updating info...")

	// Update module info
	module.ID = pluginID
	module.Name = pluginID
	module.ComponentType = "external_plugin"
	module.IsActive = true

	// Create or update external plugin entry
	extPlugin, exists := h.ExternalPlugins[pluginID]
	if !exists {
		extPlugin = &ExternalPlugin{
			PluginID:    pluginID,
			IP:          ip,
			Module:      module,
			Status:      "connected",
			ConnectedAt: time.Now(),
		}
		h.ExternalPlugins[pluginID] = extPlugin
		log.Printf("🔌 External plugin registered: %s (IP: %s)", pluginID, ip)
	} else {
		extPlugin.mu.Lock()
		extPlugin.Status = "connected"
		extPlugin.ConnectedAt = time.Now()
		extPlugin.IP = ip
		extPlugin.Module = module
		extPlugin.mu.Unlock()
		log.Printf("🔄 External plugin reconnected: %s (IP: %s)", pluginID, ip)
	}

	// Add to Plugins map for routing
	h.Plugins[pluginID] = module

	h.mu.Unlock()

	// Update last heartbeat
	extPlugin.mu.Lock()
	extPlugin.LastHeartbeat = time.Now()
	extPlugin.mu.Unlock()

	// Send registered confirmation
	confirmMsg := NewMessage("hub", pluginID, "registered", map[string]interface{}{
		"plugin_id": pluginID,
		"status":    "connected",
	})
	if data, err := confirmMsg.ToJSON(); err == nil {
		module.Send <- data
	}

	// Notify main module
	h.notifyMainModuleExternalPluginStatus(extPlugin)
}

// ✅ NEW: handleExternalPluginHeartbeat handles heartbeat from external plugin
func (h *Hub) handleExternalPluginHeartbeat(msg *Message) {
	pluginID, ok := msg.Payload["plugin_id"].(string)
	if !ok {
		log.Printf("⚠️  External plugin heartbeat missing plugin_id")
		return
	}

	h.mu.RLock()
	extPlugin, exists := h.ExternalPlugins[pluginID]
	h.mu.RUnlock()

	if !exists {
		log.Printf("⚠️  Heartbeat from unknown external plugin: %s", pluginID)
		return
	}

	extPlugin.mu.Lock()
	wasDisconnected := extPlugin.Status != "connected"
	extPlugin.LastHeartbeat = time.Now()
	extPlugin.Status = "connected"
	extPlugin.mu.Unlock()

	if wasDisconnected {
		log.Printf("💚 External plugin back online: %s", pluginID)
		h.notifyMainModuleExternalPluginStatus(extPlugin)
	}
}

// ✅ NEW: handleGetExternalPluginStatus handles status query
func (h *Hub) handleGetExternalPluginStatus(msg *Message) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	plugins := make([]map[string]interface{}, 0, len(h.ExternalPlugins))
	for _, extPlugin := range h.ExternalPlugins {
		extPlugin.mu.RLock()
		uptime := time.Since(extPlugin.ConnectedAt).Seconds()
		pluginInfo := map[string]interface{}{
			"plugin_id":      extPlugin.PluginID,
			"status":         extPlugin.Status,
			"last_heartbeat": extPlugin.LastHeartbeat.Unix(),
			"uptime":         uptime,
			"metadata": map[string]interface{}{
				"ip": extPlugin.IP,
			},
		}
		extPlugin.mu.RUnlock()
		plugins = append(plugins, pluginInfo)
	}

	// Send response
	responseMsg := NewMessage("hub", msg.From, "external_plugin_status_response", map[string]interface{}{
		"plugins": plugins,
	})

	h.mu.RLock()
	var destination *Module
	if h.MainModule != nil && h.MainModule.ID == msg.From {
		destination = h.MainModule
	} else if plugin, ok := h.Plugins[msg.From]; ok {
		destination = plugin
	}
	h.mu.RUnlock()

	if destination != nil && destination.IsActive {
		if data, err := responseMsg.ToJSON(); err == nil {
			destination.Send <- data
		}
	}
}

// ✅ NEW: handleIdentifyMainModule identifies the main module
func (h *Hub) handleIdentifyMainModule(msg *Message) {
	h.mu.Lock()

	// Find the module
	var module *Module
	if h.MainModule != nil && h.MainModule.ID == msg.From {
		module = h.MainModule
	}
	h.mu.Unlock()

	if module != nil {
		log.Printf("🎯 Main module identified: %s", msg.From)

		// Send confirmation
		confirmMsg := NewMessage("hub", msg.From, "main_module_identified", map[string]interface{}{
			"status": "success",
		})
		if data, err := confirmMsg.ToJSON(); err == nil {
			module.Send <- data
		}

		// Send current status of all external plugins
		h.handleGetExternalPluginStatus(&Message{
			From: "hub",
			To:   msg.From,
			Type: "get_external_plugin_status",
		})
	}
}

// ✅ NEW: monitorExternalPlugins monitors external plugins for timeout
func (h *Hub) monitorExternalPlugins() {
	ticker := time.NewTicker(h.pingInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			h.mu.RLock()
			for _, extPlugin := range h.ExternalPlugins {
				extPlugin.mu.RLock()
				timeSinceHeartbeat := time.Since(extPlugin.LastHeartbeat)
				currentStatus := extPlugin.Status
				module := extPlugin.Module
				pluginID := extPlugin.PluginID
				extPlugin.mu.RUnlock()

				// Check if heartbeat timeout exceeded
				if timeSinceHeartbeat > h.heartbeatTimeout {
					if currentStatus == "connected" {
						extPlugin.mu.Lock()
						extPlugin.Status = "disconnected"
						extPlugin.mu.Unlock()

						log.Printf("⏱️  External plugin heartbeat timeout: %s (%.1fs)", pluginID, timeSinceHeartbeat.Seconds())
						h.notifyMainModuleExternalPluginStatus(extPlugin)
					}
				} else if currentStatus == "connected" && module != nil && module.IsActive {
					// Send ping if approaching timeout
					if timeSinceHeartbeat > h.heartbeatInterval*2 {
						pingMsg := NewMessage("hub", pluginID, "ping", map[string]interface{}{
							"timestamp": time.Now().Unix(),
						})
						if data, err := pingMsg.ToJSON(); err == nil {
							select {
							case module.Send <- data:
								log.Printf("🔔 Sent ping to external plugin: %s", pluginID)
							default:
								// Send buffer full
							}
						}
					}
				}
			}
			h.mu.RUnlock()

		case <-h.shutdown:
			return
		}
	}
}

// ✅ NEW: notifyMainModuleExternalPluginStatus notifies main module about external plugin status
func (h *Hub) notifyMainModuleExternalPluginStatus(extPlugin *ExternalPlugin) {
	h.mu.RLock()
	mainModule := h.MainModule
	h.mu.RUnlock()

	if mainModule == nil || !mainModule.IsActive {
		return
	}

	extPlugin.mu.RLock()
	uptime := time.Since(extPlugin.ConnectedAt).Seconds()
	statusMsg := NewMessage("hub", mainModule.ID, "external_plugin_status_update", map[string]interface{}{
		"plugin_id":      extPlugin.PluginID,
		"status":         extPlugin.Status,
		"last_heartbeat": extPlugin.LastHeartbeat.Unix(),
		"uptime":         uptime,
		"metadata": map[string]interface{}{
			"ip": extPlugin.IP,
		},
	})
	extPlugin.mu.RUnlock()

	if data, err := statusMsg.ToJSON(); err == nil {
		select {
		case mainModule.Send <- data:
			log.Printf("📤 Notified main module: %s status = %s", extPlugin.PluginID, extPlugin.Status)
		default:
			log.Printf("⚠️  Cannot notify main module (send buffer full)")
		}
	}
}

// handleMainModuleRegister registers a main module
func (h *Hub) handleMainModuleRegister(module *Module) {
	h.mu.Lock()

	// Check if another main module is active
	if h.MainModule != nil && h.MainModule != module {
		h.mu.Unlock()
		log.Printf("❌ ERROR: Main module already active: %s", h.MainModule.ID)

		errorMsg := NewMessage("hub", module.ID, "error", map[string]interface{}{
			"code":          "main_module_already_active",
			"message":       "Another main module is running",
			"active_module": h.MainModule.ID,
		})
		if data, err := errorMsg.ToJSON(); err == nil {
			module.Send <- data
		}
		module.Connection.Close()
		return
	}

	h.MainModule = module
	module.ComponentType = "main_module"
	h.mu.Unlock()

	log.Printf("✅ Main module registered: %s (%s)", module.ID, module.Name)

	// Send confirmation
	confirmMsg := NewMessage("hub", module.ID, "registered", map[string]interface{}{
		"status":      "main_module_active",
		"hub_version": "2.1.0", // ✅ Updated version
	})
	if data, err := confirmMsg.ToJSON(); err == nil {
		module.Send <- data
	}

	// Notify existing plugins
	h.mu.RLock()
	for _, plugin := range h.Plugins {
		if plugin.IsActive && plugin != module {
			h.notifyPluginOnline(plugin)
		}
	}
	h.mu.RUnlock()
}

// handlePluginRegister registers a plugin
func (h *Hub) handlePluginRegister(plugin *Module) {
	h.mu.Lock()

	// ✅ Add to Plugins map
	h.Plugins[plugin.ID] = plugin
	plugin.ComponentType = "plugin"
	isExpected := h.ExpectedPlugins[plugin.ID]

	h.mu.Unlock()

	log.Printf("✅ Plugin registered: %s (%s)", plugin.ID, plugin.Name)

	// ✅ Update PluginManager status to "online"
	if h.PluginManager != nil {
		h.PluginManager.mu.Lock()
		if pluginProc, exists := h.PluginManager.plugins[plugin.ID]; exists {
			pluginProc.Status = "connected"
			log.Printf("🟢 Plugin %s status: online", plugin.ID)
		}
		h.PluginManager.mu.Unlock()
	}

	// Send confirmation to plugin
	confirmMsg := NewMessage("hub", plugin.ID, "registered", map[string]interface{}{
		"status": "plugin_active",
	})
	if data, err := confirmMsg.ToJSON(); err == nil {
		plugin.Send <- data
	}

	// Notify main module if plugin was expected
	if isExpected && h.MainModule != nil && h.MainModule.IsActive {
		log.Printf("🔗 Matching plugin %s to main module", plugin.ID)
		h.notifyPluginOnline(plugin)
	}

	// Update health monitor
	if h.HealthMonitor != nil {
		h.HealthMonitor.RegisterPlugin(plugin.ID)
	}
}

// handleDeclareRequiredPlugins processes plugin requirements from main module
func (h *Hub) handleDeclareRequiredPlugins(msg *Message) {
	h.mu.Lock()
	defer h.mu.Unlock()

	// Oczekujemy teraz listy ID ([]string) zamiast pełnych obiektów pluginów
	pluginIDs, ok := msg.Payload["plugins"].([]interface{})
	if !ok {
		log.Printf("⚠️ Invalid plugins payload - expected list of plugin IDs")
		return
	}

	log.Printf("📋 Main module declared %d required plugins", len(pluginIDs))

	// Clear expected plugins
	h.ExpectedPlugins = make(map[string]bool)

	// Process each plugin ID
	for _, p := range pluginIDs {
		// Teraz p powinien być bezpośrednio ID (string), a nie mapą
		id, ok := p.(string)
		if !ok || id == "" {
			log.Printf("⚠️ Skipping invalid plugin ID: %v", p)
			continue
		}

		h.ExpectedPlugins[id] = true
		log.Printf("   Expected: %s", id)

		// Check if plugin is already connected
		if existingPlugin, exists := h.Plugins[id]; exists && existingPlugin.IsActive {
			h.notifyPluginOnline(existingPlugin)
		} else {
			// Plugin not connected, try to start it via PluginManager (only for local plugins)
			if h.PluginManager != nil {
				// Check if this is a local plugin that PluginManager can start
				h.PluginManager.mu.RLock()
				pluginProc, isManaged := h.PluginManager.plugins[id]
				h.PluginManager.mu.RUnlock()
				log.Println(pluginProc)
				if isManaged {
					// This is a local plugin managed by PluginManager
					go func(pluginID string) {
						log.Printf("🚀 Starting required local plugin: %s", pluginID)
						if err := h.PluginManager.StartPlugin(pluginID); err != nil {
							log.Printf("❌ Failed to start plugin %s: %v", pluginID, err)
						}
					}(id)
				} else {
					// This is an external plugin - just wait for it to connect
					log.Printf("⏳ Waiting for external plugin to connect: %s", id)
				}
			}
		}
	}
}

// handleHeartbeat processes heartbeat messages
func (h *Hub) handleHeartbeat(msg *Message) {
	h.mu.RLock()

	var module *Module
	if h.MainModule != nil && h.MainModule.ID == msg.From {
		module = h.MainModule
	} else if plugin, ok := h.Plugins[msg.From]; ok {
		module = plugin
	}

	// ✅ NEW: Check if this is an external plugin heartbeat
	if module != nil && module.ComponentType == "external_plugin" {
		// Handle external plugin heartbeat
		if extPlugin, exists := h.ExternalPlugins[msg.From]; exists {
			h.mu.RUnlock()

			extPlugin.mu.Lock()
			wasDisconnected := extPlugin.Status != "connected"
			extPlugin.LastHeartbeat = time.Now()
			extPlugin.Status = "connected"
			extPlugin.mu.Unlock()

			// Update health monitor
			if h.HealthMonitor != nil {
				h.HealthMonitor.UpdateHeartbeat(msg.From)
			}

			if wasDisconnected {
				log.Printf("💚 External plugin back online: %s", msg.From)
				h.notifyMainModuleExternalPluginStatus(extPlugin)
			}
			return
		}
	}

	h.mu.RUnlock()

	if module != nil {
		module.LastPing = time.Now()
		if h.HealthMonitor != nil {
			h.HealthMonitor.UpdateHeartbeat(module.ID)
		}
	}
}

// handleSubscribe handles subscribe messages
func (h *Hub) handleSubscribe(msg *Message) {
	h.mu.Lock()
	defer h.mu.Unlock()

	// Znajdź moduł
	var module *Module
	if h.MainModule != nil && h.MainModule.ID == msg.From {
		module = h.MainModule
	} else if plugin, ok := h.Plugins[msg.From]; ok {
		module = plugin
	}

	if module == nil {
		log.Printf("⚠️ Module not found: %s", msg.From)
		return
	}

	// Initialize Capabilities if nil
	if module.Capabilities == nil {
		module.Capabilities = []string{}
	}

	// Obsługa różnych formatów dla pola 'class'
	var classNames []string

	switch classValue := msg.Payload["class"].(type) {
	case string:
		// Pojedyncza klasa jako string
		classNames = []string{classValue}
	case []interface{}:
		// Lista klas jako []interface{}
		for _, item := range classValue {
			if className, ok := item.(string); ok && className != "" {
				classNames = append(classNames, className)
			}
		}
	case []string:
		// Lista klas jako []string (jeśli struktura Message to obsługuje)
		classNames = classValue
	default:
		log.Printf("⚠️ Invalid class payload type from %s: %T", msg.From, classValue)
		return
	}

	if len(classNames) == 0 {
		log.Printf("⚠️ No valid class names from %s", msg.From)
		return
	}

	// Dodaj każdą klasę do capabilities modułu
	for _, className := range classNames {
		// Sprawdź czy klasa już istnieje
		hasCapability := false
		for _, cap := range module.Capabilities {
			if cap == className {
				hasCapability = true
				break
			}
		}

		if !hasCapability {
			module.Capabilities = append(module.Capabilities, className)
			log.Printf("📢 %s subscribed to class: %s", msg.From, className)
		} else {
			log.Printf("ℹ️ %s already subscribed to class: %s", msg.From, className)
		}
	}
}

// handleUnsubscribe handles unsubscribe messages
func (h *Hub) handleUnsubscribe(msg *Message) {
	className, ok := msg.Payload["class"].(string)
	if !ok {
		return
	}

	h.mu.Lock()
	defer h.mu.Unlock()

	var module *Module
	if h.MainModule != nil && h.MainModule.ID == msg.From {
		module = h.MainModule
	} else if plugin, ok := h.Plugins[msg.From]; ok {
		module = plugin
	}

	if module != nil && module.Capabilities != nil {
		newCaps := []string{}
		for _, cap := range module.Capabilities {
			if cap != className {
				newCaps = append(newCaps, cap)
			}
		}
		module.Capabilities = newCaps
		log.Printf("📢 %s unsubscribed from class: %s", msg.From, className)
	}
}

// notifyPluginOnline notifies main module that a plugin is online
func (h *Hub) notifyPluginOnline(plugin *Module) {
	if h.MainModule == nil || !h.MainModule.IsActive {
		return
	}

	notifyMsg := NewMessage("hub", h.MainModule.ID, "plugin_online", map[string]interface{}{
		"plugin_id":   plugin.ID,
		"plugin_name": plugin.Name,
		"plugin_type": plugin.Type,
	})

	if data, err := notifyMsg.ToJSON(); err == nil {
		h.MainModule.Send <- data
	}
}

// notifyPluginOffline notifies main module that a plugin went offline
func (h *Hub) notifyPluginOffline(plugin *Module) {
	if h.MainModule == nil || !h.MainModule.IsActive {
		return
	}

	notifyMsg := NewMessage("hub", h.MainModule.ID, "plugin_offline", map[string]interface{}{
		"plugin_id":   plugin.ID,
		"plugin_name": plugin.Name,
	})

	if data, err := notifyMsg.ToJSON(); err == nil {
		h.MainModule.Send <- data
	}
}

// handleUnregister handles module disconnection
func (h *Hub) handleUnregister(module *Module) {
	h.mu.Lock()

	// Remove from pending if still there
	delete(h.PendingModules, module)

	module.IsActive = false

	if module.ComponentType == "main_module" {
		log.Printf("🔌 Main module disconnected: %s", module.ID)
		h.MainModule = nil
		h.mu.Unlock()

	} else if module.ComponentType == "external_plugin" {
		// ✅ NEW: Handle external plugin disconnect
		log.Printf("🔌 External plugin disconnected: %s", module.ID)

		if extPlugin, exists := h.ExternalPlugins[module.ID]; exists {
			extPlugin.mu.Lock()
			extPlugin.Status = "disconnected"
			extPlugin.Module = nil
			extPlugin.mu.Unlock()

			h.mu.Unlock()
			h.notifyMainModuleExternalPluginStatus(extPlugin)
		} else {
			h.mu.Unlock()
		}

		delete(h.Plugins, module.ID)

	} else if module.ComponentType == "plugin" {
		log.Printf("🔌 Plugin disconnected: %s", module.ID)

		if h.Plugins[module.ID] != nil {
			delete(h.Plugins, module.ID)
			isExpected := h.ExpectedPlugins[module.ID]
			h.mu.Unlock()

			// Notify main module
			h.notifyPluginOffline(module)

			// Update health monitor
			if h.HealthMonitor != nil {
				h.HealthMonitor.UnregisterPlugin(module.ID)
			}

			// Optionally restart plugin if it was expected and NOT shutting down
			if isExpected && h.PluginManager != nil {
				// Check if plugin manager is shutting down
				h.PluginManager.mu.RLock()
				shuttingDown := h.PluginManager.shuttingDown
				h.PluginManager.mu.RUnlock()

				if !shuttingDown {
					log.Printf("🔄 Plugin %s crashed, scheduling restart...", module.ID)
					go func(id string) {
						if err := h.PluginManager.RestartPlugin(id); err != nil {
							log.Printf("❌ Failed to restart plugin %s: %v", id, err)
						}
					}(module.ID)
				} else {
					log.Printf("ℹ️  Plugin %s disconnected during shutdown, not restarting", module.ID)
				}
			}
		} else {
			h.mu.Unlock()
		}
	} else {
		h.mu.Unlock()
	}

	close(module.Send)
}

// ✅ ORIGINAL: routeMessage with broadcast class support
func (h *Hub) routeMessage(msg *Message) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	// ✅ Handle broadcast to class
	if strings.HasPrefix(msg.To, "broadcast:") {
		className := strings.TrimPrefix(msg.To, "broadcast:")
		h.broadcastToClass(msg, className)
		return
	}

	// Handle broadcast to all
	if msg.To == "broadcast" {
		h.broadcastToAll(msg)
		return
	}

	// Handle hub messages (already processed in handleMessage)
	if msg.To == "hub" {
		return
	}

	// Route to specific destination
	var destination *Module

	// Check if destination is main module
	if h.MainModule != nil && h.MainModule.ID == msg.To {
		destination = h.MainModule
	} else if plugin, ok := h.Plugins[msg.To]; ok {
		destination = plugin
	}

	if destination != nil && destination.IsActive {
		if data, err := msg.ToJSON(); err == nil {
			select {
			case destination.Send <- data:
			default:
				log.Printf("⚠️  Failed to send to %s (channel full)", msg.To)
			}
		}
	} else {
		log.Printf("⚠️  Destination not found or inactive: %s", msg.To)
	}
}

// ✅ ORIGINAL: Broadcast to all modules with specific capability (class)
func (h *Hub) broadcastToClass(msg *Message, className string) {
	count := 0
	data, err := msg.ToJSON()
	if err != nil {
		log.Printf("⚠️  Failed to marshal message: %v", err)
		return
	}

	// Check main module
	if h.MainModule != nil && h.MainModule.IsActive && h.hasCapability(h.MainModule, className) {
		select {
		case h.MainModule.Send <- data:
			count++
		default:
			log.Printf("⚠️  Main module send buffer full")
		}
	}

	// Check plugins
	for _, plugin := range h.Plugins {
		if plugin.IsActive && h.hasCapability(plugin, className) {
			select {
			case plugin.Send <- data:
				count++
			default:
				log.Printf("⚠️  Plugin %s send buffer full", plugin.ID)
			}
		}
	}

	// if count > 0 {
	// 	log.Printf("📢 Broadcast to class '%s': %d recipients", className, count)
	// }
}

// broadcastToAll broadcasts message to all active modules
func (h *Hub) broadcastToAll(msg *Message) {
	count := 0
	data, err := msg.ToJSON()
	if err != nil {
		log.Printf("⚠️  Failed to marshal message: %v", err)
		return
	}

	// Send to main module
	if h.MainModule != nil && h.MainModule.IsActive {
		select {
		case h.MainModule.Send <- data:
			count++
		default:
			log.Printf("⚠️  Main module send buffer full")
		}
	}

	// Send to all plugins
	for _, plugin := range h.Plugins {
		if plugin.IsActive {
			select {
			case plugin.Send <- data:
				count++
			default:
				log.Printf("⚠️  Plugin %s send buffer full", plugin.ID)
			}
		}
	}

	// if count > 0 {
	// 	log.Printf("📢 Broadcast to all: %d recipients", count)
	// }
}

// hasCapability checks if module has a specific capability
func (h *Hub) hasCapability(module *Module, capability string) bool {
	if module.Capabilities == nil {
		return false
	}

	for _, cap := range module.Capabilities {
		if cap == capability {
			return true
		}
	}

	return false
}

// Shutdown gracefully shuts down the hub
func (h *Hub) Shutdown() {
	log.Println("🛑 Shutting down Hub...")
	close(h.shutdown)
}

// GetPluginStatus returns status of all plugins (both local and external)
func (h *Hub) GetPluginStatus() map[string]interface{} {
	h.mu.RLock()
	defer h.mu.RUnlock()

	status := make(map[string]interface{})

	// Main module status
	if h.MainModule != nil {
		status["main_module"] = map[string]interface{}{
			"id":           h.MainModule.ID,
			"name":         h.MainModule.Name,
			"active":       h.MainModule.IsActive,
			"capabilities": h.MainModule.Capabilities,
		}
	}

	// Local plugins status
	plugins := make([]map[string]interface{}, 0)
	for id, plugin := range h.Plugins {
		// Skip external plugins (they're in ExternalPlugins map)
		if plugin.ComponentType == "external_plugin" {
			continue
		}

		plugins = append(plugins, map[string]interface{}{
			"id":           id,
			"name":         plugin.Name,
			"type":         plugin.Type,
			"active":       plugin.IsActive,
			"expected":     h.ExpectedPlugins[id],
			"capabilities": plugin.Capabilities,
		})
	}
	status["plugins"] = plugins

	// External plugins status
	externalPlugins := make([]map[string]interface{}, 0)
	for _, extPlugin := range h.ExternalPlugins {
		extPlugin.mu.RLock()
		uptime := time.Since(extPlugin.ConnectedAt).Seconds()
		externalPlugins = append(externalPlugins, map[string]interface{}{
			"plugin_id":      extPlugin.PluginID,
			"status":         extPlugin.Status,
			"ip":             extPlugin.IP,
			"last_heartbeat": extPlugin.LastHeartbeat.Unix(),
			"uptime":         uptime,
		})
		extPlugin.mu.RUnlock()
	}
	status["external_plugins"] = externalPlugins

	// Health monitor status
	if h.HealthMonitor != nil {
		status["health"] = h.HealthMonitor.GetAllHealth()
	}

	return status
}
