package main

import (
	"encoding/json"
	"fmt"
	"log"
	"mime"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"sync"
	"time"
)

// Kanał sterujący managera (E2d3c1). Osobny serwer HTTP HUB-a, tylko na 127.0.0.1:<control_port> (domyślnie 8079), niezależny
// od WebSocketu pluginów: manager nie rejestruje się, nie wysyła heartbeatów i nie jest liczony w /status ani w monitorze zdrowia.
// Każde żądanie jest krótkie i niezależne; HUB nie pamięta managera. Ochrona przed stroną w przeglądarce: żądanie z nagłówkiem
// Origin jest odrzucane, a POST wymaga Content-Type: application/json (przeglądarka nie wyśle go bez zapytania wstępnego CORS).
//
//   GET  /state          stan HUB-a, modułów, sesji i recordera (kształt przypięty testem do controlProtocolVersion)
//   POST /module/start   {"id": "<id z module.json>"}; HUB wymusza wyłączność (jeden aktywny moduł)
//   POST /module/stop    zatrzymuje tylko moduł; blokada przy otwartej sesji i przy nieznanym statusie sesji
//   POST /hub/stop       celowe zatrzymanie HUB-a (przycisk "ZATRZYMAJ HUB" do czasu E2e2); te same blokady
//   GET  /recorder       stan nagrywania z recorder-pluginu (polecenie recording_status, do 3 s)

// controlProtocolVersion rozstrzyga zgodność managera z HUB-em: manager oczekuje konkretnej wartości. Każda zmiana kształtu
// odpowiedzi /state albo /recorder wymaga podniesienia tej liczby (test TestControlResponseShapeIsPinnedToProtocolVersion).
const controlProtocolVersion = 1

// buildCommit wpisuje hub\build.bat (-ldflags "-X main.buildCommit=<commit>[-dirty]"); zwykłe "go build" zostawia pusty (wersja nieznana).
var buildCommit = ""

// Stany aktywnego modułu w /state.
const (
	activeStarting      = "starting"       // HUB uruchomił proces, moduł jeszcze nie odpowiada
	activeRunning       = "running"        // moduł działa
	activeStopping      = "stopping"       // trwa zatrzymywanie
	activeError         = "error"          // proces działa, ale zgłasza błąd (np. brak odpowiedzi portu)
	activeManual        = "manual"         // moduł uruchomiony ręcznie, poza HUB-em, rozpoznany po nazwie z rejestracji
	activeManualUnknown = "manual_unknown" // moduł uruchomiony ręcznie, którego nazwy nie ma w żadnym module.json
)

type controlState struct {
	Protocol       int             `json:"protocol"`
	Hub            controlHub      `json:"hub"`
	Modules        []controlModule `json:"modules"`
	ModuleWarnings []string        `json:"module_warnings"`
	Active         *controlActive  `json:"active"`
	LastModule     controlLast     `json:"last_module"`
	Session        controlSession  `json:"session"`
	Recorder       controlRecConn  `json:"recorder"`
}

type controlHub struct {
	Commit   string `json:"commit"` // "" = wersja nieznana (hub.exe zbudowany bez build.bat)
	PID      int    `json:"pid"`
	UptimeS  int    `json:"uptime_s"`
	LogDir   string `json:"log_dir"`
	HubLog   string `json:"hub_log"`
	Stopping bool   `json:"stopping"`
}

type controlModule struct {
	ID      string `json:"id"`
	Button  string `json:"button"`
	Port    int    `json:"port"`
	LogName string `json:"log_name"`
	Order   int    `json:"order"`
	Folder  string `json:"folder"`
}

type controlActive struct {
	ID      string `json:"id"` // "" przy manual_unknown
	Button  string `json:"button"`
	Name    string `json:"name"` // nazwa z rejestracji modułu w HUB-ie (MODULE_NAME)
	State   string `json:"state"`
	PID     int    `json:"pid"`
	Missing bool   `json:"missing"` // folder albo module.json działającego modułu zniknął
	Error   string `json:"error"`
}

// controlLast: ostatni moduł uruchamiany przez HUB, także gdy już nie działa (np. zakończył się błędem).
type controlLast struct {
	ID     string `json:"id"`
	Status string `json:"status"`
	Error  string `json:"error"`
}

type controlSession struct {
	State     string `json:"state"` // none / preparation / on_air; "" gdy nieznany
	Known     bool   `json:"known"`
	Open      bool   `json:"open"`
	SessionID int    `json:"session_id"`
	FromFile  bool   `json:"from_file"`
}

type controlRecConn struct {
	Connected bool `json:"connected"`
}

// controlRecorder: odpowiedź /recorder.
type controlRecorder struct {
	State   string          `json:"state"` // recording / not_recording / unknown
	Reason  string          `json:"reason"`
	Cameras map[string]bool `json:"cameras"`
}

// controlResult: odpowiedź na POST (i na odrzucone żądania).
type controlResult struct {
	OK     bool   `json:"ok"`
	Reason string `json:"reason"` // kod powodu odmowy (busy, unknown_module, port_busy, session_open, session_unknown, no_module, ...)
	Error  string `json:"error"`  // komunikat dla operatora
}

const recorderQueryTimeout = 3 * time.Second

type controlServer struct {
	hub       *Hub
	cfg       *LoadedHubConfig
	startedAt time.Time
	recTO     time.Duration
	stopHub   func() // uruchamia zamykanie HUB-a (to samo co Ctrl+C)
	// serviceFor składa usługę "module" dla modułu z katalogu (testy podmieniają ją na proces pomocniczy)
	serviceFor func(ModuleManifest) ServiceConfig

	mu             sync.Mutex
	catalog        *ModuleCatalog
	stopping       bool // HUB zamyka się na polecenie kanału
	manualStopping bool // wysłano shutdown_module do modułu uruchomionego ręcznie
	stopCh         chan struct{}
	stopOnce       sync.Once
}

func newControlServer(h *Hub, cfg *LoadedHubConfig) *controlServer {
	c := &controlServer{hub: h, cfg: cfg, startedAt: time.Now(), recTO: recorderQueryTimeout, stopCh: make(chan struct{})}
	c.catalog = cfg.Catalog
	c.serviceFor = cfg.moduleServiceFor
	c.stopHub = func() { c.stopOnce.Do(func() { close(c.stopCh) }) }
	return c
}

// StopRequested zamyka się, gdy kanał zlecił zamknięcie HUB-a.
func (c *controlServer) StopRequested() <-chan struct{} { return c.stopCh }

// Listen otwiera serwer kanału na 127.0.0.1. Błąd (np. port zajęty) tylko w logu: HUB działa dalej, manager pokaże "HUB nie odpowiada".
func (c *controlServer) Listen(port int) {
	addr := net.JoinHostPort("127.0.0.1", strconv.Itoa(port))
	ln, err := net.Listen("tcp", addr)
	if err != nil {
		log.Printf("❌ Kanał sterujący managera: nie można otworzyć %s: %v (manager nie będzie mógł sterować HUB-em)", addr, err)
		return
	}
	log.Printf("🎛️  Kanał sterujący managera: http://%s (tylko z tego komputera)", addr)
	go func() {
		srv := &http.Server{Handler: c.Handler(), ReadHeaderTimeout: 5 * time.Second}
		if err := srv.Serve(ln); err != nil && err != http.ErrServerClosed {
			log.Printf("❌ Kanał sterujący managera: %v", err)
		}
	}()
}

// Handler: obsługa żądań z kontrolą dostępu.
func (c *controlServer) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/state", c.method(http.MethodGet, c.handleState))
	mux.HandleFunc("/module/start", c.method(http.MethodPost, c.handleModuleStart))
	mux.HandleFunc("/module/stop", c.method(http.MethodPost, c.handleModuleStop))
	mux.HandleFunc("/hub/stop", c.method(http.MethodPost, c.handleHubStop))
	mux.HandleFunc("/recorder", c.method(http.MethodGet, c.handleRecorder))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Origin") != "" {
			writeJSON(w, http.StatusForbidden, controlResult{Reason: "origin", Error: "żądania ze stron w przeglądarce są odrzucane (nagłówek Origin)"})
			return
		}
		if !isLoopback(r.RemoteAddr) {
			writeJSON(w, http.StatusForbidden, controlResult{Reason: "remote", Error: "kanał sterujący przyjmuje tylko połączenia z tego komputera"})
			return
		}
		mux.ServeHTTP(w, r)
	})
}

func (c *controlServer) method(m string, h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != m {
			writeJSON(w, http.StatusMethodNotAllowed, controlResult{Reason: "method", Error: "dozwolona metoda: " + m})
			return
		}
		if m == http.MethodPost {
			mt, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
			if err != nil || mt != "application/json" {
				writeJSON(w, http.StatusUnsupportedMediaType, controlResult{Reason: "content_type", Error: "wymagany Content-Type: application/json"})
				return
			}
		}
		h(w, r)
	}
}

func isLoopback(remote string) bool {
	host, _, err := net.SplitHostPort(remote)
	if err != nil {
		return false
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}

func writeJSON(w http.ResponseWriter, code int, v interface{}) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

// rescan odczytuje pliki module.json ponownie (dodanie albo usunięcie folderu modułu bez restartu HUB-a).
func (c *controlServer) rescan() *ModuleCatalog {
	cat := scanModuleCatalog(c.cfg.abs(c.cfg.ModulesDir))
	c.mu.Lock()
	c.catalog = cat
	c.mu.Unlock()
	return cat
}

// active ustala aktywny moduł: najpierw usługa "module" uruchomiona lub przejęta przez HUB, potem moduł połączony z HUB-em
// bez usługi (uruchomiony ręcznie), rozpoznany po nazwie z rejestracji.
func (c *controlServer) active(cat *ModuleCatalog) *controlActive {
	if c.hub.Services != nil {
		status, pid, modID, lastErr, stopping, alive := c.hub.Services.Info("module")
		if alive {
			m, ok := cat.Get(modID)
			a := &controlActive{ID: modID, Button: m.Button, Name: m.EffectiveLogName(), PID: pid, Missing: !ok, Error: lastErr}
			if !ok {
				a.Button = modID
				a.Name = modID
			}
			switch {
			case stopping:
				a.State = activeStopping
			case status == "online":
				a.State = activeRunning
			case status == "starting":
				a.State = activeStarting
			default:
				a.State = activeError
			}
			return a
		}
	}
	c.hub.mu.RLock()
	mm := c.hub.MainModule
	name, connected := "", false
	if mm != nil && mm.IsActive {
		name, connected = mm.Name, true
	}
	c.hub.mu.RUnlock()
	c.mu.Lock()
	if !connected {
		c.manualStopping = false
	}
	manualStopping := c.manualStopping
	c.mu.Unlock()
	if !connected {
		return nil
	}
	a := &controlActive{Name: name, State: activeManual}
	if m, ok := cat.ByLogName(name); ok {
		a.ID, a.Button = m.ID, m.Button
	} else {
		a.State = activeManualUnknown
		a.Button = name
	}
	if manualStopping {
		a.State = activeStopping
	}
	return a
}

func (c *controlServer) state() controlState {
	cat := c.rescan()
	st := controlState{Protocol: controlProtocolVersion, Modules: []controlModule{}, ModuleWarnings: append([]string{}, cat.Warnings...)}
	c.mu.Lock()
	st.Hub.Stopping = c.stopping
	c.mu.Unlock()
	st.Hub.Commit = buildCommit
	st.Hub.PID = os.Getpid()
	st.Hub.UptimeS = int(time.Since(c.startedAt).Seconds())
	st.Hub.LogDir = runLogDir
	if runLogDir != "" {
		st.Hub.HubLog = filepath.Join(runLogDir, "hub.log")
	}
	for _, m := range cat.Modules {
		st.Modules = append(st.Modules, controlModule{ID: m.ID, Button: m.Button, Port: m.Port, LogName: m.EffectiveLogName(),
			Order: m.Order, Folder: filepath.Base(m.Dir)})
	}
	st.Active = c.active(cat)
	if c.hub.Services != nil {
		status, _, modID, lastErr, _, _ := c.hub.Services.Info("module")
		st.LastModule = controlLast{ID: modID, Status: status, Error: lastErr}
	}
	s := c.hub.SessionStatus()
	st.Session = controlSession{State: s.State, Known: s.Known, Open: s.IsOpen(), SessionID: s.SessionID, FromFile: s.FromFile}
	c.hub.mu.RLock()
	if p, ok := c.hub.Plugins["recorder-plugin"]; ok && p.IsActive {
		st.Recorder.Connected = true
	}
	c.hub.mu.RUnlock()
	return st
}

func (c *controlServer) handleState(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, c.state())
}

// sessionGate: zatrzymanie modułu i HUB-a jest zablokowane przy otwartej sesji i przy nieznanym statusie sesji.
// Wyjście awaryjne przy nieznanym statusie: E2e2.
func (c *controlServer) sessionGate() (reason, msg string) {
	s := c.hub.SessionStatus()
	switch {
	case !s.Known:
		return "session_unknown", "Stan sesji transmisji jest nieznany: zatrzymanie zablokowane (bezpieczna strona)"
	case s.IsOpen():
		return "session_open", fmt.Sprintf("Najpierw zamknij sesję transmisji (sesja %s, nr %d)", s.State, s.SessionID)
	}
	return "", ""
}

func (c *controlServer) handleModuleStart(w http.ResponseWriter, r *http.Request) {
	var req struct {
		ID string `json:"id"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096)).Decode(&req); err != nil || req.ID == "" {
		writeJSON(w, http.StatusBadRequest, controlResult{Reason: "bad_request", Error: "oczekiwano {\"id\": \"<moduł>\"}"})
		return
	}
	c.mu.Lock()
	stopping := c.stopping
	c.mu.Unlock()
	if stopping || (c.hub.Services != nil && c.hub.Services.isShuttingDown()) {
		writeJSON(w, http.StatusConflict, controlResult{Reason: "hub_stopping", Error: "HUB się zamyka"})
		return
	}
	cat := c.rescan()
	m, ok := cat.Get(req.ID)
	if !ok {
		writeJSON(w, http.StatusNotFound, controlResult{Reason: "unknown_module", Error: fmt.Sprintf("nieznany moduł %q (brak pliku module.json)", req.ID)})
		return
	}
	if a := c.active(cat); a != nil {
		who := a.Button
		if who == "" {
			who = a.Name
		}
		writeJSON(w, http.StatusConflict, controlResult{Reason: "busy", Error: fmt.Sprintf("działa już moduł %s; najpierw go zatrzymaj", who)})
		return
	}
	if tcpOpen(net.JoinHostPort("127.0.0.1", strconv.Itoa(m.Port))) {
		writeJSON(w, http.StatusConflict, controlResult{Reason: "port_busy",
			Error: fmt.Sprintf("port %d jest zajęty przez inny proces (np. wersja transmisyjna); moduł nie został uruchomiony", m.Port)})
		return
	}
	if c.hub.Services == nil {
		writeJSON(w, http.StatusInternalServerError, controlResult{Reason: "no_services", Error: "HUB nie ma menedżera usług"})
		return
	}
	if err := c.hub.Services.Replace(c.serviceFor(m)); err != nil {
		writeJSON(w, http.StatusConflict, controlResult{Reason: "busy", Error: err.Error()})
		return
	}
	log.Printf("🎛️  Kanał sterujący: start modułu %s", m.ID)
	if err := c.hub.Services.Start("module"); err != nil {
		writeJSON(w, http.StatusInternalServerError, controlResult{Reason: "start_failed", Error: err.Error()})
		return
	}
	writeJSON(w, http.StatusAccepted, controlResult{OK: true})
}

func (c *controlServer) handleModuleStop(w http.ResponseWriter, r *http.Request) {
	cat := c.rescan()
	a := c.active(cat)
	if a == nil {
		writeJSON(w, http.StatusConflict, controlResult{Reason: "no_module", Error: "żaden moduł nie działa"})
		return
	}
	if reason, msg := c.sessionGate(); reason != "" {
		writeJSON(w, http.StatusConflict, controlResult{Reason: reason, Error: msg})
		return
	}
	if a.State == activeManual || a.State == activeManualUnknown || (a.State == activeStopping && a.PID == 0) {
		if !c.hub.gracefulStopService("module") {
			writeJSON(w, http.StatusConflict, controlResult{Reason: "not_connected", Error: "moduł uruchomiony ręcznie nie jest połączony z HUB-em"})
			return
		}
		c.mu.Lock()
		c.manualStopping = true
		c.mu.Unlock()
		log.Printf("🎛️  Kanał sterujący: prośba o zamknięcie modułu uruchomionego ręcznie (%s)", a.Name)
		writeJSON(w, http.StatusAccepted, controlResult{OK: true})
		return
	}
	log.Printf("🎛️  Kanał sterujący: zatrzymanie modułu %s (HUB, OBS i pluginy zostają)", a.ID)
	go func() {
		if err := c.hub.Services.Stop("module"); err != nil {
			log.Printf("⚠️  Kanał sterujący: zatrzymanie modułu: %v", err)
		}
	}()
	writeJSON(w, http.StatusAccepted, controlResult{OK: true})
}

func (c *controlServer) handleHubStop(w http.ResponseWriter, r *http.Request) {
	if reason, msg := c.sessionGate(); reason != "" {
		writeJSON(w, http.StatusConflict, controlResult{Reason: reason, Error: msg})
		return
	}
	c.mu.Lock()
	c.stopping = true
	c.mu.Unlock()
	log.Printf("🎛️  Kanał sterujący: celowe zatrzymanie HUB-a")
	writeJSON(w, http.StatusAccepted, controlResult{OK: true})
	go c.stopHub()
}

func (c *controlServer) handleRecorder(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, c.hub.recorderStatus(c.recTO))
}

// recorderStatus pyta recorder-plugin o stan nagrywania (polecenie recording_status; odpowiedź recording_status_response
// z {cameras: {camera1: bool, ...}}). "nagrywa" gdy którakolwiek kamera nagrywa; "nie nagrywa" tylko przy czytelnej odpowiedzi,
// w której żadna nie nagrywa; w pozostałych przypadkach "nie wiadomo" z powodem. Recorder-pluginu nie zmieniamy (E2d3b).
func (h *Hub) recorderStatus(timeout time.Duration) controlRecorder {
	out := controlRecorder{State: "unknown", Cameras: map[string]bool{}}
	resp, err := h.RequestByContext("recorder-plugin", "recording_status", map[string]interface{}{}, timeout)
	if err != nil {
		out.Reason = err.Error()
		return out
	}
	if st, _ := resp.Payload["status"].(string); st != "ok" {
		e, _ := resp.Payload["error"].(string)
		out.Reason = fmt.Sprintf("recorder-plugin odpowiedział błędem: %s", e)
		return out
	}
	cams, ok := resp.Payload["cameras"].(map[string]interface{})
	if !ok {
		out.Reason = "nieczytelna odpowiedź recorder-pluginu (brak listy kamer)"
		return out
	}
	recording := false
	for id, v := range cams {
		b, isBool := v.(bool)
		if !isBool {
			out.Cameras = map[string]bool{}
			out.Reason = fmt.Sprintf("nieczytelna odpowiedź recorder-pluginu (kamera %s)", id)
			return out
		}
		out.Cameras[id] = b
		recording = recording || b
	}
	if recording {
		out.State = "recording"
	} else {
		out.State = "not_recording"
	}
	return out
}

// RequestByContext wysyła do pluginu polecenie z identyfikatorem pytania w kontekście (plugin odsyła kontekst polecenia w odpowiedzi,
// E2c) i czeka na odpowiedź <polecenie>_response adresowaną do HUB-a.
func (h *Hub) RequestByContext(pluginID, msgType string, payload map[string]interface{}, timeout time.Duration) (*Message, error) {
	h.mu.RLock()
	plugin := h.Plugins[pluginID]
	h.mu.RUnlock()
	if plugin == nil || !plugin.IsActive {
		return nil, fmt.Errorf("plugin %s nie jest połączony", pluginID)
	}
	h.requests.mu.Lock()
	if h.requests.pending == nil {
		h.requests.pending = map[string]*pendingRequest{}
	}
	h.requests.seq++
	id := fmt.Sprintf("hub-%d", h.requests.seq)
	req := &pendingRequest{requestType: msgType + "_response", byContext: true, ch: make(chan *Message, 1)}
	h.requests.pending[id] = req
	h.requests.mu.Unlock()
	defer func() {
		h.requests.mu.Lock()
		delete(h.requests.pending, id)
		h.requests.mu.Unlock()
	}()
	msg := NewMessage("hub", pluginID, msgType, payload)
	msg.Context = map[string]interface{}{"hub_request_id": id}
	h.sendSafely(plugin, msg)
	select {
	case resp := <-req.ch:
		return resp, nil
	case <-time.After(timeout):
		return nil, fmt.Errorf("brak odpowiedzi pluginu %s w %v", pluginID, timeout)
	}
}

// deliverByContext przekazuje odpowiedź z identyfikatorem pytania w kontekście do oczekującego pytania. true = dostarczono.
func (h *Hub) deliverByContext(msg *Message) bool {
	id, _ := msg.Context["hub_request_id"].(string)
	if id == "" {
		return false
	}
	h.requests.mu.Lock()
	defer h.requests.mu.Unlock()
	req, ok := h.requests.pending[id]
	if !ok || !req.byContext || req.requestType != msg.Type {
		// spóźniona albo niepasująca odpowiedź na pytanie HUB-a: nie trafia dalej (adresatem jest HUB)
		log.Printf("ℹ️  Pominięto odpowiedź %s od %s na pytanie HUB-a %s (pytanie już nie czeka)", msg.Type, msg.From, id)
		return true
	}
	select {
	case req.ch <- msg:
	default:
	}
	return true
}
