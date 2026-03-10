package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"syscall"
	"time"
)

// RecordingMeta holds metadata written to JSON files on recording start.
type RecordingMeta struct {
	CameraID    string `json:"camera_id"`
	CameraName  string `json:"camera_name"`
	FileName    string `json:"file_name"`  // e.g. "camera1_20060102_150405.mkv"
	FilePath    string `json:"file_path"`  // full path to .mkv
	StartedAt   int64  `json:"started_at"` // Unix timestamp ms
	ServiceName string `json:"service_name"`
	// --- fields populated by hub messages ---
	MatchID  string `json:"match_id,omitempty"`
	PeriodID string `json:"period_id,omitempty"`
}

// CameraConfig holds per-camera configuration loaded from config.json.
type CameraConfig struct {
	ID          string `json:"id"`           // e.g. "camera1"
	DeviceName  string `json:"device_name"`  // human-readable alias
	DevicePath  string `json:"device_path"`  // e.g. "/dev/v4l/by-id/usb-...-video-index0"
	ServiceName string `json:"service_name"` // kept for compatibility, not used for start/stop
	Enabled     bool   `json:"enabled"`
}

// CameraRecorder manages recording state for a single camera.
// It starts and stops ffmpeg directly as a child process — no systemd user
// services involved, which avoids all D-Bus / XDG_RUNTIME_DIR issues.
type CameraRecorder struct {
	config    CameraConfig
	outputDir string

	mu        sync.Mutex
	recording bool
	lastMeta  RecordingMeta
	cmd       *exec.Cmd // active ffmpeg process, nil when not recording
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
func (cr *CameraRecorder) LastMeta() RecordingMeta {
	cr.mu.Lock()
	defer cr.mu.Unlock()
	return cr.lastMeta
}

// OutputDuration returns the elapsed recording time in milliseconds.
// Calculated as: now_ms - started_at_ms. Returns 0 if not recording.
func (cr *CameraRecorder) OutputDuration() int64 {
	cr.mu.Lock()
	defer cr.mu.Unlock()
	if !cr.recording || cr.lastMeta.StartedAt == 0 {
		return 0
	}
	return time.Now().UnixMilli() - cr.lastMeta.StartedAt
}

// StartRecord starts ffmpeg for this camera.
func (cr *CameraRecorder) StartRecord(meta RecordingMeta) error {
	cr.mu.Lock()
	defer cr.mu.Unlock()

	if cr.recording {
		// Flaga mówi "nagrywa" — weryfikuj przez rzeczywisty stan procesu.
		// Goroutine w startFFmpeg zeruje flagę przy normalnym wyjściu ffmpeg,
		// ale race condition lub nieoczekiwana śmierć procesu może zostawić
		// recording=true z cr.cmd wskazującym na martwy proces.
		if cr.cmd != nil && cr.cmd.Process != nil {
			// FindProcess zawsze zwraca sukces na Linuksie — użyj Signal(0)
			// które sprawdza czy proces istnieje bez wysyłania sygnału.
			if err := cr.cmd.Process.Signal(syscall.Signal(0)); err != nil {
				// Błąd oznacza że proces nie istnieje — wyczyść stan
				log.Printf("⚠️  [%s] recording=true but ffmpeg (pid %d) is gone (%v) — clearing stale state",
					cr.config.ID, cr.cmd.Process.Pid, err)
				cr.recording = false
				cr.cmd = nil
			} else {
				return fmt.Errorf("camera %s is already recording — ignoring start request", cr.config.ID)
			}
		} else {
			// cmd == nil ale recording == true — niespójny stan, wyczyść
			log.Printf("⚠️  [%s] recording=true but cmd is nil — clearing stale state", cr.config.ID)
			cr.recording = false
		}
	}

	if cr.config.DevicePath == "" {
		return fmt.Errorf("camera %s has no device_path configured", cr.config.ID)
	}

	now := time.Now()
	timestamp := now.Format("20060102_150405")
	fileName := fmt.Sprintf("%s_%s.mkv", cr.config.ID, timestamp)
	filePath := filepath.Join(cr.outputDir, fileName)

	meta.CameraID = cr.config.ID
	meta.CameraName = cr.config.DeviceName
	meta.FileName = fileName
	meta.FilePath = filePath
	meta.StartedAt = now.UnixMilli()
	meta.ServiceName = cr.config.ServiceName

	if err := cr.writeMetaFiles(meta); err != nil {
		return fmt.Errorf("failed to write metadata for camera %s: %w", cr.config.ID, err)
	}

	if err := cr.startFFmpeg(filePath); err != nil {
		return fmt.Errorf("failed to start ffmpeg for camera %s: %w", cr.config.ID, err)
	}

	cr.recording = true
	cr.lastMeta = meta
	log.Printf("▶️  [%s] Recording started → %s", cr.config.ID, fileName)
	return nil
}

// StopRecord stops the ffmpeg process for this camera.
func (cr *CameraRecorder) StopRecord() error {
	cr.mu.Lock()
	defer cr.mu.Unlock()

	if !cr.recording {
		return fmt.Errorf("camera %s is not recording — ignoring stop request", cr.config.ID)
	}

	if err := cr.stopFFmpeg(); err != nil {
		return fmt.Errorf("failed to stop ffmpeg for camera %s: %w", cr.config.ID, err)
	}

	cr.recording = false
	log.Printf("⏹️  [%s] Recording stopped", cr.config.ID)

	// Clear current.json — recording is over, data moved to history
	if err := cr.clearCurrentMeta(); err != nil {
		log.Printf("⚠️  [%s] Failed to clear current meta: %v", cr.config.ID, err)
	}
	return nil
}

// --- ffmpeg process management ---

// startFFmpeg launches ffmpeg as a child process capturing from the v4l2 device.
//
// ffmpeg arguments:
//
//	-f v4l2              — Video4Linux2 input
//	-input_format mjpeg  — request MJPEG from camera (lower USB bandwidth than YUYV,
//	                       required for 1920x1080 @ 30 fps on most USB cameras)
//	-video_size 1920x1080
//	-framerate 30
//	-i <device>          — capture device path
//	-c:v libx264         — encode to H.264
//	-preset ultrafast    — lowest CPU usage, acceptable quality
//	-crf 23              — constant quality (18=near-lossless, 28=lower quality)
//	-an                  — no audio
//	-y                   — overwrite output without asking
func (cr *CameraRecorder) startFFmpeg(filePath string) error {
	if err := os.MkdirAll(cr.outputDir, 0o755); err != nil {
		return fmt.Errorf("failed to create output dir: %w", err)
	}

	cmd := exec.Command("ffmpeg",
		"-f", "v4l2",
		"-input_format", "mjpeg",
		"-video_size", "1920x1080",
		"-framerate", "30",
		"-i", cr.config.DevicePath,
		"-c:v", "libx264",
		"-preset", "ultrafast",
		"-crf", "23",
		"-g", "30", // keyframe co 30 klatek = co 1 sekundę (przy 30fps)
		"-keyint_min", "30", // wymusz minimalny interwał keyframe
		"-force_key_frames", "expr:gte(t,n_forced*1)", // keyframe dokładnie co 1s
		"-movflags", "+dash", // fragmentowany MKV — klastry zamykane na bieżąco
		"-cluster_size_limit", "2M", // max rozmiar klastra MKV
		"-cluster_time_limit", "1000", // lub co 1000ms — cokolwiek nastąpi pierwsze
		"-an",
		"-y",
		filePath,
	)

	cmd.Stdout = newPrefixedWriter(fmt.Sprintf("[ffmpeg/%s] ", cr.config.ID))
	cmd.Stderr = newPrefixedWriter(fmt.Sprintf("[ffmpeg/%s] ", cr.config.ID))

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("exec.Start failed: %w", err)
	}

	cr.cmd = cmd
	log.Printf("🎬 [%s] ffmpeg started (pid %d) → %s", cr.config.ID, cmd.Process.Pid, filePath)

	// Watch for unexpected ffmpeg exit in background
	go func() {
		err := cmd.Wait()

		cr.mu.Lock()
		defer cr.mu.Unlock()

		if cr.cmd != cmd {
			return
		}
		cr.cmd = nil

		if cr.recording {
			cr.recording = false
			if err != nil {
				log.Printf("❌ [%s] ffmpeg exited unexpectedly: %v", cr.config.ID, err)
			} else {
				log.Printf("⚠️  [%s] ffmpeg exited with status 0 (unexpected)", cr.config.ID)
			}
		}
	}()

	return nil
}

// stopFFmpeg sends SIGINT to ffmpeg so it flushes and finalises the MKV file,
// then waits up to 10 s for a clean exit before sending SIGKILL.
func (cr *CameraRecorder) stopFFmpeg() error {
	cmd := cr.cmd
	if cmd == nil || cmd.Process == nil {
		return nil
	}

	log.Printf("🛑 [%s] Sending SIGINT to ffmpeg (pid %d)", cr.config.ID, cmd.Process.Pid)
	if err := cmd.Process.Signal(os.Interrupt); err != nil {
		log.Printf("⚠️  [%s] SIGINT failed: %v — trying SIGKILL", cr.config.ID, err)
		cmd.Process.Kill()
		cr.cmd = nil
		return nil
	}

	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()

	select {
	case err := <-done:
		cr.cmd = nil
		if err != nil {
			log.Printf("⚠️  [%s] ffmpeg exit: %v", cr.config.ID, err)
		} else {
			log.Printf("✅ [%s] ffmpeg exited cleanly", cr.config.ID)
		}
	case <-time.After(10 * time.Second):
		log.Printf("⚠️  [%s] ffmpeg did not exit in 10 s — killing", cr.config.ID)
		cmd.Process.Kill()
		<-done
		cr.cmd = nil
	}

	return nil
}

// prefixedWriter forwards each Write call to the standard logger with a prefix.
type prefixedWriter struct{ prefix string }

func newPrefixedWriter(prefix string) *prefixedWriter { return &prefixedWriter{prefix: prefix} }

func (pw *prefixedWriter) Write(p []byte) (int, error) {
	log.Printf("%s%s", pw.prefix, p)
	return len(p), nil
}

// --- JSON metadata helpers ---

func (cr *CameraRecorder) currentMetaPath() string {
	return filepath.Join(cr.outputDir, fmt.Sprintf("%s_current.json", cr.config.ID))
}

func (cr *CameraRecorder) historyMetaPath() string {
	return filepath.Join(cr.outputDir, fmt.Sprintf("%s_history.json", cr.config.ID))
}

func (cr *CameraRecorder) writeMetaFiles(meta RecordingMeta) error {
	if err := os.MkdirAll(cr.outputDir, 0o755); err != nil {
		return fmt.Errorf("failed to create output dir: %w", err)
	}
	if err := cr.writeCurrentMeta(meta); err != nil {
		return err
	}
	return cr.appendHistoryMeta(meta)
}

// clearCurrentMeta overwrites current.json with an empty object, signalling
// that no recording is active. Called after StopRecord.
func (cr *CameraRecorder) clearCurrentMeta() error {
	tmpPath := cr.currentMetaPath() + ".tmp"
	if err := os.WriteFile(tmpPath, []byte("{}\n"), 0o644); err != nil {
		return fmt.Errorf("failed to write empty current meta: %w", err)
	}
	return os.Rename(tmpPath, cr.currentMetaPath())
}

func (cr *CameraRecorder) writeCurrentMeta(meta RecordingMeta) error {
	data, err := json.Marshal(meta)
	if err != nil {
		return fmt.Errorf("failed to marshal current meta: %w", err)
	}
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

func (cr *CameraRecorder) appendHistoryMeta(meta RecordingMeta) error {
	histPath := cr.historyMetaPath()

	var history []RecordingMeta
	if data, err := os.ReadFile(histPath); err == nil {
		if jsonErr := json.Unmarshal(data, &history); jsonErr != nil {
			log.Printf("⚠️  [%s] History file corrupted, starting fresh: %v", cr.config.ID, jsonErr)
			history = nil
		}
	}

	history = append(history, meta)

	data, err := json.MarshalIndent(history, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal history: %w", err)
	}

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
