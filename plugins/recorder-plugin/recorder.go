package main

import (
	"fmt"
	"log"
	"sync"
	"time"
)

// RecorderManager coordinates recording across all configured cameras.
// It owns one CameraRecorder per camera and is the single point of contact
// for start/stop commands arriving from the hub.
type RecorderManager struct {
	cameras   map[string]*CameraRecorder // keyed by CameraConfig.ID
	outputDir string
	hubClient *HubClient // used to notify main_module on recording start/stop
	streamer  *StreamManager
	mu        sync.RWMutex
}

const (
	autoRestartDelay    = 3 * time.Second // pauza przed restartem po crashu ffmpeg
	autoRestartMaxTries = 5               // max prób restartu z rzędu zanim się podda
)

// NewRecorderManager creates a RecorderManager from the loaded Config.
func NewRecorderManager(cfg Config) *RecorderManager {
	rm := &RecorderManager{
		cameras:   make(map[string]*CameraRecorder),
		outputDir: cfg.OutputDir,
	}

	segCfg := SegmentConfig{
		MinDuration: time.Duration(cfg.SegmentMinSeconds) * time.Second,
		MaxDuration: time.Duration(cfg.SegmentMaxSeconds) * time.Second,
		SignalDelay: time.Duration(cfg.SegmentSignalDelaySeconds) * time.Second,
	}

	for _, camCfg := range cfg.Cameras {
		if !camCfg.Enabled {
			log.Printf("⏭️  Camera %s is disabled — skipping", camCfg.ID)
			continue
		}
		cam := NewCameraRecorder(camCfg, cfg.OutputDir, segCfg, cfg.RecordingCodec)
		rm.cameras[camCfg.ID] = cam

		// Capture camCfg.ID for the closures below
		camID := camCfg.ID
		cam.SetOnUnexpectedStop(func(cameraID string, meta RecordingMeta) {
			rm.handleUnexpectedStop(cameraID, meta)
		})
		cam.SetOnSegmentRotated(func(meta RecordingMeta, reason string) {
			rm.notifySegmentRotated(camID, meta, reason)
		})
		log.Printf("📷 Camera registered: %s (service: %s, codec: %s, segment: min=%s max=%s delay=%s)",
			camCfg.ID, camCfg.ServiceName, cam.codec, segCfg.MinDuration, segCfg.MaxDuration, segCfg.SignalDelay)
	}

	// Every camera with a loopback_device gets its own stream port: an
	// explicit CameraConfig.StreamPort if set, otherwise the next free port
	// starting at cfg.StreamPort, assigned in camera list order so the
	// mapping is stable and predictable from config.json alone.
	loopbacks := make(map[string]string)
	ports := make(map[string]int)
	basePort := cfg.StreamPort
	if basePort == 0 {
		basePort = 9000
	}
	nextAutoPort := basePort
	for _, camCfg := range cfg.Cameras {
		if !camCfg.Enabled || camCfg.LoopbackDevice == "" {
			continue
		}
		loopbacks[camCfg.ID] = camCfg.LoopbackDevice
		if camCfg.StreamPort != 0 {
			ports[camCfg.ID] = camCfg.StreamPort
		} else {
			ports[camCfg.ID] = nextAutoPort
			nextAutoPort++
		}
	}
	streamCfg := StreamConfig{
		Host:     cfg.StreamWindowsHost,
		Protocol: cfg.StreamProtocol,
		Codec:    cfg.StreamCodec,
		Bitrate:  cfg.StreamBitrate,
	}
	rm.streamer = NewStreamManager(loopbacks, ports, func(id string) bool {
		rm.mu.RLock()
		cam, ok := rm.cameras[id]
		rm.mu.RUnlock()
		return ok && cam.IsRecording()
	}, streamCfg)
	rm.streamer.SetOnStreamChanged(func(cameraID string, active bool, errMsg string) {
		rm.notifyStreamChanged(cameraID, active, errMsg)
	})

	if streamCfg.Host == "" {
		log.Printf("⏭️  Streaming to Windows disabled — stream_windows_host not set in config")
	} else if len(loopbacks) == 0 {
		log.Printf("⏭️  Streaming to Windows configured (host=%s) but no camera has loopback_device set — nothing streamable", streamCfg.Host)
	} else {
		for _, camCfg := range cfg.Cameras {
			if port, ok := ports[camCfg.ID]; ok {
				log.Printf("📡 Streaming to Windows ready: %s → %s:%d (codec=%s)",
					camCfg.ID, streamCfg.Host, port, streamCfg.Codec)
			}
		}
	}

	return rm
}

// SetHubClient sets the hub client used for recording notifications.
// Called after the hub connection is established.
func (rm *RecorderManager) SetHubClient(hc *HubClient) {
	rm.mu.Lock()
	defer rm.mu.Unlock()
	rm.hubClient = hc
}

// notifyRecordingStarted sends a recording_started event to main_module.
func (rm *RecorderManager) notifyRecordingStarted(meta RecordingMeta) {
	rm.mu.RLock()
	hc := rm.hubClient
	rm.mu.RUnlock()

	if hc == nil {
		return
	}
	_ = hc.Send(&Message{
		To:   "main-module",
		Type: "recording_started",
		Payload: map[string]interface{}{
			"camera_id":     meta.CameraID,
			"camera_name":   meta.CameraName,
			"file_name":     meta.FileName,
			"file_path":     meta.FilePath,
			"started_at":    meta.StartedAt,
			"match_id":      meta.MatchID,
			"period_id":     meta.PeriodID,
			"session_id":    meta.SessionID,
			"segment_index": meta.SegmentIndex,
		},
	})
	log.Printf("📡 [%s] Notified main_module: recording_started", meta.CameraID)
}

// notifySegmentRotated sends a segment_rotated event to main_module after a
// segment has been rotated (new file opened, previous one cleanly closed).
// reason is "max_duration" or "signal".
func (rm *RecorderManager) notifySegmentRotated(cameraID string, meta RecordingMeta, reason string) {
	rm.mu.RLock()
	hc := rm.hubClient
	rm.mu.RUnlock()

	if hc == nil {
		return
	}
	_ = hc.Send(&Message{
		To:   "main-module",
		Type: "segment_rotated",
		Payload: map[string]interface{}{
			"camera_id":     cameraID,
			"session_id":    meta.SessionID,
			"segment_index": meta.SegmentIndex,
			"file_name":     meta.FileName,
			"file_path":     meta.FilePath,
			"started_at":    meta.StartedAt,
			"reason":        reason,
			"match_id":      meta.MatchID,
			"period_id":     meta.PeriodID,
		},
	})
	log.Printf("📡 [%s] Notified main_module: segment_rotated (segment %d, reason=%s)",
		cameraID, meta.SegmentIndex, reason)
}

// notifyStreamChanged sends a stream_changed event to main_module whenever
// streaming to Windows starts, is stopped on request, or stops unexpectedly
// (errMsg non-empty in that last case).
func (rm *RecorderManager) notifyStreamChanged(cameraID string, active bool, errMsg string) {
	rm.mu.RLock()
	hc := rm.hubClient
	rm.mu.RUnlock()

	if hc == nil {
		return
	}
	payload := map[string]interface{}{
		"camera_id": cameraID,
		"active":    active,
	}
	if errMsg != "" {
		payload["error"] = errMsg
	}
	_ = hc.Send(&Message{
		To:      "main-module",
		Type:    "stream_changed",
		Payload: payload,
	})
	log.Printf("📡 [%s] Notified main_module: stream_changed (active=%v)", cameraID, active)
}

// notifyRecordingStopped sends a recording_stopped event to main_module.
func (rm *RecorderManager) notifyRecordingStopped(cameraID string) {
	rm.mu.RLock()
	hc := rm.hubClient
	rm.mu.RUnlock()

	if hc == nil {
		return
	}
	_ = hc.Send(&Message{
		To:   "main-module",
		Type: "recording_stopped",
		Payload: map[string]interface{}{
			"camera_id": cameraID,
		},
	})
	log.Printf("📡 [%s] Notified main_module: recording_stopped", cameraID)
}

// handleUnexpectedStop is called by CameraRecorder when ffmpeg exits without
// an explicit StopRecord command. It notifies main_module and auto-restarts.
func (rm *RecorderManager) handleUnexpectedStop(cameraID string, meta RecordingMeta) {
	log.Printf("🔄 [%s] Unexpected stop detected — scheduling auto-restart", cameraID)

	// The camera's own ffmpeg (and with it, the loopback feed) just died, so
	// its stream to Windows has nothing left to read — stop it too. A
	// successful auto-restart below re-starts the stream via StartRecord.
	if err := rm.streamer.StopStream(cameraID); err != nil {
		log.Printf("⏭️  [%s] auto-stream stop after crash: %v", cameraID, err)
	}

	// Powiadom main_module z reason="crash"
	rm.mu.RLock()
	hc := rm.hubClient
	rm.mu.RUnlock()

	if hc != nil {
		_ = hc.Send(&Message{
			To:   "main-module",
			Type: "recording_stopped",
			Payload: map[string]interface{}{
				"camera_id": cameraID,
				"reason":    "crash",
			},
		})
	}

	// Auto-restart w tle
	go func() {
		for attempt := 1; attempt <= autoRestartMaxTries; attempt++ {
			log.Printf("⏳ [%s] Auto-restart attempt %d/%d in %v",
				cameraID, attempt, autoRestartMaxTries, autoRestartDelay)
			time.Sleep(autoRestartDelay)

			if err := rm.StartRecord(cameraID, meta); err != nil {
				log.Printf("❌ [%s] Auto-restart attempt %d failed: %v",
					cameraID, attempt, err)
				continue
			}

			log.Printf("✅ [%s] Auto-restart successful (attempt %d)", cameraID, attempt)

			// Powiadom main_module o wznowieniu
			rm.mu.RLock()
			hc2 := rm.hubClient
			rm.mu.RUnlock()
			if hc2 != nil {
				_ = hc2.Send(&Message{
					To:   "main-module",
					Type: "recording_restarted",
					Payload: map[string]interface{}{
						"camera_id": cameraID,
						"attempt":   attempt,
						"match_id":  meta.MatchID,
						"period_id": meta.PeriodID,
					},
				})
			}
			return
		}

		log.Printf("🛑 [%s] Auto-restart gave up after %d attempts", cameraID, autoRestartMaxTries)
		if hc != nil {
			_ = hc.Send(&Message{
				To:   "main-module",
				Type: "recording_restart_failed",
				Payload: map[string]interface{}{
					"camera_id": cameraID,
					"attempts":  autoRestartMaxTries,
				},
			})
		}
	}()
}

// StartRecord starts recording for the given camera.
// Returns an error if:
//   - the camera ID is unknown
//   - recording is already active for that camera
//   - the systemd service cannot be started
//
// On success, notifies main_module via notifyRecordingStarted() — this is
// the only call site for StartRecord (including the crash auto-restart path
// in handleUnexpectedStop), so it also covers "started recording again after
// a crash" without any extra wiring there.
func (rm *RecorderManager) StartRecord(cameraID string, meta RecordingMeta) error {
	rm.mu.RLock()
	cam, ok := rm.cameras[cameraID]
	rm.mu.RUnlock()

	if !ok {
		return fmt.Errorf("unknown camera: %s", cameraID)
	}

	if err := cam.StartRecord(meta); err != nil {
		return err
	}

	rm.notifyRecordingStarted(cam.LastMeta())

	// Auto-start this camera's stream to Windows, if configured. Streaming
	// is best-effort here: a failure (e.g. stream_windows_host unset, or no
	// loopback_device for this camera) must not fail the recording itself,
	// so it's only logged, not returned.
	if err := rm.streamer.StartStream(cameraID); err != nil {
		log.Printf("⏭️  [%s] auto-stream not started: %v", cameraID, err)
	}

	return nil
}

// StopRecord stops recording for the given camera.
// On success, notifies main_module via notifyRecordingStopped().
func (rm *RecorderManager) StopRecord(cameraID string) error {
	rm.mu.RLock()
	cam, ok := rm.cameras[cameraID]
	rm.mu.RUnlock()

	if !ok {
		return fmt.Errorf("unknown camera: %s", cameraID)
	}

	if err := cam.StopRecord(); err != nil {
		return err
	}

	rm.notifyRecordingStopped(cameraID)

	// The loopback has no data once recording ffmpeg has stopped, so stop
	// this camera's stream too (best-effort — no-op if it wasn't streaming).
	if err := rm.streamer.StopStream(cameraID); err != nil {
		log.Printf("⏭️  [%s] auto-stream stop: %v", cameraID, err)
	}

	return nil
}

// StopAll stops recording on every active camera. Called on plugin shutdown.
func (rm *RecorderManager) StopAll() {
	rm.mu.RLock()
	ids := make([]string, 0, len(rm.cameras))
	for id := range rm.cameras {
		ids = append(ids, id)
	}
	rm.mu.RUnlock()

	for _, id := range ids {
		if err := rm.StopRecord(id); err != nil {
			// "not recording" errors are expected here — log only real errors
			log.Printf("⚠️  StopAll [%s]: %v", id, err)
		}
	}

	// Belt-and-braces: StopRecord above already stops each camera's stream,
	// but this catches anything left running (e.g. a manually-started
	// stream for a camera that was never recording).
	rm.streamer.StopAllStreams()
}

// Status returns a snapshot of recording state for all cameras.
func (rm *RecorderManager) Status() map[string]bool {
	rm.mu.RLock()
	defer rm.mu.RUnlock()

	status := make(map[string]bool, len(rm.cameras))
	for id, cam := range rm.cameras {
		status[id] = cam.IsRecording()
	}
	return status
}

// HandleHubMessage processes a recording-related message received from the hub.
// Recognised message types:
//
//	"start_recording" — payload must contain "camera_id" (string)
//	                    optional: "match_id", "period_id"
//	"stop_recording"  — payload must contain "camera_id" (string)
//	"stop_all"        — stops all active recordings
//	"recording_status"— hub polls plugin for current state; plugin replies via hubClient
func (rm *RecorderManager) HandleHubMessage(msg *Message, hubClient *HubClient) {
	switch msg.Type {

	case "start_recording":
		cameraID, ok := stringField(msg.Payload, "camera_id")
		if !ok {
			log.Printf("⚠️  start_recording: missing camera_id")
			rm.replyError(hubClient, msg, "missing camera_id")
			return
		}

		meta := RecordingMeta{
			MatchID:  optStringField(msg.Payload, "match_id"),
			PeriodID: optStringField(msg.Payload, "period_id"),
		}

		if err := rm.StartRecord(cameraID, meta); err != nil {
			log.Printf("❌ start_recording [%s]: %v", cameraID, err)
			rm.replyError(hubClient, msg, err.Error())
			return
		}

		rm.replyOK(hubClient, msg, map[string]interface{}{
			"camera_id": cameraID,
			"recording": true,
		})

	case "stop_recording":
		cameraID, ok := stringField(msg.Payload, "camera_id")
		if !ok {
			log.Printf("⚠️  stop_recording: missing camera_id")
			rm.replyError(hubClient, msg, "missing camera_id")
			return
		}

		if err := rm.StopRecord(cameraID); err != nil {
			log.Printf("❌ stop_recording [%s]: %v", cameraID, err)
			rm.replyError(hubClient, msg, err.Error())
			return
		}

		rm.replyOK(hubClient, msg, map[string]interface{}{
			"camera_id": cameraID,
			"recording": false,
		})

	case "stop_all":
		rm.StopAll()
		rm.replyOK(hubClient, msg, map[string]interface{}{
			"stopped": true,
		})

	case "recording_status":
		rm.replyOK(hubClient, msg, map[string]interface{}{
			"cameras": rm.Status(),
		})

	case "mark_segment_end":
		rm.handleMarkSegmentEnd(msg, hubClient)

	case "start_stream":
		// Every configured camera can stream concurrently, so this starts
		// (or re-starts) any number of them at once. Streaming already
		// starts automatically with recording — this is for manual control.
		// payload: {"camera_id": "camera1"} or {"camera_id": "all"} or {}
		results := make(map[string]interface{})
		for _, id := range rm.streamTargets(msg.Payload) {
			if err := rm.streamer.StartStream(id); err != nil {
				log.Printf("❌ start_stream [%s]: %v", id, err)
				results[id] = map[string]interface{}{"streaming": false, "error": err.Error()}
				continue
			}
			results[id] = map[string]interface{}{"streaming": true}
		}
		if len(results) == 0 {
			rm.replyError(hubClient, msg, "no matching camera(s) to stream")
			return
		}
		rm.replyOK(hubClient, msg, map[string]interface{}{"cameras": results})

	case "stop_stream":
		// payload: {"camera_id": "camera1"} or {"camera_id": "all"} or {}
		// (defaults to "all" — stopping whatever is currently streaming)
		results := make(map[string]interface{})
		for _, id := range rm.streamTargets(msg.Payload) {
			if err := rm.streamer.StopStream(id); err != nil {
				log.Printf("❌ stop_stream [%s]: %v", id, err)
				results[id] = map[string]interface{}{"streaming": true, "error": err.Error()}
				continue
			}
			results[id] = map[string]interface{}{"streaming": false}
		}
		rm.replyOK(hubClient, msg, map[string]interface{}{"cameras": results})

	default:
		// Not a recording message — caller should handle it
	}
}

// streamTargets resolves which cameras a start_stream/stop_stream message
// applies to: a single "camera_id", or every camera known to the streamer
// (i.e. every enabled camera with a loopback_device configured) when
// camera_id is "all", empty, or absent.
func (rm *RecorderManager) streamTargets(payload map[string]interface{}) []string {
	cameraID, hasCameraID := stringField(payload, "camera_id")
	if hasCameraID && cameraID != "" && cameraID != "all" {
		return []string{cameraID}
	}
	return rm.streamer.ConfiguredCameras()
}

// handleMarkSegmentEnd processes a "mark_segment_end" hub message — a signal
// that the current segment should end (subject to SegmentConfig's minimum
// duration and delay, see CameraRecorder.MarkSegmentEnd).
//
// Expected payload:
//
//	{"camera_id": "camera1"}   — mark only that camera
//	{}  or  {"camera_id": "all"} — mark every currently recording camera
func (rm *RecorderManager) handleMarkSegmentEnd(msg *Message, hubClient *HubClient) {
	cameraID, hasCameraID := stringField(msg.Payload, "camera_id")
	single := hasCameraID && cameraID != "" && cameraID != "all"

	rm.mu.RLock()
	var targets []string
	if single {
		if _, ok := rm.cameras[cameraID]; ok {
			targets = []string{cameraID}
		}
	} else {
		for id := range rm.cameras {
			targets = append(targets, id)
		}
	}
	rm.mu.RUnlock()

	if single && len(targets) == 0 {
		log.Printf("⚠️  mark_segment_end: unknown camera: %s", cameraID)
		rm.replyError(hubClient, msg, "unknown camera: "+cameraID)
		return
	}

	results := make(map[string]interface{})
	for _, id := range targets {
		rm.mu.RLock()
		cam := rm.cameras[id]
		rm.mu.RUnlock()

		if err := cam.MarkSegmentEnd(); err != nil {
			log.Printf("⚠️  mark_segment_end [%s]: %v", id, err)
			results[id] = map[string]interface{}{"acknowledged": false, "error": err.Error()}
			continue
		}
		results[id] = map[string]interface{}{"acknowledged": true}
	}

	rm.replyOK(hubClient, msg, map[string]interface{}{"cameras": results})
}

// handleRecordingCommand handles the shared recording_command message format,
// which is compatible with the OBS WebSocket API structure.
//
// Expected payload:
//
//	{
//	  "requestType": "StartRecord" | "StopRecord",
//	  "request_id":  "<optional-unique-id>",
//	  "cameras":     {"camera1": true, "camera2": false, ...}
//	}
//
// The "cameras" map controls which physical cameras are started/stopped.
// Cameras with value true are started (StartRecord) or stopped (StopRecord).
// Cameras absent from the map or set to false are ignored.
// OBS receives the same message independently via obs-ws-plugin.
func (rm *RecorderManager) handleRecordingCommand(msg *Message, hubClient *HubClient) {
	requestType, ok := stringField(msg.Payload, "requestType")
	if !ok || requestType == "" {
		log.Printf("⚠️  recording_command: missing requestType")
		rm.replyError(hubClient, msg, "recording_command payload must contain requestType")
		return
	}

	requestID, ok := stringField(msg.Payload, "request_id")
	if !ok || requestID == "" {
		requestID = ""
	}

	// Parse cameras map: {"camera1": true/false, ...}
	// Only cameras explicitly set to true are acted upon.
	camerasRaw, hasCameras := msg.Payload["cameras"].(map[string]interface{})
	if !hasCameras {
		log.Printf("⚠️  recording_command: missing or invalid cameras map")
		rm.replyError(hubClient, msg, "recording_command payload must contain cameras map")
		return
	}

	// Build list of cameras to act on (value == true)
	var targetCameras []string
	for camID, val := range camerasRaw {
		if enabled, ok := val.(bool); ok && enabled {
			targetCameras = append(targetCameras, camID)
		}
	}

	// Optional context fields forwarded to RecordingMeta
	meta := RecordingMeta{
		MatchID:  optStringField(msg.Payload, "match_id"),
		PeriodID: optStringField(msg.Payload, "period_id"),
	}

	switch requestType {
	case "StartRecord":
		results := make(map[string]interface{})
		hasError := false
		for _, camID := range targetCameras {
			if err := rm.StartRecord(camID, meta); err != nil {
				log.Printf("❌ recording_command StartRecord [%s]: %v", camID, err)
				results[camID] = map[string]interface{}{"succes": false, "error": err.Error()}
				hasError = true
			} else {
				log.Printf("▶️  recording_command StartRecord [%s]: OK", camID)
				results[camID] = map[string]interface{}{"succes": true, "is_recording": true}
			}
		}
		if hasError {
			rm.replyError(hubClient, msg, "one or more cameras failed to start")
			// Also include per-camera results in a follow-up status field
			_ = hubClient.Send(&Message{
				To:   msg.From,
				Type: "recording_command_response",
				Payload: map[string]interface{}{
					"status":     "partial_error",
					"cameras":    results,
					"request_id": requestID,
				},
			})
		} else {
			rm.replyOK(hubClient, msg, map[string]interface{}{
				"requestType": requestType,
				"cameras":     results,
				"request_id":  requestID,
			})
		}

	case "StopRecord":
		results := make(map[string]interface{})
		hasError := false
		for _, camID := range targetCameras {
			if err := rm.StopRecord(camID); err != nil {
				log.Printf("❌ recording_command StopRecord [%s]: %v", camID, err)
				results[camID] = map[string]interface{}{"succes": false, "error": err.Error()}
				hasError = true
			} else {
				log.Printf("⏹️  recording_command StopRecord [%s]: OK", camID)
				results[camID] = map[string]interface{}{"succes": true, "is_recording": false}
			}
		}
		if hasError {
			_ = hubClient.Send(&Message{
				To:   msg.From,
				Type: "recording_command_response",
				Payload: map[string]interface{}{
					"status":     "partial_error",
					"cameras":    results,
					"request_id": requestID,
				},
			})
		} else {
			rm.replyOK(hubClient, msg, map[string]interface{}{
				"requestType": requestType,
				"cameras":     results,
				"request_id":  requestID,
			})
		}

	case "GetRecordStatus":
		// For each active camera that was requested, return the current recording
		// file path and estimated duration (file size → ms).
		// game_event_id is forwarded unchanged so the caller can correlate responses.
		gameEventID, _ := msg.Payload["game_event_id"]

		cameraResults := make(map[string]interface{})
		for _, camID := range targetCameras {
			cam, ok := rm.cameras[camID]
			if !ok {
				log.Printf("⚠️  GetRecordStatus: unknown camera: %s", camID)
				cameraResults[camID] = map[string]interface{}{
					"error": "camera not found",
				}
				continue
			}
			if !cam.IsRecording() {
				log.Printf("⚠️  GetRecordStatus: camera not recording: %s", camID)
				cameraResults[camID] = map[string]interface{}{
					"is_recording": false,
				}
				continue
			}
			meta := cam.LastMeta()
			duration := cam.OutputDuration()
			log.Printf("📊 GetRecordStatus [%s]: file=%s duration=%dms", camID, meta.FileName, duration)
			cameraResults[camID] = map[string]interface{}{
				"file_name":       meta.FileName,
				"file_path":       meta.FilePath,
				"output_duration": duration,
				"is_recording":    true,
			}
		}

		rm.replyOK(hubClient, msg, map[string]interface{}{
			"requestType":   requestType,
			"request_id":    requestID,
			"game_event_id": gameEventID,
			"cameras":       cameraResults,
		})

	case "MarkSegmentEnd":
		// Signal the end of the current segment for the given cameras.
		// Subject to SegmentConfig's minimum duration and delay — see
		// CameraRecorder.MarkSegmentEnd. Does not stop recording.
		results := make(map[string]interface{})
		for _, camID := range targetCameras {
			cam, ok := rm.cameras[camID]
			if !ok {
				log.Printf("⚠️  recording_command MarkSegmentEnd: unknown camera: %s", camID)
				results[camID] = map[string]interface{}{"acknowledged": false, "error": "camera not found"}
				continue
			}
			if err := cam.MarkSegmentEnd(); err != nil {
				log.Printf("⚠️  recording_command MarkSegmentEnd [%s]: %v", camID, err)
				results[camID] = map[string]interface{}{"acknowledged": false, "error": err.Error()}
				continue
			}
			log.Printf("🔔 recording_command MarkSegmentEnd [%s]: acknowledged", camID)
			results[camID] = map[string]interface{}{"acknowledged": true}
		}
		rm.replyOK(hubClient, msg, map[string]interface{}{
			"requestType": requestType,
			"cameras":     results,
			"request_id":  requestID,
		})

	case "StartStream":
		// Streams every camera set to true in the "cameras" map, all
		// concurrently — this never stops another camera's stream, and
		// never touches recording. Streaming already starts automatically
		// when a camera starts recording; this is for manual control.
		if len(targetCameras) == 0 {
			rm.replyError(hubClient, msg, "StartStream requires at least one camera in the cameras map")
			return
		}
		results := make(map[string]interface{})
		for _, camID := range targetCameras {
			if err := rm.streamer.StartStream(camID); err != nil {
				log.Printf("❌ recording_command StartStream [%s]: %v", camID, err)
				results[camID] = map[string]interface{}{"streaming": false, "error": err.Error()}
				continue
			}
			results[camID] = map[string]interface{}{"streaming": true}
		}
		rm.replyOK(hubClient, msg, map[string]interface{}{
			"requestType": requestType,
			"cameras":     results,
			"request_id":  requestID,
		})

	case "StopStream":
		// Stops every camera set to true in the "cameras" map; empty map
		// stops every currently-configured camera's stream.
		targets := targetCameras
		if len(targets) == 0 {
			targets = rm.streamer.ConfiguredCameras()
		}
		results := make(map[string]interface{})
		for _, camID := range targets {
			if err := rm.streamer.StopStream(camID); err != nil {
				log.Printf("❌ recording_command StopStream [%s]: %v", camID, err)
				results[camID] = map[string]interface{}{"streaming": true, "error": err.Error()}
				continue
			}
			results[camID] = map[string]interface{}{"streaming": false}
		}
		rm.replyOK(hubClient, msg, map[string]interface{}{
			"requestType": requestType,
			"cameras":     results,
			"request_id":  requestID,
		})

	default:
		log.Printf("⚠️  recording_command: unknown requestType: %s", requestType)
		rm.replyError(hubClient, msg, "unknown requestType: "+requestType)
	}
}

// --- reply helpers ---

func (rm *RecorderManager) replyOK(hc *HubClient, req *Message, payload map[string]interface{}) {
	if hc == nil {
		return
	}
	payload["status"] = "ok"
	_ = hc.Send(&Message{
		To:      req.From,
		Type:    req.Type + "_response",
		Payload: payload,
	})
}

func (rm *RecorderManager) replyError(hc *HubClient, req *Message, errMsg string) {
	if hc == nil {
		return
	}
	_ = hc.Send(&Message{
		To:   req.From,
		Type: req.Type + "_response",
		Payload: map[string]interface{}{
			"status": "error",
			"error":  errMsg,
		},
	})
}

// --- payload helpers ---

func stringField(payload map[string]interface{}, key string) (string, bool) {
	v, ok := payload[key]
	if !ok {
		return "", false
	}
	s, ok := v.(string)
	return s, ok
}

func optStringField(payload map[string]interface{}, key string) string {
	s, _ := stringField(payload, key)
	return s
}
