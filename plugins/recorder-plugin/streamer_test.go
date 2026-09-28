package main

import (
	"os"
	"strings"
	"testing"
	"time"
)

func TestBuildFFmpegArgsWithoutLoopback(t *testing.T) {
	args := buildFFmpegArgs(CameraConfig{ID: "camA", DevicePath: "/dev/camA"}, "libx264", "", "/out/camA.mkv")
	joined := strings.Join(args, " ")

	if strings.Contains(joined, "filter_complex") {
		t.Fatalf("did not expect -filter_complex when LoopbackDevice is empty, got: %s", joined)
	}
	if strings.Count(joined, "-f v4l2") != 1 {
		t.Fatalf("expected exactly one v4l2 output (none, only the input) when LoopbackDevice is empty, got: %s", joined)
	}
	if args[len(args)-1] != "/out/camA.mkv" {
		t.Fatalf("expected the mkv file path to be the last argument, got: %s", args[len(args)-1])
	}
}

func TestBuildFFmpegArgsWithLoopback(t *testing.T) {
	args := buildFFmpegArgs(CameraConfig{ID: "camA", DevicePath: "/dev/camA", LoopbackDevice: "/dev/video10"}, "libx264", "", "/out/camA.mkv")
	joined := strings.Join(args, " ")

	if !strings.Contains(joined, "-filter_complex [0:v]split=2[rec][stream]") {
		t.Fatalf("expected split filter_complex when LoopbackDevice is set, got: %s", joined)
	}
	if !strings.Contains(joined, "-map [rec]") || !strings.Contains(joined, "-map [stream]") {
		t.Fatalf("expected both [rec] and [stream] to be mapped, got: %s", joined)
	}
	if args[len(args)-1] != "/dev/video10" {
		t.Fatalf("expected the loopback device to be the final argument (second output), got: %s", args[len(args)-1])
	}
	// The mkv file must still appear as the first output's destination,
	// i.e. it appears before "-map [stream]" in the argument list.
	mkvIdx, streamMapIdx := -1, -1
	for i, a := range args {
		if a == "/out/camA.mkv" {
			mkvIdx = i
		}
		if a == "[stream]" && i > 0 && args[i-1] == "-map" {
			streamMapIdx = i
		}
	}
	if mkvIdx == -1 || streamMapIdx == -1 || mkvIdx > streamMapIdx {
		t.Fatalf("expected the recording (.mkv) output before the streaming ([stream]) output, args=%v", args)
	}
}

func TestBuildFFmpegArgsCodecBranches(t *testing.T) {
	cfg := CameraConfig{ID: "camA", DevicePath: "/dev/camA"}

	libx264 := strings.Join(buildFFmpegArgs(cfg, "libx264", "", "/out/camA.mkv"), " ")
	if !strings.Contains(libx264, "-preset ultrafast") || !strings.Contains(libx264, "-crf 23") {
		t.Fatalf("expected libx264 branch to use -preset/-crf, got: %s", libx264)
	}
	if strings.Contains(libx264, "-global_quality") {
		t.Fatalf("did not expect -global_quality in the libx264 branch, got: %s", libx264)
	}

	qsv := strings.Join(buildFFmpegArgs(cfg, "h264_qsv", "", "/out/camA.mkv"), " ")
	if !strings.Contains(qsv, "-global_quality 23") {
		t.Fatalf("expected h264_qsv branch to use -global_quality, got: %s", qsv)
	}
	if strings.Contains(qsv, "-crf") {
		t.Fatalf("did not expect -crf (libx264-only flag) in the h264_qsv branch, got: %s", qsv)
	}

	// Empty codec must default to libx264, not crash or emit "-c:v " with nothing after it.
	defaulted := buildFFmpegArgs(cfg, "", "", "/out/camA.mkv")
	found := false
	for i, a := range defaulted {
		if a == "-c:v" && i+1 < len(defaulted) && defaulted[i+1] == "libx264" {
			found = true
		}
	}
	if !found {
		t.Fatalf("expected empty codec to default to libx264, got: %v", defaulted)
	}
}

func TestBuildFFmpegArgsVaapiWithoutLoopback(t *testing.T) {
	cfg := CameraConfig{ID: "camA", DevicePath: "/dev/camA"}
	args := buildFFmpegArgs(cfg, "h264_vaapi", "/dev/dri/renderD128", "/out/camA.mkv")
	joined := strings.Join(args, " ")

	if !strings.Contains(joined, "-vaapi_device /dev/dri/renderD128") {
		t.Fatalf("expected -vaapi_device to be set, got: %s", joined)
	}
	if !strings.Contains(joined, "-vf format=nv12,hwupload") {
		t.Fatalf("expected a simple -vf hwupload chain when there's no loopback, got: %s", joined)
	}
	if strings.Contains(joined, "filter_complex") {
		t.Fatalf("did not expect -filter_complex without a loopback device, got: %s", joined)
	}
	if !strings.Contains(joined, "-qp 23") {
		t.Fatalf("expected the vaapi branch to use -qp, got: %s", joined)
	}

	// Empty vaapiDevice must default to /dev/dri/renderD128, not emit
	// "-vaapi_device " with nothing after it.
	defaulted := strings.Join(buildFFmpegArgs(cfg, "h264_vaapi", "", "/out/camA.mkv"), " ")
	if !strings.Contains(defaulted, "-vaapi_device /dev/dri/renderD128") {
		t.Fatalf("expected empty vaapiDevice to default to /dev/dri/renderD128, got: %s", defaulted)
	}
}

func TestBuildFFmpegArgsVaapiWithLoopback(t *testing.T) {
	cfg := CameraConfig{ID: "camA", DevicePath: "/dev/camA", LoopbackDevice: "/dev/video10"}
	args := buildFFmpegArgs(cfg, "h264_vaapi", "/dev/dri/renderD128", "/out/camA.mkv")
	joined := strings.Join(args, " ")

	// The [rec] branch must be uploaded to the VAAPI surface, but the
	// [stream] branch (loopback) must stay software — a v4l2 output can't
	// accept a hardware surface reference.
	if !strings.Contains(joined, "-filter_complex [0:v]split=2[rec][stream];[rec]format=nv12,hwupload[rechw]") {
		t.Fatalf("expected the split+hwupload filter graph, got: %s", joined)
	}
	if !strings.Contains(joined, "-map [rechw]") {
		t.Fatalf("expected the encoder to read from [rechw], got: %s", joined)
	}
	if !strings.Contains(joined, "-map [stream]") {
		t.Fatalf("expected the loopback output to still be mapped from [stream], got: %s", joined)
	}
	if args[len(args)-1] != "/dev/video10" {
		t.Fatalf("expected the loopback device to be the final argument, got: %s", args[len(args)-1])
	}
}

// TestBuildStreamArgsForcesKeyframeInterval guards against the "Failed to
// find stream info" incident: a viewer joining the stream fresh (OBS's
// Media Source) needs a keyframe within its probe window, so every codec
// branch of the streaming ffmpeg command must force one roughly every
// second, same as the recording side already does.
func TestBuildStreamArgsForcesKeyframeInterval(t *testing.T) {
	for _, codec := range []string{"libx264", "h264_qsv", "h264_vaapi", ""} {
		args := buildStreamArgs(codec, "", "4M", "/dev/video11", "srt://host:9000?mode=caller")
		joined := strings.Join(args, " ")
		if !strings.Contains(joined, "-g 30") || !strings.Contains(joined, "-keyint_min 30") {
			t.Fatalf("codec %q: expected forced keyframe interval (-g/-keyint_min), got: %s", codec, joined)
		}
		if !strings.Contains(joined, "-force_key_frames expr:gte(t,n_forced*1)") {
			t.Fatalf("codec %q: expected -force_key_frames, got: %s", codec, joined)
		}
	}
}

func TestBuildStreamArgsVaapi(t *testing.T) {
	args := buildStreamArgs("h264_vaapi", "/dev/dri/renderD128", "4M", "/dev/video11", "srt://host:9000?mode=caller")
	joined := strings.Join(args, " ")
	if !strings.Contains(joined, "-vaapi_device /dev/dri/renderD128") {
		t.Fatalf("expected -vaapi_device to be set, got: %s", joined)
	}
	if !strings.Contains(joined, "-vf format=nv12,hwupload") {
		t.Fatalf("expected hwupload filter, got: %s", joined)
	}

	defaulted := strings.Join(buildStreamArgs("h264_vaapi", "", "4M", "/dev/video11", "srt://host:9000?mode=caller"), " ")
	if !strings.Contains(defaulted, "-vaapi_device /dev/dri/renderD128") {
		t.Fatalf("expected empty vaapiDevice to default to /dev/dri/renderD128, got: %s", defaulted)
	}
}

// TestBuildStreamArgsVaapiUsesCQP guards against the "Driver does not
// support any RC mode compatible with selected options (supported modes:
// CQP)" incident: this driver only accepts CQP rate control, so the
// h264_vaapi branch must use -qp (which implies CQP), the same way the
// recording pipeline's own VAAPI branch already does (buildFFmpegArgs in
// camera.go) — and must NOT pass -b:v, which requests a bitrate-targeting
// RC mode the driver rejects outright, making the encoder fail to open on
// every single attempt (observed as a permanent crash-restart loop that
// never actually streams).
func TestBuildStreamArgsVaapiUsesCQP(t *testing.T) {
	joined := strings.Join(buildStreamArgs("h264_vaapi", "/dev/dri/renderD128", "4M", "/dev/video11", "srt://host:9000?mode=caller"), " ")
	if !strings.Contains(joined, "-qp 23") {
		t.Fatalf("expected the h264_vaapi branch to use -qp (CQP), got: %s", joined)
	}
	if strings.Contains(joined, "-b:v") {
		t.Fatalf("did not expect -b:v in the h264_vaapi branch — this driver only supports CQP, not a bitrate-targeting RC mode, got: %s", joined)
	}

	// libx264 and any other/unknown codec must still get a bitrate — only
	// h264_vaapi is special-cased here.
	libx264 := strings.Join(buildStreamArgs("libx264", "", "4M", "/dev/video11", "srt://host:9000?mode=caller"), " ")
	if !strings.Contains(libx264, "-b:v 4M") {
		t.Fatalf("expected libx264 to still use -b:v, got: %s", libx264)
	}
}

// fakeFFmpegPath writes a small shell script standing in for ffmpeg (loops
// until SIGINT/SIGTERM) and puts it first on PATH for the duration of the test.
func fakeFFmpegPath(t *testing.T) {
	t.Helper()
	dir := t.TempDir()
	path := dir + "/ffmpeg"
	script := "#!/bin/sh\ntrap 'exit 0' INT TERM\nwhile true; do sleep 0.05; done\n"
	if err := os.WriteFile(path, []byte(script), 0o755); err != nil {
		t.Fatalf("failed to write fake ffmpeg: %v", err)
	}
	oldPath := os.Getenv("PATH")
	os.Setenv("PATH", dir+":"+oldPath)
	t.Cleanup(func() { os.Setenv("PATH", oldPath) })
}

func TestStreamManagerValidation(t *testing.T) {
	fakeFFmpegPath(t)

	// Host is no longer required: Debian is the SRT listener now, so an
	// empty Host (nothing configured to print in the friendly log line)
	// must NOT block streaming — only a missing loopback device, port, or
	// a not-recording camera should.
	dir := t.TempDir()
	device := dir + "/video10"
	if err := os.WriteFile(device, nil, 0o644); err != nil {
		t.Fatalf("failed to create fake loopback device: %v", err)
	}
	smEmptyHost := NewStreamManager(map[string]string{"cam1": device}, map[string]int{"cam1": 9000},
		func(string) bool { return true }, StreamConfig{Host: ""})
	if err := smEmptyHost.StartStream("cam1"); err != nil {
		t.Fatalf("expected StartStream to succeed with an empty Host (no longer required), got: %v", err)
	}
	_ = smEmptyHost.StopStream("cam1")

	sm2 := NewStreamManager(map[string]string{}, map[string]int{},
		func(string) bool { return true }, StreamConfig{Host: "192.168.1.50"})
	if err := sm2.StartStream("cam1"); err == nil {
		t.Fatalf("expected error when camera has no loopback_device configured")
	}

	sm3 := NewStreamManager(map[string]string{"cam1": "/dev/video10"}, map[string]int{},
		func(string) bool { return true }, StreamConfig{Host: "192.168.1.50"})
	if err := sm3.StartStream("cam1"); err == nil {
		t.Fatalf("expected error when camera has no stream port configured")
	}

	sm4 := NewStreamManager(map[string]string{"cam1": "/dev/video10"}, map[string]int{"cam1": 9000},
		func(string) bool { return false }, StreamConfig{Host: "192.168.1.50"})
	if err := sm4.StartStream("cam1"); err == nil {
		t.Fatalf("expected error when camera is not recording")
	}

	// "/dev/video10" passes every config check above but doesn't exist on
	// this machine — this is the exact failure mode from the incident this
	// guard was added for: v4l2loopback not loaded, so the device is
	// configured but absent. Must fail fast with a clear error instead of
	// spawning an ffmpeg process that immediately exits.
	sm5 := NewStreamManager(map[string]string{"cam1": "/dev/video10"}, map[string]int{"cam1": 9000},
		func(string) bool { return true }, StreamConfig{Host: "192.168.1.50"})
	if err := sm5.StartStream("cam1"); err == nil {
		t.Fatalf("expected error when loopback device does not exist on disk")
	}
}

// TestStreamManagerConcurrentCameras verifies that all configured cameras
// can stream at the same time, independently — starting or stopping one
// must never touch another, matching the "stream all 4 cameras (or fewer,
// whichever are in use) continuously" design.
func TestStreamManagerConcurrentCameras(t *testing.T) {
	fakeFFmpegPath(t)

	// StartStream now stats the loopback device before launching ffmpeg (see
	// camera.go/streamer.go — a missing device must fail fast, not spawn a
	// doomed process), so these stand-ins need to actually exist on disk.
	// Real content doesn't matter: the fake ffmpeg never reads them.
	dir := t.TempDir()
	touch := func(name string) string {
		path := dir + "/" + name
		if err := os.WriteFile(path, nil, 0o644); err != nil {
			t.Fatalf("failed to create fake loopback device %s: %v", path, err)
		}
		return path
	}
	loopbacks := map[string]string{"cam1": touch("video10"), "cam2": touch("video11"), "cam3": touch("video12")}
	ports := map[string]int{"cam1": 9000, "cam2": 9001, "cam3": 9002}
	sm := NewStreamManager(loopbacks, ports, func(string) bool { return true },
		StreamConfig{Host: "192.168.1.50", Codec: "libx264", Bitrate: "4M"})

	events := make(chan struct {
		cam    string
		active bool
	}, 8)
	sm.SetOnStreamChanged(func(cameraID string, active bool, errMsg string) {
		events <- struct {
			cam    string
			active bool
		}{cameraID, active}
	})

	drainStart := func(want string) {
		t.Helper()
		select {
		case ev := <-events:
			if ev.cam != want || !ev.active {
				t.Fatalf("expected (%s, active=true) event, got %+v", want, ev)
			}
		case <-time.After(time.Second):
			t.Fatalf("timed out waiting for start event for %s", want)
		}
	}

	// Only 2 of the 3 configured cameras are actually "in use" here —
	// cam3 is never started, exercising "fewer if not all are used".
	if err := sm.StartStream("cam1"); err != nil {
		t.Fatalf("StartStream(cam1) failed: %v", err)
	}
	drainStart("cam1")
	if err := sm.StartStream("cam2"); err != nil {
		t.Fatalf("StartStream(cam2) failed: %v", err)
	}
	drainStart("cam2")

	// Both must be active at once — starting cam2 must not have stopped cam1.
	if !sm.IsStreaming("cam1") || !sm.IsStreaming("cam2") {
		t.Fatalf("expected both cam1 and cam2 streaming concurrently, got cam1=%v cam2=%v",
			sm.IsStreaming("cam1"), sm.IsStreaming("cam2"))
	}
	if sm.IsStreaming("cam3") {
		t.Fatalf("cam3 was never started, must not be streaming")
	}
	active := sm.ActiveCameras()
	if len(active) != 2 || active[0] != "cam1" || active[1] != "cam2" {
		t.Fatalf("expected ActiveCameras() == [cam1 cam2], got %v", active)
	}

	// Starting the same camera again is a no-op (no new event).
	if err := sm.StartStream("cam1"); err != nil {
		t.Fatalf("StartStream(cam1) again should be a no-op, got error: %v", err)
	}
	select {
	case ev := <-events:
		t.Fatalf("unexpected event on redundant StartStream: %+v", ev)
	case <-time.After(150 * time.Millisecond):
		// OK
	}

	// Stopping cam1 must not affect cam2.
	if err := sm.StopStream("cam1"); err != nil {
		t.Fatalf("StopStream(cam1) failed: %v", err)
	}
	select {
	case ev := <-events:
		if ev.cam != "cam1" || ev.active {
			t.Fatalf("expected (cam1, active=false) event, got %+v", ev)
		}
	case <-time.After(time.Second):
		t.Fatalf("timed out waiting for stop event")
	}
	if sm.IsStreaming("cam1") {
		t.Fatalf("expected cam1 to have stopped streaming")
	}
	if !sm.IsStreaming("cam2") {
		t.Fatalf("expected cam2 to still be streaming after cam1 was stopped")
	}

	// Stopping cam1 again is a no-op, no error, no event.
	if err := sm.StopStream("cam1"); err != nil {
		t.Fatalf("StopStream(cam1) (idempotent) failed: %v", err)
	}
	select {
	case ev := <-events:
		t.Fatalf("unexpected event on redundant StopStream: %+v", ev)
	case <-time.After(150 * time.Millisecond):
		// OK
	}

	if err := sm.StopStream("cam2"); err != nil {
		t.Fatalf("StopStream(cam2) failed: %v", err)
	}
	if len(sm.ActiveCameras()) != 0 {
		t.Fatalf("expected no active streams left, got %v", sm.ActiveCameras())
	}
}

// TestStreamManagerAutoRestartsAfterUnexpectedExit guards the fix for "OBS
// crashes/restarts and Debian never reconnects": when the streaming ffmpeg
// process exits without an explicit StopStream, the manager must relaunch it
// on its own (as long as the camera is still recording), rather than leaving
// the stream dead until someone notices and restarts it by hand.
func TestStreamManagerAutoRestartsAfterUnexpectedExit(t *testing.T) {
	fakeFFmpegPath(t)

	dir := t.TempDir()
	device := dir + "/video10"
	if err := os.WriteFile(device, nil, 0o644); err != nil {
		t.Fatalf("failed to create fake loopback device: %v", err)
	}

	sm := NewStreamManager(map[string]string{"cam1": device}, map[string]int{"cam1": 9000},
		func(string) bool { return true }, StreamConfig{})
	sm.overrideRestartDelayForTest(50 * time.Millisecond)

	events := make(chan bool, 8)
	sm.SetOnStreamChanged(func(cameraID string, active bool, errMsg string) {
		if cameraID == "cam1" {
			events <- active
		}
	})

	if err := sm.StartStream("cam1"); err != nil {
		t.Fatalf("StartStream failed: %v", err)
	}
	if v := <-events; !v {
		t.Fatalf("expected initial start event")
	}

	// Simulate an unexpected exit (e.g. the far end dropping the SRT
	// connection) by killing the process directly instead of going through
	// StopStream — StopStream is the only thing allowed to mark a stop as
	// "expected" and suppress the auto-restart.
	sm.mu.Lock()
	proc := sm.streams["cam1"]
	sm.mu.Unlock()
	if proc == nil || proc.cmd == nil || proc.cmd.Process == nil {
		t.Fatalf("expected an active process for cam1")
	}
	_ = proc.cmd.Process.Kill()

	if v := <-events; v {
		t.Fatalf("expected a stop event after the unexpected kill")
	}

	// The watchdog should bring it back on its own, without any StartStream
	// call from the test.
	select {
	case v := <-events:
		if !v {
			t.Fatalf("expected a restart (active=true) event")
		}
	case <-time.After(2 * time.Second):
		t.Fatalf("timed out waiting for auto-restart after unexpected exit")
	}
	if !sm.IsStreaming("cam1") {
		t.Fatalf("expected cam1 to be streaming again after auto-restart")
	}

	// An explicit StopStream must NOT be followed by an auto-restart.
	if err := sm.StopStream("cam1"); err != nil {
		t.Fatalf("StopStream failed: %v", err)
	}
	select {
	case v := <-events:
		if v {
			t.Fatalf("expected a stop event, got start")
		}
	case <-time.After(time.Second):
		t.Fatalf("timed out waiting for the explicit stop event")
	}
	select {
	case v := <-events:
		t.Fatalf("expected no auto-restart after an explicit StopStream, got event active=%v", v)
	case <-time.After(300 * time.Millisecond):
		// OK — StopStream cleared "desired", so the watchdog stays quiet.
	}
}

// TestBuildListenerDestination guards the caller/listener role swap: Debian
// must bind locally ("0.0.0.0"), never dial sm.cfg.Host — that was the
// original misconfiguration (a remote hostname used as a local bind
// address) that caused OBS's "unable to create/configure SRT socket".
func TestStreamManagerListensLocally(t *testing.T) {
	fakeFFmpegPath(t)

	dir := t.TempDir()
	device := dir + "/video10"
	if err := os.WriteFile(device, nil, 0o644); err != nil {
		t.Fatalf("failed to create fake loopback device: %v", err)
	}

	// A fake ffmpeg that records the args it was invoked with, instead of
	// the generic loop-until-signalled stand-in fakeFFmpegPath installs.
	fakeDir := t.TempDir()
	argsFile := fakeDir + "/args.txt"
	script := "#!/bin/sh\necho \"$@\" > " + argsFile + "\ntrap 'exit 0' INT TERM\nwhile true; do sleep 0.05; done\n"
	if err := os.WriteFile(fakeDir+"/ffmpeg", []byte(script), 0o755); err != nil {
		t.Fatalf("failed to write fake ffmpeg: %v", err)
	}
	oldPath := os.Getenv("PATH")
	os.Setenv("PATH", fakeDir+":"+oldPath)
	t.Cleanup(func() { os.Setenv("PATH", oldPath) })

	sm := NewStreamManager(map[string]string{"cam1": device}, map[string]int{"cam1": 9000},
		func(string) bool { return true }, StreamConfig{Host: "Lenovo.local"})
	if err := sm.StartStream("cam1"); err != nil {
		t.Fatalf("StartStream failed: %v", err)
	}
	defer sm.StopStream("cam1")

	time.Sleep(100 * time.Millisecond) // let the fake ffmpeg write its args
	got, err := os.ReadFile(argsFile)
	if err != nil {
		t.Fatalf("failed to read recorded args: %v", err)
	}
	joined := string(got)
	if !strings.Contains(joined, "srt://0.0.0.0:9000?mode=listener") {
		t.Fatalf("expected Debian to bind as SRT listener on 0.0.0.0, got: %s", joined)
	}
	if strings.Contains(joined, "Lenovo.local") {
		t.Fatalf("must never dial cfg.Host — Debian listens, it doesn't call out, got: %s", joined)
	}
}

func TestStreamManagerConfiguredCameras(t *testing.T) {
	loopbacks := map[string]string{"cam1": "/dev/video10", "cam2": "/dev/video11", "cam3": ""}
	ports := map[string]int{"cam1": 9000, "cam2": 0} // cam2 has no port assigned
	sm := NewStreamManager(loopbacks, ports, func(string) bool { return true },
		StreamConfig{Host: "192.168.1.50"})

	got := sm.ConfiguredCameras()
	if len(got) != 1 || got[0] != "cam1" {
		t.Fatalf("expected ConfiguredCameras() == [cam1] (cam2 has no port, cam3 has no device), got %v", got)
	}
}
