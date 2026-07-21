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
	mu        sync.RWMutex
}

const (
	autoRestartDelay   = 3 * time.Second // pauza przed restartem po crashu ffmpeg
	autoRestartMaxTries = 5              // max prób restartu z rzędu zanim się podda
)

// NewRecorderManager creates a RecorderManager from the loaded Config.
func NewRecorderManager(cfg Config) *RecorderManager {
	rm := &RecorderManager{
		cameras:   make(map[string]*CameraRecorder),
		outputDir: cfg.OutputDir,
	}

	for _, camCfg := range cfg.Cameras {
		if !camCfg.Enabled {
			log.Printf("⏭️  Camera %s is disabled — skipping", camCfg.ID)
			continue
		}
		cam := NewCameraRecorder(camCfg, cfg.OutputDir)
		rm.cameras[camCfg.ID] = cam

		// Capture camCfg.ID for closure
		camID := camCfg.ID
		cam.SetOnUnexpectedStop(func(cameraID string, meta RecordingMeta) {
			rm.handleUnexpectedStop(cameraID, meta)
		})
		_ = camID // used in closure above
		log.Printf("📷 Camera registered: %s (service: %s)", camCfg.ID, camCfg.ServiceName)
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
			"camera_id":   meta.CameraID,
			"camera_name": meta.CameraName,
			"file_name":   meta.FileName,
			"file_path":   meta.FilePath,
			"started_at":  meta.StartedAt,
			"match_id":    meta.MatchID,
			"period_id":   meta.PeriodID,
		},
	})
	log.Printf("📡 [%s] Notified main_module: recording_started", meta.CameraID)
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
						"camera_id":  cameraID,
						"attempt":    attempt,
						"match_id":   meta.MatchID,
						"period_id":  meta.PeriodID,
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

	default:
		// Not a recording message — caller should handle it
	}
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
