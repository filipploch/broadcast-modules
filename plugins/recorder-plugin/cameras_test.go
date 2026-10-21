package main

import (
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// testRM: RecorderManager z kamerami o odbiorze udawanym procesem pomocniczym (bez prawdziwego ffmpeg).
func testRM(t *testing.T, ids ...string) (*RecorderManager, map[string]*int32) {
	t.Helper()
	rm := &RecorderManager{
		cameras:  map[string]*CameraRecorder{},
		feeds:    map[string]*CameraFeed{},
		streamer: NewStreamManager(map[string]string{}, map[string]int{}, nil, StreamConfig{}),
	}
	launches := map[string]*int32{}
	for _, id := range ids {
		cfg := CameraConfig{ID: id, DevicePath: "/dev/" + id, LoopbackDevice: "/dev/loop-" + id, Enabled: true}
		cam := NewCameraRecorder(cfg, t.TempDir(), SegmentConfig{}, "libx264", "")
		feed := NewCameraFeed(cfg)
		var n int32
		launches[id] = &n
		feed.newCmd = helperCmd("sleep", &n)
		feed.grace = 100 * 1e6
		feed.retryDelay = 50 * 1e6
		cam.feedRunning = feed.Running
		feed.SetOnChange(func(cameraID, state, errMsg string) { rm.onFeedChanged(cameraID, state, errMsg) })
		rm.cameras[id] = cam
		rm.feeds[id] = feed
	}
	t.Cleanup(func() {
		for _, f := range rm.feeds {
			f.Stop()
		}
	})
	return rm, launches
}

func TestSetActiveCamerasStartsAndStopsToMatchList(t *testing.T) {
	rm, _ := testRM(t, "camera1", "camera2", "camera3")

	if _, err := rm.SetActiveCameras([]string{"camera1", "camera2"}, false); err != nil {
		t.Fatal(err)
	}
	waitState(t, rm.feeds["camera1"], FeedRunning)
	waitState(t, rm.feeds["camera2"], FeedRunning)
	if rm.feeds["camera3"].Wanted() {
		t.Fatal("camera3 nie jest na liście")
	}

	if _, err := rm.SetActiveCameras([]string{"camera1", "camera3"}, false); err != nil {
		t.Fatal(err)
	}
	waitState(t, rm.feeds["camera3"], FeedRunning)
	if st, _ := rm.feeds["camera2"].State(); st != FeedOff || rm.feeds["camera2"].Wanted() {
		t.Fatalf("camera2 zdjęta z listy ma być wyłączona, jest %q", st)
	}
	if !rm.feeds["camera1"].Running() {
		t.Fatal("camera1 została na liście i ma dalej działać")
	}

	if _, err := rm.SetActiveCameras(nil, false); err != nil { // pusta lista wyłącza wszystko
		t.Fatal(err)
	}
	for id, f := range rm.feeds {
		if f.Wanted() {
			t.Fatalf("%s powinna być wyłączona", id)
		}
	}
}

func TestSetActiveCamerasSameListTwiceChangesNothing(t *testing.T) {
	rm, launches := testRM(t, "camera1", "camera2")
	list := []string{"camera1", "camera2"}
	_, _ = rm.SetActiveCameras(list, false)
	waitState(t, rm.feeds["camera1"], FeedRunning)
	waitState(t, rm.feeds["camera2"], FeedRunning)
	before1, before2 := atomic.LoadInt32(launches["camera1"]), atomic.LoadInt32(launches["camera2"])

	_, _ = rm.SetActiveCameras(list, false)
	if atomic.LoadInt32(launches["camera1"]) != before1 || atomic.LoadInt32(launches["camera2"]) != before2 {
		t.Fatal("ta sama lista wysłana drugi raz nie może restartować kamer")
	}
}

func TestSetActiveCamerasRejectsUnknownCameraWithoutChanges(t *testing.T) {
	rm, launches := testRM(t, "camera1")
	_, err := rm.SetActiveCameras([]string{"camera1", "camera9"}, false)
	if err == nil || !strings.Contains(err.Error(), "camera9") {
		t.Fatalf("nieznana kamera ma odrzucić całą listę z jej nazwą, błąd: %v", err)
	}
	if rm.feeds["camera1"].Wanted() || atomic.LoadInt32(launches["camera1"]) != 0 {
		t.Fatal("odrzucona lista nie może nic zmienić")
	}
}

func TestSetActiveCamerasKeepsRecordingCameraUnlessConfirmed(t *testing.T) {
	rm, _ := testRM(t, "camera1", "camera2")
	_, _ = rm.SetActiveCameras([]string{"camera1", "camera2"}, false)
	waitState(t, rm.feeds["camera2"], FeedRunning)

	rm.cameras["camera2"].recording = true // udajemy trwające nagrywanie
	blocked, err := rm.SetActiveCameras([]string{"camera1"}, false)
	if err != nil {
		t.Fatal(err)
	}
	if len(blocked) != 1 || blocked[0] != "camera2" {
		t.Fatalf("camera2 nagrywa: zdjęcie z listy ma być zablokowane do potwierdzenia, blocked=%v", blocked)
	}
	if !rm.feeds["camera2"].Running() {
		t.Fatal("zablokowana kamera dalej działa")
	}
}

func TestStartRecordWaitsForFeedWhenCameraIsStarting(t *testing.T) {
	rm, _ := testRM(t, "camera1")
	// odbiór chciany, ale proces jeszcze nie przeżył okresu uruchomienia
	rm.feeds["camera1"].grace = 5 * 1e9
	_ = rm.feeds["camera1"].Start()
	waitState(t, rm.feeds["camera1"], FeedStarting)

	err := rm.StartRecord("camera1", RecordingMeta{})
	if err == nil || !strings.Contains(err.Error(), "jeszcze nie działa") {
		t.Fatalf("nagrywanie kamery, którą trzyma startujący odbiór, ma się nie uruchomić: %v", err)
	}
	if rm.cameras["camera1"].IsRecording() {
		t.Fatal("nagrywanie nie powinno ruszyć")
	}
}

func TestLoopbackHasDataFollowsFeedOrDirectRecording(t *testing.T) {
	rm, _ := testRM(t, "camera1")
	if rm.loopbackHasData("camera1") {
		t.Fatal("bez odbioru i nagrywania urządzenie pośrednie jest puste")
	}
	rm.cameras["camera1"].recording = true
	if !rm.loopbackHasData("camera1") {
		t.Fatal("nagrywanie bezpośrednie zapisuje kopię obrazu na urządzenie pośrednie")
	}
	rm.cameras["camera1"].recording = false
	_ = rm.feeds["camera1"].Start()
	waitState(t, rm.feeds["camera1"], FeedRunning)
	if !rm.loopbackHasData("camera1") {
		t.Fatal("działający odbiór dostarcza obraz")
	}
}

func TestCamerasStatusDescribesEachCamera(t *testing.T) {
	rm, _ := testRM(t, "camera1", "camera2")
	_, _ = rm.SetActiveCameras([]string{"camera1"}, false)
	waitState(t, rm.feeds["camera1"], FeedRunning)
	st := rm.CamerasStatus()
	c1 := st["camera1"].(map[string]interface{})
	c2 := st["camera2"].(map[string]interface{})
	if c1["state"] != FeedRunning || c1["wanted"] != true || c1["recording"] != false {
		t.Fatalf("camera1: %v", c1)
	}
	if c2["state"] != FeedOff || c2["wanted"] != false {
		t.Fatalf("camera2: %v", c2)
	}
}

func TestSetActiveCamerasMessageRepliesWithStatusAndBlocked(t *testing.T) {
	hc, got := ctxTestHub(t)
	rm, _ := testRM(t, "camera1")
	rm.hubClient = hc

	rm.handleSetActiveCameras(&Message{From: "main-module", Type: "set_active_cameras",
		Payload: map[string]interface{}{"cameras": []interface{}{"camera1"}}}, hc)
	rm.handleSetActiveCameras(&Message{From: "main-module", Type: "set_active_cameras",
		Payload: map[string]interface{}{"cameras": "camera1"}}, hc)

	var reply, bad, running *Message
	deadline := time.After(5 * time.Second)
	for reply == nil || bad == nil || running == nil {
		select {
		case m := <-got:
			switch {
			case m.Type == "set_active_cameras_response" && m.Payload["status"] == "ok":
				reply = &m
			case m.Type == "set_active_cameras_response" && m.Payload["status"] == "error":
				bad = &m
			case m.Type == "camera_state" && m.Payload["state"] == FeedRunning:
				running = &m
			}
		case <-deadline:
			t.Fatalf("brak wiadomości: odpowiedź=%v błąd=%v działa=%v", reply != nil, bad != nil, running != nil)
		}
	}
	cams := reply.Payload["cameras"].(map[string]interface{})
	if _, ok := cams["camera1"]; !ok {
		t.Fatalf("odpowiedź ma opisywać kamery: %v", reply.Payload)
	}
	if running.Payload["camera_id"] != "camera1" {
		t.Fatalf("camera_state: %v", running.Payload)
	}
}
