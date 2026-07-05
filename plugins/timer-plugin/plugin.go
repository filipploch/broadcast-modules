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
	case "ensure_timer":
		p.handleEnsureTimer(msg)
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

// buildTimerConfig constructs a TimerConfig from a hub message payload.
// timerID is used as the timer's external (and now internal) ID.
func (p *Plugin) buildTimerConfig(msg *Message, timerID string) TimerConfig {
	timerType, _ := msg.Payload["timer_type"].(string)
	if timerType == "" {
		timerType = "independent"
	}

	config := TimerConfig{Type: TimerType(timerType)}

	if parentID, ok := msg.Payload["parent_id"].(string); ok {
		config.ParentID = parentID
	}

	if limitTime, ok := msg.Payload["limit"].(float64); ok {
		config.Limit = time.Duration(limitTime) * time.Millisecond
	}

	if pal, ok := msg.Payload["pause_at_limit"].(bool); ok {
		config.PauseAtLimit = pal
	}

	if initTime, ok := msg.Payload["initial_time"].(float64); ok {
		config.InitialTime = time.Duration(initTime) * time.Millisecond
	}

	if metadata, ok := msg.Payload["metadata"].(map[string]interface{}); ok {
		config.Metadata = metadata
	} else {
		config.Metadata = make(map[string]interface{})
	}
	config.Metadata["timer_id"] = timerID
	config.Metadata["creator"] = msg.From

	if intervalMs, ok := msg.Payload["update_interval_ms"].(float64); ok && intervalMs > 0 {
		config.UpdateInterval = time.Duration(intervalMs) * time.Millisecond
	} else if p.config.UpdateInterval > 0 {
		config.UpdateInterval = time.Duration(p.config.UpdateInterval) * time.Millisecond
	}

	config.Callbacks = &Callbacks{
		OnStart: func(_ time.Duration, id string) {
			p.broadcastTimerStarted(id, id, 0)
		},
		OnSecondTick: func(elapsedTime time.Duration, id string) {
			p.broadcastTimerUpdated(id, id, elapsedTime)
		},
		OnPause: func(_ time.Duration, id string) {
			p.broadcastTimerPaused(id, id, 0)
		},
		OnLimit: func(_ time.Duration, id string) {
			p.broadcastLimitReached(id, id, 0)
		},
	}

	return config
}

func (p *Plugin) handleCreateTimer(msg *Message) {
	timerID, ok := msg.Payload["timer_id"].(string)
	if !ok {
		p.sendError(msg.From, "create_timer", "timer_id is required")
		return
	}

	config := p.buildTimerConfig(msg, timerID)

	p.manager.Create(timerID, config)

	timerState, _ := p.manager.GetState(timerID)

	p.hubClient.Send(&Message{
		From: p.ID,
		To:   msg.From,
		Type: "timer_created",
		Payload: map[string]interface{}{
			"timer_id":     timerID,
			"internal_id":  timerID,
			"initial_time": config.InitialTime.Milliseconds(),
			"state":        string(timerState.State),
			"limit":        timerState.Limit.Milliseconds(),
		},
	})
}

func (p *Plugin) handleEnsureTimer(msg *Message) {
	timerID, ok := msg.Payload["timer_id"].(string)
	if !ok {
		p.sendError(msg.From, "ensure_timer", "timer_id is required")
		return
	}

	config := p.buildTimerConfig(msg, timerID)
	created := p.manager.Ensure(timerID, config)

	timerState, err := p.manager.GetState(timerID)
	if err != nil {
		p.sendError(msg.From, "ensure_timer", err.Error())
		return
	}

	var limitMs interface{}
	if timerState.Limit > 0 {
		limitMs = timerState.Limit.Milliseconds()
	}

	p.hubClient.Send(&Message{
		From: p.ID,
		To:   msg.From,
		Type: "timer_ensured",
		Payload: map[string]interface{}{
			"timer_id":     timerID,
			"created":      created,
			"initial_time": timerState.InitialTime.Milliseconds(),
			"state":        string(timerState.State),
			"limit":        limitMs,
			"elapsed_time": timerState.ElapsedTime.Milliseconds(),
		},
	})

	log.Printf("✅ Timer ensured: %s (created=%v)", timerID, created)
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
		if err := p.manager.Start(timerID); err != nil {
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

	if err := p.manager.Pause(timerID); err != nil {
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

	if err := p.manager.Resume(timerID); err != nil {
		p.sendError(msg.From, "resume_timer", err.Error())
		return
	}

	// Broadcast resume to all receivers (main_module + overlays)
	timerInfo, err := p.manager.GetState(timerID)
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

	if err := p.manager.Reset(timerID); err != nil {
		p.sendError(msg.From, "reset_timer", err.Error())
		return
	}

	// Get state and broadcast
	timerInfo, err := p.manager.GetState(timerID)
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

	deltaTime := time.Duration(delta) * time.Millisecond
	if err := p.manager.AdjustTime(timerID, deltaTime); err != nil {
		p.sendError(msg.From, "adjust_time", err.Error())
		return
	}

	// Get state and broadcast
	timerInfo, err := p.manager.GetState(timerID)
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

	newElapsed := time.Duration(elapsedMs) * time.Millisecond
	if err := p.manager.SetElapsedTime(timerID, newElapsed); err != nil {
		p.sendError(msg.From, "set_elapsed_time", err.Error())
		return
	}

	// Broadcast new state to all receivers
	timerInfo, err := p.manager.GetState(timerID)
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

	timerInfo, err := p.manager.GetState(timerID)
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
		states = append(states, p.convertTimerInfo(timerInfo, timerInfo.ID))
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
	if err := p.manager.Remove(timerID); err != nil {
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

func (p *Plugin) broadcastTimerUpdated(internalID, externalID string, elapsedTime time.Duration) {
	timerInfo, err := p.manager.GetState(internalID)
	if err != nil {
		return
	}
	var limitMs interface{}
	if timerInfo.Limit > 0 {
		limitMs = timerInfo.Limit.Milliseconds()
	}
	// Use the passed elapsedTime when non-zero (from OnSecondTick, already rounded to the
	// second boundary). Fall back to real elapsed for direct calls (e.g. post-start sync).
	reported := elapsedTime
	if reported == 0 {
		reported = timerInfo.ElapsedTime
	}
	p.hubClient.Send(&Message{
		From: p.ID,
		To:   "broadcast:timer_update_receiver",
		Type: "timer_updated",
		Payload: map[string]interface{}{
			"timer_id":     externalID,
			"elapsed_time": reported.Milliseconds(),
			"initial_time": timerInfo.InitialTime.Milliseconds(),
			"limit":        limitMs,
			"state":        string(timerInfo.State),
		},
	})
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
