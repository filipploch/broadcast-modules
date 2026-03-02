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

// RecordingMeta holds metadata written to JSON files on recording start.
// Fields marked "future" will be populated once hub sends them.
type RecordingMeta struct {
	CameraID    string `json:"camera_id"`
	CameraName  string `json:"camera_name"`
	FileName    string `json:"file_name"`    // e.g. "camera1_20060102_150405.mkv"
	FilePath    string `json:"file_path"`    // full path to .mkv
	StartedAt   string `json:"started_at"`   // RFC3339
	ServiceName string `json:"service_name"` // systemd service name
	// --- future fields populated by hub messages ---
	MatchID  string `json:"match_id,omitempty"`
	PeriodID string `json:"period_id,omitempty"`
}

// CameraConfig holds per-camera configuration loaded from config.json.
type CameraConfig struct {
	ID          string `json:"id"`           // e.g. "camera1"
	DeviceName  string `json:"device_name"`  // Debian device alias, e.g. "camera1"
	ServiceName string `json:"service_name"` // systemd service, e.g. "recorder-camera1.service"
	Enabled     bool   `json:"enabled"`
}

// CameraRecorder manages recording state for a single camera.
// It is the only object allowed to start/stop the camera's systemd service.
type CameraRecorder struct {
	config    CameraConfig
	outputDir string

	mu        sync.Mutex
	recording bool          // true while systemd service is active
	lastMeta  RecordingMeta // metadata of the most recent (or active) recording session
}

// NewCameraRecorder creates a CameraRecorder for the given camera config.
func NewCameraRecorder(cfg CameraConfig, outputDir string) *CameraRecorder {
	return &CameraRecorder{
		config:    cfg,
		outputDir: outputDir,
	}
}

// IsRecording returns true if a recording session is currently active.
func (cr *CameraRecorder) IsRecording() bool {
	cr.mu.Lock()
	defer cr.mu.Unlock()
	return cr.recording
}

// LastMeta returns the metadata of the most recent recording session.
// Safe to call after StartRecord returns nil.
func (cr *CameraRecorder) LastMeta() RecordingMeta {
	cr.mu.Lock()
	defer cr.mu.Unlock()
	return cr.lastMeta
}

// StartRecord starts the systemd recording service for this camera.
// Returns an error if recording is already active (prevents duplicate services).
// meta contains optional context fields (MatchID, PeriodID) received from hub.
func (cr *CameraRecorder) StartRecord(meta RecordingMeta) error {
	cr.mu.Lock()
	defer cr.mu.Unlock()

	if cr.recording {
		return fmt.Errorf("camera %s is already recording — ignoring start request", cr.config.ID)
	}

	now := time.Now()
	timestamp := now.Format("20060102_150405")
	fileName := fmt.Sprintf("%s_%s.mkv", cr.config.ID, timestamp)
	filePath := filepath.Join(cr.outputDir, fileName)

	// Populate metadata
	meta.CameraID = cr.config.ID
	meta.CameraName = cr.config.DeviceName
	meta.FileName = fileName
	meta.FilePath = filePath
	meta.StartedAt = now.Format(time.RFC3339)
	meta.ServiceName = cr.config.ServiceName

	// Write JSON files BEFORE starting the service so data is always consistent
	if err := cr.writeMetaFiles(meta); err != nil {
		return fmt.Errorf("failed to write metadata for camera %s: %w", cr.config.ID, err)
	}

	// Start systemd service — passes recording context via environment/drop-in
	if err := cr.startService(fileName, filePath); err != nil {
		return fmt.Errorf("failed to start service %s: %w", cr.config.ServiceName, err)
	}

	cr.recording = true
	log.Printf("▶️  [%s] Recording started → %s", cr.config.ID, fileName)
	return nil
}

// StopRecord stops the systemd recording service for this camera.
func (cr *CameraRecorder) StopRecord() error {
	cr.mu.Lock()
	defer cr.mu.Unlock()

	if !cr.recording {
		return fmt.Errorf("camera %s is not recording — ignoring stop request", cr.config.ID)
	}

	if err := cr.stopService(); err != nil {
		return fmt.Errorf("failed to stop service %s: %w", cr.config.ServiceName, err)
	}

	cr.recording = false
	log.Printf("⏹️  [%s] Recording stopped", cr.config.ID)
	return nil
}

// --- systemd helpers ---

// startService writes a systemd override with the output file path and
// starts the service. Using an override (drop-in) keeps the base .service
// file static while injecting the dynamic file name at runtime.
func (cr *CameraRecorder) startService(fileName, filePath string) error {
	// Write drop-in override so the service knows the output file path.
	// The base .service unit reads $RECORDING_FILE from the environment.
	overrideDir := fmt.Sprintf("/run/systemd/system/%s.d", cr.config.ServiceName)
	overrideFile := filepath.Join(overrideDir, "recording-env.conf")

	if err := os.MkdirAll(overrideDir, 0o755); err != nil {
		return fmt.Errorf("failed to create override dir: %w", err)
	}

	overrideContent := fmt.Sprintf("[Service]\nEnvironment=RECORDING_FILE=%s\nEnvironment=RECORDING_FILENAME=%s\n",
		filePath, fileName)

	if err := os.WriteFile(overrideFile, []byte(overrideContent), 0o644); err != nil {
		return fmt.Errorf("failed to write override: %w", err)
	}

	// Reload systemd so it picks up the new override
	if err := runCmd("systemctl", "daemon-reload"); err != nil {
		return fmt.Errorf("daemon-reload failed: %w", err)
	}

	// Start the service (will fail if it's already active — extra safety net)
	if err := runCmd("systemctl", "start", cr.config.ServiceName); err != nil {
		return fmt.Errorf("systemctl start failed: %w", err)
	}

	return nil
}

// stopService stops the systemd service and removes the drop-in override.
func (cr *CameraRecorder) stopService() error {
	if err := runCmd("systemctl", "stop", cr.config.ServiceName); err != nil {
		// Log but don't abort — service may have already stopped (e.g. crash)
		log.Printf("⚠️  [%s] systemctl stop returned error (may be already stopped): %v",
			cr.config.ID, err)
	}

	// Clean up drop-in override
	overrideDir := fmt.Sprintf("/run/systemd/system/%s.d", cr.config.ServiceName)
	if err := os.RemoveAll(overrideDir); err != nil {
		log.Printf("⚠️  [%s] Failed to remove override dir: %v", cr.config.ID, err)
	}

	return nil
}

// runCmd runs a system command and returns its combined output on error.
func runCmd(name string, args ...string) error {
	cmd := exec.Command(name, args...)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%s %v: %s", name, args, string(out))
	}
	return nil
}

// --- JSON metadata helpers ---

// currentMetaPath returns the path of the "current recording" JSON file.
// File name convention: <camera_id>_current.json
func (cr *CameraRecorder) currentMetaPath() string {
	return filepath.Join(cr.outputDir, fmt.Sprintf("%s_current.json", cr.config.ID))
}

// historyMetaPath returns the path of the "recording history" JSON file.
// File name convention: <camera_id>_history.json
func (cr *CameraRecorder) historyMetaPath() string {
	return filepath.Join(cr.outputDir, fmt.Sprintf("%s_history.json", cr.config.ID))
}

// writeMetaFiles writes recording metadata to both JSON files atomically.
//
//   - currentMetaPath  → overwritten with the single latest RecordingMeta
//   - historyMetaPath  → RecordingMeta appended to a JSON array
func (cr *CameraRecorder) writeMetaFiles(meta RecordingMeta) error {
	if err := os.MkdirAll(cr.outputDir, 0o755); err != nil {
		return fmt.Errorf("failed to create output dir: %w", err)
	}

	// 1. Overwrite current file
	if err := cr.writeCurrentMeta(meta); err != nil {
		return err
	}

	// 2. Append to history file
	if err := cr.appendHistoryMeta(meta); err != nil {
		return err
	}

	return nil
}

// writeCurrentMeta overwrites the current-recording JSON file.
func (cr *CameraRecorder) writeCurrentMeta(meta RecordingMeta) error {
	data, err := json.MarshalIndent(meta, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal current meta: %w", err)
	}

	// Write via temp file + rename for atomicity
	tmpPath := cr.currentMetaPath() + ".tmp"
	if err := os.WriteFile(tmpPath, data, 0o644); err != nil {
		return fmt.Errorf("failed to write current meta tmp: %w", err)
	}
	if err := os.Rename(tmpPath, cr.currentMetaPath()); err != nil {
		return fmt.Errorf("failed to rename current meta: %w", err)
	}

	log.Printf("📄 [%s] Current meta → %s", cr.config.ID, cr.currentMetaPath())
	return nil
}

// appendHistoryMeta appends a RecordingMeta entry to the history JSON array.
// If the file doesn't exist yet it is created with a single-element array.
func (cr *CameraRecorder) appendHistoryMeta(meta RecordingMeta) error {
	histPath := cr.historyMetaPath()

	// Read existing history (or start fresh)
	var history []RecordingMeta
	if data, err := os.ReadFile(histPath); err == nil {
		if jsonErr := json.Unmarshal(data, &history); jsonErr != nil {
			// History file corrupted — start a new one and log the issue
			log.Printf("⚠️  [%s] History file corrupted, starting fresh: %v", cr.config.ID, jsonErr)
			history = nil
		}
	}

	history = append(history, meta)

	data, err := json.MarshalIndent(history, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal history: %w", err)
	}

	// Write via temp file + rename for atomicity
	tmpPath := histPath + ".tmp"
	if err := os.WriteFile(tmpPath, data, 0o644); err != nil {
		return fmt.Errorf("failed to write history tmp: %w", err)
	}
	if err := os.Rename(tmpPath, histPath); err != nil {
		return fmt.Errorf("failed to rename history: %w", err)
	}

	log.Printf("📋 [%s] History meta  → %s (%d entries)", cr.config.ID, histPath, len(history))
	return nil
}
