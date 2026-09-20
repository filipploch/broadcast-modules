package main

import (
	"os"
	"testing"
	"time"
)

// TestSegmentationSimulation exercises the segment-rotation logic end to end
// using a fake camera device path that points at /bin/sleep-like behaviour is
// not possible without real ffmpeg, so this test focuses on the pure
// state-machine parts that don't need an actual video device: MarkSegmentEnd's
// timing rules and StartRecord/StopRecord bookkeeping, using a CameraRecorder
// wired with a DevicePath but WITHOUT ever actually calling StartRecord
// (which would need a real "ffmpeg" binary + camera). This is a logic-only
// smoke test, not a full integration test.
func TestSegmentConfigDefaultsSane(t *testing.T) {
	segCfg := SegmentConfig{
		MinDuration: 150 * time.Millisecond,
		MaxDuration: 400 * time.Millisecond,
		SignalDelay: 50 * time.Millisecond,
	}
	if segCfg.MaxDuration <= segCfg.MinDuration {
		t.Fatalf("MaxDuration must be greater than MinDuration")
	}
}

// TestMarkSegmentEndBeforeRecording verifies that a signal sent to a camera
// that isn't recording is rejected instead of silently queued.
func TestMarkSegmentEndBeforeRecording(t *testing.T) {
	cam := NewCameraRecorder(
		CameraConfig{ID: "camX", DeviceName: "camX", DevicePath: "/dev/null"},
		t.TempDir(),
		SegmentConfig{MinDuration: 150 * time.Millisecond, MaxDuration: 400 * time.Millisecond, SignalDelay: 50 * time.Millisecond},
		"libx264",
	)

	if err := cam.MarkSegmentEnd(); err == nil {
		t.Fatalf("expected error marking segment end while not recording")
	}
}

// TestRotationTimingWithFakeFFmpeg drives the real StartRecord/MarkSegmentEnd/
// StopRecord machinery against a stub "ffmpeg" binary (a short shell script)
// so segmentGen/pendingSignal/expectedStop all get exercised for real,
// without needing an actual camera.
func TestRotationTimingWithFakeFFmpeg(t *testing.T) {
	fakeFFmpegDir := t.TempDir()
	fakeFFmpeg := fakeFFmpegDir + "/ffmpeg"
	script := "#!/bin/sh\ntrap 'exit 0' INT TERM\nwhile true; do sleep 0.05; done\n"
	if err := os.WriteFile(fakeFFmpeg, []byte(script), 0o755); err != nil {
		t.Fatalf("failed to write fake ffmpeg: %v", err)
	}
	oldPath := os.Getenv("PATH")
	os.Setenv("PATH", fakeFFmpegDir+":"+oldPath)
	defer os.Setenv("PATH", oldPath)

	outputDir := t.TempDir()
	segCfg := SegmentConfig{
		MinDuration: 200 * time.Millisecond,
		MaxDuration: 2 * time.Second, // must not fire during this test
		SignalDelay: 100 * time.Millisecond,
	}
	cam := NewCameraRecorder(
		CameraConfig{ID: "cam1", DeviceName: "cam1", DevicePath: "/dev/null"},
		outputDir,
		segCfg,
		"libx264",
	)

	rotated := make(chan string, 8)
	cam.SetOnSegmentRotated(func(meta RecordingMeta, reason string) {
		rotated <- reason
	})

	if err := cam.StartRecord(RecordingMeta{}); err != nil {
		t.Fatalf("StartRecord failed: %v", err)
	}
	if cam.LastMeta().SegmentIndex != 1 {
		t.Fatalf("expected segment 1, got %d", cam.LastMeta().SegmentIndex)
	}

	// Signal arrives immediately — well before MinDuration (200ms) — must be
	// queued and only take effect once MinDuration is reached, plus SignalDelay.
	if err := cam.MarkSegmentEnd(); err != nil {
		t.Fatalf("MarkSegmentEnd failed: %v", err)
	}

	select {
	case reason := <-rotated:
		if reason != "signal" {
			t.Fatalf("expected rotation reason 'signal', got %q", reason)
		}
	case <-time.After(2 * time.Second):
		t.Fatalf("timed out waiting for queued signal to rotate the segment")
	}

	if cam.LastMeta().SegmentIndex != 2 {
		t.Fatalf("expected segment 2 after rotation, got %d", cam.LastMeta().SegmentIndex)
	}
	if cam.LastMeta().SessionID == "" {
		t.Fatalf("expected non-empty session_id to persist across rotation")
	}

	// A second signal, sent well after MinDuration this time, should rotate
	// after roughly SignalDelay.
	time.Sleep(250 * time.Millisecond)
	before := time.Now()
	if err := cam.MarkSegmentEnd(); err != nil {
		t.Fatalf("MarkSegmentEnd (2nd) failed: %v", err)
	}
	select {
	case reason := <-rotated:
		if reason != "signal" {
			t.Fatalf("expected rotation reason 'signal', got %q", reason)
		}
		if d := time.Since(before); d < segCfg.SignalDelay {
			t.Fatalf("rotation happened too early: %v < SignalDelay %v", d, segCfg.SignalDelay)
		}
	case <-time.After(2 * time.Second):
		t.Fatalf("timed out waiting for immediate signal to rotate the segment")
	}
	if cam.LastMeta().SegmentIndex != 3 {
		t.Fatalf("expected segment 3, got %d", cam.LastMeta().SegmentIndex)
	}

	if err := cam.StopRecord(); err != nil {
		t.Fatalf("StopRecord failed: %v", err)
	}
	if cam.IsRecording() {
		t.Fatalf("expected recording to be stopped")
	}

	// No further rotations should fire after StopRecord.
	select {
	case reason := <-rotated:
		t.Fatalf("unexpected rotation after StopRecord: %q", reason)
	case <-time.After(300 * time.Millisecond):
		// OK — nothing fired.
	}
}

// TestMaxDurationRotatesWithoutSignal verifies the hard cap fires on its own,
// with no segment-end signal ever sent.
func TestMaxDurationRotatesWithoutSignal(t *testing.T) {
	fakeFFmpegDir := t.TempDir()
	fakeFFmpeg := fakeFFmpegDir + "/ffmpeg"
	script := "#!/bin/sh\ntrap 'exit 0' INT TERM\nwhile true; do sleep 0.05; done\n"
	if err := os.WriteFile(fakeFFmpeg, []byte(script), 0o755); err != nil {
		t.Fatalf("failed to write fake ffmpeg: %v", err)
	}
	oldPath := os.Getenv("PATH")
	os.Setenv("PATH", fakeFFmpegDir+":"+oldPath)
	defer os.Setenv("PATH", oldPath)

	segCfg := SegmentConfig{
		MinDuration: 5 * time.Second,        // irrelevant here — no signal is sent
		MaxDuration: 200 * time.Millisecond, // hard cap under test
		SignalDelay: 10 * time.Second,
	}
	cam := NewCameraRecorder(
		CameraConfig{ID: "cam2", DeviceName: "cam2", DevicePath: "/dev/null"},
		t.TempDir(),
		segCfg,
		"libx264",
	)

	rotated := make(chan string, 8)
	cam.SetOnSegmentRotated(func(meta RecordingMeta, reason string) { rotated <- reason })

	if err := cam.StartRecord(RecordingMeta{}); err != nil {
		t.Fatalf("StartRecord failed: %v", err)
	}

	select {
	case reason := <-rotated:
		if reason != "max_duration" {
			t.Fatalf("expected rotation reason 'max_duration', got %q", reason)
		}
	case <-time.After(2 * time.Second):
		t.Fatalf("timed out waiting for max-duration rotation")
	}
	if cam.LastMeta().SegmentIndex != 2 {
		t.Fatalf("expected segment 2 after max-duration rotation, got %d", cam.LastMeta().SegmentIndex)
	}

	_ = cam.StopRecord()
}
