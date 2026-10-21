package main

import (
	"fmt"
	"log"
	"os"
	"os/exec"
	"time"
)

// camera_feed.go: nagrywanie z odbioru obrazu (feed.go) — pauza przy utracie obrazu i jawna rotacja segmentu po jego powrocie.
//
// Zasada: nagrania NIE wznawiają się samoczynnie po restarcie odbioru. Proces nagrywający czyta z urządzenia pośredniego i
// po utracie obrazu mógłby wisieć bez klatek albo zapisać plik z dziurą. Dlatego:
//   - odbiór padł lub zamarł  → bieżący segment jest zamykany czysto (PauseForFeed), sesja nagrania trwa, plik jest w historii;
//   - obraz wrócił            → otwierany jest NOWY segment tej samej sesji (ResumeAfterFeed), zdarzenie segment_rotated z powodem "feed_restart";
//   - sam proces nagrywający zamarł (żyje, nie zapisuje klatek) → watchdog (watchRecording) zabija go, a obsługa awarii
//     (RecorderManager.handleUnexpectedStop) zamyka segment i otwiera następny, gdy obraz jest.

const (
	recordFirstFrameTimeout = 20 * time.Second // proces nagrywający bez pierwszej klatki
	recordStallTimeout      = 10 * time.Second // proces nagrywający bez nowej klatki (dłużej niż stallTimeout odbioru, by odbiór zareagował pierwszy)
)

// LastFromFeed: ostatni segment czytał z urządzenia pośredniego.
func (cr *CameraRecorder) LastFromFeed() bool {
	cr.mu.Lock()
	defer cr.mu.Unlock()
	return cr.curFromFeed
}

// Paused: sesja nagrania trwa, ale bieżący segment jest zamknięty i czeka na powrót obrazu.
func (cr *CameraRecorder) Paused() bool {
	cr.mu.Lock()
	defer cr.mu.Unlock()
	return cr.feedPaused
}

// PauseForFeed zamyka bieżący segment (czysto, SIGINT) po utracie obrazu z odbioru. Sesja nagrania trwa (recording zostaje true).
// stillDown jest sprawdzane pod blokadą operacji: jeśli obraz zdążył wrócić, nic nie robi (kolejność zdarzeń „błąd → działa”
// nie może zostawić zatrzymanego nagrania przy działającym obrazie). Zwraca true, gdy segment został zamknięty.
func (cr *CameraRecorder) PauseForFeed(reason string, stillDown func() bool) (bool, error) {
	cr.opMu.Lock()
	defer cr.opMu.Unlock()

	cr.mu.Lock()
	if !cr.recording || cr.feedPaused || !cr.curFromFeed {
		cr.mu.Unlock()
		return false, nil
	}
	cr.mu.Unlock()
	if stillDown != nil && !stillDown() {
		return false, nil
	}

	if err := cr.stopFFmpeg(); err != nil {
		return false, fmt.Errorf("failed to close segment of camera %s: %w", cr.config.ID, err)
	}

	cr.mu.Lock()
	cr.lastMeta.FinishedAt = time.Now().UnixMilli()
	cr.lastMeta.EndReason = reason
	meta := cr.lastMeta
	cr.feedPaused = true
	cr.pendingSignal = false
	cr.segmentGen++ // unieważnia zegary rotacji tego segmentu
	cr.mu.Unlock()

	_ = cr.appendHistoryMeta(meta)
	log.Printf("⏸️  [%s] Segment %d zamknięty (%s) — sesja nagrania trwa, czekam na obraz z odbioru", cr.config.ID, meta.SegmentIndex, reason)
	return true, nil
}

// pauseAfterCrash: proces nagrywający z odbioru zakończył się sam (waiter wyzerował recording). Zamiast nowej sesji zostawiamy
// sesję w pauzie, tak jak po utracie obrazu; kolejny segment otworzy ResumeAfterFeed. Zwraca false, gdy to nie był tryb z odbioru.
func (cr *CameraRecorder) pauseAfterCrash(reason string) bool {
	cr.opMu.Lock()
	defer cr.opMu.Unlock()

	cr.mu.Lock()
	if !cr.curFromFeed || cr.feedPaused || cr.sessionID == "" {
		cr.mu.Unlock()
		return false
	}
	cr.recording = true
	cr.feedPaused = true
	cr.pendingSignal = false
	cr.segmentGen++
	cr.lastMeta.FinishedAt = time.Now().UnixMilli()
	cr.lastMeta.EndReason = reason
	meta := cr.lastMeta
	cr.mu.Unlock()

	_ = cr.appendHistoryMeta(meta)
	log.Printf("⏸️  [%s] Proces nagrywający zakończył się sam (%s) — sesja w pauzie, nowy segment po powrocie obrazu", cr.config.ID, reason)
	return true
}

// ResumeAfterFeed otwiera NOWY segment tej samej sesji po powrocie obrazu (jawna rotacja, nie wznowienie procesu).
// ready jest sprawdzane pod blokadą operacji: gdy obrazu znów nie ma, nic nie robi. Błąd uruchomienia zostawia sesję w pauzie
// (ponowna próba przy kolejnym powrocie obrazu lub z pętli ponawiania w RecorderManager).
func (cr *CameraRecorder) ResumeAfterFeed(ready func() bool) (bool, error) {
	cr.opMu.Lock()
	defer cr.opMu.Unlock()

	cr.mu.Lock()
	if !cr.recording || !cr.feedPaused {
		cr.mu.Unlock()
		return false, nil
	}
	sessionID := cr.sessionID
	nextIndex := cr.segmentIndex + 1
	prev := cr.lastMeta
	cr.mu.Unlock()
	if ready != nil && !ready() {
		return false, nil
	}

	nextMeta := RecordingMeta{MatchID: prev.MatchID, PeriodID: prev.PeriodID}
	if err := cr.launchSegment(nextMeta, sessionID, nextIndex); err != nil {
		cr.mu.Lock()
		cr.recording = true // launchSegment mógł zostawić false po nieudanym starcie
		cr.mu.Unlock()
		return false, fmt.Errorf("failed to open segment %d of camera %s after feed return: %w", nextIndex, cr.config.ID, err)
	}

	cr.mu.Lock()
	cr.feedPaused = false
	cb := cr.onSegmentRotated
	newMeta := cr.lastMeta
	cr.mu.Unlock()
	log.Printf("▶️  [%s] Obraz wrócił — otwarto segment %d tej samej sesji", cr.config.ID, nextIndex)
	if cb != nil {
		cb(newMeta, "feed_restart")
	}
	return true, nil
}

// watchRecording to watchdog procesu nagrywającego z odbioru: proces, który żyje, ale nie zapisuje nowych klatek, jest zabijany.
// Zakończenie zgłasza zwykła obsługa awarii (waiter w startFFmpeg → onUnexpectedStop), która robi pauzę i nowy segment.
func (cr *CameraRecorder) watchRecording(cmd *exec.Cmd, done chan struct{}, progress *progressTracker) {
	tick := cr.recWatchTick
	if tick <= 0 {
		tick = time.Second
	}
	ticker := time.NewTicker(tick)
	defer ticker.Stop()
	for {
		select {
		case <-done:
			return
		case <-ticker.C:
			cr.mu.Lock()
			expected := cr.expectedStop
			cr.mu.Unlock()
			if expected {
				continue
			}
			var reason string
			if progress.Frames() == 0 {
				if progress.SinceStart() > cr.recFirstFrameTimeout {
					reason = fmt.Sprintf("brak klatek przez %s od uruchomienia", cr.recFirstFrameTimeout)
				}
			} else if progress.SinceAdvance() > cr.recStallTimeout {
				reason = fmt.Sprintf("brak nowych klatek od %s", cr.recStallTimeout)
			}
			if reason != "" && cmd.Process != nil {
				log.Printf("🐕 [%s] watchdog nagrywania: %s — zabijam ffmpeg (pid %d)", cr.config.ID, reason, cmd.Process.Pid)
				// najpierw SIGINT (szansa na domknięcie pliku), po 3 s SIGKILL
				_ = cmd.Process.Signal(os.Interrupt)
				select {
				case <-done:
				case <-time.After(3 * time.Second):
					_ = cmd.Process.Kill()
				}
				return
			}
		}
	}
}
