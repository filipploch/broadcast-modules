package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"sync"
	"syscall"
	"time"
)

// ── Config ────────────────────────────────────────────────────────────────────

// Config przechowuje ustawienia pluginu.
//
// KeyBindings mapuje logiczne nazwy zdarzeń kontrolera na kody klawiszy
// wirtualnych Windows (VK_*) oraz opcjonalne modyfikatory. Domyślnie używane
// jest Ctrl+F1–Ctrl+F6, bo Sikai.exe często nie pozwala ustawić F13+.
//
// Operator MUSI raz przeprogramować pad dołączonym Sikai.exe tak, żeby każdy
// z fizycznych przycisków/kierunków rolki wysyłał odpowiedni z tych klawiszy.
// Patrz README.md.
//
// WheelBatchMs — okno akumulacji obrotów rolki w ms. Wszystkie tiki zliczone
// w tym oknie zostaną wysłane jako jeden controller_wheel z większą deltą.
// Zapobiega zalewaniu workerа replay-plugin przy szybkim kręceniu.
type KeyBinding struct {
	VK    int  `json:"vk"`
	Ctrl  bool `json:"ctrl,omitempty"`
	Shift bool `json:"shift,omitempty"`
	Alt   bool `json:"alt,omitempty"`
	Win   bool `json:"win,omitempty"`
}

// UnmarshalJSON pozwala używać zarówno starego formatu:
//
//	"btn1": 124
//
// jak i nowego formatu z modyfikatorami:
//
//	"btn1": { "vk": 112, "ctrl": true }
func (b *KeyBinding) UnmarshalJSON(data []byte) error {
	var oldVK int
	if err := json.Unmarshal(data, &oldVK); err == nil {
		b.VK = oldVK
		b.Ctrl = false
		b.Shift = false
		b.Alt = false
		b.Win = false
		return nil
	}

	type alias KeyBinding
	var v alias
	if err := json.Unmarshal(data, &v); err != nil {
		return err
	}

	*b = KeyBinding(v)
	return nil
}

// HookBinding to gotowa do użycia, zwalidowana postać wiązania przekazywana
// do hooka klawiatury.
type HookBinding struct {
	Logical string
	VK      uint32
	Ctrl    bool
	Shift   bool
	Alt     bool
	Win     bool
}

type Config struct {
	PluginID     string                `json:"plugin_id"`
	PluginName   string                `json:"plugin_name"`
	HubURL       string                `json:"hub_url"`
	KeyBindings  map[string]KeyBinding `json:"key_bindings"`
	WheelBatchMs int                   `json:"wheel_batch_ms"`
}

func defaultConfig() Config {
	return Config{
		PluginID:   "controller-plugin",
		PluginName: "USB Controller Plugin",
		HubURL:     "ws://localhost:8080/ws",
		// Domyślnie Ctrl+F1–Ctrl+F6. Operator musi tak skonfigurować
		// pad w Sikai.exe. Stary format configu z samymi liczbami VK nadal działa.
		KeyBindings: map[string]KeyBinding{
			"btn1":      {VK: 0x70, Ctrl: true}, // Ctrl+F1
			"btn2":      {VK: 0x71, Ctrl: true}, // Ctrl+F2
			"btn3":      {VK: 0x72, Ctrl: true}, // Ctrl+F3
			"wheel_btn": {VK: 0x73, Ctrl: true}, // Ctrl+F4
			"wheel_cw":  {VK: 0x74, Ctrl: true}, // Ctrl+F5
			"wheel_ccw": {VK: 0x75, Ctrl: true}, // Ctrl+F6
		},
		WheelBatchMs: 25,
	}
}

func loadConfig(path string) (Config, error) {
	cfg := defaultConfig()
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		out, _ := json.MarshalIndent(cfg, "", "  ")
		if werr := os.WriteFile(path, out, 0644); werr != nil {
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
	// Uzupełnij brakujące klucze z domyślnych — gwarantuje wsteczną kompatybilność
	// gdy użytkownik ma stary config.json bez nowo-dodanego wiązania.
	def := defaultConfig()
	if cfg.KeyBindings == nil {
		cfg.KeyBindings = map[string]KeyBinding{}
	}
	for k, v := range def.KeyBindings {
		if _, ok := cfg.KeyBindings[k]; !ok {
			cfg.KeyBindings[k] = v
		}
	}
	if cfg.WheelBatchMs <= 0 {
		cfg.WheelBatchMs = def.WheelBatchMs
	}
	return cfg, nil
}

// ── Plugin ────────────────────────────────────────────────────────────────────

type Plugin struct {
	cfg     Config
	hub     *HubClient
	eventCh chan ControllerEvent
	mu      sync.Mutex
}

func NewPlugin(cfg Config) *Plugin {
	return &Plugin{
		cfg:     cfg,
		eventCh: make(chan ControllerEvent, 64),
	}
}

func (p *Plugin) Start() error {
	if runtime.GOOS != "windows" {
		return fmt.Errorf("controller-plugin działa tylko na Windows (low-level keyboard hook)")
	}

	p.hub = NewHubClient(p.cfg.PluginID, p.cfg.PluginName, p.cfg.HubURL)
	if err := p.hub.Connect(); err != nil {
		return fmt.Errorf("cannot connect to Hub: %w", err)
	}
	go p.hub.AutoReconnect()
	go p.heartbeatLoop()
	go p.processEvents()

	// Zbuduj listę wiązań: logiczna nazwa + vkCode + wymagane modyfikatory.
	bindings := make([]HookBinding, 0, len(p.cfg.KeyBindings))
	for logical, b := range p.cfg.KeyBindings {
		if b.VK <= 0 {
			return fmt.Errorf("invalid key binding for %s: vk must be > 0", logical)
		}
		bindings = append(bindings, HookBinding{
			Logical: logical,
			VK:      uint32(b.VK),
			Ctrl:    b.Ctrl,
			Shift:   b.Shift,
			Alt:     b.Alt,
			Win:     b.Win,
		})
	}

	// Hook musi mieć własny zablokowany wątek z pompą wiadomości Win32
	go func() {
		if err := runKeyHook(bindings, p.eventCh); err != nil {
			log.Printf("❌ runKeyHook: %v", err)
		}
	}()

	log.Printf("✅ Controller Plugin uruchomiony")
	return nil
}

// processEvents czyta z eventCh, akumuluje obroty rolki w oknie WheelBatchMs
// i wysyła do main-module:
//   - controller_wheel { delta: int }   — dla obrotów (zsumowanych)
//   - controller_button { button, action } — dla przycisków (każdy press od razu)
//
// Akumulacja zachowuje porządek: jeśli przyjdzie przycisk w trakcie zbierania
// tików, najpierw flushujemy bieżący batch, dopiero potem wysyłamy przycisk.
func (p *Plugin) processEvents() {
	batch := time.Duration(p.cfg.WheelBatchMs) * time.Millisecond

	wheelDelta := 0
	var flushTimer *time.Timer

	flush := func() {
		if wheelDelta == 0 {
			return
		}
		d := wheelDelta
		wheelDelta = 0
		p.hub.Send(&Message{
			To:   "main-module",
			Type: "controller_wheel",
			Payload: map[string]interface{}{
				"delta": d,
			},
		})
	}

	resetTimer := func() {
		if flushTimer == nil {
			flushTimer = time.NewTimer(batch)
			return
		}
		if !flushTimer.Stop() {
			select {
			case <-flushTimer.C:
			default:
			}
		}
		flushTimer.Reset(batch)
	}

	timerC := func() <-chan time.Time {
		if flushTimer == nil {
			return nil
		}
		return flushTimer.C
	}

	for {
		select {
		case ev := <-p.eventCh:
			switch ev.Logical {
			case "wheel_cw":
				wheelDelta++
				resetTimer()
			case "wheel_ccw":
				wheelDelta--
				resetTimer()
			default:
				// Najpierw wypchnij zaległą rolkę żeby nie pomieszać kolejności.
				flush()
				if flushTimer != nil {
					flushTimer.Stop()
					flushTimer = nil
				}
				p.hub.Send(&Message{
					To:   "main-module",
					Type: "controller_button",
					Payload: map[string]interface{}{
						"button": ev.Logical,
						"action": "press",
					},
				})
			}
		case <-timerC():
			flush()
			flushTimer = nil
		}
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
	stopKeyHook()
	if p.hub != nil {
		p.hub.Close()
	}
	log.Printf("🛑 Controller Plugin zatrzymany")
}

// ── main ──────────────────────────────────────────────────────────────────────

func main() {
	log.SetFlags(log.Ldate | log.Ltime | log.Lmsgprefix)
	log.SetPrefix("[controller] ")
	log.Println("🚀 Controller Plugin startuje...")

	configPath := "config.json"
	if len(os.Args) > 1 {
		configPath = os.Args[1]
	}
	if abs, err := filepath.Abs(configPath); err == nil {
		configPath = abs
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

	log.Printf("   Plugin ID:     %s", cfg.PluginID)
	log.Printf("   Hub URL:       %s", cfg.HubURL)
	log.Printf("   Wheel batch:   %dms", cfg.WheelBatchMs)
	log.Printf("   Key bindings:")
	for logical, binding := range cfg.KeyBindings {
		mods := ""
		if binding.Ctrl {
			mods += "Ctrl+"
		}
		if binding.Shift {
			mods += "Shift+"
		}
		if binding.Alt {
			mods += "Alt+"
		}
		if binding.Win {
			mods += "Win+"
		}
		log.Printf("     %-10s → %sVK 0x%02X (%d)", logical, mods, binding.VK, binding.VK)
	}

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
