package main

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"
)

// PluginConfig represents plugin configuration
type PluginConfig struct {
	ID                  string   `json:"id"`
	Name                string   `json:"name"`
	Type                string   `json:"type"` // "local", "external"
	ExecutablePath      string   `json:"executable_path"`
	WorkingDir          string   `json:"working_dir"`
	Args                []string `json:"args"`
	Env                 []string `json:"env"`
	AutoStart           bool     `json:"auto_start"`
	RestartOnCrash      bool     `json:"restart_on_crash"`
	MaxRestarts         int      `json:"max_restarts"`
	RestartDelay        int      `json:"restart_delay_ms"`      // milliseconds
	StartupDelay        int      `json:"startup_delay_ms"`      // milliseconds
	HealthCheckInterval int      `json:"health_check_interval"` // seconds
	IsCritical          bool     `json:"is_critical"`
}

// PluginProcess represents a running plugin process
type PluginProcess struct {
	Config       PluginConfig
	Process      *exec.Cmd
	Status       string // "stopped", "starting", "online", "error"
	LastError    error
	RestartCount int
	StartedAt    time.Time
	exitChan     chan struct{} // Channel to signal process exit
}

// PluginManager manages plugin processes
type PluginManager struct {
	hub          *Hub
	configPath   string
	plugins      map[string]*PluginProcess
	mu           sync.RWMutex
	shuttingDown bool // Flag to prevent auto-restarts during shutdown
}

// NewPluginManager creates a new plugin manager
func NewPluginManager(hub *Hub) *PluginManager {
	return &PluginManager{
		hub:        hub,
		configPath: "config/plugins.json",
		plugins:    make(map[string]*PluginProcess),
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
	data, err := ioutil.ReadFile(pm.configPath)
	if err != nil {
		return fmt.Errorf("failed to read config: %w", err)
	}

	// Parse JSON
	var configs map[string]PluginConfig
	if err := json.Unmarshal(data, &configs); err != nil {
		return fmt.Errorf("failed to parse config: %w", err)
	}

	// Initialize plugin processes (skip external plugins)
	for id, config := range configs {
		config.ID = id // Ensure ID matches key

		// Skip external plugins - they connect on their own
		if config.Type == "external" {
			log.Printf("   Skipped external plugin: %s (managed remotely)", id)
			continue
		}

		pm.plugins[id] = &PluginProcess{
			Config:   config,
			Status:   "stopped",
			exitChan: make(chan struct{}),
		}
		log.Printf("   Loaded config for: %s", id)
	}

	log.Printf("✅ Loaded %d plugin configurations", len(pm.plugins))
	return nil
}

// createDefaultConfig creates a default plugin configuration
func (pm *PluginManager) createDefaultConfig() error {
	// Create config directory
	os.MkdirAll("config", 0755)

	// Default configuration
	defaultConfigs := map[string]PluginConfig{
		"timer-plugin": {
			ID:                  "timer-plugin",
			Name:                "Timer Plugin",
			Type:                "local",
			ExecutablePath:      "../plugins/timer-plugin/timer-plugin.exe",
			WorkingDir:          "../plugins/timer-plugin",
			Args:                []string{},
			Env:                 []string{},
			AutoStart:           false,
			RestartOnCrash:      true,
			MaxRestarts:         3,
			RestartDelay:        3000,
			StartupDelay:        1000,
			HealthCheckInterval: 10,
			IsCritical:          false,
		},
	}

	// Marshal to JSON
	data, err := json.MarshalIndent(defaultConfigs, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal config: %w", err)
	}

	// Write to file
	if err := ioutil.WriteFile(pm.configPath, data, 0644); err != nil {
		return fmt.Errorf("failed to write config: %w", err)
	}

	// Initialize plugins
	for id, config := range defaultConfigs {
		pm.plugins[id] = &PluginProcess{
			Config:   config,
			Status:   "stopped",
			exitChan: make(chan struct{}),
		}
	}

	log.Printf("✅ Created default config at: %s", pm.configPath)
	return nil
}

// StartPlugin starts a specific plugin
func (pm *PluginManager) StartPlugin(pluginID string) error {
	pm.mu.Lock()
	pluginProc, exists := pm.plugins[pluginID]
	if !exists {
		pm.mu.Unlock()
		return fmt.Errorf("plugin not found in config: %s", pluginID)
	}

	// ✅ Check if this is an external plugin
	if pluginProc.Config.Type == "external" {
		pm.mu.Unlock()
		return fmt.Errorf("cannot start external plugin %s - external plugins connect on their own", pluginID)
	}

	pm.mu.Unlock()

	// Check if already running
	if pluginProc.Status == "online" || pluginProc.Status == "starting" {
		log.Printf("ℹ️  Plugin %s is already %s", pluginID, pluginProc.Status)
		return nil
	}

	// ✅ FIX: Check restart limit ONLY if this is a RESTART (not first start)
	// RestartCount starts at 0, so first start is OK
	// After first start, RestartCount becomes 1, then we check if 1 > MaxRestarts
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

	// Set working directory
	if config.WorkingDir != "" {
		cmd.Dir = config.WorkingDir
	}

	// Set environment variables
	cmd.Env = append(os.Environ(), config.Env...)

	// Add plugin ID to environment
	cmd.Env = append(cmd.Env, fmt.Sprintf("PLUGIN_ID=%s", pluginID))

	// Set output
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
	pluginProc.exitChan = make(chan struct{}) // Reset exit channel for new process
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

	// Signal that process has exited - check if channel is still open
	if pluginProc.exitChan != nil {
		close(pluginProc.exitChan)
		pluginProc.exitChan = nil // Prevent double close
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

	// Auto-restart if configured and NOT shutting down
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
	} else if pm.shuttingDown {
		log.Printf("ℹ️  Plugin %s exited during shutdown, not restarting", pluginID)
	} else if pluginProc.RestartCount >= pluginProc.Config.MaxRestarts {
		log.Printf("⚠️  Plugin %s exceeded max restarts, not restarting", pluginID)
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

	// Try to send termination signal
	// On Windows, os.Interrupt is not supported, so we go directly to Kill
	// Check if Process is not nil before accessing Process.Process
	if pluginProc.Process != nil && pluginProc.Process.Process != nil {
		signalErr := pluginProc.Process.Process.Signal(os.Kill)
		if signalErr != nil {
			log.Printf("⚠️  Failed to send kill signal: %v", signalErr)
			// Process might already be dead, continue to wait
		}
	}

	// Wait for process to exit via exitChan (which is closed by monitorProcess)
	// or timeout after 5 seconds
	pm.mu.Lock()
	exitChan := pluginProc.exitChan
	pm.mu.Unlock()

	if exitChan == nil {
		// Process already exited
		log.Printf("✅ Plugin %s already stopped", pluginID)
		pm.mu.Lock()
		pluginProc.Status = "stopped"
		pluginProc.Process = nil
		pm.mu.Unlock()
		return nil
	}

	select {
	case <-exitChan:
		log.Printf("✅ Plugin %s stopped", pluginID)
	case <-time.After(5 * time.Second):
		log.Printf("⚠️  Plugin %s did not stop in time, giving up", pluginID)
		// At this point the process is stuck, but we've done our best
	}

	pm.mu.Lock()
	pluginProc.Status = "stopped"
	pluginProc.Process = nil
	pluginProc.exitChan = nil // Mark as closed
	pm.mu.Unlock()

	return nil
}

// RestartPlugin restarts a plugin
func (pm *PluginManager) RestartPlugin(pluginID string) error {
	log.Printf("🔄 Restarting plugin: %s", pluginID)

	// Stop plugin
	if err := pm.StopPlugin(pluginID); err != nil {
		log.Printf("⚠️  Failed to stop plugin %s: %v", pluginID, err)
	}

	// Wait a bit
	time.Sleep(1 * time.Second)

	// Start plugin
	return pm.StartPlugin(pluginID)
}

// StopAllPlugins stops all running plugins
func (pm *PluginManager) StopAllPlugins() {
	log.Println("⏹️  Stopping all plugins...")

	// Set shutdown flag to prevent auto-restarts
	pm.mu.Lock()
	pm.shuttingDown = true
	pm.mu.Unlock()

	pm.mu.RLock()
	pluginIDs := make([]string, 0, len(pm.plugins))
	for id := range pm.plugins {
		pluginIDs = append(pluginIDs, id)
	}
	pm.mu.RUnlock()

	for _, id := range pluginIDs {
		if err := pm.StopPlugin(id); err != nil {
			log.Printf("⚠️  Error stopping plugin %s: %v", id, err)
		}
	}

	log.Println("✅ All plugins stopped")
}

// GetPluginStatus returns status of a plugin
func (pm *PluginManager) GetPluginStatus(pluginID string) (map[string]interface{}, error) {
	pm.mu.RLock()
	defer pm.mu.RUnlock()

	pluginProc, exists := pm.plugins[pluginID]
	if !exists {
		return nil, fmt.Errorf("plugin not found: %s", pluginID)
	}

	status := map[string]interface{}{
		"id":            pluginProc.Config.ID,
		"name":          pluginProc.Config.Name,
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

// GetAllStatus returns status of all plugins
func (pm *PluginManager) GetAllStatus() []map[string]interface{} {
	pm.mu.RLock()
	defer pm.mu.RUnlock()

	statuses := make([]map[string]interface{}, 0, len(pm.plugins))

	for id := range pm.plugins {
		if status, err := pm.GetPluginStatus(id); err == nil {
			statuses = append(statuses, status)
		}
	}

	return statuses
}

// ResetRestartCount resets restart counter for a plugin
func (pm *PluginManager) ResetRestartCount(pluginID string) error {
	pm.mu.Lock()
	defer pm.mu.Unlock()

	pluginProc, exists := pm.plugins[pluginID]
	if !exists {
		return fmt.Errorf("plugin not found: %s", pluginID)
	}

	pluginProc.RestartCount = 0
	log.Printf("✅ Reset restart count for plugin: %s", pluginID)

	return nil
}
