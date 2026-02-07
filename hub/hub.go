package main

import (
	"log"
	"strings"
	"sync"
	"time"
)

// Hub is the central message router and plugin manager
type Hub struct {
	MainModule      *Module
	Plugins         map[string]*Module // ALL plugins (local + external) after registration
	ExpectedPlugins map[string]bool    // Plugins declared by main module

	// Track pending connections before registration
	PendingModules map[*Module]bool

	Register   chan *Module
	Unregister chan *Module
	Route      chan *Message

	PluginManager *PluginManager
	HealthMonitor *HealthMonitor

	Port int // HTTP/WebSocket port

	mu       sync.RWMutex
	shutdown chan struct{}
}

// NewHub creates a new Hub instance
func NewHub(port int, enablePluginManager bool, enableHealthMonitor bool) *Hub {
	hub := &Hub{
		Plugins:         make(map[string]*Module),
		ExpectedPlugins: make(map[string]bool),
		PendingModules:  make(map[*Module]bool),
		Register:        make(chan *Module),
		Unregister:      make(chan *Module),
		Route:           make(chan *Message, 256),
		shutdown:        make(chan struct{}),
		Port:            port,
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

	for {
		select {
		case module := <-h.Register:
			// Track module as pending until registered
			h.mu.Lock()
			h.PendingModules[module] = true
			h.mu.Unlock()

			log.Printf("📥 New connection added to pending modules")

		case module := <-h.Unregister:
			h.handleUnregister(module)

		case message := <-h.Route:
			log.Printf("🔀 Message received in Route channel: type=%s", message.Type) // ← DODAJ TO
			h.handleMessage(message)

		case <-h.shutdown:
			log.Println("⏹️  Hub shutting down...")
			return
		}
	}
}

// handleUnregister handles module disconnection
func (h *Hub) handleUnregister(module *Module) {
	h.mu.Lock()
	defer h.mu.Unlock()

	// Remove from pending if never registered
	if h.PendingModules[module] {
		delete(h.PendingModules, module)
		log.Printf("📤 Removed pending connection")
		return
	}

	// Handle registered modules
	if module == h.MainModule {
		log.Printf("❌ Main module disconnected: %s", module.ID)
		h.MainModule = nil
	} else if _, exists := h.Plugins[module.ID]; exists {
		log.Printf("🔌 Plugin disconnected: %s", module.ID)
		delete(h.Plugins, module.ID)

		// Notify main module
		if h.MainModule != nil && h.MainModule.IsActive {
			notification := NewMessage("hub", "futsal-nalf", "plugin_status", map[string]interface{}{
				"plugin_id": module.ID,
				"status":    "disconnected",
			})
			if data, err := notification.ToJSON(); err == nil {
				h.MainModule.Send <- data
			}
		}

		// Update PluginManager status for local plugins
		if h.PluginManager != nil {
			h.PluginManager.UpdatePluginStatus(module.ID, "offline")
		}
	}

	close(module.Send)
}

// handleMessage routes messages based on type
func (h *Hub) handleMessage(msg *Message) {
	log.Printf("📬 Incoming: type=%s from=%s", msg.Type, msg.From)

	switch msg.Type {
	case "register":
		log.Printf("🔍 DEBUG: Calling handleRegister for: %s", msg.From) // ← DODAJ
		h.handleRegister(msg)
	case "heartbeat":
		h.handleHeartbeat(msg)
	case "declare_required_plugins":
		h.handleDeclareRequiredPlugins(msg)
	case "get_plugin_status":
		h.handleGetPluginStatus(msg)
	case "subscribe":
		h.handleSubscribe(msg)
	default:
		h.routeMessage(msg)
	}
}

// handleRegister processes registration messages
func (h *Hub) handleRegister(msg *Message) {
	log.Printf("🔍 DEBUG: handleRegister called, payload: %+v", msg.Payload) // ← DODAJ na początku
	// Extract registration data
	componentType, _ := msg.Payload["component_type"].(string)
	pluginID, hasPluginID := msg.Payload["plugin_id"].(string)
	moduleID, hasModuleID := msg.Payload["id"].(string)

	// Determine ID
	var id string
	if hasPluginID && pluginID != "" {
		id = pluginID
	} else if hasModuleID && moduleID != "" {
		id = moduleID
	} else {
		log.Printf("⚠️  Registration missing both 'id' and 'plugin_id'")
		return
	}

	log.Printf("📝 Registration: id=%s, component_type=%s", id, componentType)

	// Find the module that sent this message
	h.mu.Lock()
	var module *Module
	for m := range h.PendingModules {
		if m.ID == "" || m.ID == msg.From || msg.From == "" {
			module = m
			delete(h.PendingModules, m)
			break
		}
	}
	h.mu.Unlock()

	if module == nil {
		log.Printf("❌ Cannot find pending module for registration: %s", id)
		return
	}

	// Update module info
	module.ID = id
	if name, ok := msg.Payload["name"].(string); ok {
		module.Name = name
	} else {
		module.Name = id
	}
	module.ComponentType = componentType
	module.IsActive = true

	// Register based on component type
	if componentType == "main_module" {
		h.registerMainModule(module)
	} else {
		// All plugins (local + external) go through same path
		h.registerPlugin(module)
	}
}

// registerMainModule registers the main application module
func (h *Hub) registerMainModule(module *Module) {
	h.mu.Lock()
	h.MainModule = module
	h.mu.Unlock()

	log.Printf("✅ Main module registered: %s (%s)", module.ID, module.Name)

	// Send confirmation
	confirmMsg := NewMessage("hub", module.ID, "registered", map[string]interface{}{
		"status": "connected",
	})
	if data, err := confirmMsg.ToJSON(); err == nil {
		module.Send <- data
	}
}

// registerPlugin registers a plugin (local or external - doesn't matter!)
func (h *Hub) registerPlugin(module *Module) {
	h.mu.Lock()
	h.Plugins[module.ID] = module
	isExpected := h.ExpectedPlugins[module.ID]
	h.mu.Unlock()

	log.Printf("✅ Plugin registered: %s (%s)", module.ID, module.Name)

	// Update PluginManager status for local plugins
	if h.PluginManager != nil {
		h.PluginManager.UpdatePluginStatus(module.ID, "online")
	}

	// Add to HealthMonitor if enabled
	if h.HealthMonitor != nil {
		h.HealthMonitor.RegisterPlugin(module.ID)
	}

	// Send confirmation to plugin
	confirmMsg := NewMessage("hub", module.ID, "registered", map[string]interface{}{
		"status": "connected",
	})
	if data, err := confirmMsg.ToJSON(); err == nil {
		module.Send <- data
	}

	// If this is an expected plugin, notify main module
	if isExpected && h.MainModule != nil && h.MainModule.IsActive {
		h.notifyPluginOnline(module)
	}
}

// notifyPluginOnline notifies main module that a plugin is online
func (h *Hub) notifyPluginOnline(plugin *Module) {
	notification := NewMessage("hub", "futsal-nalf", "plugin_status", map[string]interface{}{
		"plugin_id": plugin.ID,
		"status":    "connected",
	})

	if data, err := notification.ToJSON(); err == nil {
		h.MainModule.Send <- data
		log.Printf("📤 Notified main module: %s status = connected", plugin.ID)
	}
}

// handleDeclareRequiredPlugins processes plugin requirements from main module
func (h *Hub) handleDeclareRequiredPlugins(msg *Message) {
	h.mu.Lock()
	defer h.mu.Unlock()

	pluginIDs, ok := msg.Payload["plugins"].([]interface{})
	if !ok {
		log.Printf("⚠️  Invalid plugins payload - expected list of plugin IDs")
		return
	}

	log.Printf("📋 Main module declared %d required plugins", len(pluginIDs))

	// Clear expected plugins
	h.ExpectedPlugins = make(map[string]bool)

	// Process each plugin ID
	for _, p := range pluginIDs {
		id, ok := p.(string)
		if !ok || id == "" {
			log.Printf("⚠️  Skipping invalid plugin ID: %v", p)
			continue
		}

		h.ExpectedPlugins[id] = true
		log.Printf("   Expected: %s", id)

		// Check if plugin is already connected
		if existingPlugin, exists := h.Plugins[id]; exists && existingPlugin.IsActive {
			h.notifyPluginOnline(existingPlugin)
		} else {
			// Plugin not connected yet
			// Check if it's a LOCAL plugin that PluginManager should start
			if h.PluginManager != nil && h.PluginManager.IsLocalPlugin(id) {
				go func(pluginID string) {
					log.Printf("🚀 Starting required local plugin: %s", pluginID)
					if err := h.PluginManager.StartPlugin(pluginID); err != nil {
						log.Printf("❌ Failed to start plugin %s: %v", pluginID, err)
					}
				}(id)
			} else {
				// External plugin - just wait for it to connect
				log.Printf("⏳ Waiting for external plugin to connect: %s", id)
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

	h.mu.RUnlock()

	if module != nil {
		module.LastPing = time.Now()

		// Update HealthMonitor
		if h.HealthMonitor != nil {
			h.HealthMonitor.RecordHeartbeat(msg.From)
		}
	}
}

// handleGetPluginStatus returns status of all plugins
func (h *Hub) handleGetPluginStatus(msg *Message) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	// Build status for all plugins
	pluginStatuses := make(map[string]interface{})

	for id, plugin := range h.Plugins {
		status := "connected"
		if !plugin.IsActive {
			status = "disconnected"
		}

		pluginStatuses[id] = map[string]interface{}{
			"status": status,
			"name":   plugin.Name,
		}
	}

	// Send response
	response := NewMessage("hub", msg.From, "plugin_status_response", map[string]interface{}{
		"plugins": pluginStatuses,
	})

	if module, ok := h.Plugins[msg.From]; ok {
		if data, err := response.ToJSON(); err == nil {
			module.Send <- data
		}
	}
}

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

// handleSubscribe handles subscription requests
// func (h *Hub) handleSubscribe(msg *Message) {
// 	class, ok := msg.Payload["class"].(string)
// 	if !ok {
// 		log.Printf("⚠️  Invalid subscribe request from %s", msg.From)
// 		return
// 	}

// 	h.mu.RLock()
// 	module := h.Plugins[msg.From]
// 	if module == nil && h.MainModule != nil && h.MainModule.ID == msg.From {
// 		module = h.MainModule
// 	}
// 	h.mu.RUnlock()

// 	if module == nil {
// 		log.Printf("⚠️  Subscribe from unknown module: %s", msg.From)
// 		return
// 	}

// 	module.Subscribe(class)
// 	log.Printf("📢 %s subscribed to class: %s", msg.From, class)
// }

// routeMessage routes a message to its destination
// routeMessage routes a message to its destination
func (h *Hub) routeMessage(msg *Message) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	// Check if this is a class-based broadcast
	class, hasClass := msg.Payload["class"].(string)
	// ✅ Handle broadcast to class
	if strings.HasPrefix(msg.To, "broadcast:") {
		className := strings.TrimPrefix(msg.To, "broadcast:")
		h.broadcastToClass(msg, className)
		return
	}

	// Broadcast to all OR class subscribers
	if msg.To == "" || msg.To == "broadcast" {
		for _, plugin := range h.Plugins {
			if !plugin.IsActive {
				continue
			}

			// Skip main module in broadcasts (unless subscribed)
			if plugin == h.MainModule && !hasClass {
				continue
			}

			// If class specified, check subscription
			if hasClass && class != "" {
				if !plugin.IsSubscribedTo(class) {
					continue // Skip non-subscribers
				}
			}

			if data, err := msg.ToJSON(); err == nil {
				select {
				case plugin.Send <- data:
					if hasClass {
						log.Printf("📤 Sent to %s (subscribed to %s)", plugin.ID, class)
					}
				default:
					log.Printf("⚠️  Plugin %s channel full, skipping message", plugin.ID)
				}
			}
		}
		return
	}

	// Route to specific destination
	var destination *Module
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
				log.Printf("⚠️  Destination %s channel full", msg.To)
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
	log.Println("⏹️  Initiating Hub shutdown...")

	// Stop plugin manager first
	if h.PluginManager != nil {
		h.PluginManager.StopAllPlugins()
	}

	// Stop health monitor
	if h.HealthMonitor != nil {
		h.HealthMonitor.Stop()
	}

	// Signal shutdown
	close(h.shutdown)

	log.Println("✅ Hub shutdown complete")
}
