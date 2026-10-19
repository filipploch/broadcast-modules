package main

import (
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strconv"
	"strings"
	"testing"
	"time"
)

// --- przypięcie kształtu odpowiedzi do wersji protokołu ---

// jsonShape opisuje typ jako posortowaną listę ścieżek pól JSON z rodzajem wartości (np. "hub.commit:string").
func jsonShape(t reflect.Type) []string {
	var out []string
	var walk func(prefix string, t reflect.Type)
	walk = func(prefix string, t reflect.Type) {
		for t.Kind() == reflect.Ptr {
			t = t.Elem()
		}
		switch t.Kind() {
		case reflect.Struct:
			for i := 0; i < t.NumField(); i++ {
				f := t.Field(i)
				name := strings.Split(f.Tag.Get("json"), ",")[0]
				if name == "-" || f.PkgPath != "" {
					continue
				}
				if name == "" {
					name = f.Name
				}
				p := name
				if prefix != "" {
					p = prefix + "." + name
				}
				walk(p, f.Type)
			}
		case reflect.Slice:
			walk(prefix+"[]", t.Elem())
		case reflect.Map:
			walk(prefix+"{}", t.Elem())
		default:
			out = append(out, prefix+":"+t.Kind().String())
		}
	}
	walk("", t)
	sort.Strings(out)
	return out
}

// pinnedControlShape: kształt odpowiedzi kanału sterującego dla każdej wersji protokołu. Zmiana kształtu wymaga podniesienia
// controlProtocolVersion i dopisania tu nowej wersji (manager porównuje wersję, więc stara wersja managera nie pomyli pól).
var pinnedControlShape = map[int]string{
	1: strings.Join([]string{
		"state: active.button:string active.error:string active.id:string active.missing:bool active.name:string active.pid:int active.state:string " +
			"hub.commit:string hub.hub_log:string hub.log_dir:string hub.pid:int hub.stopping:bool hub.uptime_s:int " +
			"last_module.error:string last_module.id:string last_module.status:string " +
			"module_warnings[]:string modules[].button:string modules[].folder:string modules[].id:string modules[].log_name:string " +
			"modules[].order:int modules[].port:int protocol:int recorder.connected:bool session.from_file:bool session.known:bool " +
			"session.open:bool session.session_id:int session.state:string",
		"recorder: cameras{}:bool reason:string state:string",
		"result: error:string ok:bool reason:string",
	}, "\n"),
}

func currentControlShape() string {
	return strings.Join([]string{
		"state: " + strings.Join(jsonShape(reflect.TypeOf(controlState{})), " "),
		"recorder: " + strings.Join(jsonShape(reflect.TypeOf(controlRecorder{})), " "),
		"result: " + strings.Join(jsonShape(reflect.TypeOf(controlResult{})), " "),
	}, "\n")
}

func TestControlResponseShapeIsPinnedToProtocolVersion(t *testing.T) {
	want, ok := pinnedControlShape[controlProtocolVersion]
	if !ok {
		t.Fatalf("brak przypiętego kształtu dla controlProtocolVersion=%d; dopisz go do pinnedControlShape", controlProtocolVersion)
	}
	if got := currentControlShape(); got != want {
		t.Fatalf("kształt odpowiedzi kanału sterującego zmienił się bez podniesienia controlProtocolVersion (%d).\n"+
			"Podnieś wersję i dopisz nowy kształt do pinnedControlShape.\nobecny:\n%s\nprzypięty:\n%s", controlProtocolVersion, got, want)
	}
}

// --- otoczenie testowe ---

type controlEnv struct {
	hub  *Hub
	ctl  *controlServer
	srv  *httptest.Server
	root string
}

func newControlEnv(t *testing.T) *controlEnv {
	t.Helper()
	useRunDir(t)
	root := t.TempDir()
	mods := filepath.Join(root, "modules")
	pa, pb := freePort(t), freePort(t)
	writeManifest(t, mods, "a", fmt.Sprintf(`{"format":1,"id":"alfa","button":"ALFA","script":"a.py","port":%d,"log_name":"alfa_log","order":1}`, pa))
	writeManifest(t, mods, "b", fmt.Sprintf(`{"format":1,"id":"beta","button":"BETA","script":"b.py","port":%d,"order":2}`, pb))
	cfg := &LoadedHubConfig{HubConfig: defaultHubConfig(), Root: root}
	cfg.ModulesDir = "modules"
	cfg.Catalog = scanModuleCatalog(mods)
	h := NewHub(0, false, false)
	h.Services = newTestSM(t)
	ctl := newControlServer(h, cfg)
	ctl.recTO = 300 * time.Millisecond
	ctl.serviceFor = func(m ModuleManifest) ServiceConfig {
		c := svcCfg("module", "http", m.Port)
		c.ModuleID = m.ID
		return c
	}
	srv := httptest.NewServer(ctl.Handler()) // httptest słucha na 127.0.0.1
	t.Cleanup(srv.Close)
	return &controlEnv{hub: h, ctl: ctl, srv: srv, root: root}
}

func (e *controlEnv) get(t *testing.T, path string, out interface{}) int {
	t.Helper()
	resp, err := http.Get(e.srv.URL + path)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if out != nil {
		if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
			t.Fatal(err)
		}
	}
	return resp.StatusCode
}

func (e *controlEnv) post(t *testing.T, path, body string) (int, controlResult) {
	t.Helper()
	resp, err := http.Post(e.srv.URL+path, "application/json", strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var r controlResult
	json.NewDecoder(resp.Body).Decode(&r)
	return resp.StatusCode, r
}

func (e *controlEnv) state(t *testing.T) controlState {
	t.Helper()
	var st controlState
	if code := e.get(t, "/state", &st); code != 200 {
		t.Fatalf("/state: %d", code)
	}
	return st
}

func (e *controlEnv) session(state string) {
	e.hub.session.set(SessionStatus{State: state, Known: true, At: time.Now()})
}

// --- ochrona kanału ---

func TestControlRejectsOriginHeader(t *testing.T) {
	e := newControlEnv(t)
	for _, m := range []string{http.MethodGet, http.MethodPost} {
		path := "/state"
		if m == http.MethodPost {
			path = "/module/start"
		}
		req, _ := http.NewRequest(m, e.srv.URL+path, strings.NewReader(`{"id":"alfa"}`))
		req.Header.Set("Origin", "http://localhost:8081")
		req.Header.Set("Content-Type", "application/json")
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()
		if resp.StatusCode != http.StatusForbidden {
			t.Fatalf("%s %s z Origin: %d, oczekiwano 403", m, path, resp.StatusCode)
		}
	}
	if e.hub.Services.Has("module") {
		t.Fatal("żądanie z Origin nie może uruchomić modułu")
	}
}

func TestControlPostRequiresJSONContentType(t *testing.T) {
	e := newControlEnv(t)
	for _, ct := range []string{"", "text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x"} {
		req, _ := http.NewRequest(http.MethodPost, e.srv.URL+"/hub/stop", strings.NewReader(`{}`))
		if ct != "" {
			req.Header.Set("Content-Type", ct)
		}
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()
		if resp.StatusCode != http.StatusUnsupportedMediaType {
			t.Fatalf("Content-Type %q: %d, oczekiwano 415", ct, resp.StatusCode)
		}
	}
	select {
	case <-e.ctl.StopRequested():
		t.Fatal("POST bez application/json nie może zatrzymać HUB-a")
	default:
	}
	// z parametrem charset przechodzi kontrolę typu (dalej blokuje go nieznany status sesji)
	req, _ := http.NewRequest(http.MethodPost, e.srv.URL+"/hub/stop", strings.NewReader(`{}`))
	req.Header.Set("Content-Type", "application/json; charset=utf-8")
	resp, _ := http.DefaultClient.Do(req)
	resp.Body.Close()
	if resp.StatusCode != http.StatusConflict {
		t.Fatalf("application/json; charset=utf-8: %d, oczekiwano 409 (blokada sesji)", resp.StatusCode)
	}
}

func TestControlRejectsWrongMethodAndRemoteAddress(t *testing.T) {
	e := newControlEnv(t)
	resp, _ := http.Get(e.srv.URL + "/module/start")
	resp.Body.Close()
	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Fatalf("GET /module/start: %d", resp.StatusCode)
	}
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/state", nil)
	req.RemoteAddr = "192.168.1.50:40000"
	e.ctl.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("żądanie spoza komputera: %d, oczekiwano 403", rec.Code)
	}
}

// Serwer kanału nasłuchuje wyłącznie na 127.0.0.1, na własnym porcie (nie na porcie WebSocketu pluginów).
func TestControlListensOnlyOnLoopback(t *testing.T) {
	e := newControlEnv(t)
	port := freePort(t)
	e.ctl.Listen(port)
	waitCond(t, "kanał nasłuchuje", 2*time.Second, func() bool { return portOpen(port) })
	resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/state", port))
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != 200 {
		t.Fatalf("/state przez Listen: %d", resp.StatusCode)
	}
	addrs, _ := net.InterfaceAddrs()
	for _, a := range addrs {
		ipn, ok := a.(*net.IPNet)
		if !ok || ipn.IP.IsLoopback() || ipn.IP.To4() == nil {
			continue
		}
		c, err := net.DialTimeout("tcp", net.JoinHostPort(ipn.IP.String(), strconv.Itoa(port)), 500*time.Millisecond)
		if err == nil {
			c.Close()
			t.Fatalf("kanał odpowiada na adresie sieciowym %s, a ma tylko na 127.0.0.1", ipn.IP)
		}
	}
}

// Manager nie jest uczestnikiem HUB-a: żądania kanału nie tworzą rejestracji, połączeń oczekujących ani wpisów monitora zdrowia.
func TestControlRequestsDoNotRegisterManager(t *testing.T) {
	e := newControlEnv(t)
	for i := 0; i < 5; i++ {
		e.state(t)
	}
	e.post(t, "/module/stop", `{}`)
	e.hub.mu.RLock()
	defer e.hub.mu.RUnlock()
	if e.hub.MainModule != nil || len(e.hub.Plugins) != 0 || len(e.hub.PendingModules) != 0 {
		t.Fatalf("kanał zostawił ślad w HUB-ie: main=%v plugins=%d pending=%d", e.hub.MainModule, len(e.hub.Plugins), len(e.hub.PendingModules))
	}
}

// --- stan, start i wyłączność ---

func TestControlStateListsModulesVersionAndSession(t *testing.T) {
	e := newControlEnv(t)
	old := buildCommit
	buildCommit = "abc123-dirty"
	t.Cleanup(func() { buildCommit = old })
	st := e.state(t)
	if st.Protocol != controlProtocolVersion || st.Hub.Commit != "abc123-dirty" || st.Hub.PID != os.Getpid() {
		t.Fatalf("wersja i HUB: %+v", st.Hub)
	}
	if st.Hub.HubLog == "" || !strings.HasSuffix(st.Hub.HubLog, "hub.log") {
		t.Fatalf("ścieżka hub.log: %q", st.Hub.HubLog)
	}
	if len(st.Modules) != 2 || st.Modules[0].ID != "alfa" || st.Modules[0].Button != "ALFA" || st.Modules[1].LogName != "beta" {
		t.Fatalf("moduły: %+v", st.Modules)
	}
	if st.Active != nil || st.Session.Known || st.Recorder.Connected {
		t.Fatalf("stan początkowy: active=%+v session=%+v rec=%+v", st.Active, st.Session, st.Recorder)
	}
	e.session(sessionOnAir)
	if st = e.state(t); !st.Session.Known || !st.Session.Open || st.Session.State != sessionOnAir {
		t.Fatalf("sesja: %+v", st.Session)
	}
	// nowy folder modułu pojawia się bez restartu HUB-a, usunięty znika
	writeManifest(t, filepath.Join(e.root, "modules"), "c", `{"format":1,"id":"gamma","button":"GAMMA","script":"c.py","port":1,"order":3}`)
	if st = e.state(t); len(st.Modules) != 3 {
		t.Fatalf("nowy moduł nie pojawił się: %+v", st.Modules)
	}
	os.RemoveAll(filepath.Join(e.root, "modules", "c"))
	if st = e.state(t); len(st.Modules) != 2 {
		t.Fatalf("usunięty moduł nie zniknął: %+v", st.Modules)
	}
}

func TestControlStartIsExclusiveAndUnknownIsRefused(t *testing.T) {
	e := newControlEnv(t)
	if code, r := e.post(t, "/module/start", `{"id":"nie-ma"}`); code != http.StatusNotFound || r.Reason != "unknown_module" {
		t.Fatalf("nieznany moduł: %d %+v", code, r)
	}
	if code, r := e.post(t, "/module/start", `{}`); code != http.StatusBadRequest {
		t.Fatalf("brak id: %d %+v", code, r)
	}
	if code, r := e.post(t, "/module/start", `{"id":"alfa"}`); code != http.StatusAccepted || !r.OK {
		t.Fatalf("start alfa: %d %+v", code, r)
	}
	waitCond(t, "alfa działa", 10*time.Second, func() bool {
		a := e.state(t).Active
		return a != nil && a.ID == "alfa" && a.State == activeRunning
	})
	if code, r := e.post(t, "/module/start", `{"id":"beta"}`); code != http.StatusConflict || r.Reason != "busy" || !strings.Contains(r.Error, "ALFA") {
		t.Fatalf("drugi moduł przy działającym: %d %+v", code, r)
	}
	if code, _ := e.post(t, "/module/start", `{"id":"alfa"}`); code != http.StatusConflict {
		t.Fatalf("ten sam moduł drugi raz: %d", code)
	}
	if a := e.state(t).Active; a.ID != "alfa" {
		t.Fatalf("aktywny moduł zmienił się: %+v", a)
	}
}

func TestControlStartRefusesBusyPort(t *testing.T) {
	e := newControlEnv(t)
	m, _ := e.ctl.cfg.Catalog.Get("beta")
	ln, err := net.Listen("tcp", net.JoinHostPort("127.0.0.1", strconv.Itoa(m.Port)))
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()
	if code, r := e.post(t, "/module/start", `{"id":"beta"}`); code != http.StatusConflict || r.Reason != "port_busy" {
		t.Fatalf("zajęty port: %d %+v", code, r)
	}
	if e.hub.Services.Running("module") {
		t.Fatal("moduł nie powinien wystartować")
	}
}

// Po zatrzymaniu modułu można uruchomić inny (zmiana modułu bez restartu HUB-a).
func TestControlStopThenStartOtherModule(t *testing.T) {
	e := newControlEnv(t)
	e.session(sessionNone)
	e.post(t, "/module/start", `{"id":"alfa"}`)
	waitCond(t, "alfa działa", 10*time.Second, func() bool { a := e.state(t).Active; return a != nil && a.State == activeRunning })
	if code, r := e.post(t, "/module/stop", `{}`); code != http.StatusAccepted {
		t.Fatalf("stop: %d %+v", code, r)
	}
	waitCond(t, "alfa zatrzymany", 10*time.Second, func() bool { return e.state(t).Active == nil })
	if code, r := e.post(t, "/module/start", `{"id":"beta"}`); code != http.StatusAccepted {
		t.Fatalf("start beta po zatrzymaniu alfa: %d %+v", code, r)
	}
	waitCond(t, "beta działa", 10*time.Second, func() bool { a := e.state(t).Active; return a != nil && a.ID == "beta" && a.State == activeRunning })
	if st := e.state(t); st.LastModule.ID != "beta" {
		t.Fatalf("ostatni moduł: %+v", st.LastModule)
	}
}

// --- blokady zatrzymania ---

func TestControlModuleStopBlockedByOpenOrUnknownSession(t *testing.T) {
	e := newControlEnv(t)
	if code, r := e.post(t, "/module/stop", `{}`); code != http.StatusConflict || r.Reason != "no_module" {
		t.Fatalf("stop bez modułu: %d %+v", code, r)
	}
	e.post(t, "/module/start", `{"id":"alfa"}`)
	waitCond(t, "alfa działa", 10*time.Second, func() bool { a := e.state(t).Active; return a != nil && a.State == activeRunning })
	if code, r := e.post(t, "/module/stop", `{}`); code != http.StatusConflict || r.Reason != "session_unknown" {
		t.Fatalf("nieznany status sesji: %d %+v", code, r)
	}
	for _, s := range []string{sessionPreparation, sessionOnAir} {
		e.session(s)
		if code, r := e.post(t, "/module/stop", `{}`); code != http.StatusConflict || r.Reason != "session_open" || !strings.Contains(r.Error, "Najpierw zamknij sesję transmisji") {
			t.Fatalf("sesja %s: %d %+v", s, code, r)
		}
	}
	if !e.hub.Services.Running("module") {
		t.Fatal("moduł nie powinien zostać zatrzymany przy otwartej sesji")
	}
	e.session(sessionNone)
	if code, _ := e.post(t, "/module/stop", `{}`); code != http.StatusAccepted {
		t.Fatalf("stop przy zamkniętej sesji: %d", code)
	}
	waitCond(t, "moduł zatrzymany", 10*time.Second, func() bool { return !e.hub.Services.Running("module") })
	select {
	case <-e.ctl.StopRequested():
		t.Fatal("zatrzymanie modułu nie może zatrzymywać HUB-a")
	default:
	}
}

func TestControlHubStopGatedBySessionAndSignalsShutdown(t *testing.T) {
	e := newControlEnv(t)
	for _, s := range []string{"", sessionPreparation, sessionOnAir} {
		if s != "" {
			e.session(s)
		}
		code, r := e.post(t, "/hub/stop", `{}`)
		if code != http.StatusConflict {
			t.Fatalf("sesja %q: %d %+v", s, code, r)
		}
		select {
		case <-e.ctl.StopRequested():
			t.Fatalf("HUB nie może się zamknąć przy sesji %q", s)
		default:
		}
	}
	e.session(sessionNone)
	if code, r := e.post(t, "/hub/stop", `{}`); code != http.StatusAccepted || !r.OK {
		t.Fatalf("stop HUB-a: %d %+v", code, r)
	}
	select {
	case <-e.ctl.StopRequested():
	case <-time.After(2 * time.Second):
		t.Fatal("polecenie zatrzymania HUB-a nie dotarło do pętli głównej")
	}
	if !e.state(t).Hub.Stopping {
		t.Fatal("/state powinien zgłaszać zamykanie HUB-a")
	}
	if code, r := e.post(t, "/module/start", `{"id":"alfa"}`); code != http.StatusConflict || r.Reason != "hub_stopping" {
		t.Fatalf("start modułu w trakcie zamykania HUB-a: %d %+v", code, r)
	}
}

// --- moduł uruchomiony ręcznie i zniknięcie folderu ---

func TestControlRecognizesManualModuleByRegisteredName(t *testing.T) {
	e := newControlEnv(t)
	mm := NewModule(e.hub, nil)
	mm.ID, mm.Name, mm.ComponentType, mm.IsActive = "main-module", "alfa_log", "main_module", true
	e.hub.MainModule = mm
	a := e.state(t).Active
	if a == nil || a.State != activeManual || a.ID != "alfa" || a.Button != "ALFA" || a.PID != 0 {
		t.Fatalf("moduł ręczny: %+v", a)
	}
	if code, r := e.post(t, "/module/start", `{"id":"beta"}`); code != http.StatusConflict || r.Reason != "busy" {
		t.Fatalf("start przy module ręcznym: %d %+v", code, r)
	}
	if code, _ := e.post(t, "/module/stop", `{}`); code != http.StatusConflict {
		t.Fatal("stop modułu ręcznego przy nieznanym statusie sesji musi być zablokowany")
	}
	e.session(sessionNone)
	if code, r := e.post(t, "/module/stop", `{}`); code != http.StatusAccepted {
		t.Fatalf("stop modułu ręcznego: %d %+v", code, r)
	}
	if got := readSent(t, mm); got == nil || got.Type != "shutdown_module" {
		t.Fatalf("moduł ręczny powinien dostać shutdown_module, dostał %+v", got)
	}
	if a := e.state(t).Active; a.State != activeStopping {
		t.Fatalf("stan po prośbie o zamknięcie: %+v", a)
	}
	e.hub.mu.Lock()
	mm.IsActive = false
	e.hub.mu.Unlock()
	if a := e.state(t).Active; a != nil {
		t.Fatalf("po rozłączeniu modułu ręcznego: %+v", a)
	}
	// nazwa spoza plików module.json
	mm2 := NewModule(e.hub, nil)
	mm2.ID, mm2.Name, mm2.ComponentType, mm2.IsActive = "main-module", "hokej", "main_module", true
	e.hub.MainModule = mm2
	if a := e.state(t).Active; a == nil || a.State != activeManualUnknown || a.ID != "" || a.Name != "hokej" {
		t.Fatalf("nieznany moduł ręczny: %+v", a)
	}
	if code, _ := e.post(t, "/module/start", `{"id":"alfa"}`); code != http.StatusConflict {
		t.Fatal("start przy nieznanym module ręcznym musi być zablokowany")
	}
}

func TestControlRunningModuleWithRemovedFolderIsMissing(t *testing.T) {
	e := newControlEnv(t)
	e.post(t, "/module/start", `{"id":"alfa"}`)
	waitCond(t, "alfa działa", 10*time.Second, func() bool { a := e.state(t).Active; return a != nil && a.State == activeRunning })
	os.RemoveAll(filepath.Join(e.root, "modules", "a"))
	st := e.state(t)
	if st.Active == nil || !st.Active.Missing || st.Active.ID != "alfa" {
		t.Fatalf("moduł bez folderu: %+v", st.Active)
	}
	for _, m := range st.Modules {
		if m.ID == "alfa" {
			t.Fatal("usunięty moduł nie powinien być na liście")
		}
	}
}

// --- /recorder ---

// fakeRecorder: połączony recorder-plugin, który na recording_status odpowiada podanym ładunkiem (nil = milczy).
func fakeRecorder(t *testing.T, h *Hub, reply map[string]interface{}) {
	t.Helper()
	p := NewModule(h, nil)
	p.ID, p.ComponentType, p.IsActive = "recorder-plugin", "plugin", true
	h.mu.Lock()
	h.Plugins[p.ID] = p
	h.mu.Unlock()
	done := make(chan struct{})
	t.Cleanup(func() { close(done) })
	go func() {
		for {
			select {
			case <-done:
				return
			case data := <-p.Send:
				msg, err := FromJSON(data)
				if err != nil || msg.Type != "recording_status" || reply == nil {
					continue
				}
				resp := NewMessage(p.ID, msg.From, msg.Type+"_response", reply)
				resp.Context = msg.Context
				resp.Source = p
				h.handleMessage(resp)
			}
		}
	}()
}

func TestControlRecorderStates(t *testing.T) {
	cases := []struct {
		name     string
		reply    map[string]interface{}
		noPlugin bool
		want     string
		reason   string
	}{
		{"nagrywa", map[string]interface{}{"status": "ok", "cameras": map[string]interface{}{"camera1": false, "camera2": true}}, false, "recording", ""},
		{"nie nagrywa", map[string]interface{}{"status": "ok", "cameras": map[string]interface{}{"camera1": false, "camera2": false}}, false, "not_recording", ""},
		{"milczy", nil, false, "unknown", "brak odpowiedzi"},
		{"rozłączony", nil, true, "unknown", "nie jest połączony"},
		{"błąd", map[string]interface{}{"status": "error", "error": "awaria"}, false, "unknown", "błędem"},
		{"bez kamer", map[string]interface{}{"status": "ok"}, false, "unknown", "nieczytelna"},
		{"zła wartość", map[string]interface{}{"status": "ok", "cameras": map[string]interface{}{"camera1": "tak"}}, false, "unknown", "nieczytelna"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			e := newControlEnv(t)
			if !c.noPlugin {
				fakeRecorder(t, e.hub, c.reply)
			}
			var r controlRecorder
			if code := e.get(t, "/recorder", &r); code != 200 {
				t.Fatalf("/recorder: %d", code)
			}
			if r.State != c.want || !strings.Contains(r.Reason, c.reason) {
				t.Fatalf("oczekiwano %s (%q), jest %+v", c.want, c.reason, r)
			}
			if c.want == "recording" && !r.Cameras["camera2"] {
				t.Fatalf("lista kamer: %+v", r.Cameras)
			}
			if st := e.state(t); st.Recorder.Connected == c.noPlugin {
				t.Fatalf("recorder.connected w /state: %v", st.Recorder.Connected)
			}
		})
	}
}

// Spóźniona odpowiedź recordera (po upływie czasu) nie trafia dalej jako wiadomość do "hub" i nie psuje kolejnego pytania.
func TestControlLateRecorderReplyIsSwallowed(t *testing.T) {
	logs := captureLog(t)
	h := NewHub(0, false, false)
	late := NewMessage("recorder-plugin", "hub", "recording_status_response", map[string]interface{}{"status": "ok"})
	late.Context = map[string]interface{}{"hub_request_id": "hub-999"}
	if !h.handleHubAddressed(late) {
		t.Fatal("spóźniona odpowiedź na pytanie HUB-a powinna zostać przyjęta (i pominięta)")
	}
	if !strings.Contains(logs.String(), "Pominięto odpowiedź") {
		t.Fatalf("brak wpisu w logu: %q", logs.String())
	}
}

// --- przejęcie modułu z pliku stanu mimo --module none ---

func TestPrepareModuleAdoptionUsesModuleFromStateFile(t *testing.T) {
	e := newControlEnv(t)
	statePath := filepath.Join(t.TempDir(), "uslugi.json")
	e.hub.State = NewStateStore(statePath)
	if err := e.hub.State.Save(StateFile{Entries: []StateEntry{{ID: "module", Kind: "service", PID: 1, Module: "beta"}}}); err != nil {
		t.Fatal(err)
	}
	e.ctl.cfg.Catalog = scanModuleCatalog(filepath.Join(e.root, "modules"))
	e.hub.prepareModuleAdoption(e.ctl.cfg)
	if _, _, id, _, _, _ := e.hub.Services.Info("module"); id != "beta" {
		t.Fatalf("usługa module powinna dostać definicję modułu beta z pliku stanu, ma %q", id)
	}
	// moduł bez pliku module.json: nie przejmujemy (wpis w logu), usługa bez zmian
	logs := captureLog(t)
	e.hub.State.Save(StateFile{Entries: []StateEntry{{ID: "module", Kind: "service", PID: 1, Module: "znikniety"}}})
	e.hub.prepareModuleAdoption(e.ctl.cfg)
	if !strings.Contains(logs.String(), "nie ma pliku module.json") {
		t.Fatalf("brak wpisu o module bez pliku: %q", logs.String())
	}
	// wpis w pliku stanu niesie id modułu (zapis po starcie przez kanał)
	e.session(sessionNone)
	e.hub.State = nil
	e.post(t, "/module/start", `{"id":"alfa"}`)
	waitCond(t, "alfa działa", 10*time.Second, func() bool { return e.hub.Services.Running("module") })
	found := false
	for _, se := range e.hub.Services.StateEntries() {
		if se.ID == "module" && se.Module == "alfa" {
			found = true
		}
	}
	if !found {
		t.Fatalf("wpis pliku stanu bez id modułu: %+v", e.hub.Services.StateEntries())
	}
}
