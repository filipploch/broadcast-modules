package main

import (
	"fmt"
	"log"
	"os"
	"os/exec"
	"sync"
	"time"
)

// StreamConfig holds the settings used to send a camera's feed to Windows.
type StreamConfig struct {
	Host     string // Windows machine IP/hostname — required for streaming to work
	Port     int    // default 9000
	Protocol string // only "srt" is implemented for now
	Codec    string // "libx264" (default, works everywhere) or e.g. "h264_qsv" on hardware that has it
	Bitrate  string // e.g. "4M"
}

// StreamManager sends ONE camera's feed to a Windows machine at a time, read
// from that camera's v4l2loopback device (see CameraConfig.LoopbackDevice) —
// entirely independent of CameraRecorder, so starting, stopping or switching
// the stream never touches recording. Switching cameras is simply: stop
// whatever is currently streaming, start the new one.
type StreamManager struct {
	loopbacks   map[string]string // cameraID -> loopback device path
	isRecording func(cameraID string) bool
	cfg         StreamConfig

	opMu sync.Mutex // serializes StartStream/StopStream so they can't interleave

	mu           sync.Mutex
	activeCamera string
	cmd          *exec.Cmd
	cmdDone      chan struct{}
	expectedStop bool

	onStreamChanged func(cameraID string, active bool, errMsg string)
}

// NewStreamManager creates a StreamManager. loopbacks maps camera ID to its
// configured loopback device path (cameras without one are simply absent —
// streaming for them fails with a clear error). isRecording is consulted
// before starting a stream, since the loopback only has data while the
// camera's own recording ffmpeg process is running.
func NewStreamManager(loopbacks map[string]string, isRecording func(cameraID string) bool, cfg StreamConfig) *StreamManager {
	return &StreamManager{
		loopbacks:   loopbacks,
		isRecording: isRecording,
		cfg:         cfg,
	}
}

// SetOnStreamChanged registers a callback invoked whenever streaming starts,
// stops (requested) or stops unexpectedly (errMsg non-empty in that case).
func (sm *StreamManager) SetOnStreamChanged(fn func(cameraID string, active bool, errMsg string)) {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	sm.onStreamChanged = fn
}

// ActiveCamera returns the camera ID currently being streamed, and whether
// any stream is active at all.
func (sm *StreamManager) ActiveCamera() (string, bool) {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	return sm.activeCamera, sm.cmd != nil
}

// StartStream begins streaming cameraID to Windows, stopping whatever camera
// was previously streaming (if any) first. Starting the same camera that is
// already streaming is a no-op success.
func (sm *StreamManager) StartStream(cameraID string) error {
	sm.opMu.Lock()
	defer sm.opMu.Unlock()

	sm.mu.Lock()
	if sm.activeCamera == cameraID && sm.cmd != nil {
		sm.mu.Unlock()
		log.Printf("📡 [stream] camera %s is already streaming — nothing to do", cameraID)
		return nil
	}
	sm.mu.Unlock()

	if sm.cfg.Host == "" {
		return fmt.Errorf("streaming not configured: stream_windows_host is empty")
	}
	device, ok := sm.loopbacks[cameraID]
	if !ok || device == "" {
		return fmt.Errorf("camera %s has no loopback_device configured — streaming unavailable", cameraID)
	}
	if sm.isRecording != nil && !sm.isRecording(cameraID) {
		return fmt.Errorf("camera %s is not recording — its loopback has no data to stream", cameraID)
	}

	// Switching cameras: stop whatever is currently active first, under the
	// same opMu we're already holding, so nothing else can race in between.
	if err := sm.stopLocked(); err != nil {
		return fmt.Errorf("failed to stop previous stream: %w", err)
	}

	if err := sm.launch(cameraID, device); err != nil {
		return err
	}

	log.Printf("📡 [stream] now streaming %s → %s:%d", cameraID, sm.cfg.Host, sm.cfg.Port)

	sm.mu.Lock()
	cb := sm.onStreamChanged
	sm.mu.Unlock()
	if cb != nil {
		cb(cameraID, true, "")
	}
	return nil
}

// StopStream stops whatever camera is currently streaming. A no-op (not an
// error) if nothing is streaming.
func (sm *StreamManager) StopStream() error {
	sm.opMu.Lock()
	defer sm.opMu.Unlock()

	sm.mu.Lock()
	prevCamera := sm.activeCamera
	hadStream := sm.cmd != nil
	sm.mu.Unlock()

	if err := sm.stopLocked(); err != nil {
		return err
	}

	if hadStream {
		sm.mu.Lock()
		cb := sm.onStreamChanged
		sm.mu.Unlock()
		if cb != nil {
			cb(prevCamera, false, "")
		}
	}
	return nil
}

// launch starts the ffmpeg process reading from the given loopback device
// and sending it to sm.cfg.Host over SRT. Caller must hold opMu.
func (sm *StreamManager) launch(cameraID, device string) error {
	codec := sm.cfg.Codec
	if codec == "" {
		codec = "libx264"
	}
	bitrate := sm.cfg.Bitrate
	if bitrate == "" {
		bitrate = "4M"
	}
	port := sm.cfg.Port
	if port == 0 {
		port = 9000
	}
	dest := fmt.Sprintf("srt://%s:%d?mode=caller", sm.cfg.Host, port)

	args := []string{
		"-f", "v4l2",
		"-i", device,
		"-c:v", codec,
		"-b:v", bitrate,
	}
	if codec == "libx264" {
		// Only meaningful for the software encoder — hardware encoders
		// (h264_qsv, h264_vaapi, ...) have their own preset semantics or
		// none at all, so we leave those to the operator via stream_codec.
		args = append(args, "-preset", "veryfast", "-tune", "zerolatency")
	}
	args = append(args, "-f", "mpegts", dest)

	cmd := exec.Command("ffmpeg", args...)
	cmd.Stdout = newPrefixedWriter(fmt.Sprintf("[stream/%s] ", cameraID))
	cmd.Stderr = newPrefixedWriter(fmt.Sprintf("[stream/%s] ", cameraID))

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("failed to start streaming ffmpeg for camera %s: %w", cameraID, err)
	}

	doneCh := make(chan struct{})

	sm.mu.Lock()
	sm.cmd = cmd
	sm.cmdDone = doneCh
	sm.activeCamera = cameraID
	sm.mu.Unlock()

	log.Printf("🎥 [stream/%s] ffmpeg started (pid %d) reading %s → %s", cameraID, cmd.Process.Pid, device, dest)

	go func() {
		waitErr := cmd.Wait()

		sm.mu.Lock()
		wasExpected := sm.expectedStop
		sm.expectedStop = false
		stillActive := sm.cmd == cmd
		if stillActive {
			sm.cmd = nil
			sm.activeCamera = ""
		}
		callback := sm.onStreamChanged
		sm.mu.Unlock()

		close(doneCh)

		if stillActive && !wasExpected {
			errMsg := "exited with status 0 (unexpected)"
			if waitErr != nil {
				errMsg = waitErr.Error()
			}
			log.Printf("❌ [stream/%s] ffmpeg exited unexpectedly: %s", cameraID, errMsg)
			if callback != nil {
				callback(cameraID, false, errMsg)
			}
		}
	}()

	return nil
}

// stopLocked stops the currently active stream process, if any. Caller must
// hold opMu (but not mu).
func (sm *StreamManager) stopLocked() error {
	sm.mu.Lock()
	cmd := sm.cmd
	doneCh := sm.cmdDone
	if cmd == nil || cmd.Process == nil {
		sm.mu.Unlock()
		return nil
	}
	sm.expectedStop = true
	sm.mu.Unlock()

	log.Printf("🛑 [stream] Sending SIGINT to ffmpeg (pid %d)", cmd.Process.Pid)
	if err := cmd.Process.Signal(os.Interrupt); err != nil {
		log.Printf("⚠️  [stream] SIGINT failed: %v — trying SIGKILL", err)
		_ = cmd.Process.Kill()
	}

	if doneCh == nil {
		return nil
	}

	select {
	case <-doneCh:
		log.Printf("✅ [stream] ffmpeg exited cleanly")
	case <-time.After(5 * time.Second):
		log.Printf("⚠️  [stream] ffmpeg did not exit in 5 s — killing")
		_ = cmd.Process.Kill()
		<-doneCh
	}

	sm.mu.Lock()
	sm.activeCamera = ""
	sm.mu.Unlock()
	return nil
}
