package main

import (
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func startFeedAndWait(t *testing.T, rm *RecorderManager, id string) {
	t.Helper()
	if _, err := rm.SetActiveCameras([]string{id}, false); err != nil {
		t.Fatal(err)
	}
	waitState(t, rm.feeds[id], FeedRunning)
}

func waitCond(t *testing.T, what string, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(8 * time.Second)
	for time.Now().Before(deadline) {
		if cond() {
			return
		}
		time.Sleep(15 * time.Millisecond)
	}
	t.Fatalf("nie doczekano: %s", what)
}

func TestBuildRecordArgsFromFeedHasExplicitTimingAndProgress(t *testing.T) {
	cfg := CameraConfig{ID: "c", DevicePath: "/dev/camera1", LoopbackDevice: "/dev/video11"}
	args := buildRecordArgs(cfg, "libx264", "", "/out/c.mkv", true)
	joined := strings.Join(args, " ")
	for _, want := range []string{"-progress pipe:1", "-use_wallclock_as_timestamps 1", "-video_size 1920x1080", "-framerate 30", "-input_format yuyv422"} {
		if !strings.Contains(joined, want) {
			t.Fatalf("brak %q: %s", want, joined)
		}
	}
	if strings.Index(joined, "-use_wallclock_as_timestamps") > strings.Index(joined, "-i /dev/video11") {
		t.Fatalf("opcje wejścia muszą stać przed -i: %s", joined)
	}
	direct := strings.Join(buildFFmpegArgs(cfg, "libx264", "", "/out/c.mkv"), " ")
	if strings.Contains(direct, "-progress") || strings.Contains(direct, "wallclock") {
		t.Fatalf("tryb bezpośredni ma zostać bez zmian: %s", direct)
	}
}

func TestStartRecordWhenFeedRunningRecordsFromFeed(t *testing.T) {
	rm, _ := testRM(t, "camera1")
	startFeedAndWait(t, rm, "camera1")
	if err := rm.StartRecord("camera1", RecordingMeta{}); err != nil {
		t.Fatal(err)
	}
	if !rm.cameras["camera1"].LastFromFeed() {
		t.Fatal("przy działającym odbiorze nagrywanie ma czytać z urządzenia pośredniego")
	}
	if rm.feeds["camera1"].Suspended() {
		t.Fatal("odbiór nie jest wstrzymany")
	}
	if err := rm.StopRecord("camera1"); err != nil {
		t.Fatal(err)
	}
	if !rm.feeds["camera1"].Running() {
		t.Fatal("koniec nagrywania nie przerywa odbioru")
	}
}

// Odbiór w błędzie + Start nagrywania = nagrywanie wprost z kamery (jak dotąd), nie brak nagrania.
func TestStartRecordWhenFeedInErrorRecordsDirectAndFeedWaits(t *testing.T) {
	rm, _ := testRM(t, "camera1")
	feed := rm.feeds["camera1"]
	feed.newCmd = helperCmd("exit", nil) // brak kamery / urządzenia pośredniego
	_ = feed.Start()
	waitState(t, feed, FeedError)

	if err := rm.StartRecord("camera1", RecordingMeta{}); err != nil {
		t.Fatalf("w stanie błędu nagrywanie ma ruszyć wprost z kamery: %v", err)
	}
	cam := rm.cameras["camera1"]
	if !cam.IsRecording() || cam.LastFromFeed() {
		t.Fatalf("nagrywanie wprost: recording=%v fromFeed=%v", cam.IsRecording(), cam.LastFromFeed())
	}
	if !feed.Suspended() || !feed.Wanted() {
		t.Fatal("odbiór oddaje kamerę na czas nagrywania, ale dalej jest chciany")
	}
	// wstrzymany odbiór nie ponawia prób (nie otwiera kamery drugi raz)
	var launches int32
	feed.newCmd = helperCmd("exit", &launches)
	time.Sleep(300 * time.Millisecond)
	if atomic.LoadInt32(&launches) != 0 {
		t.Fatal("wstrzymany odbiór nie może się uruchamiać")
	}

	feed.newCmd = helperCmd("frames", nil) // kamera wróciła
	if err := rm.StopRecord("camera1"); err != nil {
		t.Fatal(err)
	}
	if feed.Suspended() {
		t.Fatal("po nagraniu wprost odbiór wraca")
	}
	waitState(t, feed, FeedRunning)
}

func TestStartRecordWaitsForStartingFeedThenUsesIt(t *testing.T) {
	rm, _ := testRM(t, "camera1")
	feed := rm.feeds["camera1"]
	feed.newCmd = func(args []string) *exec.Cmd { // pierwsza klatka dopiero po chwili
		time.Sleep(250 * time.Millisecond)
		return helperCmd("frames", nil)(args)
	}
	_ = feed.Start()
	waitState(t, feed, FeedStarting)
	if err := rm.StartRecord("camera1", RecordingMeta{}); err != nil {
		t.Fatal(err)
	}
	if !rm.cameras["camera1"].LastFromFeed() {
		t.Fatal("startujący odbiór, który zdążył ruszyć, ma być źródłem nagrania")
	}
}

func TestFeedLossPausesRecordingAndReturnOpensNewSegmentOfSameSession(t *testing.T) {
	rm, _ := testRM(t, "camera1")
	feed := rm.feeds["camera1"]
	cam := rm.cameras["camera1"]
	var mu sync.Mutex
	var rotated []string
	cam.SetOnSegmentRotated(func(meta RecordingMeta, reason string) {
		mu.Lock()
		rotated = append(rotated, reason+":"+strconv.Itoa(meta.SegmentIndex))
		mu.Unlock()
	})

	startFeedAndWait(t, rm, "camera1")
	if err := rm.StartRecord("camera1", RecordingMeta{MatchID: "m1"}); err != nil {
		t.Fatal(err)
	}
	session := cam.LastMeta().SessionID

	// Utrata obrazu: odbiór zamiera (kolejny start daje 10 klatek i cisza); watchdog odbioru go zabija.
	feed.newCmd = helperCmd("stall", nil)
	// zabicie bieżącego procesu odbioru z zewnątrz (awaria)
	feed.mu.Lock()
	victim := feed.cmd
	feed.mu.Unlock()
	_ = victim.Process.Kill()

	waitCond(t, "pauza nagrania po utracie obrazu", func() bool { return cam.Paused() })
	if !cam.IsRecording() {
		t.Fatal("sesja nagrania trwa mimo pauzy segmentu")
	}

	feed.newCmd = helperCmd("frames", nil) // obraz wraca
	waitCond(t, "nowy segment po powrocie obrazu", func() bool { return !cam.Paused() && cam.LastMeta().SegmentIndex >= 2 })
	meta := cam.LastMeta()
	if meta.SessionID != session || meta.MatchID != "m1" {
		t.Fatalf("nowy segment ma należeć do tej samej sesji i meczu: %+v", meta)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(rotated) == 0 || !strings.HasPrefix(rotated[len(rotated)-1], "feed_restart:") {
		t.Fatalf("zdarzenie rotacji: %v", rotated)
	}
}

func TestPauseForFeedIsNoopWhenFeedAlreadyBack(t *testing.T) {
	rm, _ := testRM(t, "camera1")
	cam := rm.cameras["camera1"]
	startFeedAndWait(t, rm, "camera1")
	_ = rm.StartRecord("camera1", RecordingMeta{})

	paused, err := cam.PauseForFeed("feed_lost", func() bool { return false }) // obraz zdążył wrócić
	if err != nil || paused || cam.Paused() {
		t.Fatalf("pauza przy działającym obrazie ma nic nie robić: paused=%v err=%v", paused, err)
	}
}

func TestResumeAfterFeedIsNoopWhenNotPausedOrNotReady(t *testing.T) {
	rm, _ := testRM(t, "camera1")
	cam := rm.cameras["camera1"]
	startFeedAndWait(t, rm, "camera1")
	_ = rm.StartRecord("camera1", RecordingMeta{})

	if ok, _ := cam.ResumeAfterFeed(func() bool { return true }); ok {
		t.Fatal("nagranie nie jest w pauzie")
	}
	_, _ = cam.PauseForFeed("feed_lost", func() bool { return true })
	if ok, _ := cam.ResumeAfterFeed(func() bool { return false }); ok || !cam.Paused() {
		t.Fatal("gdy obrazu nie ma, wznowienie nie rusza")
	}
}

func TestStopRecordWhilePausedEndsSession(t *testing.T) {
	rm, _ := testRM(t, "camera1")
	cam := rm.cameras["camera1"]
	startFeedAndWait(t, rm, "camera1")
	_ = rm.StartRecord("camera1", RecordingMeta{})
	_, _ = cam.PauseForFeed("feed_lost", func() bool { return true })
	if err := rm.StopRecord("camera1"); err != nil {
		t.Fatalf("zatrzymanie nagrania w pauzie: %v", err)
	}
	if cam.IsRecording() || cam.Paused() {
		t.Fatal("po Stop sesja zakończona")
	}
}

// Watchdog nagrywania: proces żyje, ale nie zapisuje klatek → zabity; sesja zostaje w pauzie i dostaje nowy segment (obraz działa).
func TestRecordingWatchdogKillsStalledProcessAndSessionContinues(t *testing.T) {
	rm, _ := testRM(t, "camera1")
	cam := rm.cameras["camera1"]
	startFeedAndWait(t, rm, "camera1")
	cam.SetOnUnexpectedStop(func(cameraID string, meta RecordingMeta) { rm.handleUnexpectedStop(cameraID, meta) })
	cam.newFFmpeg = helperCmd("stall", nil) // nagrywanie zamiera po 10 klatkach

	if err := rm.StartRecord("camera1", RecordingMeta{}); err != nil {
		t.Fatal(err)
	}
	session := cam.LastMeta().SessionID
	first := cam.LastMeta().SegmentIndex
	cam.newFFmpeg = helperCmd("frames", nil) // następny segment zdrowy
	waitCond(t, "nowy segment po zabiciu zamarłego procesu", func() bool {
		return cam.IsRecording() && !cam.Paused() && cam.LastMeta().SegmentIndex > first
	})
	if cam.LastMeta().SessionID != session {
		t.Fatal("po zamarciu procesu nagrywającego sesja ma zostać ta sama (nowy segment, nie nowe nagranie)")
	}
}

// Przy końcu pracy pluginu nie zostają procesy odbioru.
func TestShutdownAllLeavesNoFeedProcesses(t *testing.T) {
	ids := []string{"camera1", "camera2", "camera3"}
	rm, _ := testRM(t, ids...)
	var mu sync.Mutex
	var cmds []*exec.Cmd
	for _, id := range ids {
		inner := rm.feeds[id].newCmd
		rm.feeds[id].newCmd = func(args []string) *exec.Cmd {
			c := inner(args)
			mu.Lock()
			cmds = append(cmds, c)
			mu.Unlock()
			return c
		}
	}
	if _, err := rm.SetActiveCameras(ids, false); err != nil {
		t.Fatal(err)
	}
	for _, id := range ids {
		waitState(t, rm.feeds[id], FeedRunning)
	}
	_ = rm.StartRecord("camera1", RecordingMeta{})

	rm.ShutdownAll()

	mu.Lock()
	defer mu.Unlock()
	if len(cmds) != 3 {
		t.Fatalf("uruchomiono %d procesów odbioru, oczekiwano 3", len(cmds))
	}
	for i, c := range cmds {
		if c.ProcessState == nil {
			t.Fatalf("proces odbioru %d (pid %d) nie został zakończony razem z pluginem", i, c.Process.Pid)
		}
	}
	for id, f := range rm.feeds {
		if f.Wanted() {
			t.Fatalf("%s dalej chciana po ShutdownAll", id)
		}
	}
	if rm.cameras["camera1"].IsRecording() {
		t.Fatal("nagrywanie zatrzymane")
	}
}

// Plugin zginął bez sprzątania (SIGKILL/awaria): następny start kończy osierocone procesy odbioru z plików pid.
func TestReapOrphanFeedsKillsLeftoverProcess(t *testing.T) {
	dir := t.TempDir()
	orphan := helperCmd("frames", nil)(nil)
	if err := orphan.Start(); err != nil {
		t.Fatal(err)
	}
	done := make(chan struct{})
	go func() { _ = orphan.Wait(); close(done) }()
	t.Cleanup(func() { _ = orphan.Process.Kill() })

	f := NewCameraFeed(CameraConfig{ID: "camera1", DevicePath: "/dev/c", LoopbackDevice: "/dev/video11"})
	f.pidDir = dir
	f.writePidFile(orphan.Process.Pid)

	old := processLooksLikeFeed
	processLooksLikeFeed = func(pid int, loopback string) bool { return pid == orphan.Process.Pid && loopback == "/dev/video11" }
	t.Cleanup(func() { processLooksLikeFeed = old })

	if n := ReapOrphanFeeds(dir); n != 1 {
		t.Fatalf("zakończono %d procesów, oczekiwano 1", n)
	}
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("osierocony proces nadal żyje")
	}
	if entries, _ := os.ReadDir(dir); len(entries) != 0 {
		t.Fatal("plik pid ma zostać usunięty")
	}
}

func TestReapOrphanFeedsLeavesForeignProcessAlone(t *testing.T) {
	dir := t.TempDir()
	other := helperCmd("frames", nil)(nil)
	if err := other.Start(); err != nil {
		t.Fatal(err)
	}
	done := make(chan struct{})
	go func() { _ = other.Wait(); close(done) }()
	t.Cleanup(func() { _ = other.Process.Kill() })

	f := NewCameraFeed(CameraConfig{ID: "camera1", DevicePath: "/dev/c", LoopbackDevice: "/dev/video11"})
	f.pidDir = dir
	f.writePidFile(other.Process.Pid) // numer, który tymczasem należy do innego programu

	old := processLooksLikeFeed
	processLooksLikeFeed = func(int, string) bool { return false }
	t.Cleanup(func() { processLooksLikeFeed = old })

	if n := ReapOrphanFeeds(dir); n != 0 {
		t.Fatalf("obcy proces nie może zostać zakończony, zakończono %d", n)
	}
	select {
	case <-done:
		t.Fatal("obcy proces został zabity")
	case <-time.After(300 * time.Millisecond):
	}
}
