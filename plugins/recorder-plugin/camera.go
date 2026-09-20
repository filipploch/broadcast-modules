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
	FileName    string `json:"file_name"`   // e.g. "camera1_20060102_150405.mkv"
	FilePath    string `json:"file_path"`   // full path to .mkv
	StartedAt   int64  `json:"started_at"`  // Unix timestamp ms — start of THIS segment
	FinishedAt  int64  `json:"finished_at"` // Unix timestamp ms; 0 if still recording
	ServiceName string `json:"service_name"`
	// --- fields populated by hub messages ---
	MatchID  string `json:"match_id,omitempty"`
	PeriodID string `json:"period_id,omitempty"`
	// --- segmentation fields ---
	SessionID    string `json:"session_id,omitempty"`    // stable across all segments of one recording session
	SegmentIndex int    `json:"segment_index,omitempty"` // 1-based index of this segment within the session
	EndReason    string `json:"end_reason,omitempty"`    // "manual_stop" | "max_duration" | "signal" | "crash"
}

// CameraConfig holds per-camera configuration loaded from config.json.
type CameraConfig struct {
	ID          string `json:"id"`           // e.g. "camera1"
	DeviceName  string `json:"device_name"`  // human-readable alias
	DevicePath  string `json:"device_path"`  // e.g. "/dev/v4l/by-id/usb-...-video-index0"
	ServiceName string `json:"service_name"` // kept for compatibility, not used for start/stop
	Enabled     bool   `json:"enabled"`

	// LoopbackDevice, if set (e.g. "/dev/video10"), is a v4l2loopback device
	// that the recording ffmpeg process ALSO writes a raw, undecoded copy of
	// this camera's feed to (via -filter_complex split — one decode, two
	// outputs). StreamManager reads from it to send this camera's feed to
	// Windows, independently of recording. Requires the v4l2loopback kernel
	// module and this device to already exist — see README/deployment notes.
	// Leave empty to disable streaming for this camera entirely.
	LoopbackDevice string `json:"loopback_device,omitempty"`

	// StreamPort, if set, is the port this camera's stream is sent to on the
	// Windows host — each camera streams concurrently on its own port, so
	// these must be distinct across cameras. Leave at 0 to auto-assign
	// sequentially from Config.StreamPort in camera list order (see
	// NewRecorderManager), which is enough for most setups.
	StreamPort int `json:"stream_port,omitempty"`
}

// SegmentConfig controls automatic segment rotation for a recording session.
//
// A segment always ends after MaxDuration, regardless of anything else. It can
// also end earlier, triggered by an external "segment end" signal (typically a
// hub message), but only once at least MinDuration has elapsed — a signal that
// arrives earlier is queued and applied automatically the moment MinDuration is
// reached. In both cases, the actual cut happens SignalDelay after the
// triggering moment, so a few extra seconds of action are captured.
type SegmentConfig struct {
	MinDuration time.Duration // earliest a signal-triggered rotation may happen
	MaxDuration time.Duration // hard cap — always rotates after this, signal or not
	SignalDelay time.Duration // delay applied after a signal becomes actionable
}

// CameraRecorder manages recording state for a single camera.
// It starts and stops ffmpeg directly as a child process — no systemd user
// services involved, which avoids all D-Bus / XDG_RUNTIME_DIR issues.
//
// A single "recording session" (started by StartRecord, ended by StopRecord)
// can span several consecutive files ("segments"), rotated automatically by
// rotateSegment — see SegmentConfig.
type CameraRecorder struct {
	config    CameraConfig
	outputDir string
	segCfg    SegmentConfig
	codec     string // "libx264" (default) or e.g. "h264_qsv" — see buildFFmpegArgs

	// opMu serializes the "big" state transitions (start / stop / rotate) so
	// they can never interleave — e.g. a manual stop arriving mid-rotation.
	opMu sync.Mutex

	mu           sync.Mutex
	recording    bool
	lastMeta     RecordingMeta
	cmd          *exec.Cmd     // active ffmpeg process, nil when not recording
	cmdDone      chan struct{} // closed exactly once, when cmd's single Wait() call returns
	expectedStop bool          // true = the next process exit is intentional (stop/rotation), not a crash

	sessionID        string
	segmentIndex     int
	segmentStartedAt time.Time
	segmentGen       uint64 // bumped on every segment start/stop; invalidates stale rotation timers
	pendingSignal    bool   // a segment-end signal arrived before MinDuration elapsed

	onUnexpectedStop func(cameraID string, meta RecordingMeta) // callback → RecorderManager
	onSegmentRotated func(meta RecordingMeta, reason string)   // callback → RecorderManager
}

// NewCameraRecorder creates a CameraRecorder for the given camera config.
// codec selects the recording encoder ("libx264" if empty/unrecognised —
// see buildFFmpegArgs for what changes per codec).
func NewCameraRecorder(cfg CameraConfig, outputDir string, segCfg SegmentConfig, codec string) *CameraRecorder {
	if codec == "" {
		codec = "libx264"
	}
	return &CameraRecorder{
		config:    cfg,
		outputDir: outputDir,
		segCfg:    segCfg,
		codec:     codec,
	}
}

// SetOnUnexpectedStop registers a callback invoked when ffmpeg exits unexpectedly.
// The callback receives the camera ID and last recording metadata.
func (cr *CameraRecorder) SetOnUnexpectedStop(fn func(cameraID string, meta RecordingMeta)) {
	cr.mu.Lock()
	defer cr.mu.Unlock()
	cr.onUnexpectedStop = fn
}

// SetOnSegmentRotated registers a callback invoked after a segment has been
// rotated (new file opened, previous one cleanly closed). reason is one of
// "max_duration" or "signal".
func (cr *CameraRecorder) SetOnSegmentRotated(fn func(meta RecordingMeta, reason string)) {
	cr.mu.Lock()
	defer cr.mu.Unlock()
	cr.onSegmentRotated = fn
}

// IsRecording returns true if a recording session is currently active.
func (cr *CameraRecorder) IsRecording() bool {
	cr.mu.Lock()
	defer cr.mu.Unlock()
	return cr.recording
}

// LastMeta returns the metadata of the most recent (or active) segment.
func (cr *CameraRecorder) LastMeta() RecordingMeta {
	cr.mu.Lock()
	defer cr.mu.Unlock()
	return cr.lastMeta
}

// OutputDuration returns the elapsed time of the CURRENT SEGMENT in milliseconds.
// Calculated as: now_ms - segment_started_at_ms. Returns 0 if not recording.
func (cr *CameraRecorder) OutputDuration() int64 {
	cr.mu.Lock()
	defer cr.mu.Unlock()
	if !cr.recording || cr.lastMeta.StartedAt == 0 {
		return 0
	}
	return time.Now().UnixMilli() - cr.lastMeta.StartedAt
}

// StartRecord starts a new recording session (segment 1) for this camera.
func (cr *CameraRecorder) StartRecord(meta RecordingMeta) error {
	cr.opMu.Lock()
	defer cr.opMu.Unlock()

	cr.mu.Lock()
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
				cr.mu.Unlock()
				return fmt.Errorf("camera %s is already recording — ignoring start request", cr.config.ID)
			}
		} else {
			// cmd == nil ale recording == true — niespójny stan, wyczyść
			log.Printf("⚠️  [%s] recording=true but cmd is nil — clearing stale state", cr.config.ID)
			cr.recording = false
		}
	}

	if cr.config.DevicePath == "" {
		cr.mu.Unlock()
		return fmt.Errorf("camera %s has no device_path configured", cr.config.ID)
	}
	cr.mu.Unlock()

	sessionID := fmt.Sprintf("%s_%s", cr.config.ID, time.Now().Format("20060102_150405"))
	return cr.launchSegment(meta, sessionID, 1)
}

// StopRecord stops the ffmpeg process for this camera, ending the whole
// recording session (all segments).
func (cr *CameraRecorder) StopRecord() error {
	cr.opMu.Lock()
	defer cr.opMu.Unlock()

	cr.mu.Lock()
	if !cr.recording {
		cr.mu.Unlock()
		return fmt.Errorf("camera %s is not recording — ignoring stop request", cr.config.ID)
	}
	cr.mu.Unlock()

	if err := cr.stopFFmpeg(); err != nil {
		return fmt.Errorf("failed to stop ffmpeg for camera %s: %w", cr.config.ID, err)
	}

	cr.mu.Lock()
	cr.lastMeta.FinishedAt = time.Now().UnixMilli()
	cr.lastMeta.EndReason = "manual_stop"
	finalMeta := cr.lastMeta
	cr.recording = false
	cr.pendingSignal = false
	cr.segmentGen++ // invalidate any rotation timers still pending for this segment
	cr.mu.Unlock()

	_ = cr.appendHistoryMeta(finalMeta)
	log.Printf("⏹️  [%s] Recording stopped", cr.config.ID)

	// Clear current.json — recording is over, data moved to history
	if err := cr.clearCurrentMeta(); err != nil {
		log.Printf("⚠️  [%s] Failed to clear current meta: %v", cr.config.ID, err)
	}
	return nil
}

// --- segmentation ---

// MarkSegmentEnd is called when a segment-end signal arrives (typically from
// a hub message). See SegmentConfig for the exact timing rules.
func (cr *CameraRecorder) MarkSegmentEnd() error {
	cr.mu.Lock()
	if !cr.recording {
		cr.mu.Unlock()
		return fmt.Errorf("camera %s is not recording — ignoring segment-end signal", cr.config.ID)
	}
	gen := cr.segmentGen
	elapsed := time.Since(cr.segmentStartedAt)
	minDur := cr.segCfg.MinDuration
	delay := cr.segCfg.SignalDelay
	cr.mu.Unlock()

	if elapsed >= minDur {
		log.Printf("🔔 [%s] Segment-end signal received (elapsed=%s ≥ min=%s) — rotating in %s",
			cr.config.ID, elapsed.Round(time.Second), minDur, delay)
		time.AfterFunc(delay, func() { cr.tryRotate(gen, "signal") })
		return nil
	}

	// Too early — remember the signal and apply it automatically once
	// MinDuration is reached, rather than dropping it on the floor.
	cr.mu.Lock()
	alreadyPending := cr.pendingSignal
	cr.pendingSignal = true
	cr.mu.Unlock()

	if alreadyPending {
		log.Printf("🔔 [%s] Segment-end signal received, already queued for min-duration mark", cr.config.ID)
		return nil
	}

	remaining := minDur - elapsed
	log.Printf("🔔 [%s] Segment-end signal received early (elapsed=%s < min=%s) — will apply at min-duration mark (in %s) + %s delay",
		cr.config.ID, elapsed.Round(time.Second), minDur, remaining.Round(time.Second), delay)

	time.AfterFunc(remaining, func() {
		cr.mu.Lock()
		stillPending := cr.pendingSignal && cr.segmentGen == gen
		cr.pendingSignal = false
		cr.mu.Unlock()
		if !stillPending {
			return // segment already rotated/stopped for another reason in the meantime
		}
		time.AfterFunc(delay, func() { cr.tryRotate(gen, "signal") })
	})
	return nil
}

// tryRotate rotates the segment identified by gen, unless it has already
// been rotated or stopped for another reason (stale timer/goroutine).
func (cr *CameraRecorder) tryRotate(gen uint64, reason string) {
	cr.mu.Lock()
	stillCurrent := cr.recording && cr.segmentGen == gen
	cr.mu.Unlock()
	if !stillCurrent {
		return
	}
	if err := cr.rotateSegment(reason); err != nil {
		log.Printf("❌ [%s] Segment rotation (%s) failed: %v", cr.config.ID, reason, err)
	}
}

// rotateSegment cleanly closes the current segment's ffmpeg process (SIGINT,
// same as a manual stop, so the MKV is fully finalised with its Cues index)
// and immediately opens the next segment on the same camera, under the same
// session. Recording itself is never considered "stopped" during this.
func (cr *CameraRecorder) rotateSegment(reason string) error {
	cr.opMu.Lock()
	defer cr.opMu.Unlock()

	cr.mu.Lock()
	if !cr.recording {
		cr.mu.Unlock()
		return fmt.Errorf("camera %s is not recording", cr.config.ID)
	}
	sessionID := cr.sessionID
	nextIndex := cr.segmentIndex + 1
	started := cr.segmentStartedAt
	prevMatchID := cr.lastMeta.MatchID
	prevPeriodID := cr.lastMeta.PeriodID
	cr.pendingSignal = false
	cr.mu.Unlock()

	log.Printf("🔁 [%s] Rotating segment %d → %d (reason=%s, segment duration=%s)",
		cr.config.ID, nextIndex-1, nextIndex, reason, time.Since(started).Round(time.Second))

	if err := cr.stopFFmpeg(); err != nil {
		return fmt.Errorf("failed to close current segment: %w", err)
	}

	cr.mu.Lock()
	cr.lastMeta.FinishedAt = time.Now().UnixMilli()
	cr.lastMeta.EndReason = reason
	finishedMeta := cr.lastMeta
	cr.mu.Unlock()
	_ = cr.appendHistoryMeta(finishedMeta)

	nextMeta := RecordingMeta{MatchID: prevMatchID, PeriodID: prevPeriodID}
	if err := cr.launchSegment(nextMeta, sessionID, nextIndex); err != nil {
		// Recording session is now effectively dead (no active ffmpeg) even
		// though cr.recording may still read true from a half-finished state.
		// Surface this loudly — it needs a human or the crash-recovery path.
		cr.mu.Lock()
		cr.recording = false
		cr.mu.Unlock()
		return fmt.Errorf("failed to start next segment: %w", err)
	}

	cr.mu.Lock()
	cb := cr.onSegmentRotated
	newMeta := cr.lastMeta
	cr.mu.Unlock()
	if cb != nil {
		cb(newMeta, reason)
	}

	return nil
}

// launchSegment builds the segment's file name, writes metadata, starts
// ffmpeg and arms the MaxDuration hard-rotation timer. Caller must not hold
// cr.mu or cr.opMu... actually opMu IS expected to be held by the caller
// (StartRecord / rotateSegment), to keep segment bookkeeping atomic.
func (cr *CameraRecorder) launchSegment(meta RecordingMeta, sessionID string, segmentIndex int) error {
	now := time.Now()
	timestamp := now.Format("20060102_150405")
	fileName := fmt.Sprintf("%s_%s.mkv", cr.config.ID, timestamp)
	filePath := filepath.Join(cr.outputDir, fileName)

	meta.CameraID = cr.config.ID
	meta.CameraName = cr.config.DeviceName
	meta.FileName = fileName
	meta.FilePath = filePath
	meta.StartedAt = now.UnixMilli()
	meta.FinishedAt = 0
	meta.EndReason = ""
	meta.ServiceName = cr.config.ServiceName
	meta.SessionID = sessionID
	meta.SegmentIndex = segmentIndex

	if err := cr.writeMetaFiles(meta); err != nil {
		return fmt.Errorf("failed to write metadata for camera %s: %w", cr.config.ID, err)
	}

	if err := cr.startFFmpeg(filePath); err != nil {
		return fmt.Errorf("failed to start ffmpeg for camera %s: %w", cr.config.ID, err)
	}

	cr.mu.Lock()
	cr.recording = true
	cr.lastMeta = meta
	cr.sessionID = sessionID
	cr.segmentIndex = segmentIndex
	cr.segmentStartedAt = now
	cr.pendingSignal = false
	cr.segmentGen++
	gen := cr.segmentGen
	maxDur := cr.segCfg.MaxDuration
	cr.mu.Unlock()

	log.Printf("▶️  [%s] Segment %d started (session=%s) → %s", cr.config.ID, segmentIndex, sessionID, fileName)

	if maxDur > 0 {
		time.AfterFunc(maxDur, func() { cr.tryRotate(gen, "max_duration") })
	}

	return nil
}

// --- ffmpeg process management ---

// buildFFmpegArgs builds the ffmpeg argument list for a camera's recording
// process. It is a pure function (no side effects) so it can be unit-tested
// without a real camera or ffmpeg binary.
//
// Base capture arguments:
//
//	-f v4l2              — Video4Linux2 input
//	-input_format mjpeg  — request MJPEG from camera (lower USB bandwidth than YUYV,
//	                       required for 1920x1080 @ 30 fps on most USB cameras)
//	-video_size 1920x1080
//	-framerate 30
//	-i <device>          — capture device path
//
// Recording output (always present):
//
//	-c:v <codec>          — encode to H.264 — "libx264" (software, works
//	                        everywhere) or a hardware encoder such as
//	                        "h264_qsv" on Intel Quick Sync hardware. The
//	                        exact rate-control flags differ per codec — see
//	                        the branches below — but the goal in both cases
//	                        is "good constant quality at 1080p30", not a
//	                        fixed bitrate.
//	-an                   — no audio
//	-y                    — overwrite output without asking
//
// If cfg.LoopbackDevice is set, a second output is added via -filter_complex
// split — the camera is decoded ONCE, and a raw (uncompressed) copy of the
// same frames is written to the loopback device alongside the encoded
// recording. This is what lets StreamManager read a live feed of this camera
// without opening the (exclusive-access) physical device a second time.
func buildFFmpegArgs(cfg CameraConfig, codec string, filePath string) []string {
	if codec == "" {
		codec = "libx264"
	}

	args := []string{
		"-f", "v4l2",
		"-input_format", "mjpeg",
		"-video_size", "1920x1080",
		"-framerate", "30",
		"-i", cfg.DevicePath,
	}

	if cfg.LoopbackDevice != "" {
		args = append(args,
			"-filter_complex", "[0:v]split=2[rec][stream]",
			"-map", "[rec]",
		)
	}

	args = append(args, "-c:v", codec)
	switch codec {
	case "libx264":
		args = append(args,
			"-preset", "ultrafast", // lowest CPU usage, acceptable quality
			"-crf", "23", // constant quality (18=near-lossless, 28=lower quality)
		)
	case "h264_qsv":
		// QSV's analogue of libx264's -crf is -global_quality (ICQ mode) —
		// variable bitrate targeting a quality level rather than a fixed
		// rate. "-look_ahead 0" keeps latency/CPU-side buffering low, which
		// matters less for recording than for streaming but costs nothing.
		// NOTE: QSV rate-control flags are driver/ffmpeg-build sensitive —
		// verify this actually produces expected quality/bitrate on the
		// target machine (intel-media-driver + this ffmpeg build) before
		// relying on it; the libx264 path above is fully deterministic
		// software behaviour, this one is not.
		args = append(args,
			"-preset", "veryfast",
			"-global_quality", "23",
			"-look_ahead", "0",
		)
	default:
		// Unknown/other hardware encoder (e.g. h264_vaapi, h264_nvenc):
		// pass a sane bitrate-based fallback rather than guessing at
		// codec-specific quality flags we haven't validated.
		args = append(args, "-b:v", "6M")
	}

	args = append(args,
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

	if cfg.LoopbackDevice != "" {
		args = append(args,
			"-map", "[stream]",
			"-f", "v4l2",
			"-pix_fmt", "yuyv422", // widely accepted by v4l2loopback + OBS/ffmpeg readers
			cfg.LoopbackDevice,
		)
	}

	return args
}

func (cr *CameraRecorder) startFFmpeg(filePath string) error {
	if err := os.MkdirAll(cr.outputDir, 0o755); err != nil {
		return fmt.Errorf("failed to create output dir: %w", err)
	}

	cmd := exec.Command("ffmpeg", buildFFmpegArgs(cr.config, cr.codec, filePath)...)

	cmd.Stdout = newPrefixedWriter(fmt.Sprintf("[ffmpeg/%s] ", cr.config.ID))
	cmd.Stderr = newPrefixedWriter(fmt.Sprintf("[ffmpeg/%s] ", cr.config.ID))

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("exec.Start failed: %w", err)
	}

	doneCh := make(chan struct{})

	cr.mu.Lock()
	cr.cmd = cmd
	cr.cmdDone = doneCh
	cr.mu.Unlock()

	log.Printf("🎬 [%s] ffmpeg started (pid %d) → %s", cr.config.ID, cmd.Process.Pid, filePath)

	// Single, exclusive owner of cmd.Wait() for this process — calling Wait()
	// more than once on the same *exec.Cmd is not safe, so every other place
	// that needs to know "has it exited yet" (stopFFmpeg's timeout logic,
	// crash detection) synchronises on doneCh instead of calling Wait() itself.
	go func() {
		waitErr := cmd.Wait()

		cr.mu.Lock()
		wasExpected := cr.expectedStop
		cr.expectedStop = false
		stillRecording := cr.recording
		if cr.cmd == cmd {
			cr.cmd = nil
		}
		if stillRecording && !wasExpected {
			cr.recording = false
		}
		callback := cr.onUnexpectedStop
		snapshotMeta := cr.lastMeta
		cr.mu.Unlock()

		close(doneCh) // unblocks anyone in stopFFmpeg waiting for this exit

		if stillRecording && !wasExpected {
			if waitErr != nil {
				log.Printf("❌ [%s] ffmpeg exited unexpectedly: %v", cr.config.ID, waitErr)
			} else {
				log.Printf("⚠️  [%s] ffmpeg exited with status 0 (unexpected)", cr.config.ID)
			}
			if callback != nil {
				callback(cr.config.ID, snapshotMeta)
			}
		}
	}()

	return nil
}

// stopFFmpeg marks the current process's exit as "expected" (so the crash
// watcher in startFFmpeg's goroutine stays quiet), sends SIGINT so ffmpeg
// flushes and finalises the MKV file, then waits up to 10 s for a clean exit
// before sending SIGKILL. Used both for a final StopRecord and for a segment
// rotation — in both cases we want a cleanly closed, fully indexed MKV.
func (cr *CameraRecorder) stopFFmpeg() error {
	cr.mu.Lock()
	cmd := cr.cmd
	doneCh := cr.cmdDone
	if cmd == nil || cmd.Process == nil {
		cr.mu.Unlock()
		return nil
	}
	cr.expectedStop = true
	cr.mu.Unlock()

	log.Printf("🛑 [%s] Sending SIGINT to ffmpeg (pid %d)", cr.config.ID, cmd.Process.Pid)
	if err := cmd.Process.Signal(os.Interrupt); err != nil {
		log.Printf("⚠️  [%s] SIGINT failed: %v — trying SIGKILL", cr.config.ID, err)
		_ = cmd.Process.Kill()
	}

	if doneCh == nil {
		return nil
	}

	select {
	case <-doneCh:
		log.Printf("✅ [%s] ffmpeg exited cleanly", cr.config.ID)
	case <-time.After(10 * time.Second):
		log.Printf("⚠️  [%s] ffmpeg did not exit in 10 s — killing", cr.config.ID)
		_ = cmd.Process.Kill()
		<-doneCh
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
	// Only update current.json on segment start — history is appended on
	// every segment close (manual stop OR rotation), with finished_at set.
	return cr.writeCurrentMeta(meta)
}

// clearCurrentMeta overwrites current.json with an empty object, signalling
// that no recording is active. Called after StopRecord (not after a
// rotation — rotation immediately writes the next segment's current.json).
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
