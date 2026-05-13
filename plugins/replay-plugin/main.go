package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"strconv"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

// ── Stałe ────────────────────────────────────────────────────────────────────

const (
	speedMin = 0.3
	speedMax = 0.9
)

func clampSpeed(speed float64) float64 {
	if speed < speedMin {
		return speedMin
	}
	if speed > speedMax {
		return speedMax
	}
	return speed
}

// ── Config ────────────────────────────────────────────────────────────────────

type Config struct {
	PluginID         string  `json:"plugin_id"`
	PluginName       string  `json:"plugin_name"`
	HubURL           string  `json:"hub_url"`
	MpvPath          string  `json:"mpv_path"`
	MpvPipe          string  `json:"mpv_pipe"`
	WindowGeometry   string  `json:"window_geometry"`
	MpvScreen        string  `json:"mpv_screen"`
	TransitionLeadMs int64   `json:"transition_lead_ms"`
	DefaultSpeed     float64 `json:"default_speed"`
}

func defaultConfig() Config {
	exeDir, _ := filepath.Abs(filepath.Dir(os.Args[0]))
	return Config{
		PluginID:         "replay-plugin",
		PluginName:       "Replay Plugin",
		HubURL:           "ws://localhost:8080/ws",
		MpvPath:          filepath.Join(exeDir, "mpv.exe"),
		MpvPipe:          `\\.\pipe\mpvsocket`,
		WindowGeometry:   "1920x1080+0+0",
		MpvScreen:        "1",
		TransitionLeadMs: 700,
		DefaultSpeed:     0.9,
	}
}

func loadConfig(path string) (Config, error) {
	cfg := defaultConfig()
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		data, _ = json.MarshalIndent(cfg, "", "  ")
		if werr := os.WriteFile(path, data, 0644); werr != nil {
			log.Printf("⚠️  Cannot write default config: %v", werr)
		} else {
			log.Printf("📄 Created default config: %s", path)
		}
		return cfg, nil
	}
	if err != nil {
		return cfg, err
	}
	if err := json.Unmarshal(data, &cfg); err != nil {
		return cfg, fmt.Errorf("invalid config JSON: %w", err)
	}
	return cfg, nil
}

// ── Plugin ────────────────────────────────────────────────────────────────────

type Plugin struct {
	cfg    Config
	hub    *HubClient
	mpv    *MpvController
	mpvCmd *exec.Cmd
	mu     sync.Mutex

	// Stan bieżącej sesji powtórki.
	// autoEndTimer działa tylko dopóki użytkownik nie wykona ręcznej modyfikacji
	// odtwarzania (pauza, resume, speed, frame-step itd.).
	autoEndTimer *time.Timer
	activeReplay bool
	manualMode   bool

	// sessionID: atomic counter — inkrementowany przy każdym replay_play.
	// Timer callback porównuje swój sessionID z aktualnym, żeby ignorować
	// callbacki ze starych powtórek.
	sessionID atomic.Int64

	// speedCh: debounce channel dla zmian prędkości.
	speedCh chan float64

	// seekFwdCh / seekBackCh: kanały dla poklatki.
	// Capacity=1 — jeśli worker jest zajęty, nowe żądanie zastępuje oczekujące.
	// Jeśli kanał pełny i worker zajęty — żądanie jest droppowane.
	seekFwdCh  chan struct{}
	seekBackCh chan struct{}
}

func NewPlugin(cfg Config) *Plugin {
	return &Plugin{
		cfg:        cfg,
		mpv:        NewMpvController(cfg.MpvPipe),
		speedCh:    make(chan float64, 1),
		seekFwdCh:  make(chan struct{}, 1),
		seekBackCh: make(chan struct{}, 1),
	}
}

func (p *Plugin) Start() error {
	if runtime.GOOS != "windows" {
		return fmt.Errorf("replay-plugin działa tylko na Windows (Named Pipe IPC)")
	}

	if err := p.startMpv(); err != nil {
		return fmt.Errorf("cannot start mpv: %w", err)
	}

	log.Printf("⏳ Czekam na pipe mpv...")
	if err := p.mpv.WaitForIPC(10 * time.Second); err != nil {
		return fmt.Errorf("mpv IPC timeout: %w", err)
	}

	p.hub = NewHubClient(p.cfg.PluginID, p.cfg.PluginName, p.cfg.HubURL)
	if err := p.hub.Connect(); err != nil {
		return fmt.Errorf("cannot connect to Hub: %w", err)
	}
	go p.hub.AutoReconnect()
	go p.messageLoop()
	go p.heartbeatLoop()

	log.Printf("✅ Replay Plugin uruchomiony")
	return nil
}

func (p *Plugin) killExistingMpv() {
	exec.Command("taskkill", "/F", "/IM", "mpv.exe").Run()
	time.Sleep(500 * time.Millisecond)
}

func (p *Plugin) startMpv() error {
	if _, err := os.Stat(p.cfg.MpvPath); os.IsNotExist(err) {
		return fmt.Errorf("mpv.exe nie znaleziony: %s", p.cfg.MpvPath)
	}
	p.killExistingMpv()

	args := []string{
		"--idle=yes",
		"--keep-open=yes",
		"--no-border",
		"--geometry=" + p.cfg.WindowGeometry,
		"--input-ipc-server=" + p.cfg.MpvPipe,
		"--force-window=yes",
		"--osd-level=0",
		"--mute=yes",
		"--volume=0",
		"--demuxer-max-bytes=500MiB",
		// Duży back-cache: mpv trzyma zdekodowane dane wstecz w pamięci.
		// Dzięki temu frame-back-step na klatkach które były już wyświetlane
		// trafia w cache zamiast wymuszać seek do keyframe'a + redekodowanie.
		// Przy GOP=1s i 1080p H.264, 300MiB pokrywa wiele sekund wstecz.
		"--demuxer-max-back-bytes=300MiB",
		"--demuxer-readahead-secs=0",
		// Osobny wątek dla demuxera — konieczne przy odtwarzaniu pliku MKV
		// nagrywany równocześnie przez OBS. Bez tego IPC pipe może się zablokować
		// gdy mpv czeka na dane z rosnącego pliku.
		"--demuxer-thread=yes",
		"--force-seekable=yes",
		"--hr-seek=yes",
		"--title=replay-plugin-mpv",
		"--gpu-api=d3d11",
		"--fullscreen=yes",
		"--screen=" + p.cfg.MpvScreen,
	}

	cmd := exec.Command(p.cfg.MpvPath, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("exec failed: %w", err)
	}
	p.mpvCmd = cmd
	log.Printf("🎬 mpv uruchomiony (PID %d)", cmd.Process.Pid)
	go func() {
		if err := cmd.Wait(); err != nil {
			log.Printf("⚠️  mpv zakończył się: %v", err)
		}
	}()
	return nil
}

// cancelAutoEndTimerLocked anuluje timer automatycznego zakończenia powtórki.
// Wymaga zewnętrznej blokady p.mu.
func (p *Plugin) cancelAutoEndTimerLocked() {
	if p.autoEndTimer != nil {
		p.autoEndTimer.Stop()
		p.autoEndTimer = nil
	}
}

// enterManualMode przełącza bieżącą powtórkę w tryb ręczny.
// Od tej chwili replay-plugin nie wyśle replay_done automatycznie;
// zakończenie musi przyjść jako end_replay.
func (p *Plugin) enterManualMode(reason string) {
	p.mu.Lock()
	if !p.activeReplay {
		p.mu.Unlock()
		return
	}
	alreadyManual := p.manualMode
	p.manualMode = true
	p.cancelAutoEndTimerLocked()
	p.mu.Unlock()

	if !alreadyManual {
		log.Printf("🕹  replay manual mode (%s) — auto end disabled", reason)
	}
}

// resetReplaySettings resetuje stan mpv po zakończeniu powtórki.
// resetSession to ID sesji dla której reset został zaplanowany —
// jeśli w międzyczasie uruchomiono nową powtórkę, reset jest ignorowany.
func (p *Plugin) resetReplaySettings(resetSession int64) {
	if p.sessionID.Load() != resetSession {
		log.Printf("⏭  resetReplaySettings: skipped (new replay active)")
		return
	}
	if err := p.mpv.SetSpeed(p.cfg.DefaultSpeed); err != nil {
		log.Printf("⚠️  Reset speed: %v", err)
	}
	if err := p.mpv.Pause(); err != nil {
		log.Printf("⚠️  Pause: %v", err)
	}
	log.Printf("⏸  mpv paused, speed reset → %.2f", p.cfg.DefaultSpeed)
}

func (p *Plugin) finishReplay(source string, payload map[string]interface{}) {
	p.mu.Lock()
	if !p.activeReplay {
		p.mu.Unlock()
		log.Printf("⏹  finishReplay(%s) ignored — no active replay", source)
		return
	}
	p.activeReplay = false
	p.manualMode = false
	p.cancelAutoEndTimerLocked()
	closingSession := p.sessionID.Add(1)
	p.mu.Unlock()

	if payload == nil {
		payload = map[string]interface{}{}
	}
	payload["source"] = source

	// Najpierw informujemy backend, żeby ukrył źródło Replay w OBS.
	// Faktyczne zatrzymanie/pauza mpv następuje dopiero po TransitionLeadMs,
	// dzięki czemu ukrycie źródła wyprzedza koniec powtórki.
	p.hub.Send(&Message{
		To:      "main-module",
		Type:    "replay_done",
		Payload: payload,
	})

	lead := p.cfg.TransitionLeadMs
	if lead < 0 {
		lead = 0
	}
	log.Printf("⏳ replay_done sent (%s); mpv pause/reset in %dms", source, lead)
	time.AfterFunc(time.Duration(lead)*time.Millisecond, func() {
		p.resetReplaySettings(closingSession)
	})
}

func (p *Plugin) messageLoop() {
	// Worker: zmiana prędkości — debounce 30ms.
	// Zawsze bierze najnowszą wartość z kanału.
	go func() {
		for speed := range p.speedCh {
			for len(p.speedCh) > 0 {
				speed = <-p.speedCh
			}
			if err := p.mpv.SetSpeed(speed); err != nil {
				log.Printf("⚠️  SetSpeed: %v", err)
			}
			time.Sleep(30 * time.Millisecond)
		}
	}()

	// Worker: seek do przodu.
	// Kanał capacity=1: jedno żądanie może czekać; kolejne są droppowane.
	// FrameStepForward blokuje do potwierdzenia od mpv (SendAndWait) —
	// worker naturalnie czeka aż mpv skończy przed obsłużeniem kolejnego.
	go func() {
		for range p.seekFwdCh {
			if err := p.mpv.FrameStepForward(); err != nil {
				log.Printf("⚠️  FrameStepForward: %v", err)
			}
		}
	}()

	// Worker: seek do tyłu — identyczny schemat.
	go func() {
		for range p.seekBackCh {
			if err := p.mpv.FrameStepBack(); err != nil {
				log.Printf("⚠️  FrameStepBack: %v", err)
			}
		}
	}()

	for msg := range p.hub.Receive() {
		switch msg.Type {

		case "registered":
			log.Printf("✅ Zarejestrowano w hubie jako %s", p.cfg.PluginID)

		case "replay_play":
			go p.handlePlay(msg.Payload)

		case "replay_speed":
			// Zmiana prędkości = ingerencja → tryb ręczny
			p.enterManualMode("speed")
			speed := clampSpeed(payloadFloat(msg.Payload, "speed", p.cfg.DefaultSpeed))
			log.Printf("⚡ speed request → %.2f (clamped to [%.1f, %.1f])", speed, speedMin, speedMax)
			select {
			case p.speedCh <- speed:
			default:
				for len(p.speedCh) > 0 {
					<-p.speedCh
				}
				p.speedCh <- speed
			}

		case "replay_pause":
			p.enterManualMode("pause")
			go func() {
				if err := p.mpv.Pause(); err != nil {
					log.Printf("⚠️  Pause: %v", err)
					return
				}
				p.hub.Send(&Message{
					To:   "main-module",
					Type: "replay_paused",
					Payload: map[string]interface{}{},
				})
			}()

		case "replay_resume":
			p.enterManualMode("resume")
			go func() {
				if err := p.mpv.Resume(); err != nil {
					log.Printf("⚠️  Resume: %v", err)
					return
				}
				p.hub.Send(&Message{
					To:   "main-module",
					Type: "replay_resumed",
					Payload: map[string]interface{}{},
				})
			}()

		case "replay_stop":
			p.finishReplay("stop", nil)

		case "replay_frame_forward":
			// Wrzuć żądanie do kanału workerа (non-blocking).
			// Jeśli kanał pełny (worker zajęty i jedno żądanie czeka) — drop.
			p.enterManualMode("frame_forward")
			select {
			case p.seekFwdCh <- struct{}{}:
			default:
				log.Printf("⏭  frame_forward: dropped (worker busy)")
			}

		case "replay_frame_back":
			p.enterManualMode("frame_back")
			select {
			case p.seekBackCh <- struct{}{}:
			default:
				log.Printf("⏭  frame_back: dropped (worker busy)")
			}

		case "cancel_time_dependent_replay_end":
			p.enterManualMode("cancel_time_dependent_replay_end")
			log.Printf("⏹  auto end cancelled — waiting for end_replay")

		case "end_replay":
			log.Printf("✅ end_replay — finishing replay")
			p.finishReplay("manual", nil)
		}
	}
}

func (p *Plugin) handlePlay(payload map[string]interface{}) {
	videoPath, ok := payload["video_path"].(string)
	if !ok || videoPath == "" {
		log.Printf("⚠️  replay_play: brak video_path")
		return
	}
	if _, err := os.Stat(videoPath); os.IsNotExist(err) {
		log.Printf("❌ replay_play: plik nie istnieje: %s", videoPath)
		p.hub.Send(&Message{
			To:   "main-module",
			Type: "replay_error",
			Payload: map[string]interface{}{
				"error":      fmt.Sprintf("Plik nie istnieje: %s", videoPath),
				"video_path": videoPath,
			},
		})
		return
	}

	startMs := payloadInt64(payload, "replay_start_time", 0)
	endMs := payloadInt64(payload, "replay_end_time", 0)
	speed := clampSpeed(payloadFloat(payload, "speed", p.cfg.DefaultSpeed))
	estimatedDurationMs := payloadInt64(payload, "estimated_duration_ms", 0)

	if estimatedDurationMs <= 0 && endMs > startMs && speed > 0 {
		estimatedDurationMs = int64(float64(endMs-startMs) / speed)
	}

	// Opróżnij kanał speed — stare wartości z poprzedniej powtórki.
	for len(p.speedCh) > 0 {
		<-p.speedCh
	}

	// Nowa sesja.
	p.mu.Lock()
	p.cancelAutoEndTimerLocked()
	p.activeReplay = true
	p.manualMode = false
	mySession := p.sessionID.Add(1)
	p.mu.Unlock()

	if err := p.mpv.LoadAndPlay(videoPath, startMs, endMs, speed); err != nil {
		log.Printf("❌ LoadAndPlay: %v", err)
		p.mu.Lock()
		p.activeReplay = false
		p.manualMode = false
		p.cancelAutoEndTimerLocked()
		p.mu.Unlock()
		p.hub.Send(&Message{
			To:   "main-module",
			Type: "replay_error",
			Payload: map[string]interface{}{
				"error":      err.Error(),
				"video_path": videoPath,
			},
		})
		return
	}

	p.hub.Send(&Message{
		To:   "main-module",
		Type: "replay_started",
		Payload: map[string]interface{}{
			"video_path": videoPath,
			"start_ms":   startMs,
			"end_ms":     endMs,
			"speed":      speed,
		},
	})
	// replay_state zachowany dla kompatybilności wstecznej
	p.hub.Send(&Message{
		To:   "main-module",
		Type: "replay_state",
		Payload: map[string]interface{}{
			"status":     "playing",
			"video_path": videoPath,
			"start_ms":   startMs,
			"end_ms":     endMs,
			"speed":      speed,
		},
	})

	// Timer automatycznego zakończenia.
	// Anulowany przez enterManualMode() przy pierwszej ingerencji użytkownika.
	lead := p.cfg.TransitionLeadMs
	doneTriggerMs := estimatedDurationMs - lead
	if doneTriggerMs < 0 {
		doneTriggerMs = 0
	}

	log.Printf("⏱  replay_done za ~%dms (transition lead=%dms)", doneTriggerMs, lead)

	p.mu.Lock()
	p.autoEndTimer = time.AfterFunc(
		time.Duration(doneTriggerMs)*time.Millisecond,
		func() {
			p.mu.Lock()
			if p.sessionID.Load() != mySession || !p.activeReplay || p.manualMode {
				p.mu.Unlock()
				log.Printf("⏹  timer: session/state changed — skipping replay_done")
				return
			}
			p.activeReplay = false
			p.autoEndTimer = nil
			closingSession := p.sessionID.Add(1)
			p.mu.Unlock()

			log.Printf("⏱  replay auto end — sending replay_done")
			p.hub.Send(&Message{
				To:   "main-module",
				Type: "replay_done",
				Payload: map[string]interface{}{
					"video_path": videoPath,
					"start_ms":   startMs,
					"end_ms":     endMs,
					"source":     "timer",
				},
			})
			time.AfterFunc(time.Duration(lead)*time.Millisecond, func() {
				p.resetReplaySettings(closingSession)
			})
		},
	)
	p.mu.Unlock()
}

func (p *Plugin) heartbeatLoop() {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	for range ticker.C {
		p.hub.Send(&Message{
			To:   "hub",
			Type: "heartbeat",
			Payload: map[string]interface{}{
				"plugin_id": p.cfg.PluginID,
				"timestamp": time.Now().Unix(),
			},
		})
	}
}

func (p *Plugin) Stop() {
	p.mu.Lock()
	p.cancelAutoEndTimerLocked()
	p.activeReplay = false
	p.manualMode = false
	p.mu.Unlock()
	p.mpv.Stop()
	p.mpv.Close()
	if p.mpvCmd != nil && p.mpvCmd.Process != nil {
		p.mpvCmd.Process.Signal(syscall.SIGTERM)
	}
	p.hub.Close()
	log.Printf("🛑 Replay Plugin zatrzymany")
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func payloadFloat(p map[string]interface{}, key string, def float64) float64 {
	v, ok := p[key]
	if !ok {
		return def
	}
	switch val := v.(type) {
	case float64:
		return val
	case string:
		if f, err := strconv.ParseFloat(val, 64); err == nil {
			return f
		}
	}
	return def
}

func payloadInt64(p map[string]interface{}, key string, def int64) int64 {
	v, ok := p[key]
	if !ok {
		return def
	}
	switch val := v.(type) {
	case float64:
		return int64(val)
	case int64:
		return val
	case int:
		return int64(val)
	}
	return def
}

// ── main ──────────────────────────────────────────────────────────────────────

func main() {
	log.SetFlags(log.Ldate | log.Ltime | log.Lmsgprefix)
	log.SetPrefix("[replay] ")

	log.Println("🚀 Replay Plugin startuje...")

	configPath := "config.json"
	if len(os.Args) > 1 {
		configPath = os.Args[1]
	}
	cfg, err := loadConfig(configPath)
	if err != nil {
		log.Fatalf("❌ Config error: %v", err)
	}

	if v := os.Getenv("HUB_URL"); v != "" {
		cfg.HubURL = v
	}
	if v := os.Getenv("PLUGIN_ID"); v != "" {
		cfg.PluginID = v
	}

	log.Printf("   Plugin ID:   %s", cfg.PluginID)
	log.Printf("   Hub URL:     %s", cfg.HubURL)
	log.Printf("   mpv path:    %s", cfg.MpvPath)
	log.Printf("   Window:      %s", cfg.WindowGeometry)
	log.Printf("   Screen:      %s", cfg.MpvScreen)
	log.Printf("   Lead:        %dms", cfg.TransitionLeadMs)
	log.Printf("   Def. speed:  %.2f", cfg.DefaultSpeed)

	plugin := NewPlugin(cfg)
	if err := plugin.Start(); err != nil {
		log.Fatalf("❌ Start failed: %v", err)
	}

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, os.Interrupt, syscall.SIGTERM)
	<-quit

	log.Println("🛑 Zatrzymywanie...")
	plugin.Stop()
	log.Println("✅ Gotowe")
}
