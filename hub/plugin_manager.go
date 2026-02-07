package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"
)

// PluginConfig represents plugin configuration
type PluginConfig struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	Type string `json:"type"` // "local" or "external"

	// Local plugin fields
	ExecutablePath string   `json:"executable_path"`
	WorkingDir     string   `json:"working_dir"`
	Args           []string `json:"args"`
	Env            []string `json:"env"`
	AutoStart      bool     `json:"auto_start"`
	RestartOnCrash bool     `json:"restart_on_crash"`
	MaxRestarts    int      `json:"max_restarts"`
	RestartDelay   int      `json:"restart_delay_ms"`
	StartupDelay   int      `json:"startup_delay_ms"`

	// External plugin fields
	DiscoveryMode     string `json:"discovery_mode"`
	DiscoveryHostname string `json:"discovery_hostname"`
	DiscoveryPort     int    `json:"discovery_port"`

	// Common fields
	HealthCheckInterval int    `json:"health_check_interval"`
	HeartbeatTimeout    int    `json:"heartbeat_timeout"`
	IsCritical          bool   `json:"is_critical"`
	Description         string `json:"description"`
}

// PluginProcess represents a running local plugin process
type PluginProcess struct {
	Config       PluginConfig
	Process      *exec.Cmd
	Status       string // "stopped", "starting", "online", "offline", "error"
	LastError    error
	RestartCount int
	StartedAt    time.Time
	exitChan     chan struct{}
}

// PluginManager manages plugin processes (LOCAL PLUGINS ONLY!)
type PluginManager struct {
	hub          *Hub
	configPath   string
	plugins      map[string]*PluginProcess // Only LOCAL plugins
	allConfigs   map[string]PluginConfig   // All plugin configs (local + external)
	mu           sync.RWMutex
	shuttingDown bool
}

// NewPluginManager creates a new plugin manager
func NewPluginManager(hub *Hub) *PluginManager {
	return &PluginManager{
		hub:        hub,
		configPath: "config/plugins.json",
		plugins:    make(map[string]*PluginProcess),
		allConfigs: make(map[string]PluginConfig),
	}
}

// LoadConfig loads plugin configurations from JSON file
func (pm *PluginManager) LoadConfig() error {
	pm.mu.Lock()
	defer pm.mu.Unlock()

	// Check if config file exists
	if _, err := os.Stat(pm.configPath); os.IsNotExist(err) {
		log.Printf("⚠️  Plugin config not found: %s", pm.configPath)
		log.Printf("   Creating default config...")
		return pm.createDefaultConfig()
	}

	// Read config file
	data, err := os.ReadFile(pm.configPath)
	if err != nil {
		return fmt.Errorf("failed to read config: %w", err)
	}

	// Parse JSON
	var configs map[string]PluginConfig
	if err := json.Unmarshal(data, &configs); err != nil {
		return fmt.Errorf("failed to parse config: %w", err)
	}

	// Store all configs
	pm.allConfigs = configs

	// Initialize LOCAL plugin processes only
	localCount := 0
	externalCount := 0

	for id, config := range configs {
		config.ID = id // Ensure ID matches key

		if config.Type == "local" {
			// This is a LOCAL plugin - PluginManager will manage its process
			pm.plugins[id] = &PluginProcess{
				Config:   config,
				Status:   "stopped",
				exitChan: make(chan struct{}),
			}
			localCount++
			log.Printf("   ✅ Loaded LOCAL plugin: %s", id)
		} else if config.Type == "external" {
			// This is an EXTERNAL plugin - PluginManager just tracks config
			externalCount++
			log.Printf("   📡 Loaded EXTERNAL plugin config: %s", id)
		} else {
			log.Printf("   ⚠️  Unknown plugin type '%s' for: %s", config.Type, id)
		}
	}

	log.Printf("✅ Loaded %d plugin configurations (%d local, %d external)",
		len(configs), localCount, externalCount)

	return nil
}

// createDefaultConfig creates a default plugin configuration
func (pm *PluginManager) createDefaultConfig() error {
	os.MkdirAll("config", 0755)

	defaultConfigs := map[string]PluginConfig{
		"timer-plugin": {
			ID:                  "timer-plugin",
			Name:                "Timer Plugin",
			Type:                "local",
			ExecutablePath:      "../plugins/timer-plugin/timer-plugin.exe",
			WorkingDir:          "../plugins/timer-plugin",
			Args:                []string{},
			Env:                 []string{"PLUGIN_ID=timer-plugin", "HUB_URL=ws://localhost:8080/ws"},
			AutoStart:           true,
			RestartOnCrash:      true,
			MaxRestarts:         10,
			RestartDelay:        3000,
			StartupDelay:        1000,
			HealthCheckInterval: 10,
			IsCritical:          false,
		},
		"obs-ws-plugin": {
			ID:                  "obs-ws-plugin",
			Name:                "OBS WebSocket Plugin",
			Type:                "local",
			ExecutablePath:      "../plugins/obs-ws-plugin/obs-ws-plugin.exe",
			WorkingDir:          "../plugins/obs-ws-plugin",
			Args:                []string{},
			Env:                 []string{"PLUGIN_ID=obs-ws-plugin", "HUB_URL=ws://localhost:8080/ws"},
			AutoStart:           true,
			RestartOnCrash:      true,
			MaxRestarts:         10,
			RestartDelay:        3000,
			StartupDelay:        1000,
			HealthCheckInterval: 10,
			IsCritical:          true,
		},
		"recorder-plugin": {
			ID:                  "recorder-plugin",
			Name:                "Camera Recorder Plugin",
			Type:                "external",
			DiscoveryMode:       "reverse",
			DiscoveryHostname:   "debian.local",
			DiscoveryPort:       9999,
			HealthCheckInterval: 15,
			HeartbeatTimeout:    30,
			IsCritical:          false,
			Description:         "External camera recorder plugin on Debian",
		},
	}

	data, err := json.MarshalIndent(defaultConfigs, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal config: %w", err)
	}

	if err := os.WriteFile(pm.configPath, data, 0644); err != nil {
		return fmt.Errorf("failed to write config: %w", err)
	}

	// Store configs
	pm.allConfigs = defaultConfigs

	// Initialize LOCAL plugins only
	for id, config := range defaultConfigs {
		if config.Type == "local" {
			pm.plugins[id] = &PluginProcess{
				Config:   config,
				Status:   "stopped",
				exitChan: make(chan struct{}),
			}
		}
	}

	log.Printf("✅ Created default config at: %s", pm.configPath)
	return nil
}

// IsLocalPlugin checks if a plugin is managed locally
func (pm *PluginManager) IsLocalPlugin(pluginID string) bool {
	pm.mu.RLock()
	defer pm.mu.RUnlock()

	_, exists := pm.plugins[pluginID]
	return exists
}

// StartPlugin starts a specific LOCAL plugin
func (pm *PluginManager) StartPlugin(pluginID string) error {
	pm.mu.Lock()
	pluginProc, exists := pm.plugins[pluginID]
	if !exists {
		pm.mu.Unlock()
		return fmt.Errorf("plugin not found or not local: %s", pluginID)
	}
	pm.mu.Unlock()

	// Check if already running
	if pluginProc.Status == "online" || pluginProc.Status == "starting" {
		log.Printf("ℹ️  Plugin %s is already %s", pluginID, pluginProc.Status)
		return nil
	}

	// Check restart limit
	if pluginProc.RestartCount > 0 && pluginProc.RestartCount >= pluginProc.Config.MaxRestarts {
		return fmt.Errorf("plugin %s exceeded max restarts (%d)",
			pluginID, pluginProc.Config.MaxRestarts)
	}

	config := pluginProc.Config

	log.Printf("▶️  Starting plugin: %s", pluginID)

	// Get absolute path
	execPath := config.ExecutablePath
	if !filepath.IsAbs(execPath) {
		absPath, err := filepath.Abs(execPath)
		if err != nil {
			return fmt.Errorf("failed to resolve path: %w", err)
		}
		execPath = absPath
	}

	// Check if executable exists
	if _, err := os.Stat(execPath); os.IsNotExist(err) {
		return fmt.Errorf("executable not found: %s", execPath)
	}

	// Create command
	cmd := exec.Command(execPath, config.Args...)

	if config.WorkingDir != "" {
		cmd.Dir = config.WorkingDir
	}

	cmd.Env = append(os.Environ(), config.Env...)
	cmd.Env = append(cmd.Env, fmt.Sprintf("PLUGIN_ID=%s", pluginID))

	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	// Start process
	if err := cmd.Start(); err != nil {
		pluginProc.Status = "error"
		pluginProc.LastError = err
		return fmt.Errorf("failed to start plugin: %w", err)
	}

	// Update status
	pm.mu.Lock()
	pluginProc.Process = cmd
	pluginProc.Status = "starting"
	pluginProc.StartedAt = time.Now()
	pluginProc.RestartCount++
	pluginProc.exitChan = make(chan struct{})
	pm.mu.Unlock()

	log.Printf("✅ Plugin %s started (PID: %d)", pluginID, cmd.Process.Pid)

	// Wait for startup delay
	if config.StartupDelay > 0 {
		time.Sleep(time.Duration(config.StartupDelay) * time.Millisecond)
	}

	// Monitor process
	go pm.monitorProcess(pluginID, cmd)

	return nil
}

// monitorProcess monitors a plugin process
func (pm *PluginManager) monitorProcess(pluginID string, cmd *exec.Cmd) {
	err := cmd.Wait()

	pm.mu.Lock()
	pluginProc := pm.plugins[pluginID]

	if pluginProc.exitChan != nil {
		close(pluginProc.exitChan)
		pluginProc.exitChan = nil
	}
	pm.mu.Unlock()

	if err != nil {
		log.Printf("❌ Plugin %s exited with error: %v", pluginID, err)
		pm.mu.Lock()
		pluginProc.Status = "error"
		pluginProc.LastError = err
		pm.mu.Unlock()
	} else {
		log.Printf("🔌 Plugin %s exited normally", pluginID)
		pm.mu.Lock()
		pluginProc.Status = "stopped"
		pm.mu.Unlock()
	}

	// Auto-restart if configured
	pm.mu.Lock()
	shouldRestart := !pm.shuttingDown &&
		pluginProc.Config.RestartOnCrash &&
		pluginProc.RestartCount < pluginProc.Config.MaxRestarts
	pm.mu.Unlock()

	if shouldRestart {
		log.Printf("🔄 Restarting plugin %s in %dms...",
			pluginID, pluginProc.Config.RestartDelay)

		time.Sleep(time.Duration(pluginProc.Config.RestartDelay) * time.Millisecond)

		if err := pm.StartPlugin(pluginID); err != nil {
			log.Printf("❌ Failed to restart plugin %s: %v", pluginID, err)
		}
	}
}

// UpdatePluginStatus updates plugin status when it connects/disconnects via WebSocket
func (pm *PluginManager) UpdatePluginStatus(pluginID string, status string) {
	pm.mu.Lock()
	defer pm.mu.Unlock()

	if pluginProc, exists := pm.plugins[pluginID]; exists {
		pluginProc.Status = status
		log.Printf("🟢 Plugin %s status: %s", pluginID, status)
	}
}

// StopPlugin stops a specific plugin
func (pm *PluginManager) StopPlugin(pluginID string) error {
	pm.mu.Lock()
	pluginProc, exists := pm.plugins[pluginID]
	if !exists {
		pm.mu.Unlock()
		return fmt.Errorf("plugin not found: %s", pluginID)
	}
	pm.mu.Unlock()

	if pluginProc.Process == nil {
		log.Printf("ℹ️  Plugin %s is not running", pluginID)
		return nil
	}

	log.Printf("⏹️  Stopping plugin: %s", pluginID)

	if pluginProc.Process != nil && pluginProc.Process.Process != nil {
		pluginProc.Process.Process.Signal(os.Kill)
	}

	pm.mu.Lock()
	exitChan := pluginProc.exitChan
	pm.mu.Unlock()

	if exitChan != nil {
		select {
		case <-exitChan:
			log.Printf("✅ Plugin %s stopped", pluginID)
		case <-time.After(5 * time.Second):
			log.Printf("⚠️  Plugin %s did not stop in time", pluginID)
		}
	}

	pm.mu.Lock()
	pluginProc.Status = "stopped"
	pluginProc.Process = nil
	pluginProc.exitChan = nil
	pm.mu.Unlock()

	return nil
}

// StopAllPlugins stops all running plugins
func (pm *PluginManager) StopAllPlugins() {
	log.Println("⏹️  Stopping all plugins...")

	pm.mu.Lock()
	pm.shuttingDown = true
	pluginIDs := make([]string, 0, len(pm.plugins))
	for id := range pm.plugins {
		pluginIDs = append(pluginIDs, id)
	}
	pm.mu.Unlock()

	for _, id := range pluginIDs {
		if err := pm.StopPlugin(id); err != nil {
			log.Printf("⚠️  Error stopping plugin %s: %v", id, err)
		}
	}

	log.Println("✅ All plugins stopped")
}

// GetPluginStatus returns status of a plugin (local or external)
func (pm *PluginManager) GetPluginStatus(pluginID string) (map[string]interface{}, error) {
	pm.mu.RLock()
	defer pm.mu.RUnlock()

	// Check if it's a local plugin
	if pluginProc, exists := pm.plugins[pluginID]; exists {
		status := map[string]interface{}{
			"id":            pluginProc.Config.ID,
			"name":          pluginProc.Config.Name,
			"type":          "local",
			"status":        pluginProc.Status,
			"restart_count": pluginProc.RestartCount,
			"max_restarts":  pluginProc.Config.MaxRestarts,
		}

		if pluginProc.Process != nil {
			status["pid"] = pluginProc.Process.Process.Pid
		}

		if !pluginProc.StartedAt.IsZero() {
			status["uptime"] = time.Since(pluginProc.StartedAt).Seconds()
		}

		if pluginProc.LastError != nil {
			status["last_error"] = pluginProc.LastError.Error()
		}

		return status, nil
	}

	// Check if it's an external plugin in config
	if config, exists := pm.allConfigs[pluginID]; exists && config.Type == "external" {
		// External plugin - status comes from Hub's Plugins map
		return map[string]interface{}{
			"id":   config.ID,
			"name": config.Name,
			"type": "external",
		}, nil
	}

	return nil, fmt.Errorf("plugin not found: %s", pluginID)
}

// GetAllConfigs returns all plugin configs (for reverse discovery, etc.)
func (pm *PluginManager) GetAllConfigs() map[string]PluginConfig {
	pm.mu.RLock()
	defer pm.mu.RUnlock()

	// Return a copy
	configs := make(map[string]PluginConfig)
	for id, config := range pm.allConfigs {
		configs[id] = config
	}
	return configs
}

// GetAllStatus returns status of all plugins
func (pm *PluginManager) GetAllStatus() map[string]interface{} {
	pm.mu.RLock()
	defer pm.mu.RUnlock()

	result := make(map[string]interface{})

	// Local plugins
	localPlugins := make(map[string]interface{})
	for id, pluginProc := range pm.plugins {
		localPlugins[id] = map[string]interface{}{
			"status": pluginProc.Status,
			"pid":    0,
		}
		if pluginProc.Process != nil && pluginProc.Process.Process != nil {
			localPlugins[id].(map[string]interface{})["pid"] = pluginProc.Process.Process.Pid
		}
	}
	result["local_plugins"] = localPlugins

	// External plugins (from config only)
	externalPlugins := make(map[string]interface{})
	for id, config := range pm.allConfigs {
		if config.Type == "external" {
			externalPlugins[id] = map[string]interface{}{
				"status": "waiting",
			}
		}
	}
	result["external_plugins"] = externalPlugins

	return result
}
