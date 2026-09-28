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
//
// Debian is the SRT LISTENER, not the caller: each camera's streaming
// ffmpeg binds "0.0.0.0:<port>" and waits, and OBS's Media Source on
// Windows connects out to it (mode=caller). This is the opposite of the
// original design (Debian dialling out to a fixed Windows host/port as
// caller, with OBS listening) — that put the fragile, hard-to-diagnose
// half of the connection (binding and holding a listening UDP socket
// across OBS restarts/crashes) on the Windows side, the machine that
// isn't always on and isn't under our control. Debian is the stable,
// always-on box, so it should be the one holding the stable endpoint;
// Windows/OBS just has to know where to dial, and reconnecting after a
// crash or restart is exactly what a caller is supposed to do.
type StreamConfig struct {
	Host        string // informational only now — Windows machine IP/hostname, used just to print the srt://host:port?mode=caller URL to enter in OBS. Not required.
	Protocol    string // only "srt" is implemented for now
	Codec       string // "libx264" (default, works everywhere), "h264_qsv" or "h264_vaapi" on hardware that has it
	Bitrate     string // e.g. "4M"
	VaapiDevice string // e.g. "/dev/dri/renderD128" — only used when Codec == "h264_vaapi"
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

	// camLocks serializes Start/Stop PER CAMERA (built once at construction
	// time from every camera ID appearing in loopbacks/ports, then never
	// mutated — safe to read without a guard). Using one lock per camera,
	// instead of a single manager-wide lock, means camera1 retrying its
	// startup (see launch's startup grace/retry loop below) can never block
	// camera2..4 from starting or stopping at the same time.
	camLocks map[string]*sync.Mutex

	mu      sync.Mutex
	streams map[string]*streamProc // cameraID -> active process (absent = not streaming)
	desired map[string]bool        // cameraID -> "should be streaming" (survives crashes; StopStream clears it)

	restartDelay time.Duration // overridable in tests; defaults to streamRestartDelay

	onStreamChanged func(cameraID string, active bool, errMsg string)
}

// NewStreamManager creates a StreamManager. loopbacks maps camera ID to its
// configured loopback device path; ports maps camera ID to the port its
// stream is sent to on the Windows host (cameras missing from either map
// simply can't be streamed — StartStream fails with a clear error).
// isRecording is consulted before starting a stream, since the loopback
// only has data while the camera's own recording ffmpeg process is running.
func NewStreamManager(loopbacks map[string]string, ports map[string]int, isRecording func(cameraID string) bool, cfg StreamConfig) *StreamManager {
	camLocks := make(map[string]*sync.Mutex)
	for id := range loopbacks {
		camLocks[id] = &sync.Mutex{}
	}
	for id := range ports {
		if _, ok := camLocks[id]; !ok {
			camLocks[id] = &sync.Mutex{}
		}
	}
	return &StreamManager{
		loopbacks:    loopbacks,
		ports:        ports,
		isRecording:  isRecording,
		cfg:          cfg,
		camLocks:     camLocks,
		streams:      make(map[string]*streamProc),
		desired:      make(map[string]bool),
		restartDelay: streamRestartDelay,
	}
}

// overrideRestartDelayForTest shortens the auto-restart backoff so tests
// don't have to wait streamRestartDelay (several seconds) for real. Not for
// production use.
func (sm *StreamManager) overrideRestartDelayForTest(d time.Duration) {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	sm.restartDelay = d
}

// lockFor returns the per-camera lock for cameraID, or nil if that camera
// wasn't in loopbacks/ports at construction time (StartStream's own
// validation below rejects unknown cameras with a clear error either way).
func (sm *StreamManager) lockFor(cameraID string) *sync.Mutex {
	return sm.camLocks[cameraID]
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
	if lock := sm.lockFor(cameraID); lock != nil {
		lock.Lock()
		defer lock.Unlock()
	}

	sm.mu.Lock()
	if _, active := sm.streams[cameraID]; active {
		sm.mu.Unlock()
		log.Printf("📡 [stream/%s] already streaming — nothing to do", cameraID)
		return nil
	}
	sm.mu.Unlock()

	// Host is no longer required: Debian is the SRT listener now (binds
	// locally), so it doesn't need to know Windows' address to start
	// streaming — Host is only used, if set, to print a friendlier log line
	// below with the exact URL to paste into OBS.
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
	// Fail fast with a clear error instead of spawning an ffmpeg process that
	// will immediately exit (e.g. v4l2loopback not loaded on this machine) —
	// same failure mode that used to also take recording down with it, see
	// the matching check in camera.go's startFFmpeg.
	if _, err := os.Stat(device); err != nil {
		return fmt.Errorf("camera %s loopback device %s not available: %w", cameraID, device, err)
	}

	sm.mu.Lock()
	sm.desired[cameraID] = true
	sm.mu.Unlock()

	if err := sm.launch(cameraID, device, port); err != nil {
		return err
	}

	if sm.cfg.Host != "" {
		log.Printf("📡 [stream/%s] listening on port %d — OBS Media Source: srt://%s:%d?mode=caller", cameraID, port, sm.cfg.Host, port)
	} else {
		log.Printf("📡 [stream/%s] listening on port %d — set OBS Media Source to srt://<this-machine's-address>:%d?mode=caller", cameraID, port, port)
	}

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
	if lock := sm.lockFor(cameraID); lock != nil {
		lock.Lock()
		defer lock.Unlock()
	}

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

// startupGrace is how long a newly-launched stream ffmpeg is given to prove
// it's actually running before we consider it started. streamStartAttempts
// and streamRetryDelay bound how many times launch retries a quick failure
// before giving up — see the startup-race comment on launch below.
const (
	streamStartupGrace   = 900 * time.Millisecond
	streamStartAttempts  = 6
	streamStartRetryWait = 700 * time.Millisecond
)

// launch starts the ffmpeg process reading from the given loopback device
// and sending it to sm.cfg.Host:port over SRT. Caller must hold cameraID's
// per-camera lock (see lockFor).
//
// There's an inherent startup race here: StartStream is normally called
// immediately after the camera's own recording ffmpeg is launched (see
// RecorderManager.StartRecord), which only means that process has been
// forked — it hasn't necessarily opened and format-set the v4l2loopback
// device as a writer yet (it first has to negotiate the capture format with
// the real camera, initialize the encoder, etc.). If this stream's ffmpeg
// tries to open that same loopback as a reader before the writer side is
// ready, v4l2loopback rejects it (observed as ffmpeg's "Error opening input
// files: No such device", exit status 237) and the process exits almost
// immediately. So: launch retries a handful of times with a short delay
// whenever the process dies within the startup grace window, instead of
// treating that as a hard failure or an "unexpected stop".
// buildStreamArgs builds the ffmpeg argument list for the streaming process:
// read `device` (a v4l2loopback device) and send it to `dest` (an SRT URL)
// using `codec`, defaulting to "libx264" when empty; vaapiDevice is only
// used when codec is "h264_vaapi" (defaulting to "/dev/dri/renderD128"
// when empty), and bitrate defaults to "4M" when empty. Pulled out of
// launch as a pure function so the argument-building logic (in particular
// the forced-keyframe-interval fix below) can be unit tested without
// spawning ffmpeg.
func buildStreamArgs(codec, vaapiDevice, bitrate, device, dest string) []string {
	if codec == "" {
		codec = "libx264"
	}
	if bitrate == "" {
		bitrate = "4M"
	}

	var args []string
	if codec == "h264_vaapi" {
		if vaapiDevice == "" {
			vaapiDevice = "/dev/dri/renderD128"
		}
		args = append(args, "-vaapi_device", vaapiDevice)
	}
	args = append(args, "-f", "v4l2", "-i", device)
	if codec == "h264_vaapi" {
		// Loopback frames arrive as plain software (yuyv422) frames — upload
		// to the VAAPI surface before the encoder, same as the [rec] branch
		// in buildFFmpegArgs (camera.go).
		args = append(args, "-vf", "format=nv12,hwupload")
	}
	args = append(args, "-c:v", codec)
	switch codec {
	case "libx264":
		// Only meaningful for the software encoder — hardware encoders
		// (h264_qsv, h264_vaapi, ...) have their own preset semantics or
		// none at all, so we leave those to the operator via stream_codec.
		args = append(args, "-b:v", bitrate, "-preset", "veryfast", "-tune", "zerolatency")
	case "h264_vaapi":
		// NOT -b:v here: that requests a bitrate-targeting rate-control mode
		// (VBR/CBR-like), and this driver only supports CQP (constant QP) —
		// requesting anything else fails encoder init outright ("Driver does
		// not support any RC mode compatible with selected options
		// (supported modes: CQP)"), so the process exits every time
		// (observed as a permanent restart loop, never actually streaming).
		// Same fix the recording pipeline already uses and has never hit
		// this on — see the h264_vaapi branch in buildFFmpegArgs (camera.go).
		// -bf 0: no B-frames — B-frames require the encoder to hold future
		// frames to encode/reorder around them, which is pure added latency
		// for a live monitoring feed and buys nothing here (unlike for the
		// recording file, where this device's default GOP structure is fine
		// since nobody's watching it live).
		args = append(args, "-qp", "23", "-compression_level", "1", "-bf", "0")
	case "h264_qsv":
		args = append(args, "-b:v", bitrate, "-bf", "0")
	default:
		args = append(args, "-b:v", bitrate)
	}
	// Force a keyframe roughly once a second, same interval used for the
	// recording (see buildFFmpegArgs in camera.go). Without this, a fresh
	// viewer (OBS's Media Source connecting to this SRT stream) has to wait
	// for the encoder's default GOP length before it sees a keyframe to lock
	// onto — which can easily exceed OBS's ffmpeg demuxer's default probe
	// window, producing "Failed to find stream info" and a dropped
	// connection even though the stream itself is otherwise healthy.
	args = append(args, "-g", "30", "-keyint_min", "30", "-force_key_frames", "expr:gte(t,n_forced*1)")
	// Low-latency muxing: ffmpeg's mpegts muxer defaults to holding packets
	// for up to ~0.7s (max_delay/muxdelay) to interleave streams smoothly —
	// sensible for a file, pure added latency for a single-video live feed
	// nobody wants delayed by a second. This is by far the biggest knob here
	// (SRT's own buffering below is two orders of magnitude smaller).
	args = append(args, "-fflags", "nobuffer", "-max_delay", "0", "-muxdelay", "0", "-muxpreload", "0")
	args = append(args, "-f", "mpegts", dest)
	return args
}

func (sm *StreamManager) launch(cameraID, device string, port int) error {
	codec := sm.cfg.Codec
	if codec == "" {
		codec = "libx264"
	}
	bitrate := sm.cfg.Bitrate
	if bitrate == "" {
		bitrate = "4M"
	}
	// Listener, not caller: Debian binds locally and waits for OBS to dial
	// in (see the StreamConfig doc comment for why). "0.0.0.0" is a bind
	// address, not a peer to reach — unlike the old caller mode, it must
	// never be sm.cfg.Host (that was the original listener-URL bug: using
	// the peer's hostname as a local bind address).
	//
	// latency=50: SRT's own buffer for smoothing out network jitter and
	// covering retransmits — defaults to 120ms if unset. Debian and Windows
	// are on the same LAN here (minimal jitter, no real packet loss to
	// recover from), so 50ms is comfortably safe and shaves the difference
	// off end-to-end delay. Raise this back up if the stream ever gets
	// choppy over a less reliable link (Wi-Fi, a slower/busier network).
	dest := fmt.Sprintf("srt://0.0.0.0:%d?mode=listener&latency=50", port)
	args := buildStreamArgs(codec, sm.cfg.VaapiDevice, bitrate, device, dest)

	var lastErr error
	for attempt := 1; attempt <= streamStartAttempts; attempt++ {
		cmd := exec.Command("ffmpeg", args...)
		cmd.Stdout = newPrefixedWriter(fmt.Sprintf("[stream/%s] ", cameraID))
		cmd.Stderr = newPrefixedWriter(fmt.Sprintf("[stream/%s] ", cameraID))

		if err := cmd.Start(); err != nil {
			return fmt.Errorf("failed to start streaming ffmpeg for camera %s: %w", cameraID, err)
		}

		// Single owner of cmd.Wait(): this goroutine, always — whether the
		// process dies during the startup grace window below (retry path)
		// or long after it (normal lifecycle, handled by the watcher
		// goroutine started once we're past the grace window).
		waitErrCh := make(chan error, 1)
		doneCh := make(chan struct{})
		go func() {
			waitErrCh <- cmd.Wait()
			close(doneCh)
		}()

		select {
		case werr := <-waitErrCh:
			lastErr = werr
			if lastErr == nil {
				lastErr = fmt.Errorf("ffmpeg exited immediately with status 0")
			}
			if attempt < streamStartAttempts {
				log.Printf("⏳ [stream/%s] startup attempt %d/%d exited immediately (%v, likely loopback not ready yet) — retrying in %s",
					cameraID, attempt, streamStartAttempts, lastErr, streamStartRetryWait)
				time.Sleep(streamStartRetryWait)
				continue
			}
			return fmt.Errorf("camera %s: stream ffmpeg failed to start after %d attempts: %w",
				cameraID, streamStartAttempts, lastErr)

		case <-time.After(streamStartupGrace):
			// Survived the grace window — treat as successfully started and
			// hand off to the normal watcher below for the rest of its life.
		}

		proc := &streamProc{cmd: cmd, cmdDone: doneCh}
		sm.mu.Lock()
		sm.streams[cameraID] = proc
		sm.mu.Unlock()

		log.Printf("🎥 [stream/%s] ffmpeg started (pid %d) reading %s → %s", cameraID, cmd.Process.Pid, device, dest)

		go func() {
			waitErr := <-waitErrCh // already sent, or delivered whenever ffmpeg eventually exits

			sm.mu.Lock()
			wasExpected := proc.expectedStop
			stillActive := sm.streams[cameraID] == proc
			if stillActive {
				delete(sm.streams, cameraID)
			}
			callback := sm.onStreamChanged
			sm.mu.Unlock()

			if stillActive && !wasExpected {
				errMsg := "exited with status 0 (unexpected)"
				if waitErr != nil {
					errMsg = waitErr.Error()
				}
				log.Printf("❌ [stream/%s] ffmpeg exited unexpectedly: %s", cameraID, errMsg)
				if callback != nil {
					callback(cameraID, false, errMsg)
				}
				// Self-healing: an unexpected exit here just means something
				// external interrupted the SRT connection or the process
				// itself (network blip, OBS crashing/restarting on the
				// Windows side, the listener socket getting closed, etc) —
				// not that the camera is done streaming. Keep retrying in the
				// background for as long as this camera is still supposed to
				// be streaming (StopStream wasn't called) and is still
				// recording, so nobody has to notice and restart it by hand.
				sm.scheduleRestart(cameraID, device, port)
			}
		}()

		return nil
	}

	return lastErr
}

// streamRestartDelay is the pause before each auto-restart attempt after an
// unexpected exit. There's no attempt cap, unlike the recording side's
// auto-restart (autoRestartMaxTries in recorder.go) — a physical camera that
// keeps failing needs a human to look at it, but a streaming link dropping
// because the far end (OBS on Windows) is unreachable, restarting, or
// mid-crash is an expected, recoverable condition that should just keep
// quietly retrying until OBS reconnects, however long that takes. Retries
// stop on their own once the camera is no longer meant to be streaming
// (StopStream was called) or has stopped recording.
const streamRestartDelay = 5 * time.Second

// scheduleRestart relaunches cameraID's stream after streamRestartDelay, as
// long as it's still meant to be streaming and the camera is still
// recording. Safe to call repeatedly — it checks sm.desired and re-schedules
// itself on failure rather than recursing on the call stack, so it can run
// indefinitely without accumulating stack depth.
func (sm *StreamManager) scheduleRestart(cameraID, device string, port int) {
	sm.mu.Lock()
	delay := sm.restartDelay
	sm.mu.Unlock()

	go func() {
		time.Sleep(delay)

		if lock := sm.lockFor(cameraID); lock != nil {
			lock.Lock()
			defer lock.Unlock()
		}

		sm.mu.Lock()
		wantStreaming := sm.desired[cameraID]
		_, alreadyRunning := sm.streams[cameraID]
		sm.mu.Unlock()

		if !wantStreaming {
			log.Printf("⏭️  [stream/%s] not restarting — stream was stopped", cameraID)
			return
		}
		if alreadyRunning {
			// A manual StartStream (or an earlier retry) already relaunched
			// it — nothing to do.
			return
		}
		if sm.isRecording != nil && !sm.isRecording(cameraID) {
			log.Printf("⏭️  [stream/%s] not restarting — camera is no longer recording", cameraID)
			return
		}
		if _, err := os.Stat(device); err != nil {
			log.Printf("⏳ [stream/%s] loopback device not available, retrying restart in %s: %v", cameraID, delay, err)
			sm.scheduleRestart(cameraID, device, port)
			return
		}

		log.Printf("🔁 [stream/%s] auto-restarting stream after unexpected exit", cameraID)
		if err := sm.launch(cameraID, device, port); err != nil {
			log.Printf("❌ [stream/%s] auto-restart failed, retrying in %s: %v", cameraID, delay, err)
			sm.scheduleRestart(cameraID, device, port)
			return
		}

		sm.mu.Lock()
		cb := sm.onStreamChanged
		sm.mu.Unlock()
		if cb != nil {
			cb(cameraID, true, "")
		}
	}()
}

// stopLocked stops cameraID's active stream process, if any. Caller must
// hold cameraID's per-camera lock (but not mu).
func (sm *StreamManager) stopLocked(cameraID string) error {
	sm.mu.Lock()
	sm.desired[cameraID] = false // stops the auto-restart watchdog from reviving this camera
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
