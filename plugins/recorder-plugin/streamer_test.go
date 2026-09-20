package main

import (
	"os"
	"strings"
	"testing"
	"time"
)

func TestBuildFFmpegArgsWithoutLoopback(t *testing.T) {
	args := buildFFmpegArgs(CameraConfig{ID: "camA", DevicePath: "/dev/camA"}, "/out/camA.mkv")
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
	args := buildFFmpegArgs(CameraConfig{ID: "camA", DevicePath: "/dev/camA", LoopbackDevice: "/dev/video10"}, "/out/camA.mkv")
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

	sm := NewStreamManager(map[string]string{"cam1": "/dev/video10"}, func(string) bool { return true },
		StreamConfig{Host: "", Port: 9000})
	if err := sm.StartStream("cam1"); err == nil {
		t.Fatalf("expected error when stream_windows_host is empty")
	}

	sm2 := NewStreamManager(map[string]string{}, func(string) bool { return true },
		StreamConfig{Host: "192.168.1.50", Port: 9000})
	if err := sm2.StartStream("cam1"); err == nil {
		t.Fatalf("expected error when camera has no loopback_device configured")
	}

	sm3 := NewStreamManager(map[string]string{"cam1": "/dev/video10"}, func(string) bool { return false },
		StreamConfig{Host: "192.168.1.50", Port: 9000})
	if err := sm3.StartStream("cam1"); err == nil {
		t.Fatalf("expected error when camera is not recording")
	}
}

func TestStreamManagerStartStopSwitch(t *testing.T) {
	fakeFFmpegPath(t)

	loopbacks := map[string]string{"cam1": "/dev/video10", "cam2": "/dev/video11"}
	sm := NewStreamManager(loopbacks, func(string) bool { return true },
		StreamConfig{Host: "192.168.1.50", Port: 9000, Codec: "libx264", Bitrate: "4M"})

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

	if err := sm.StartStream("cam1"); err != nil {
		t.Fatalf("StartStream(cam1) failed: %v", err)
	}
	if cam, active := sm.ActiveCamera(); cam != "cam1" || !active {
		t.Fatalf("expected cam1 active, got cam=%s active=%v", cam, active)
	}
	select {
	case ev := <-events:
		if ev.cam != "cam1" || !ev.active {
			t.Fatalf("expected (cam1, active=true) event, got %+v", ev)
		}
	case <-time.After(time.Second):
		t.Fatalf("timed out waiting for start event")
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

	// Switching to cam2 stops cam1 and starts cam2.
	if err := sm.StartStream("cam2"); err != nil {
		t.Fatalf("StartStream(cam2) (switch) failed: %v", err)
	}
	if cam, active := sm.ActiveCamera(); cam != "cam2" || !active {
		t.Fatalf("expected cam2 active after switch, got cam=%s active=%v", cam, active)
	}
	select {
	case ev := <-events:
		if ev.cam != "cam2" || !ev.active {
			t.Fatalf("expected (cam2, active=true) event after switch, got %+v", ev)
		}
	case <-time.After(time.Second):
		t.Fatalf("timed out waiting for switch-start event")
	}

	if err := sm.StopStream(); err != nil {
		t.Fatalf("StopStream failed: %v", err)
	}
	if _, active := sm.ActiveCamera(); active {
		t.Fatalf("expected no active stream after StopStream")
	}
	select {
	case ev := <-events:
		if ev.cam != "cam2" || ev.active {
			t.Fatalf("expected (cam2, active=false) event after StopStream, got %+v", ev)
		}
	case <-time.After(time.Second):
		t.Fatalf("timed out waiting for stop event")
	}

	// Stopping again is a no-op, no error, no event.
	if err := sm.StopStream(); err != nil {
		t.Fatalf("StopStream (idempotent) failed: %v", err)
	}
	select {
	case ev := <-events:
		t.Fatalf("unexpected event on redundant StopStream: %+v", ev)
	case <-time.After(150 * time.Millisecond):
		// OK
	}
}
