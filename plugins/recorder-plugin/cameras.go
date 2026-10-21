package main

import (
	"fmt"
	"log"
	"sort"
	"time"
)

// cameras.go: zestaw aktywnych kamer. Moduł główny wysyła PEŁNĄ listę kamer, które mają działać ("set_active_cameras");
// plugin włącza brakujące (odbiór obrazu → urządzenie pośrednie → podgląd SRT dla OBS) i wyłącza zbędne. Ta sama lista wysłana
// dwa razy niczego nie zmienia. Obraz dla OBS nie zależy od nagrywania: nagrywanie czyta z urządzenia pośredniego (camera.go).

func (rm *RecorderManager) feedFor(cameraID string) *CameraFeed {
	rm.mu.RLock()
	defer rm.mu.RUnlock()
	return rm.feeds[cameraID]
}

// feedRunning: odbiór kamery działa (urządzenie pośrednie dostaje obraz).
func (rm *RecorderManager) feedRunning(cameraID string) bool {
	feed := rm.feedFor(cameraID)
	return feed != nil && feed.Running()
}

// loopbackHasData: czy urządzenie pośrednie kamery ma obraz do wysłania przez SRT: działa odbiór albo (tryb bezpośredni)
// nagrywanie, które samo zapisuje kopię obrazu na urządzenie pośrednie.
func (rm *RecorderManager) loopbackHasData(cameraID string) bool {
	if rm.feedRunning(cameraID) {
		return true
	}
	rm.mu.RLock()
	cam, ok := rm.cameras[cameraID]
	rm.mu.RUnlock()
	return ok && cam.IsRecording()
}

// onFeedChanged: zmiana stanu odbioru kamery. Podgląd SRT idzie za odbiorem (działa → start, inaczej stop),
// a moduł dostaje zdarzenie "camera_state" (pasek „KAMERA N: brak obrazu”, odświeżenie źródła w OBS po „działa”).
func (rm *RecorderManager) onFeedChanged(cameraID, state, errMsg string) {
	if state == FeedRunning {
		go func() {
			if err := rm.streamer.StartStream(cameraID); err != nil {
				log.Printf("⏭️  [%s] podgląd SRT nie wystartował: %v", cameraID, err)
			}
		}()
		go rm.resumeWhenFeedReady(cameraID) // nagranie w pauzie dostaje nowy segment
	} else {
		feed := rm.feedFor(cameraID)
		if feed == nil || !feed.Suspended() { // wstrzymanie = nagrywanie wprost, nie utrata obrazu
			go rm.pauseRecordingForFeed(cameraID)
		}
		if !rm.hasDirectRecording(cameraID) {
			if err := rm.streamer.StopStream(cameraID); err != nil {
				log.Printf("⏭️  [%s] zatrzymanie podglądu SRT: %v", cameraID, err)
			}
		}
	}
	rm.notifyCameraState(cameraID)
}

// pauseRecordingForFeed: odbiór stracił obraz — nagrywanie z odbioru zamyka bieżący segment (sesja trwa).
func (rm *RecorderManager) pauseRecordingForFeed(cameraID string) {
	rm.mu.RLock()
	cam := rm.cameras[cameraID]
	rm.mu.RUnlock()
	feed := rm.feedFor(cameraID)
	if cam == nil || feed == nil {
		return
	}
	paused, err := cam.PauseForFeed("feed_lost", func() bool { return !feed.Running() })
	if err != nil {
		log.Printf("❌ [%s] pauza nagrania po utracie obrazu: %v", cameraID, err)
		return
	}
	if paused {
		rm.notifyRecordingInterrupted(cameraID, "feed_lost")
	}
}

// resumeWhenFeedReady otwiera nowy segment nagrania w pauzie, gdy obraz działa (ponawia po błędzie uruchomienia).
func (rm *RecorderManager) resumeWhenFeedReady(cameraID string) {
	rm.mu.RLock()
	cam := rm.cameras[cameraID]
	rm.mu.RUnlock()
	feed := rm.feedFor(cameraID)
	if cam == nil || feed == nil {
		return
	}
	for attempt := 1; attempt <= autoRestartMaxTries; attempt++ {
		if !cam.Paused() || !feed.Running() {
			return
		}
		ok, err := cam.ResumeAfterFeed(feed.Running)
		if err == nil {
			_ = ok
			return
		}
		log.Printf("❌ [%s] nowy segment po powrocie obrazu (próba %d/%d): %v", cameraID, attempt, autoRestartMaxTries, err)
		time.Sleep(autoRestartDelay)
	}
	rm.mu.RLock()
	hc := rm.hubClient
	rm.mu.RUnlock()
	if hc != nil {
		_ = hc.Send(&Message{To: "main-module", Context: rm.cameraContext(cameraID), Type: "recording_restart_failed",
			Payload: map[string]interface{}{"camera_id": cameraID, "attempts": autoRestartMaxTries}})
	}
}

// notifyRecordingInterrupted: nagrywanie trwa jako sesja, ale bieżący segment zamknięto z powodu utraty obrazu lub awarii procesu.
func (rm *RecorderManager) notifyRecordingInterrupted(cameraID, reason string) {
	rm.mu.RLock()
	hc := rm.hubClient
	rm.mu.RUnlock()
	if hc == nil {
		return
	}
	_ = hc.Send(&Message{To: "main-module", Context: rm.cameraContext(cameraID), Type: "recording_interrupted",
		Payload: map[string]interface{}{"camera_id": cameraID, "reason": reason}})
}

// hasDirectRecording: kamera nagrywa wprost (bez odbioru) i jej strumień trzyma to nagrywanie.
func (rm *RecorderManager) hasDirectRecording(cameraID string) bool {
	rm.mu.RLock()
	cam, ok := rm.cameras[cameraID]
	rm.mu.RUnlock()
	return ok && cam.IsRecording() && !rm.feedRunning(cameraID)
}

// cameraInfo to opis jednej kamery w odpowiedziach i zdarzeniach.
func (rm *RecorderManager) cameraInfo(cameraID string) map[string]interface{} {
	info := map[string]interface{}{
		"camera_id": cameraID,
		"state":     FeedOff,
		"wanted":    false,
	}
	if feed := rm.feedFor(cameraID); feed != nil {
		st, errMsg := feed.State()
		info["state"] = st
		info["wanted"] = feed.Wanted()
		if errMsg != "" {
			info["error"] = errMsg
		}
	}
	rm.mu.RLock()
	cam, ok := rm.cameras[cameraID]
	rm.mu.RUnlock()
	info["recording"] = ok && cam.IsRecording()
	info["streaming"] = rm.streamer != nil && rm.streamer.IsStreaming(cameraID)
	return info
}

// CamerasStatus: stan wszystkich kamer plugin (z odbiorem lub nagrywaniem), po identyfikatorze.
func (rm *RecorderManager) CamerasStatus() map[string]interface{} {
	rm.mu.RLock()
	ids := make([]string, 0, len(rm.cameras))
	for id := range rm.cameras {
		ids = append(ids, id)
	}
	rm.mu.RUnlock()
	sort.Strings(ids)
	out := make(map[string]interface{}, len(ids))
	for _, id := range ids {
		out[id] = rm.cameraInfo(id)
	}
	return out
}

func (rm *RecorderManager) notifyCameraState(cameraID string) {
	rm.mu.RLock()
	hc := rm.hubClient
	rm.mu.RUnlock()
	if hc == nil {
		return
	}
	_ = hc.Send(&Message{
		To:      "main-module",
		Type:    "camera_state",
		Payload: rm.cameraInfo(cameraID),
	})
}

// SetActiveCameras uzgadnia odbiór z pełną listą kamer. Zwraca kamery, których nie wyłączono, bo trwa ich nagrywanie
// (stopRecordingForRemoved == false) — o tym, czy przerwać nagrywanie, decyduje moduł po potwierdzeniu przez operatora.
// Nieznana kamera albo kamera bez odbioru (brak device_path/loopback_device) odrzuca CAŁĄ listę, niczego nie zmieniając.
func (rm *RecorderManager) SetActiveCameras(wanted []string, stopRecordingForRemoved bool) (blocked []string, err error) {
	want := make(map[string]bool, len(wanted))
	for _, id := range wanted {
		want[id] = true
		if rm.feedFor(id) == nil {
			return nil, fmt.Errorf("kamera %q nie ma odbioru obrazu (nieznana albo brak device_path/loopback_device)", id)
		}
	}

	rm.mu.RLock()
	all := make([]string, 0, len(rm.feeds))
	for id := range rm.feeds {
		all = append(all, id)
	}
	rm.mu.RUnlock()
	sort.Strings(all)

	for _, id := range all { // najpierw włączamy brakujące, żeby zmiana zestawu nie zostawiła chwilowo pustej listy
		if want[id] {
			if e := rm.feedFor(id).Start(); e != nil {
				log.Printf("❌ [%s] start odbioru: %v", id, e)
			}
		}
	}
	for _, id := range all {
		if want[id] {
			continue
		}
		feed := rm.feedFor(id)
		if !feed.Wanted() {
			continue
		}
		rm.mu.RLock()
		cam := rm.cameras[id]
		rm.mu.RUnlock()
		if cam != nil && cam.IsRecording() {
			if !stopRecordingForRemoved {
				blocked = append(blocked, id)
				continue
			}
			if e := rm.StopRecord(id); e != nil {
				log.Printf("⚠️  [%s] zatrzymanie nagrywania przed wyłączeniem kamery: %v", id, e)
			}
		}
		feed.Stop()
		if e := rm.streamer.StopStream(id); e != nil {
			log.Printf("⏭️  [%s] zatrzymanie podglądu SRT: %v", id, e)
		}
	}
	return blocked, nil
}

// handleSetActiveCameras: payload {"cameras": ["camera1", ...], "stop_recording_for_removed": false}.
func (rm *RecorderManager) handleSetActiveCameras(msg *Message, hubClient *HubClient) {
	raw, ok := msg.Payload["cameras"].([]interface{})
	if !ok {
		rm.replyError(hubClient, msg, "missing cameras (lista identyfikatorów)")
		return
	}
	ids := make([]string, 0, len(raw))
	for _, v := range raw {
		s, isStr := v.(string)
		if !isStr || s == "" {
			rm.replyError(hubClient, msg, "cameras musi być listą identyfikatorów (tekst)")
			return
		}
		ids = append(ids, s)
	}
	stopRec, _ := msg.Payload["stop_recording_for_removed"].(bool)

	blocked, err := rm.SetActiveCameras(ids, stopRec)
	if err != nil {
		log.Printf("❌ set_active_cameras: %v", err)
		rm.replyError(hubClient, msg, err.Error())
		return
	}
	rm.replyOK(hubClient, msg, map[string]interface{}{
		"cameras": rm.CamerasStatus(),
		"blocked": blocked,
	})
}

// ShutdownAll: koniec pracy pluginu lub wyłączenie hosta: nagrania, podglądy i odbiór obrazu.
func (rm *RecorderManager) ShutdownAll() {
	rm.StopAll()
	rm.mu.RLock()
	feeds := make([]*CameraFeed, 0, len(rm.feeds))
	for _, f := range rm.feeds {
		feeds = append(feeds, f)
	}
	rm.mu.RUnlock()
	for _, f := range feeds {
		f.Stop()
	}
	rm.streamer.StopAllStreams()
}
