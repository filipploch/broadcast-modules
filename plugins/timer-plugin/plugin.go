package timer

import (
	"fmt"
	"log"
	"sync"
	"time"
)

// Plugin represents the Timer plugin with WebSocket integration
type Plugin struct {
	ID        string
	Name      string
	manager   *Manager
	hubClient *HubClient
	config    PluginConfig
	running   bool
	mu        sync.Mutex
}

// PluginConfig holds plugin configuration
type PluginConfig struct {
	PluginID          string `json:"plugin_id"`
	PluginName        string `json:"plugin_name"`
	HubURL            string `json:"hub_url"`
	Port              int    `json:"port"`
	AutoReconnect     bool   `json:"auto_reconnect"`
	MaxReconnects     int    `json:"max_reconnects"`
	UpdateInterval    int    `json:"update_interval_ms"`
	BroadcastInterval int    `json:"broadcast_interval_ms"`
	HeartbeatInterval int    `json:"heartbeat_interval_ms"`
}

// NewPlugin creates a new Timer plugin
func NewPlugin(config PluginConfig) *Plugin {
	return &Plugin{
		ID:      config.PluginID,
		Name:    config.PluginName,
		manager: NewManager(),
		config:  config,
	}
}

// Start starts the plugin
func (p *Plugin) Start() error {
	log.Printf("🚀 Starting Timer Plugin: %s", p.ID)

	// Connect to Hub
	p.hubClient = NewHubClient(p.ID, p.Name, p.config.HubURL)
	if err := p.hubClient.Connect(); err != nil {
		return fmt.Errorf("failed to connect to Hub: %w", err)
	}

	// Start auto-reconnect if enabled
	if p.config.AutoReconnect {
		go p.hubClient.AutoReconnect(p.config.MaxReconnects)
	}

	// Start heartbeat
	if p.config.HeartbeatInterval > 0 {
		go p.startHeartbeat()
	}

	// Start message handler
	p.running = true
	go p.handleMessages()

	log.Printf("✅ Timer Plugin started successfully")
	return nil
}

// Stop stops the plugin
func (p *Plugin) Stop() error {
	log.Printf("⏹️  Stopping Timer Plugin: %s", p.ID)

	p.running = false

	// Close Hub connection
	if p.hubClient != nil {
		if err := p.hubClient.Close(); err != nil {
			log.Printf("Error closing Hub connection: %v", err)
		}
	}

	log.Printf("✅ Timer Plugin stopped")
	return nil
}

// startHeartbeat sends periodic heartbeat messages
func (p *Plugin) startHeartbeat() {
	ticker := time.NewTicker(time.Duration(p.config.HeartbeatInterval) * time.Millisecond)
	defer ticker.Stop()

	for p.running {
		<-ticker.C
		if p.hubClient != nil && p.hubClient.IsConnected() {
			p.hubClient.Send(&Message{
				From: p.ID,
				To:   "hub",
				Type: "heartbeat",
				Payload: map[string]interface{}{
					"plugin_id": p.ID,
					"timestamp": time.Now().Unix(),
				},
			})
		}
	}
}

// handleMessages processes incoming WebSocket messages
func (p *Plugin) handleMessages() {
	for p.running {
		select {
		case msg := <-p.hubClient.Receive():
			p.handleMessage(msg)
		}
	}
}

// handleMessage processes a single message
func (p *Plugin) handleMessage(msg *Message) {
	// log.Printf("📩 Received: %s from %s (type: %s)", msg.Type, msg.From, msg.Type)

	switch msg.Type {
	case "registered":
		log.Printf("✅ Plugin registered with Hub")
	case "create_timer":
		p.handleCreateTimer(msg)
	case "start_timer":
		p.handleStartTimer(msg)
	case "pause_timer":
		p.handlePauseTimer(msg)
	case "resume_timer":
		p.handleResumeTimer(msg)
	case "reset_timer":
		p.handleResetTimer(msg)
	case "adjust_time":
		p.handleAdjustTime(msg)
	case "set_elapsed_time":
		p.handleSetElapsedTime(msg)
	case "get_timer_state":
		p.handleGetTimerState(msg)
	case "get_all_timers":
		p.handleGetAllTimers(msg)
	case "remove_timer":
		p.handleRemoveTimer(msg)
	case "ping":
		p.handlePing(msg)
	case "shutdown":
		p.Stop()
	default:
		log.Printf("⚠️  Unknown message type: %s", msg.Type)

	}
}

// ============================================================================
// MESSAGE HANDLERS
// ============================================================================

func (p *Plugin) handleCreateTimer(msg *Message) {
	timerID, ok := msg.Payload["timer_id"].(string)
	if !ok {
		p.sendError(msg.From, "create_timer", "timer_id is required")
		return
	}

	timerType, _ := msg.Payload["timer_type"].(string)
	if timerType == "" {
		timerType = "independent"
	}

	// Build config
	config := TimerConfig{
		Type: TimerType(timerType),
	}

	// Optional: parent_id
	if parentID, ok := msg.Payload["parent_id"].(string); ok {
		config.ParentID = parentID
	}

	// Optional: limit (renamed to limit)
	if limitTime, ok := msg.Payload["limit"].(float64); ok {
		config.Limit = time.Duration(limitTime) * time.Millisecond
	}

	// pause_at_limit
	pauseAtLimit := false
	if pal, ok := msg.Payload["pause_at_limit"].(bool); ok {
		pauseAtLimit = pal
	}
	config.PauseAtLimit = pauseAtLimit

	// Optional: initial_time (renamed to initial_time)
	initialTime := time.Duration(0)
	if initTime, ok := msg.Payload["initial_time"].(float64); ok {
		initialTime = time.Duration(initTime) * time.Millisecond
	}
	config.InitialTime = initialTime

	// Optional: metadata
	if metadata, ok := msg.Payload["metadata"].(map[string]interface{}); ok {
		config.Metadata = metadata
	} else {
		config.Metadata = make(map[string]interface{})
	}

	// Store original timer_id in metadata
	config.Metadata["timer_id"] = timerID
	config.Metadata["creator"] = msg.From

	// Set update interval: prefer per-timer value from payload, fallback to plugin config
	if intervalMs, ok := msg.Payload["update_interval_ms"].(float64); ok && intervalMs > 0 {
		config.UpdateInterval = time.Duration(intervalMs) * time.Millisecond
	} else if p.config.UpdateInterval > 0 {
		config.UpdateInterval = time.Duration(p.config.UpdateInterval) * time.Millisecond
	}

	// Setup callbacks
	config.Callbacks = &Callbacks{
		OnStart: func(elapsedTime time.Duration, internalID string) {
			p.broadcastTimerStarted(internalID, timerID, elapsedTime)
		},
		OnSecondTick: func(elapsedTime time.Duration, internalID string) {
			p.broadcastTimerUpdated(internalID, timerID, elapsedTime)
		},
		OnPause: func(elapsedTime time.Duration, internalID string) {
			p.broadcastTimerPaused(internalID, timerID, elapsedTime)
		},
		OnLimit: func(elapsedTime time.Duration, internalID string) {
			p.broadcastLimitReached(internalID, timerID, elapsedTime)
		},
	}

	// Create timer
	internalID := p.manager.Create(config)

	// Get timer state after creation
	timerState, _ := p.manager.GetState(internalID)

	// Send timer_created response
	p.hubClient.Send(&Message{
		From: p.ID,
		To:   msg.From,
		Type: "timer_created",
		Payload: map[string]interface{}{
			"timer_id":     timerID,
			"internal_id":  internalID,
			"initial_time": initialTime.Milliseconds(),
			"state":        string(timerState.State),
			"limit":        timerState.Limit.Milliseconds(),
		},
	})

	// log.Printf("✅ Timer created: %s (internal: %s, initial_time: %dms)", timerID, internalID, initialTime.Milliseconds())
}

func (p *Plugin) handleStartTimer(msg *Message) {
	var timerIDs []string

	// Handle single timer or array
	if id, ok := msg.Payload["timer_id"].(string); ok {
		timerIDs = []string{id}
	} else if ids, ok := msg.Payload["timer_id"].([]interface{}); ok {
		for _, id := range ids {
			if str, ok := id.(string); ok {
				timerIDs = append(timerIDs, str)
			}
		}
	} else {
		p.sendError(msg.From, "start_timer", "timer_id is required (string or array)")
		return
	}

	// Start all timers
	for _, timerID := range timerIDs {
		internalID := p.findInternalID(timerID)
		if internalID == "" {
			p.sendError(msg.From, "start_timer", fmt.Sprintf("timer %s not found", timerID))
			continue
		}

		if err := p.manager.Start(internalID); err != nil {
			p.sendError(msg.From, "start_timer", fmt.Sprintf("%s: %s", timerID, err.Error()))
			continue
		}

		log.Printf("▶️  Timer started: %s", timerID)
	}
}

func (p *Plugin) handlePauseTimer(msg *Message) {
	timerID, ok := msg.Payload["timer_id"].(string)
	if !ok {
		p.sendError(msg.From, "pause_timer", "timer_id is required")
		return
	}

	internalID := p.findInternalID(timerID)
	if internalID == "" {
		p.sendError(msg.From, "pause_timer", fmt.Sprintf("timer %s not found", timerID))
		return
	}

	if err := p.manager.Pause(internalID); err != nil {
		p.sendError(msg.From, "pause_timer", err.Error())
		return
	}

	log.Printf("⏸️  Timer paused: %s", timerID)
}

func (p *Plugin) handleResumeTimer(msg *Message) {
	timerID, ok := msg.Payload["timer_id"].(string)
	if !ok {
		p.sendError(msg.From, "resume_timer", "timer_id is required")
		return
	}

	internalID := p.findInternalID(timerID)
	if internalID == "" {
		p.sendError(msg.From, "resume_timer", fmt.Sprintf("timer %s not found", timerID))
		return
	}

	if err := p.manager.Resume(internalID); err != nil {
		p.sendError(msg.From, "resume_timer", err.Error())
		return
	}

	// Broadcast resume to all receivers (main_module + overlays)
	timerInfo, err := p.manager.GetState(internalID)
	if err == nil {
		var limitMs interface{}
		if timerInfo.Limit > 0 {
			limitMs = timerInfo.Limit.Milliseconds()
		}
		p.hubClient.Send(&Message{
			From: p.ID,
			To:   "broadcast:timer_update_receiver",
			Type: "timer_resumed",
			Payload: map[string]interface{}{
				"timer_id":     timerID,
				"elapsed_time": timerInfo.ElapsedTime.Milliseconds(),
				"initial_time": timerInfo.InitialTime.Milliseconds(),
				"limit":        limitMs,
				"state":        "running",
			},
		})
	}

	log.Printf("▶️  Timer resumed: %s", timerID)
}

func (p *Plugin) handleResetTimer(msg *Message) {
	timerID, ok := msg.Payload["timer_id"].(string)
	if !ok {
		p.sendError(msg.From, "reset_timer", "timer_id is required")
		return
	}

	internalID := p.findInternalID(timerID)
	if internalID == "" {
		p.sendError(msg.From, "reset_timer", fmt.Sprintf("timer %s not found", timerID))
		return
	}

	if err := p.manager.Reset(internalID); err != nil {
		p.sendError(msg.From, "reset_timer", err.Error())
		return
	}

	// Get state and broadcast
	timerInfo, err := p.manager.GetState(internalID)
	if err == nil {
		var limitMs interface{}
		if timerInfo.Limit > 0 {
			limitMs = timerInfo.Limit.Milliseconds()
		}
		p.hubClient.Send(&Message{
			From: p.ID,
			To:   "broadcast:timer_update_receiver",
			Type: "timer_reset",
			Payload: map[string]interface{}{
				"timer_id":     timerID,
				"elapsed_time": timerInfo.ElapsedTime.Milliseconds(),
				"initial_time": timerInfo.InitialTime.Milliseconds(),
				"limit":        limitMs,
				"state":        "idle",
			},
		})
	}

	log.Printf("🔄 Timer reset: %s", timerID)
}

func (p *Plugin) handleAdjustTime(msg *Message) {
	timerID, ok := msg.Payload["timer_id"].(string)
	if !ok {
		p.sendError(msg.From, "adjust_time", "timer_id is required")
		return
	}

	delta, ok := msg.Payload["delta"].(float64)
	if !ok {
		p.sendError(msg.From, "adjust_time", "delta is required")
		return
	}

	internalID := p.findInternalID(timerID)
	if internalID == "" {
		p.sendError(msg.From, "adjust_time", fmt.Sprintf("timer %s not found", timerID))
		return
	}

	deltaTime := time.Duration(delta) * time.Millisecond
	if err := p.manager.AdjustTime(internalID, deltaTime); err != nil {
		p.sendError(msg.From, "adjust_time", err.Error())
		return
	}

	// Get state and broadcast
	timerInfo, err := p.manager.GetState(internalID)
	if err == nil {
		var limitMs interface{}
		if timerInfo.Limit > 0 {
			limitMs = timerInfo.Limit.Milliseconds()
		}
		p.hubClient.Send(&Message{
			From: p.ID,
			To:   "broadcast:timer_update_receiver",
			Type: "timer_adjusted",
			Payload: map[string]interface{}{
				"timer_id":     timerID,
				"elapsed_time": timerInfo.ElapsedTime.Milliseconds(),
				"initial_time": timerInfo.InitialTime.Milliseconds(),
				"limit":        limitMs,
				"state":        string(timerInfo.State),
			},
		})
	}

	log.Printf("⏱️  Timer adjusted: %s (%+dms)", timerID, int64(delta))
}

func (p *Plugin) handleSetElapsedTime(msg *Message) {
	timerID, ok := msg.Payload["timer_id"].(string)
	if !ok {
		p.sendError(msg.From, "set_elapsed_time", "timer_id is required")
		return
	}

	// Support both elapsed_time and elapsed_time
	var elapsedMs float64
	if val, ok := msg.Payload["elapsed_time"].(float64); ok {
		elapsedMs = val
	} else {
		p.sendError(msg.From, "set_elapsed_time", "elapsed_time or elapsed_time is required")
		return
	}

	internalID := p.findInternalID(timerID)
	if internalID == "" {
		p.sendError(msg.From, "set_elapsed_time", fmt.Sprintf("timer %s not found", timerID))
		return
	}

	newElapsed := time.Duration(elapsedMs) * time.Millisecond
	if err := p.manager.SetElapsedTime(internalID, newElapsed); err != nil {
		p.sendError(msg.From, "set_elapsed_time", err.Error())
		return
	}

	// Broadcast new state to all receivers
	timerInfo, err := p.manager.GetState(internalID)
	if err == nil {
		var limitMs interface{}
		if timerInfo.Limit > 0 {
			limitMs = timerInfo.Limit.Milliseconds()
		}
		p.hubClient.Send(&Message{
			From: p.ID,
			To:   "broadcast:timer_update_receiver",
			Type: "timer_updated",
			Payload: map[string]interface{}{
				"timer_id":     timerID,
				"elapsed_time": timerInfo.ElapsedTime.Milliseconds(),
				"initial_time": timerInfo.InitialTime.Milliseconds(),
				"limit":        limitMs,
				"state":        string(timerInfo.State),
			},
		})
	}

	log.Printf("⏱️  Timer time set: %s (%dms)", timerID, int64(elapsedMs))
}

func (p *Plugin) handleGetTimerState(msg *Message) {
	timerID, ok := msg.Payload["timer_id"].(string)
	if !ok {
		p.sendError(msg.From, "get_timer_state", "timer_id is required")
		return
	}

	internalID := p.findInternalID(timerID)
	if internalID == "" {
		p.sendError(msg.From, "get_timer_state", fmt.Sprintf("timer %s not found", timerID))
		return
	}

	timerInfo, err := p.manager.GetState(internalID)
	if err != nil {
		p.sendError(msg.From, "get_timer_state", err.Error())
		return
	}

	// Broadcast to all timer_state_receiver clients
	p.hubClient.Send(&Message{
		From: p.ID,
		To:   "broadcast:timer_state_receiver",
		Type: "timer_state",
		Payload: map[string]interface{}{
			"timer_id": timerID,
			"state":    p.convertTimerInfo(timerInfo, timerID),
		},
	})
}

func (p *Plugin) handleGetAllTimers(msg *Message) {
	allTimers := p.manager.GetAllTimers()

	states := make([]map[string]interface{}, 0, len(allTimers))
	for _, timerInfo := range allTimers {
		externalID := timerInfo.ID
		if id, ok := timerInfo.Metadata["timer_id"].(string); ok {
			externalID = id
		}

		states = append(states, p.convertTimerInfo(timerInfo, externalID))
	}

	p.hubClient.Send(&Message{
		From: p.ID,
		To:   msg.From,
		Type: "all_timers",
		Payload: map[string]interface{}{
			"timers": states,
			"count":  len(states),
		},
	})
}

func (p *Plugin) handleRemoveTimer(msg *Message) {
	timerID, ok := msg.Payload["timer_id"].(string)
	if !ok {
		p.sendError(msg.From, "remove_timer", "timer_id is required")
		return
	}

	internalID := p.findInternalID(timerID)
	if internalID == "" {
		p.sendError(msg.From, "remove_timer", fmt.Sprintf("timer %s not found", timerID))
		return
	}

	// Step 1: Broadcast timer_stopped to all overlay receivers before removing
	p.hubClient.Send(&Message{
		From: p.ID,
		To:   "broadcast:timer_state_receiver",
		Type: "timer_updated",
		Payload: map[string]interface{}{
			"timer_id": timerID,
			"state":    "stopped",
		},
	})

	// Step 2: Remove timer (stops goroutine and deletes from map)
	if err := p.manager.Remove(internalID); err != nil {
		p.sendError(msg.From, "remove_timer", err.Error())
		return
	}

	// Step 3: Confirm removal to the requester
	p.hubClient.Send(&Message{
		From: p.ID,
		To:   msg.From,
		Type: "timer_removed",
		Payload: map[string]interface{}{
			"timer_id": timerID,
			"state":    "stopped",
		},
	})

	log.Printf("🗑️  Timer removed: %s", timerID)
}

func (p *Plugin) handlePing(msg *Message) {
	p.hubClient.Send(&Message{
		From: p.ID,
		To:   msg.From,
		Type: "pong",
		Payload: map[string]interface{}{
			"plugin_id": p.ID,
			"timestamp": time.Now().Unix(),
		},
	})
}

// ============================================================================
// BROADCAST METHODS
// ============================================================================

func (p *Plugin) broadcastTimerStarted(internalID, externalID string, _ time.Duration) {
	timerInfo, err := p.manager.GetState(internalID)
	if err != nil {
		return
	}
	var limitMs interface{}
	if timerInfo.Limit > 0 {
		limitMs = timerInfo.Limit.Milliseconds()
	}
	p.hubClient.Send(&Message{
		From: p.ID,
		To:   "broadcast:timer_update_receiver",
		Type: "timer_started",
		Payload: map[string]interface{}{
			"timer_id":     externalID,
			"elapsed_time": timerInfo.ElapsedTime.Milliseconds(),
			"initial_time": timerInfo.InitialTime.Milliseconds(),
			"limit":        limitMs,
			"state":        string(timerInfo.State),
		},
	})
	log.Printf("📤 [STARTED] %s: elapsed=%dms initial=%dms", externalID, timerInfo.ElapsedTime.Milliseconds(), timerInfo.InitialTime.Milliseconds())

	// After 100ms send a follow-up update with the actual elapsed_time —
	// the initial broadcast fires before the ticker has ticked even once,
	// so the UI receives a stale value on slow connections.
	go func() {
		time.Sleep(100 * time.Millisecond)
		p.broadcastTimerUpdated(internalID, externalID, 0)
	}()
}

func (p *Plugin) broadcastTimerUpdated(internalID, externalID string, _ time.Duration) {
	timerInfo, err := p.manager.GetState(internalID)
	if err != nil {
		return
	}
	var limitMs interface{}
	if timerInfo.Limit > 0 {
		limitMs = timerInfo.Limit.Milliseconds()
	}
	p.hubClient.Send(&Message{
		From: p.ID,
		To:   "broadcast:timer_update_receiver",
		Type: "timer_updated",
		Payload: map[string]interface{}{
			"timer_id":     externalID,
			"elapsed_time": timerInfo.ElapsedTime.Milliseconds(),
			"initial_time": timerInfo.InitialTime.Milliseconds(),
			"limit":        limitMs,
			"state":        string(timerInfo.State),
		},
	})
	// log.Printf("📤 [TICK] %s: %dms", externalID, timerInfo.ElapsedTime.Milliseconds())
}

func (p *Plugin) broadcastTimerPaused(internalID, externalID string, _ time.Duration) {
	timerInfo, err := p.manager.GetState(internalID)
	if err != nil {
		return
	}
	var limitMs interface{}
	if timerInfo.Limit > 0 {
		limitMs = timerInfo.Limit.Milliseconds()
	}
	p.hubClient.Send(&Message{
		From: p.ID,
		To:   "broadcast:timer_update_receiver",
		Type: "timer_paused",
		Payload: map[string]interface{}{
			"timer_id":     externalID,
			"elapsed_time": timerInfo.ElapsedTime.Milliseconds(),
			"initial_time": timerInfo.InitialTime.Milliseconds(),
			"limit":        limitMs,
			"state":        string(timerInfo.State),
		},
	})
	log.Printf("📤 [PAUSED] %s: elapsed=%dms initial=%dms", externalID, timerInfo.ElapsedTime.Milliseconds(), timerInfo.InitialTime.Milliseconds())
}

func (p *Plugin) broadcastLimitReached(internalID, externalID string, _ time.Duration) {
	timerInfo, err := p.manager.GetState(internalID)
	if err != nil {
		return
	}
	var limitMs interface{}
	if timerInfo.Limit > 0 {
		limitMs = timerInfo.Limit.Milliseconds()
	}
	p.hubClient.Send(&Message{
		From: p.ID,
		To:   "broadcast:timer_update_receiver",
		Type: "limit_reached",
		Payload: map[string]interface{}{
			"timer_id":       externalID,
			"elapsed_time":   timerInfo.ElapsedTime.Milliseconds(),
			"initial_time":   timerInfo.InitialTime.Milliseconds(),
			"limit":          limitMs,
			"state":          string(timerInfo.State),
			"pause_at_limit": timerInfo.PauseAtLimit,
		},
	})
	log.Printf("⏱️  Timer %s reached limit (elapsed=%dms initial=%dms)", externalID, timerInfo.ElapsedTime.Milliseconds(), timerInfo.InitialTime.Milliseconds())
}

// ============================================================================
// HELPER METHODS
// ============================================================================

func (p *Plugin) findInternalID(externalID string) string {
	allTimers := p.manager.GetAllTimers()
	for _, timer := range allTimers {
		if id, ok := timer.Metadata["timer_id"].(string); ok && id == externalID {
			return timer.ID
		}
	}
	return ""
}

func (p *Plugin) convertTimerInfo(info *TimerInfo, externalID string) map[string]interface{} {
	var limitMs interface{}
	if info.Limit > 0 {
		limitMs = info.Limit.Milliseconds()
	}
	return map[string]interface{}{
		"timer_id":          externalID,
		"internal_id":       info.ID,
		"elapsed_time":      info.ElapsedTime.Milliseconds(),
		"initial_time":      info.InitialTime.Milliseconds(),
		"limit":             limitMs,
		"state":             string(info.State),
		"timer_type":        string(info.Type),
		"parent_id":         info.ParentID,
		"metadata":          info.Metadata,
		"has_reached_limit": info.HasReachedLimit,
	}
}

func (p *Plugin) sendError(to, operation, message string) {
	p.hubClient.Send(&Message{
		From: p.ID,
		To:   to,
		Type: "error",
		Payload: map[string]interface{}{
			"operation": operation,
			"error":     message,
		},
	})

	log.Printf("❌ Error in %s: %s", operation, message)
}
