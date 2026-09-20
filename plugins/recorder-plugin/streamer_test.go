package main

import (
	"os"
	"strings"
	"testing"
	"time"
)

func TestBuildFFmpegArgsWithoutLoopback(t *testing.T) {
	args := buildFFmpegArgs(CameraConfig{ID: "camA", DevicePath: "/dev/camA"}, "libx264", "/out/camA.mkv")
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
	args := buildFFmpegArgs(CameraConfig{ID: "camA", DevicePath: "/dev/camA", LoopbackDevice: "/dev/video10"}, "libx264", "/out/camA.mkv")
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

	libx264 := strings.Join(buildFFmpegArgs(cfg, "libx264", "/out/camA.mkv"), " ")
	if !strings.Contains(libx264, "-preset ultrafast") || !strings.Contains(libx264, "-crf 23") {
		t.Fatalf("expected libx264 branch to use -preset/-crf, got: %s", libx264)
	}
	if strings.Contains(libx264, "-global_quality") {
		t.Fatalf("did not expect -global_quality in the libx264 branch, got: %s", libx264)
	}

	qsv := strings.Join(buildFFmpegArgs(cfg, "h264_qsv", "/out/camA.mkv"), " ")
	if !strings.Contains(qsv, "-global_quality 23") {
		t.Fatalf("expected h264_qsv branch to use -global_quality, got: %s", qsv)
	}
	if strings.Contains(qsv, "-crf") {
		t.Fatalf("did not expect -crf (libx264-only flag) in the h264_qsv branch, got: %s", qsv)
	}

	// Empty codec must default to libx264, not crash or emit "-c:v " with nothing after it.
	defaulted := buildFFmpegArgs(cfg, "", "/out/camA.mkv")
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

	sm := NewStreamManager(map[string]string{"cam1": "/dev/video10"}, map[string]int{"cam1": 9000},
		func(string) bool { return true }, StreamConfig{Host: ""})
	if err := sm.StartStream("cam1"); err == nil {
		t.Fatalf("expected error when stream_windows_host is empty")
	}

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
}

// TestStreamManagerConcurrentCameras verifies that all configured cameras
// can stream at the same time, independently — starting or stopping one
// must never touch another, matching the "stream all 4 cameras (or fewer,
// whichever are in use) continuously" design.
func TestStreamManagerConcurrentCameras(t *testing.T) {
	fakeFFmpegPath(t)

	loopbacks := map[string]string{"cam1": "/dev/video10", "cam2": "/dev/video11", "cam3": "/dev/video12"}
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
