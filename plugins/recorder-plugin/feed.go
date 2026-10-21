package main

import (
	"fmt"
	"log"
	"os"
	"os/exec"
	"sync"
	"time"
)

// Stany odbioru obrazu z kamery (CameraFeed).
const (
	FeedOff      = "off"      // kamera nie ma działać
	FeedStarting = "starting" // proces odbioru uruchomiony, jeszcze nie potwierdził pracy
	FeedRunning  = "running"  // odbiór działa: urządzenie pośrednie dostaje obraz
	FeedError    = "error"    // odbiór padł lub nie wstał; ponawiamy co feedRetryDelay
)

const (
	feedStartupGrace = 2 * time.Second // tyle musi przeżyć proces odbioru, żeby uznać go za działający
	feedRetryDelay   = 4 * time.Second // pauza między próbami po awarii/braku kamery
	feedStopWait     = 5 * time.Second // czas na czyste zakończenie ffmpeg po SIGINT
)

// CameraFeed to odbiór obrazu z JEDNEJ kamery: osobny proces ffmpeg, jedyny, który otwiera urządzenie kamery (device_path)
// i zapisuje obraz do urządzenia pośredniego v4l2loopback (loopback_device). Podgląd SRT dla OBS i nagrywanie czytają
// już tylko z urządzenia pośredniego, więc obraz w OBS nie zależy od nagrywania, a nagrywanie nie przerywa podglądu.
//
// Cykl życia: Start() ustawia „kamera ma działać” i pilnuje procesu aż do Stop(): po awarii próbuje ponownie co feedRetryDelay,
// bez limitu prób (kamera odłączona fizycznie wraca sama po podłączeniu). Zmiany stanu zgłasza przez SetOnChange.
type CameraFeed struct {
	cfg CameraConfig

	// newCmd tworzy polecenie ffmpeg (w testach podmieniane na proces pomocniczy).
	newCmd func(args []string) *exec.Cmd

	mu       sync.Mutex
	desired  bool
	state    string
	lastErr  string
	cmd      *exec.Cmd
	cmdDone  chan struct{}
	gen      uint64 // zmienia się przy każdym Start/Stop; unieważnia stare pętle
	onChange func(cameraID, state, errMsg string)

	grace      time.Duration
	retryDelay time.Duration
}

// NewCameraFeed tworzy odbiór dla kamery. Kamera bez device_path lub loopback_device nie ma odbioru (CanFeed == false).
func NewCameraFeed(cfg CameraConfig) *CameraFeed {
	return &CameraFeed{
		cfg:        cfg,
		state:      FeedOff,
		newCmd:     func(args []string) *exec.Cmd { return exec.Command("ffmpeg", args...) },
		grace:      feedStartupGrace,
		retryDelay: feedRetryDelay,
	}
}

// CanFeed: kamera ma urządzenie wejściowe i pośrednie, więc może mieć osobny odbiór.
func (f *CameraFeed) CanFeed() bool {
	return f.cfg.DevicePath != "" && f.cfg.LoopbackDevice != ""
}

func (f *CameraFeed) SetOnChange(fn func(cameraID, state, errMsg string)) {
	f.mu.Lock()
	f.onChange = fn
	f.mu.Unlock()
}

// State zwraca bieżący stan i ostatni błąd.
func (f *CameraFeed) State() (state, errMsg string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.state, f.lastErr
}

func (f *CameraFeed) Running() bool {
	st, _ := f.State()
	return st == FeedRunning
}

// Wanted: kamera ma działać (stan inny niż off), także gdy chwilowo nie wstała.
func (f *CameraFeed) Wanted() bool {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.desired
}

// buildFeedArgs: odbiór MJPEG 1920x1080@30 z kamery, jednokrotne zdekodowanie i zapis surowego obrazu (yuyv422) do urządzenia
// pośredniego. Format wejściowy i rozdzielczość jak w nagrywaniu bezpośrednim (buildFFmpegArgs); wyjście jak dotychczasowa
// druga gałąź (-map [stream]) — czytają je podgląd SRT i nagrywanie.
func buildFeedArgs(cfg CameraConfig) []string {
	return []string{
		"-hide_banner",
		"-f", "v4l2",
		"-input_format", "mjpeg",
		"-video_size", "1920x1080",
		"-framerate", "30",
		"-i", cfg.DevicePath,
		"-an",
		"-pix_fmt", "yuyv422",
		"-f", "v4l2",
		cfg.LoopbackDevice,
	}
}

// Start włącza odbiór (idempotentnie: już włączony nic nie zmienia).
func (f *CameraFeed) Start() error {
	if !f.CanFeed() {
		return fmt.Errorf("camera %s: brak device_path lub loopback_device — odbiór niedostępny", f.cfg.ID)
	}
	f.mu.Lock()
	if f.desired {
		f.mu.Unlock()
		return nil
	}
	f.desired = true
	f.gen++
	gen := f.gen
	f.mu.Unlock()

	go f.loop(gen)
	return nil
}

// Stop wyłącza odbiór i czeka na zakończenie procesu.
func (f *CameraFeed) Stop() {
	f.mu.Lock()
	if !f.desired && f.cmd == nil {
		f.mu.Unlock()
		return
	}
	f.desired = false
	f.gen++
	cmd, done := f.cmd, f.cmdDone
	f.mu.Unlock()

	if cmd != nil && cmd.Process != nil {
		log.Printf("🛑 [feed/%s] Sending interrupt to ffmpeg (pid %d)", f.cfg.ID, cmd.Process.Pid)
		if err := cmd.Process.Signal(os.Interrupt); err != nil {
			_ = cmd.Process.Kill()
		}
		if done != nil {
			select {
			case <-done:
			case <-time.After(feedStopWait):
				log.Printf("⚠️  [feed/%s] ffmpeg did not exit in %s — killing", f.cfg.ID, feedStopWait)
				_ = cmd.Process.Kill()
				<-done
			}
		}
	}
	f.setState(FeedOff, "")
}

func (f *CameraFeed) setState(state, errMsg string) {
	f.mu.Lock()
	if f.state == state && f.lastErr == errMsg {
		f.mu.Unlock()
		return
	}
	f.state, f.lastErr = state, errMsg
	cb := f.onChange
	f.mu.Unlock()
	log.Printf("📷 [feed/%s] state → %s %s", f.cfg.ID, state, errMsg)
	if cb != nil {
		cb(f.cfg.ID, state, errMsg)
	}
}

func (f *CameraFeed) current(gen uint64) bool {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.desired && f.gen == gen
}

// loop pilnuje procesu odbioru, dopóki ta generacja jest aktualna.
func (f *CameraFeed) loop(gen uint64) {
	for f.current(gen) {
		f.setState(FeedStarting, "")
		cmd := f.newCmd(buildFeedArgs(f.cfg))
		cmd.Stdout = newPrefixedWriter(fmt.Sprintf("[feed/%s] ", f.cfg.ID))
		cmd.Stderr = newPrefixedWriter(fmt.Sprintf("[feed/%s] ", f.cfg.ID))
		var errMsg string
		if err := cmd.Start(); err != nil {
			errMsg = "nie udało się uruchomić ffmpeg: " + err.Error()
		} else {
			done := make(chan struct{})
			waitErr := make(chan error, 1)
			go func() { waitErr <- cmd.Wait(); close(done) }()

			f.mu.Lock()
			if f.gen != gen { // Stop() w międzyczasie: nie zostawiaj procesu
				f.mu.Unlock()
				_ = cmd.Process.Kill()
				<-done
				return
			}
			f.cmd, f.cmdDone = cmd, done
			f.mu.Unlock()
			log.Printf("🎬 [feed/%s] ffmpeg started (pid %d): %s → %s", f.cfg.ID, cmd.Process.Pid, f.cfg.DevicePath, f.cfg.LoopbackDevice)

			select {
			case err := <-waitErr:
				errMsg = exitMessage(err)
			case <-time.After(f.grace):
				if f.current(gen) {
					f.setState(FeedRunning, "")
				}
				err := <-waitErr // czekamy do końca procesu
				errMsg = exitMessage(err)
			}

			f.mu.Lock()
			if f.cmd == cmd {
				f.cmd, f.cmdDone = nil, nil
			}
			f.mu.Unlock()
		}

		if !f.current(gen) {
			return // zatrzymane na życzenie — stan off ustawia Stop()
		}
		f.setState(FeedError, errMsg)
		time.Sleep(f.retryDelay)
	}
}

func exitMessage(err error) string {
	if err != nil {
		return "ffmpeg zakończył się: " + err.Error()
	}
	return "ffmpeg zakończył się (status 0) bez polecenia"
}
