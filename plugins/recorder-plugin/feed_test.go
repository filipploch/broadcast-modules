package main

import (
	"os"
	"os/exec"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// TestFeedHelperProcess nie jest testem: to proces udający ffmpeg odbioru. FEED_HELPER=sleep trzyma się do SIGINT/Kill,
// FEED_HELPER=exit kończy się od razu błędem.
func TestFeedHelperProcess(t *testing.T) {
	switch os.Getenv("FEED_HELPER") {
	case "sleep":
		time.Sleep(time.Minute)
		os.Exit(0)
	case "exit":
		os.Exit(3)
	}
}

func helperCmd(mode string, launches *int32) func(args []string) *exec.Cmd {
	return func(args []string) *exec.Cmd {
		if launches != nil {
			atomic.AddInt32(launches, 1)
		}
		cmd := exec.Command(os.Args[0], "-test.run=TestFeedHelperProcess")
		cmd.Env = append(os.Environ(), "FEED_HELPER="+mode)
		return cmd
	}
}

func testFeed(mode string, launches *int32) *CameraFeed {
	f := NewCameraFeed(CameraConfig{ID: "cam1", DevicePath: "/dev/cam1", LoopbackDevice: "/dev/video11"})
	f.newCmd = helperCmd(mode, launches)
	f.grace = 150 * time.Millisecond
	f.retryDelay = 60 * time.Millisecond
	return f
}

func waitState(t *testing.T, f *CameraFeed, want string) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if st, _ := f.State(); st == want {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	st, e := f.State()
	t.Fatalf("stan %q nie osiągnięty, jest %q %q", want, st, e)
}

func TestBuildFeedArgs(t *testing.T) {
	args := buildFeedArgs(CameraConfig{ID: "c", DevicePath: "/dev/camera1", LoopbackDevice: "/dev/video11"})
	joined := strings.Join(args, " ")
	for _, want := range []string{"-input_format mjpeg", "-video_size 1920x1080", "-framerate 30", "-i /dev/camera1", "-pix_fmt yuyv422", "-f v4l2"} {
		if !strings.Contains(joined, want) {
			t.Fatalf("brak %q w: %s", want, joined)
		}
	}
	if args[len(args)-1] != "/dev/video11" {
		t.Fatalf("ostatni argument ma być urządzeniem pośrednim, jest %q", args[len(args)-1])
	}
	if strings.Contains(joined, "-c:v") || strings.Contains(joined, ".mkv") {
		t.Fatalf("odbiór nie koduje ani nie nagrywa plików: %s", joined)
	}
}

func TestBuildRecordArgsFromFeedReadsLoopback(t *testing.T) {
	cfg := CameraConfig{ID: "c", DevicePath: "/dev/camera1", LoopbackDevice: "/dev/video11"}
	args := buildRecordArgs(cfg, "libx264", "", "/out/c.mkv", true)
	joined := strings.Join(args, " ")
	if !strings.Contains(joined, "-input_format yuyv422") || !strings.Contains(joined, "-i /dev/video11") {
		t.Fatalf("nagrywanie z odbioru ma czytać z urządzenia pośredniego: %s", joined)
	}
	if strings.Contains(joined, "/dev/camera1") || strings.Contains(joined, "mjpeg") {
		t.Fatalf("nagrywanie z odbioru nie może otwierać kamery: %s", joined)
	}
	if strings.Contains(joined, "filter_complex") || strings.Count(joined, "-f v4l2") != 1 {
		t.Fatalf("nagrywanie z odbioru nie pisze na urządzenie pośrednie: %s", joined)
	}
	if args[len(args)-1] != "/out/c.mkv" {
		t.Fatalf("ostatni argument ma być plikiem nagrania: %q", args[len(args)-1])
	}

	vaapi := strings.Join(buildRecordArgs(cfg, "h264_vaapi", "/dev/dri/renderD128", "/out/c.mkv", true), " ")
	if !strings.Contains(vaapi, "format=nv12") || !strings.Contains(vaapi, "hwupload") {
		t.Fatalf("VAAPI z odbioru: brak konwersji do nv12/hwupload: %s", vaapi)
	}
}

func TestBuildFFmpegArgsDirectModeUnchanged(t *testing.T) {
	cfg := CameraConfig{ID: "c", DevicePath: "/dev/camera1", LoopbackDevice: "/dev/video11"}
	direct := strings.Join(buildFFmpegArgs(cfg, "libx264", "", "/out/c.mkv"), " ")
	if !strings.Contains(direct, "-i /dev/camera1") || !strings.Contains(direct, "split=2[rec][stream]") {
		t.Fatalf("tryb bezpośredni ma otwierać kamerę i kopiować obraz na urządzenie pośrednie: %s", direct)
	}
}

func TestFeedStartsRunsAndStops(t *testing.T) {
	var launches int32
	f := testFeed("sleep", &launches)
	var mu sync.Mutex
	var seen []string
	f.SetOnChange(func(id, state, errMsg string) { mu.Lock(); seen = append(seen, state); mu.Unlock() })

	if err := f.Start(); err != nil {
		t.Fatal(err)
	}
	if err := f.Start(); err != nil { // idempotentnie
		t.Fatal(err)
	}
	waitState(t, f, FeedRunning)
	if !f.Running() || !f.Wanted() {
		t.Fatal("odbiór ma działać i być chciany")
	}
	f.Stop()
	if st, _ := f.State(); st != FeedOff || f.Wanted() {
		t.Fatalf("po Stop stan off, jest %q wanted=%v", st, f.Wanted())
	}
	if n := atomic.LoadInt32(&launches); n != 1 {
		t.Fatalf("podwójny Start uruchomił %d procesów, ma być 1", n)
	}
	mu.Lock()
	defer mu.Unlock()
	if strings.Join(seen, ",") != "starting,running,off" {
		t.Fatalf("kolejność stanów: %v", seen)
	}
}

func TestFeedRetriesAfterFailureAndRecovers(t *testing.T) {
	var launches int32
	f := testFeed("exit", &launches)
	if err := f.Start(); err != nil {
		t.Fatal(err)
	}
	waitState(t, f, FeedError)
	if _, msg := f.State(); msg != "" && !strings.Contains(msg, "ffmpeg") {
		t.Fatalf("błąd ma opisywać przyczynę: %q", msg)
	}
	deadline := time.Now().Add(5 * time.Second)
	for atomic.LoadInt32(&launches) < 3 && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if n := atomic.LoadInt32(&launches); n < 3 {
		t.Fatalf("po awarii odbiór ma ponawiać próby (bez limitu), uruchomień: %d", n)
	}

	f.newCmd = helperCmd("sleep", nil) // kamera wróciła
	waitState(t, f, FeedRunning)
	f.Stop()
}

func TestFeedStopDuringRetryDoesNotRevive(t *testing.T) {
	var launches int32
	f := testFeed("exit", &launches)
	_ = f.Start()
	waitState(t, f, FeedError)
	f.Stop()
	n := atomic.LoadInt32(&launches)
	time.Sleep(300 * time.Millisecond)
	if atomic.LoadInt32(&launches) != n {
		t.Fatal("po Stop odbiór nie może się sam wznowić")
	}
	if st, _ := f.State(); st != FeedOff {
		t.Fatalf("stan po Stop: %q", st)
	}
}

func TestFeedWithoutLoopbackCannotStart(t *testing.T) {
	f := NewCameraFeed(CameraConfig{ID: "c", DevicePath: "/dev/c"})
	if f.CanFeed() || f.Start() == nil {
		t.Fatal("kamera bez loopback_device nie ma odbioru")
	}
}
