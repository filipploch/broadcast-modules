package main

import (
	"fmt"
	"log"
	"os"
	"os/exec"
	"sort"
	"sync"
	"time"
)

// StreamConfig holds the settings used to send camera feeds to Windows.
// Port is no longer part of this struct — each camera streams on its own
// port (see StreamManager's ports map), since all configured cameras can be
// streamed to Windows at the same time.
type StreamConfig struct {
	Host     string // Windows machine IP/hostname — required for streaming to work
	Protocol string // only "srt" is implemented for now
	Codec    string // "libx264" (default, works everywhere) or e.g. "h264_qsv" on hardware that has it
	Bitrate  string // e.g. "4M"
}

// streamProc tracks one camera's running streaming ffmpeg process.
type streamProc struct {
	cmd          *exec.Cmd
	cmdDone      chan struct{}
	expectedStop bool
}

// StreamManager sends camera feeds to a Windows machine, each camera read
// from its own v4l2loopback device (see CameraConfig.LoopbackDevice) and
// sent on its own port, entirely independent of CameraRecorder — starting,
// stopping or restarting a stream never touches recording. Unlike the
// earlier single-active-stream design, StreamManager now runs one process
// per camera concurrently, so every camera that is recording (and has a
// loopback + port configured) can be watched live at the same time; a
// camera that isn't recording, or was never enabled, simply has no stream
// running for it.
type StreamManager struct {
	loopbacks   map[string]string // cameraID -> loopback device path
	ports       map[string]int    // cameraID -> destination port on the Windows host
	isRecording func(cameraID string) bool
	cfg         StreamConfig

	opMu sync.Mutex // serializes Start/Stop for a consistent view of `streams`

	mu      sync.Mutex
	streams map[string]*streamProc // cameraID -> active process (absent = not streaming)

	onStreamChanged func(cameraID string, active bool, errMsg string)
}

// NewStreamManager creates a StreamManager. loopbacks maps camera ID to its
// configured loopback device path; ports maps camera ID to the port its
// stream is sent to on the Windows host (cameras missing from either map
// simply can't be streamed — StartStream fails with a clear error).
// isRecording is consulted before starting a stream, since the loopback
// only has data while the camera's own recording ffmpeg process is running.
func NewStreamManager(loopbacks map[string]string, ports map[string]int, isRecording func(cameraID string) bool, cfg StreamConfig) *StreamManager {
	return &StreamManager{
		loopbacks:   loopbacks,
		ports:       ports,
		isRecording: isRecording,
		cfg:         cfg,
		streams:     make(map[string]*streamProc),
	}
}

// SetOnStreamChanged registers a callback invoked whenever a camera's stream
// starts, stops (requested) or stops unexpectedly (errMsg non-empty then).
func (sm *StreamManager) SetOnStreamChanged(fn func(cameraID string, active bool, errMsg string)) {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	sm.onStreamChanged = fn
}

// ActiveCameras returns the IDs of every camera currently streaming, sorted
// for deterministic output.
func (sm *StreamManager) ActiveCameras() []string {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	ids := make([]string, 0, len(sm.streams))
	for id := range sm.streams {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids
}

// IsStreaming reports whether the given camera currently has an active
// stream to Windows.
func (sm *StreamManager) IsStreaming(cameraID string) bool {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	_, ok := sm.streams[cameraID]
	return ok
}

// ConfiguredCameras returns the IDs of every camera that has both a
// loopback device and a stream port configured — i.e. every camera that
// StartStream can act on — sorted for deterministic output. This does not
// mean they're currently streaming; see ActiveCameras/IsStreaming for that.
func (sm *StreamManager) ConfiguredCameras() []string {
	ids := make([]string, 0, len(sm.loopbacks))
	for id, device := range sm.loopbacks {
		if device == "" {
			continue
		}
		if port, ok := sm.ports[id]; !ok || port == 0 {
			continue
		}
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids
}

// StartStream begins streaming cameraID to Windows on its configured port.
// Starting a camera that is already streaming is a no-op success. Other
// cameras' streams are never touched — every camera streams independently.
func (sm *StreamManager) StartStream(cameraID string) error {
	sm.opMu.Lock()
	defer sm.opMu.Unlock()

	sm.mu.Lock()
	if _, active := sm.streams[cameraID]; active {
		sm.mu.Unlock()
		log.Printf("📡 [stream/%s] already streaming — nothing to do", cameraID)
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
	port, ok := sm.ports[cameraID]
	if !ok || port == 0 {
		return fmt.Errorf("camera %s has no stream port assigned — streaming unavailable", cameraID)
	}
	if sm.isRecording != nil && !sm.isRecording(cameraID) {
		return fmt.Errorf("camera %s is not recording — its loopback has no data to stream", cameraID)
	}

	if err := sm.launch(cameraID, device, port); err != nil {
		return err
	}

	log.Printf("📡 [stream/%s] now streaming → %s:%d", cameraID, sm.cfg.Host, port)

	sm.mu.Lock()
	cb := sm.onStreamChanged
	sm.mu.Unlock()
	if cb != nil {
		cb(cameraID, true, "")
	}
	return nil
}

// StopStream stops the given camera's stream. A no-op (not an error) if that
// camera isn't currently streaming.
func (sm *StreamManager) StopStream(cameraID string) error {
	sm.opMu.Lock()
	defer sm.opMu.Unlock()

	sm.mu.Lock()
	_, hadStream := sm.streams[cameraID]
	sm.mu.Unlock()

	if err := sm.stopLocked(cameraID); err != nil {
		return err
	}

	if hadStream {
		sm.mu.Lock()
		cb := sm.onStreamChanged
		sm.mu.Unlock()
		if cb != nil {
			cb(cameraID, false, "")
		}
	}
	return nil
}

// StopAllStreams stops every currently active stream. Called on plugin
// shutdown and available for a "stop everything" hub command.
func (sm *StreamManager) StopAllStreams() {
	for _, id := range sm.ActiveCameras() {
		if err := sm.StopStream(id); err != nil {
			log.Printf("⚠️  [stream/%s] StopAllStreams: %v", id, err)
		}
	}
}

// launch starts the ffmpeg process reading from the given loopback device
// and sending it to sm.cfg.Host:port over SRT. Caller must hold opMu.
func (sm *StreamManager) launch(cameraID, device string, port int) error {
	codec := sm.cfg.Codec
	if codec == "" {
		codec = "libx264"
	}
	bitrate := sm.cfg.Bitrate
	if bitrate == "" {
		bitrate = "4M"
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
	proc := &streamProc{cmd: cmd, cmdDone: doneCh}

	sm.mu.Lock()
	sm.streams[cameraID] = proc
	sm.mu.Unlock()

	log.Printf("🎥 [stream/%s] ffmpeg started (pid %d) reading %s → %s", cameraID, cmd.Process.Pid, device, dest)

	go func() {
		waitErr := cmd.Wait()

		sm.mu.Lock()
		wasExpected := proc.expectedStop
		stillActive := sm.streams[cameraID] == proc
		if stillActive {
			delete(sm.streams, cameraID)
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

// stopLocked stops cameraID's active stream process, if any. Caller must
// hold opMu (but not mu).
func (sm *StreamManager) stopLocked(cameraID string) error {
	sm.mu.Lock()
	proc := sm.streams[cameraID]
	if proc == nil || proc.cmd == nil || proc.cmd.Process == nil {
		sm.mu.Unlock()
		return nil
	}
	proc.expectedStop = true
	sm.mu.Unlock()

	log.Printf("🛑 [stream/%s] Sending SIGINT to ffmpeg (pid %d)", cameraID, proc.cmd.Process.Pid)
	if err := proc.cmd.Process.Signal(os.Interrupt); err != nil {
		log.Printf("⚠️  [stream/%s] SIGINT failed: %v — trying SIGKILL", cameraID, err)
		_ = proc.cmd.Process.Kill()
	}

	select {
	case <-proc.cmdDone:
		log.Printf("✅ [stream/%s] ffmpeg exited cleanly", cameraID)
	case <-time.After(5 * time.Second):
		log.Printf("⚠️  [stream/%s] ffmpeg did not exit in 5 s — killing", cameraID)
		_ = proc.cmd.Process.Kill()
		<-proc.cmdDone
	}

	sm.mu.Lock()
	if sm.streams[cameraID] == proc {
		delete(sm.streams, cameraID)
	}
	sm.mu.Unlock()
	return nil
}
