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
	cfg     Config
	hub     *HubClient
	mpv     *MpvController
	mpvCmd  *exec.Cmd
	speedCh chan float64
	mu      sync.Mutex

	// Stan powtórki
	doneTimer     *time.Timer
	timeDependent bool
	// sessionID: atomic counter — inkrementowany przy każdym replay_play
	// Timer callback porównuje swój sessionID z aktualnym
	// Jeśli różne — callback jest z poprzedniej powtórki i ignoruje wysyłkę
	sessionID atomic.Int64
}

func NewPlugin(cfg Config) *Plugin {
	return &Plugin{
		cfg:     cfg,
		mpv:     NewMpvController(cfg.MpvPipe),
		speedCh: make(chan float64, 1),
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
		"--demuxer-readahead-secs=0",
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

// cancelTimer anuluje aktywny timer zakończenia powtórki.
// Bezpieczne do wywołania wielokrotnie.
func (p *Plugin) cancelTimer() {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.doneTimer != nil {
		p.doneTimer.Stop()
		p.doneTimer = nil
	}
	p.timeDependent = false
}

func (p *Plugin) messageLoop() {
	// Dedykowane goroutine z debounce dla częstych sygnałów
	frameFwdCh := make(chan struct{}, 1)
	frameBackCh := make(chan struct{}, 1)

	// Worker: zmiana prędkości — debounce 30ms
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

	// Worker: frame step forward — debounce 80ms
	go func() {
		for range frameFwdCh {
			for len(frameFwdCh) > 0 {
				<-frameFwdCh
			}
			if err := p.mpv.FrameStepForward(); err != nil {
				log.Printf("⚠️  FrameStepForward: %v", err)
			}
			time.Sleep(80 * time.Millisecond)
		}
	}()

	// Worker: frame step back — debounce 80ms
	go func() {
		for range frameBackCh {
			for len(frameBackCh) > 0 {
				<-frameBackCh
			}
			if err := p.mpv.FrameStepBack(); err != nil {
				log.Printf("⚠️  FrameStepBack: %v", err)
			}
			time.Sleep(80 * time.Millisecond)
		}
	}()

	for msg := range p.hub.Receive() {
		switch msg.Type {

		case "registered":
			log.Printf("✅ Zarejestrowano w hubie jako %s", p.cfg.PluginID)

		case "replay_play":
			go p.handlePlay(msg.Payload)

		case "replay_speed":
			// Zmiana prędkości = ingerencja → anuluj timer
			p.cancelTimer()
			speed := payloadFloat(msg.Payload, "speed", p.cfg.DefaultSpeed)
			select {
			case p.speedCh <- speed:
			default:
				for len(p.speedCh) > 0 {
					<-p.speedCh
				}
				p.speedCh <- speed
			}

		case "replay_pause":
			// Pauza = ingerencja → anuluj timer
			p.cancelTimer()
			if err := p.mpv.Pause(); err != nil {
				log.Printf("⚠️  Pause: %v", err)
			}

		case "replay_resume":
			if err := p.mpv.Resume(); err != nil {
				log.Printf("⚠️  Resume: %v", err)
			}

		case "replay_stop":
			p.cancelTimer()
			if err := p.mpv.Stop(); err != nil {
				log.Printf("⚠️  Stop: %v", err)
			}

		case "replay_frame_forward":
			// Krok klatkowy = ingerencja → anuluj timer
			p.cancelTimer()
			select {
			case frameFwdCh <- struct{}{}:
			default:
			}

		case "replay_frame_back":
			// Krok klatkowy = ingerencja → anuluj timer
			p.cancelTimer()
			select {
			case frameBackCh <- struct{}{}:
			default:
			}

		case "cancel_time_dependent_replay_end":
			// Jawne anulowanie timera + wyłącz AB-loop
			// TODO: zabezpieczenie max czasu oczekiwania na end_replay
			p.cancelTimer()
			p.mpv.DisableAbLoop()
			log.Printf("⏹  cancel_time_dependent_replay_end — czekam na end_replay")

		case "end_replay":
			p.mu.Lock()
			timeDep := p.timeDependent
			p.mu.Unlock()
			if timeDep {
				log.Printf("⚠️  end_replay zignorowany — replay jest time-dependent")
				break
			}
			log.Printf("✅ end_replay — wysyłam replay_done")
			p.mpv.SetSpeed(p.cfg.DefaultSpeed)
			p.mpv.Pause()
			p.hub.Send(&Message{
				To:   "main-module",
				Type: "replay_done",
				Payload: map[string]interface{}{
					"source": "manual",
				},
			})
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
	speed := payloadFloat(payload, "speed", p.cfg.DefaultSpeed)
	estimatedDurationMs := payloadInt64(payload, "estimated_duration_ms", 0)

	if estimatedDurationMs <= 0 && endMs > startMs && speed > 0 {
		estimatedDurationMs = int64(float64(endMs-startMs) / speed)
	}

	// Opróżnij kanał speed — stare wartości z poprzedniej powtórki
	for len(p.speedCh) > 0 {
		<-p.speedCh
	}

	// Anuluj poprzedni timer i nowa sesja
	p.mu.Lock()
	if p.doneTimer != nil {
		p.doneTimer.Stop()
		p.doneTimer = nil
	}
	p.timeDependent = false
	mySession := p.sessionID.Add(1) // nowy unikalny ID sesji
	p.mu.Unlock()

	if err := p.mpv.LoadAndPlay(videoPath, startMs, endMs, speed); err != nil {
		log.Printf("❌ LoadAndPlay: %v", err)
		return
	}

	// Poinformuj moduł o starcie
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

	// Ustaw timer zakończenia
	lead := p.cfg.TransitionLeadMs
	if estimatedDurationMs > lead {
		doneTriggerMs := estimatedDurationMs - lead
		log.Printf("⏱  replay_done za ~%dms (transition lead=%dms)", doneTriggerMs, lead)

		p.mu.Lock()
		p.timeDependent = true
		p.doneTimer = time.AfterFunc(
			time.Duration(doneTriggerMs)*time.Millisecond,
			func() {
				p.mu.Lock()
				// Sprawdź: czy to wciąż ta sama sesja i czy nadal time-dependent
				if p.sessionID.Load() != mySession || !p.timeDependent {
					p.mu.Unlock()
					log.Printf("⏹  timer: sesja lub stan nieaktualne — pomijam replay_done")
					return
				}
				p.timeDependent = false
				p.doneTimer = nil
				p.mu.Unlock()

				log.Printf("⏱  wysyłam replay_done")
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
				// Pause i reset prędkości po transition
				time.AfterFunc(time.Duration(lead)*time.Millisecond, func() {
					p.mpv.SetSpeed(p.cfg.DefaultSpeed)
					p.mpv.Pause()
					log.Printf("⏸  mpv paused, speed reset → %.2f", p.cfg.DefaultSpeed)
				})
			},
		)
		p.mu.Unlock()
	}
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
	p.cancelTimer()
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
