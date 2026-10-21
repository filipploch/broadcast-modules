package main

import (
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Stany odbioru obrazu z kamery (CameraFeed).
const (
	FeedOff      = "off"      // kamera nie ma działać
	FeedStarting = "starting" // proces odbioru uruchomiony, jeszcze nie dostarczył klatki
	FeedRunning  = "running"  // odbiór działa: urządzenie pośrednie dostaje klatki
	FeedError    = "error"    // odbiór padł, nie wstał albo zamarł; ponawiamy co feedRetryDelay (lub wstrzymany na czas nagrywania wprost)
)

const (
	feedFirstFrameTimeout = 10 * time.Second // tyle czeka na pierwszą klatkę, potem uznaje, że kamery nie ma
	feedStallTimeout      = 5 * time.Second  // tyle bez nowej klatki (przy działającym procesie) to zamarcie: proces jest zabijany i startuje od nowa
	feedRetryDelay        = 4 * time.Second  // pauza między próbami po awarii/braku kamery
	feedStopWait          = 5 * time.Second  // czas na czyste zakończenie ffmpeg po SIGINT
	feedWatchTick         = 250 * time.Millisecond
)

// CameraFeed to odbiór obrazu z JEDNEJ kamery: osobny proces ffmpeg, jedyny, który otwiera urządzenie kamery (device_path)
// i zapisuje obraz do urządzenia pośredniego v4l2loopback (loopback_device). Podgląd SRT dla OBS i nagrywanie czytają
// już tylko z urządzenia pośredniego, więc obraz w OBS nie zależy od nagrywania, a nagrywanie nie przerywa podglądu.
//
// Cykl życia: Start() ustawia „kamera ma działać” i pilnuje procesu aż do Stop(): po awarii próbuje ponownie co feedRetryDelay,
// bez limitu prób (kamera odłączona fizycznie wraca sama po podłączeniu). Stan „działa” oznacza, że proces dostarczył klatkę
// (raport -progress), a watchdog zabija proces, który żyje, ale od feedStallTimeout nie daje nowych klatek.
// Zmiany stanu zgłasza przez SetOnChange.
//
// Suspend()/Resume(): na czas nagrywania WPROST z kamery (gdy odbiór jest w błędzie, a operator uruchamia nagrywanie)
// odbiór oddaje kamerę i nie ponawia prób; po zakończeniu nagrywania Resume() przywraca jego pracę.
type CameraFeed struct {
	cfg CameraConfig

	// newCmd tworzy polecenie ffmpeg (w testach podmieniane na proces pomocniczy).
	newCmd func(args []string) *exec.Cmd

	mu        sync.Mutex
	desired   bool
	suspended bool
	state     string
	lastErr   string
	cmd       *exec.Cmd
	cmdDone   chan struct{}
	gen       uint64 // zmienia się przy każdym Start/Stop/Suspend/Resume; unieważnia stare pętle
	onChange  func(cameraID, state, errMsg string)

	firstFrameTimeout time.Duration
	stallTimeout      time.Duration
	retryDelay        time.Duration
	watchTick         time.Duration

	pidDir string // katalog plików z numerem procesu (sprzątanie po awarii pluginu); pusty = bez plików
}

// NewCameraFeed tworzy odbiór dla kamery. Kamera bez device_path lub loopback_device nie ma odbioru (CanFeed == false).
func NewCameraFeed(cfg CameraConfig) *CameraFeed {
	return &CameraFeed{
		cfg:               cfg,
		state:             FeedOff,
		newCmd:            func(args []string) *exec.Cmd { return exec.Command("ffmpeg", args...) },
		firstFrameTimeout: feedFirstFrameTimeout,
		stallTimeout:      feedStallTimeout,
		retryDelay:        feedRetryDelay,
		watchTick:         feedWatchTick,
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

// Wanted: kamera ma działać (także gdy chwilowo nie wstała albo jest wstrzymana).
func (f *CameraFeed) Wanted() bool {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.desired
}

// Suspended: odbiór oddał kamerę na czas nagrywania wprost.
func (f *CameraFeed) Suspended() bool {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.suspended
}

// buildFeedArgs: odbiór MJPEG 1920x1080@30 z kamery, jednokrotne zdekodowanie i zapis surowego obrazu (yuyv422) do urządzenia
// pośredniego. Format wejściowy i rozdzielczość jak w nagrywaniu bezpośrednim (buildFFmpegArgs); wyjście jak dotychczasowa
// druga gałąź (-map [stream]) — czytają je podgląd SRT i nagrywanie. Raport postępu (-progress) zasila watchdog klatek.
func buildFeedArgs(cfg CameraConfig) []string {
	args := []string{"-hide_banner"}
	args = append(args, progressArgs()...)
	return append(args,
		"-f", "v4l2",
		"-input_format", "mjpeg",
		"-video_size", "1920x1080",
		"-framerate", "30",
		"-i", cfg.DevicePath,
		"-an",
		"-pix_fmt", "yuyv422",
		"-f", "v4l2",
		cfg.LoopbackDevice,
	)
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
	f.suspended = false
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
	f.suspended = false
	f.gen++
	f.mu.Unlock()

	f.killProcess()
	f.removePidFile()
	f.setState(FeedOff, "")
}

// Suspend oddaje kamerę na czas nagrywania wprost: zabija proces odbioru i wstrzymuje ponawianie. Wanted() zostaje true.
func (f *CameraFeed) Suspend() {
	f.mu.Lock()
	if !f.desired || f.suspended {
		f.mu.Unlock()
		return
	}
	f.suspended = true
	f.gen++
	f.mu.Unlock()

	f.killProcess()
	f.removePidFile()
	f.setState(FeedError, "wstrzymany na czas nagrywania wprost z kamery")
}

// Resume przywraca pracę odbioru po Suspend().
func (f *CameraFeed) Resume() {
	f.mu.Lock()
	if !f.desired || !f.suspended {
		f.mu.Unlock()
		return
	}
	f.suspended = false
	f.gen++
	gen := f.gen
	f.mu.Unlock()

	go f.loop(gen)
}

// killProcess kończy bieżący proces odbioru (SIGINT, po feedStopWait SIGKILL) i czeka na jego koniec.
func (f *CameraFeed) killProcess() {
	f.mu.Lock()
	cmd, done := f.cmd, f.cmdDone
	f.mu.Unlock()
	if cmd == nil || cmd.Process == nil {
		return
	}
	log.Printf("🛑 [feed/%s] Sending interrupt to ffmpeg (pid %d)", f.cfg.ID, cmd.Process.Pid)
	if err := cmd.Process.Signal(os.Interrupt); err != nil {
		_ = cmd.Process.Kill()
	}
	if done == nil {
		return
	}
	select {
	case <-done:
	case <-time.After(feedStopWait):
		log.Printf("⚠️  [feed/%s] ffmpeg did not exit in %s — killing", f.cfg.ID, feedStopWait)
		_ = cmd.Process.Kill()
		<-done
	}
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
	return f.desired && !f.suspended && f.gen == gen
}

// loop pilnuje procesu odbioru, dopóki ta generacja jest aktualna.
func (f *CameraFeed) loop(gen uint64) {
	for f.current(gen) {
		f.setState(FeedStarting, "")
		errMsg := f.runOnce(gen)
		if !f.current(gen) {
			return // zatrzymane na życzenie — stan ustawia Stop()/Suspend()
		}
		f.setState(FeedError, errMsg)
		time.Sleep(f.retryDelay)
	}
}

// runOnce uruchamia jeden proces odbioru i pilnuje go do końca. Zwraca opis przyczyny zakończenia.
func (f *CameraFeed) runOnce(gen uint64) string {
	cmd := f.newCmd(buildFeedArgs(f.cfg))
	progress := newProgressTracker()
	cmd.Stdout = progress
	cmd.Stderr = newPrefixedWriter(fmt.Sprintf("[feed/%s] ", f.cfg.ID))
	if err := cmd.Start(); err != nil {
		return "nie udało się uruchomić ffmpeg: " + err.Error()
	}

	done := make(chan struct{})
	waitErr := make(chan error, 1)
	go func() { waitErr <- cmd.Wait(); close(done) }()

	f.mu.Lock()
	if f.gen != gen { // Stop()/Suspend() w międzyczasie: nie zostawiaj procesu
		f.mu.Unlock()
		_ = cmd.Process.Kill()
		<-done
		return ""
	}
	f.cmd, f.cmdDone = cmd, done
	f.mu.Unlock()
	f.writePidFile(cmd.Process.Pid)
	log.Printf("🎬 [feed/%s] ffmpeg started (pid %d): %s → %s", f.cfg.ID, cmd.Process.Pid, f.cfg.DevicePath, f.cfg.LoopbackDevice)

	defer func() {
		f.mu.Lock()
		if f.cmd == cmd {
			f.cmd, f.cmdDone = nil, nil
		}
		f.mu.Unlock()
		f.removePidFile()
	}()

	ticker := time.NewTicker(f.watchTick)
	defer ticker.Stop()
	running := false
	for {
		select {
		case err := <-waitErr:
			return exitMessage(err)
		case <-ticker.C:
			if !f.current(gen) {
				continue // Stop()/Suspend() zabija proces samo; czekamy na jego koniec
			}
			if !running {
				if progress.Frames() > 0 {
					running = true
					f.setState(FeedRunning, "")
				} else if progress.SinceStart() > f.firstFrameTimeout {
					msg := fmt.Sprintf("brak klatek z kamery przez %s od uruchomienia", f.firstFrameTimeout)
					f.killWatchdog(cmd, done)
					return msg
				}
			} else if progress.SinceAdvance() > f.stallTimeout {
				msg := fmt.Sprintf("brak nowych klatek od %s (kamera zamarła)", f.stallTimeout)
				f.killWatchdog(cmd, done)
				return msg
			}
		}
	}
}

// killWatchdog zabija zamarły proces (bez czekania na czyste zamknięcie: nie pisze plików, tylko do urządzenia pośredniego).
func (f *CameraFeed) killWatchdog(cmd *exec.Cmd, done chan struct{}) {
	log.Printf("🐕 [feed/%s] watchdog: zabijam ffmpeg (pid %d)", f.cfg.ID, cmd.Process.Pid)
	_ = cmd.Process.Kill()
	<-done
}

func exitMessage(err error) string {
	if err != nil {
		return "ffmpeg zakończył się: " + err.Error()
	}
	return "ffmpeg zakończył się (status 0) bez polecenia"
}

// --- sprzątanie po awarii pluginu: pliki z numerem procesu odbioru ---

func (f *CameraFeed) pidFilePath() string {
	return filepath.Join(f.pidDir, f.cfg.ID+".pid")
}

func (f *CameraFeed) writePidFile(pid int) {
	if f.pidDir == "" {
		return
	}
	if err := os.MkdirAll(f.pidDir, 0o755); err != nil {
		log.Printf("⚠️  [feed/%s] katalog plików pid: %v", f.cfg.ID, err)
		return
	}
	content := strconv.Itoa(pid) + "\n" + f.cfg.LoopbackDevice + "\n"
	if err := os.WriteFile(f.pidFilePath(), []byte(content), 0o644); err != nil {
		log.Printf("⚠️  [feed/%s] zapis pliku pid: %v", f.cfg.ID, err)
	}
}

func (f *CameraFeed) removePidFile() {
	if f.pidDir != "" {
		_ = os.Remove(f.pidFilePath())
	}
}

// processLooksLikeFeed mówi, czy proces o numerze pid to nadal odbiór (ffmpeg z danym urządzeniem pośrednim) — numer mógł
// zostać użyty ponownie przez inny program. Na Linuksie czyta /proc; w testach podmieniane.
var processLooksLikeFeed = func(pid int, loopback string) bool {
	data, err := os.ReadFile(fmt.Sprintf("/proc/%d/cmdline", pid))
	if err != nil {
		return false
	}
	cmdline := strings.ReplaceAll(string(data), "\x00", " ")
	return strings.Contains(cmdline, "ffmpeg") && strings.Contains(cmdline, loopback)
}

// ReapOrphanFeeds kończy procesy odbioru zostawione przez poprzedni egzemplarz pluginu, który zginął bez sprzątania (SIGKILL, awaria,
// zasilanie). Czyta pliki pid z katalogu; kończy tylko proces, który nadal wygląda jak odbiór tej kamery. Zwraca liczbę zakończonych.
func ReapOrphanFeeds(pidDir string) int {
	entries, err := os.ReadDir(pidDir)
	if err != nil {
		return 0
	}
	reaped := 0
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".pid") {
			continue
		}
		path := filepath.Join(pidDir, e.Name())
		data, err := os.ReadFile(path)
		_ = os.Remove(path)
		if err != nil {
			continue
		}
		lines := strings.Fields(string(data))
		if len(lines) < 2 {
			continue
		}
		pid, err := strconv.Atoi(lines[0])
		if err != nil || pid <= 0 || pid == os.Getpid() {
			continue
		}
		if !processLooksLikeFeed(pid, lines[1]) {
			continue
		}
		if p, err := os.FindProcess(pid); err == nil {
			log.Printf("🧹 Kończę osierocony odbiór kamery %s (pid %d)", strings.TrimSuffix(e.Name(), ".pid"), pid)
			if p.Kill() == nil {
				reaped++
			}
		}
	}
	return reaped
}
