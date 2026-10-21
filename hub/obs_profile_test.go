package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

// Profil i zbiór scen OBS przypisane do modułu (E2d3c3): trzy sytuacje startu, limity, ostrzeżenia, argumenty OBS.

type applyCall struct{ profile, collection string }

// scriptedObsPlugin udaje obs-ws-plugin: na ApplyObsProfile odpowiada według skryptu.
type scriptedObsPlugin struct {
	mu      sync.Mutex
	calls   []applyCall
	script  func(call int, c applyCall) *Message // nil = brak odpowiedzi
	stop    chan struct{}
	module  *Module
	replyID string
}

func (p *scriptedObsPlugin) callCount() int {
	p.mu.Lock()
	defer p.mu.Unlock()
	return len(p.calls)
}

func (p *scriptedObsPlugin) lastCall() applyCall {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.calls[len(p.calls)-1]
}

func attachScriptedObsPlugin(t *testing.T, hub *Hub, script func(call int, c applyCall) *Message) *scriptedObsPlugin {
	t.Helper()
	p := &scriptedObsPlugin{script: script, stop: make(chan struct{})}
	m := NewModule(hub, nil)
	m.ID = "obs-ws-plugin"
	m.IsActive = true
	p.module = m
	hub.mu.Lock()
	hub.Plugins["obs-ws-plugin"] = m
	hub.mu.Unlock()
	t.Cleanup(func() { close(p.stop) })
	go func() {
		for {
			select {
			case <-p.stop:
				return
			case data := <-m.Send:
				msg, err := FromJSON(data)
				if err != nil {
					continue
				}
				rt, _ := msg.Payload["requestType"].(string)
				if rt != "ApplyObsProfile" {
					continue
				}
				rd, _ := msg.Payload["requestData"].(map[string]interface{})
				c := applyCall{}
				c.profile, _ = rd["profile"].(string)
				c.collection, _ = rd["collection"].(string)
				p.mu.Lock()
				p.calls = append(p.calls, c)
				n := len(p.calls)
				p.mu.Unlock()
				reply := p.script(n, c)
				if reply == nil {
					continue
				}
				if reply.Type == "obs_response" {
					reply.Payload["requestID"] = msg.Payload["request_id"]
					reply.Payload["requestType"] = rt
				} else {
					reply.Payload["command"] = msg.Payload // jak prawdziwy plugin: identyfikator pytania w "command"
				}
				hub.handleMessage(reply)
			}
		}
	}()
	return p
}

func applyReply(profile, collection, skipped string) *Message {
	data := map[string]interface{}{
		"skipped":    skipped,
		"profile":    map[string]interface{}{"status": profile},
		"collection": map[string]interface{}{"status": collection},
	}
	if skipped != "" {
		data["detail"] = "szczegóły"
	}
	return NewMessage("obs-ws-plugin", "hub", "obs_response", map[string]interface{}{"responseData": data})
}

func obsNotConnectedReply() *Message {
	return NewMessage("obs-ws-plugin", "hub", "obs_error", map[string]interface{}{"error": "OBS not connected",
		"requestType": "ApplyObsProfile"})
}

// profRig to HUB z katalogiem modułów, usługami "obs" i "module" oraz zapisem powiadomień wysłanych do modułu głównego.
type profRig struct {
	hub  *Hub
	mods string
	main *Module
}

func newProfRig(t *testing.T, manifests map[string]string) *profRig {
	t.Helper()
	useRunDir(t)
	mods := t.TempDir()
	for folder, body := range manifests {
		writeManifest(t, mods, folder, body)
	}
	hub := NewHub(0, false, false)
	hub.Services = newTestSM(t)
	hub.catalogFn = func() *ModuleCatalog { return scanModuleCatalog(mods) }
	hub.obsApplyBudget = 600 * time.Millisecond
	hub.obsApplyWindow = 3 * time.Second
	hub.obsApplyRetry = 30 * time.Millisecond
	main := NewModule(hub, nil)
	main.ID = "main-module"
	main.IsActive = true
	hub.mu.Lock()
	hub.MainModule = main
	hub.mu.Unlock()
	return &profRig{hub: hub, mods: mods, main: main}
}

func (r *profRig) setService(t *testing.T, id, status, moduleID string) {
	t.Helper()
	sm := r.hub.Services
	if !sm.Has(id) {
		cfg := svcCfg(id, "sleep", 0)
		cfg.ModuleID = moduleID
		if err := sm.Add(cfg); err != nil {
			t.Fatal(err)
		}
	}
	sm.mu.Lock()
	sm.services[id].cfg.ModuleID = moduleID
	sm.services[id].status = status
	sm.mu.Unlock()
}

func (r *profRig) setObsStatus(status string) {
	sm := r.hub.Services
	sm.mu.Lock()
	sm.services["obs"].status = status
	sm.mu.Unlock()
}

// notices zbiera service_status wysłane do modułu głównego.
func (r *profRig) notices() []map[string]interface{} {
	var out []map[string]interface{}
	for {
		select {
		case data := <-r.main.Send:
			msg, err := FromJSON(data)
			if err == nil && msg.Type == "service_status" {
				out = append(out, msg.Payload)
			}
		default:
			return out
		}
	}
}

const nalfManifest = `{"format":1,"id":"nalf","button":"NALF","script":"n.py","port":1,"obs_profile":"NALF","obs_scene_collection":"NALF"}`
const garbManifest = `{"format":1,"id":"garbarnia","button":"GARB","script":"g.py","port":2,"obs_profile":"Garbarnia","obs_scene_collection":"Garbarnia"}`
const plainManifest = `{"format":1,"id":"plain","button":"PLAIN","script":"p.py","port":3}`

func waitView(t *testing.T, h *Hub, state string) obsProfileView {
	t.Helper()
	var v obsProfileView
	waitCond(t, "stan "+state, 5*time.Second, func() bool { v = h.obsProfile.view(); return v.State == state })
	return v
}

func TestManifestCarriesTwoIndependentObsFields(t *testing.T) {
	root := t.TempDir()
	writeManifest(t, root, "a", `{"format":1,"id":"alfa","button":"A","script":"a.py","port":1,"obs_profile":"Liga Żółtych Kaczek","obs_scene_collection":"Zbiór — wiosna"}`)
	writeManifest(t, root, "b", `{"format":1,"id":"beta","button":"B","script":"b.py","port":2,"obs_profile":"Tylko profil"}`)
	cat := scanModuleCatalog(root)
	a, _ := cat.Get("alfa")
	b, _ := cat.Get("beta")
	if a.ObsProfile != "Liga Żółtych Kaczek" || a.ObsSceneCollection != "Zbiór — wiosna" {
		t.Fatalf("alfa: %+v", a)
	}
	if b.ObsProfile != "Tylko profil" || b.ObsSceneCollection != "" {
		t.Fatalf("pola są niezależne: %+v", b)
	}
}

// (a) OBS i obs-ws-plugin działają: przełączenie PRZED startem modułu.
func TestCaseA_ObsAndPluginRunningSwitchesBeforeModuleStarts(t *testing.T) {
	r := newProfRig(t, map[string]string{"n": nalfManifest})
	r.setService(t, "obs", "online", "")
	plugin := attachScriptedObsPlugin(t, r.hub, func(int, applyCall) *Message { return applyReply("switched", "switched", "") })

	r.hub.onModuleStarting("nalf") // wraca dopiero po odpowiedzi pluginu
	if got := plugin.callCount(); got != 1 {
		t.Fatalf("plugin dostał %d zleceń, oczekiwano 1", got)
	}
	if c := plugin.lastCall(); c.profile != "NALF" || c.collection != "NALF" {
		t.Fatalf("zlecenie: %+v", c)
	}
	v := r.hub.obsProfile.view()
	if v.State != obsProfApplied {
		t.Fatalf("stan po przełączeniu: %+v", v)
	}
}

func TestCaseA_ExternalObsCountsAsRunning(t *testing.T) {
	r := newProfRig(t, map[string]string{"g": garbManifest})
	r.setService(t, "obs", "external", "")
	plugin := attachScriptedObsPlugin(t, r.hub, func(int, applyCall) *Message { return applyReply("unchanged", "unchanged", "") })
	r.hub.onModuleStarting("garbarnia")
	if plugin.callCount() != 1 || plugin.lastCall().profile != "Garbarnia" {
		t.Fatalf("obcy OBS także jest przełączany: %+v", plugin.calls)
	}
}

func TestModuleWithoutObsFieldsDoesNothing(t *testing.T) {
	r := newProfRig(t, map[string]string{"p": plainManifest})
	r.setService(t, "obs", "online", "")
	plugin := attachScriptedObsPlugin(t, r.hub, func(int, applyCall) *Message { return applyReply("switched", "switched", "") })
	r.hub.onModuleStarting("plain")
	time.Sleep(100 * time.Millisecond)
	if plugin.callCount() != 0 {
		t.Fatal("moduł bez wymagań nie powinien nic zlecać")
	}
	if v := r.hub.obsProfile.view(); v.State != obsProfNone {
		t.Fatalf("%+v", v)
	}
}

// (b) działa tylko OBS: moduł startuje od razu, wymaganie realizuje pętla, gdy plugin się zgłosi (późne połączenie).
func TestCaseB_OnlyObsRunningModuleStartsAtOnceAndLateConnectionApplies(t *testing.T) {
	r := newProfRig(t, map[string]string{"n": nalfManifest})
	r.setService(t, "obs", "online", "")

	started := time.Now()
	r.hub.onModuleStarting("nalf")
	if time.Since(started) > 300*time.Millisecond {
		t.Fatal("start modułu nie może czekać na plugin, którego nie ma")
	}
	if v := r.hub.obsProfile.view(); v.State != obsProfPending {
		t.Fatalf("oczekiwano pending: %+v", v)
	}
	plugin := attachScriptedObsPlugin(t, r.hub, func(int, applyCall) *Message { return applyReply("switched", "unchanged", "") })
	waitView(t, r.hub, obsProfApplied)
	if plugin.callCount() != 1 {
		t.Fatalf("zleceń: %d", plugin.callCount())
	}
}

// (c) nic nie działa: OBS startuje później (z argumentami), a pętla sprawdza po starcie.
func TestCaseC_NothingRunningThenObsAndPluginAppearAndAreVerified(t *testing.T) {
	r := newProfRig(t, map[string]string{"n": nalfManifest})
	r.setService(t, "obs", "stopped", "")
	r.hub.onModuleStarting("nalf")
	if v := r.hub.obsProfile.view(); v.State != obsProfPending {
		t.Fatalf("%+v", v)
	}
	plugin := attachScriptedObsPlugin(t, r.hub, func(int, applyCall) *Message { return applyReply("unchanged", "unchanged", "") })
	time.Sleep(150 * time.Millisecond)
	if plugin.callCount() != 0 {
		t.Fatal("dopóki OBS nie działa, plugin nie dostaje zlecenia")
	}
	r.setObsStatus("online")
	waitView(t, r.hub, obsProfApplied)
}

func TestPluginNotYetConnectedToObsIsRetriedUntilItWorks(t *testing.T) {
	r := newProfRig(t, map[string]string{"n": nalfManifest})
	r.setService(t, "obs", "online", "")
	plugin := attachScriptedObsPlugin(t, r.hub, func(n int, c applyCall) *Message {
		if n < 3 {
			return obsNotConnectedReply()
		}
		return applyReply("switched", "switched", "")
	})
	r.hub.onModuleStarting("nalf") // pierwsza próba: obs_error → moduł startuje, pętla ponawia
	waitView(t, r.hub, obsProfApplied)
	if plugin.callCount() != 3 {
		t.Fatalf("zleceń: %d, oczekiwano 3", plugin.callCount())
	}
}

// Wymaganie realizowane raz na uruchomienie modułu: ponowne zgłoszenie pluginu niczego nie cofa.
func TestRequirementIsAppliedOncePerModuleStart(t *testing.T) {
	r := newProfRig(t, map[string]string{"n": nalfManifest})
	r.setService(t, "obs", "online", "")
	plugin := attachScriptedObsPlugin(t, r.hub, func(int, applyCall) *Message { return applyReply("switched", "switched", "") })
	r.hub.onModuleStarting("nalf")
	// restart pluginu: rejestracja pod tym samym id
	r.hub.registerPlugin(plugin.module)
	r.hub.replayObsProfileNotice()
	time.Sleep(200 * time.Millisecond)
	if plugin.callCount() != 1 {
		t.Fatalf("restart pluginu nie może ponawiać zlecenia (ręczna zmiana operatora): %d", plugin.callCount())
	}
}

func TestNewModuleStartCancelsPendingLoopOfPreviousOne(t *testing.T) {
	r := newProfRig(t, map[string]string{"n": nalfManifest, "g": garbManifest})
	r.setService(t, "obs", "stopped", "")
	r.hub.onModuleStarting("nalf") // pętla czeka na OBS
	r.hub.onModuleStarting("garbarnia")
	plugin := attachScriptedObsPlugin(t, r.hub, func(int, applyCall) *Message { return applyReply("switched", "switched", "") })
	r.setObsStatus("online")
	waitView(t, r.hub, obsProfApplied)
	time.Sleep(150 * time.Millisecond)
	if plugin.callCount() != 1 || plugin.lastCall().profile != "Garbarnia" {
		t.Fatalf("zlecenie ma dotyczyć tylko ostatniego modułu: %+v", plugin.calls)
	}
}

// Ostrzeżenia.
func TestStreamingMeansNoSwitchAndYellowWarning(t *testing.T) {
	r := newProfRig(t, map[string]string{"n": nalfManifest})
	r.setService(t, "obs", "online", "")
	attachScriptedObsPlugin(t, r.hub, func(int, applyCall) *Message { return applyReply("skipped", "skipped", "active") })
	r.hub.onModuleStarting("nalf")
	v := r.hub.obsProfile.view()
	if v.State != obsProfWarning || !strings.Contains(v.Message, "stream") {
		t.Fatalf("%+v", v)
	}
	got := r.notices()
	if len(got) == 0 || got[len(got)-1]["kind"] != "warning" || got[len(got)-1]["service_id"] != "obs-profile" {
		t.Fatalf("moduł dostaje żółte ostrzeżenie: %v", got)
	}
}

func TestNoAnswerAboutOutputsIsYellowWarningToo(t *testing.T) {
	r := newProfRig(t, map[string]string{"n": nalfManifest})
	r.setService(t, "obs", "online", "")
	attachScriptedObsPlugin(t, r.hub, func(int, applyCall) *Message { return applyReply("skipped", "skipped", "unknown") })
	r.hub.onModuleStarting("nalf")
	v := r.hub.obsProfile.view()
	if v.State != obsProfWarning || !strings.Contains(v.Message, "nieznany") {
		t.Fatalf("%+v", v)
	}
}

func TestMissingProfileIsRedAndNamesTheProfile(t *testing.T) {
	r := newProfRig(t, map[string]string{"n": nalfManifest})
	r.setService(t, "obs", "online", "")
	attachScriptedObsPlugin(t, r.hub, func(int, applyCall) *Message { return applyReply("missing", "switched", "") })
	r.hub.onModuleStarting("nalf")
	v := r.hub.obsProfile.view()
	if v.State != obsProfError || !strings.Contains(v.Message, `nie ma profilu "NALF" w OBS`) || strings.Contains(v.Message, "zbioru") {
		t.Fatalf("%+v", v)
	}
	if got := r.notices(); len(got) == 0 || got[len(got)-1]["kind"] != "error" {
		t.Fatalf("czerwone ostrzeżenie dla modułu: %v", got)
	}
}

func TestMissingCollectionIsReportedSeparately(t *testing.T) {
	r := newProfRig(t, map[string]string{"g": garbManifest})
	r.setService(t, "obs", "online", "")
	attachScriptedObsPlugin(t, r.hub, func(int, applyCall) *Message { return applyReply("switched", "missing", "") })
	r.hub.onModuleStarting("garbarnia")
	v := r.hub.obsProfile.view()
	if v.State != obsProfError || !strings.Contains(v.Message, `nie ma zbioru scen "Garbarnia" w OBS`) || strings.Contains(v.Message, "profilu") {
		t.Fatalf("%+v", v)
	}
}

func TestBothMissingListsBoth(t *testing.T) {
	r := newProfRig(t, map[string]string{"n": nalfManifest})
	r.setService(t, "obs", "online", "")
	attachScriptedObsPlugin(t, r.hub, func(int, applyCall) *Message { return applyReply("missing", "missing", "") })
	r.hub.onModuleStarting("nalf")
	v := r.hub.obsProfile.view()
	if !strings.Contains(v.Message, "profilu") || !strings.Contains(v.Message, "zbioru scen") {
		t.Fatalf("%+v", v)
	}
}

// Limit czasu: plugin nie odpowiada → moduł startuje z ostrzeżeniem po budżecie (25 s w produkcji, tu skrócone).
func TestBudgetExhaustedModuleStartsWithWarning(t *testing.T) {
	r := newProfRig(t, map[string]string{"n": nalfManifest})
	r.setService(t, "obs", "online", "")
	attachScriptedObsPlugin(t, r.hub, func(int, applyCall) *Message { return nil }) // milczy
	started := time.Now()
	r.hub.onModuleStarting("nalf")
	if d := time.Since(started); d < 500*time.Millisecond || d > 3*time.Second {
		t.Fatalf("czekanie ma trwać około budżetu (600 ms), trwało %v", d)
	}
	v := r.hub.obsProfile.view()
	if v.State != obsProfWarning || !strings.Contains(v.Message, "przełączanie OBS nie zakończone") {
		t.Fatalf("%+v", v)
	}
}

func TestSwitchTimeoutInsidePluginIsYellowWarning(t *testing.T) {
	r := newProfRig(t, map[string]string{"n": nalfManifest})
	r.setService(t, "obs", "online", "")
	attachScriptedObsPlugin(t, r.hub, func(int, applyCall) *Message { return applyReply("switched", "timeout", "") })
	r.hub.onModuleStarting("nalf")
	v := r.hub.obsProfile.view()
	if v.State != obsProfWarning || !strings.Contains(v.Message, "nie zakończone") {
		t.Fatalf("%+v", v)
	}
}

func TestLoopGivesUpAfterWindowWithWarning(t *testing.T) {
	r := newProfRig(t, map[string]string{"n": nalfManifest})
	r.setService(t, "obs", "stopped", "")
	r.hub.obsApplyWindow = 250 * time.Millisecond
	r.hub.onModuleStarting("nalf")
	waitView(t, r.hub, obsProfWarning)
	if got := r.hub.obsProfile.view().Message; !strings.Contains(got, "nie udało się ustawić") {
		t.Fatalf("%q", got)
	}
}

func TestWarningIsReplayedToModuleThatRegistersLater(t *testing.T) {
	r := newProfRig(t, map[string]string{"n": nalfManifest})
	r.setService(t, "obs", "online", "")
	attachScriptedObsPlugin(t, r.hub, func(int, applyCall) *Message { return applyReply("missing", "unchanged", "") })
	r.hub.mu.Lock()
	r.hub.MainModule = nil // moduł jeszcze nie wystartował
	r.hub.mu.Unlock()
	r.hub.onModuleStarting("nalf")
	r.hub.mu.Lock()
	r.hub.MainModule = r.main
	r.hub.mu.Unlock()
	r.hub.replayObsProfileNotice()
	got := r.notices()
	if len(got) != 1 || got[0]["kind"] != "error" {
		t.Fatalf("po rejestracji moduł dostaje czerwone ostrzeżenie: %v", got)
	}
}

// Argumenty OBS uruchamianego przez HUB.
func TestObsLaunchArgsFromActiveModuleWithQuotedNames(t *testing.T) {
	r := newProfRig(t, map[string]string{"x": `{"format":1,"id":"liga","button":"L","script":"l.py","port":9,"obs_profile":"Liga Żółtych Kaczek","obs_scene_collection":"Zbiór scen — \"wiosna\""}`})
	r.setService(t, "module", "online", "liga")
	args := r.hub.obsLaunchArgs()
	want := []string{"--profile", "Liga Żółtych Kaczek", "--collection", `Zbiór scen — "wiosna"`}
	if fmt.Sprint(args) != fmt.Sprint(want) {
		t.Fatalf("argumenty %q, oczekiwano %q", args, want)
	}
}

func TestObsLaunchArgsOnlyForRunningModuleWithRequirements(t *testing.T) {
	r := newProfRig(t, map[string]string{"n": nalfManifest, "p": plainManifest})
	if len(r.hub.obsLaunchArgs()) != 0 {
		t.Fatal("bez usługi modułu brak argumentów")
	}
	r.setService(t, "module", "stopped", "nalf")
	if len(r.hub.obsLaunchArgs()) != 0 {
		t.Fatal("moduł zatrzymany: brak aktywnego modułu, brak argumentów")
	}
	r.setService(t, "module", "online", "plain")
	if len(r.hub.obsLaunchArgs()) != 0 {
		t.Fatal("moduł bez wymagań: brak argumentów")
	}
}

func TestObsLaunchArgsOnlyProfileOrOnlyCollection(t *testing.T) {
	r := newProfRig(t, map[string]string{"x": `{"format":1,"id":"p","button":"P","script":"p.py","port":9,"obs_profile":"Tylko"}`})
	r.setService(t, "module", "online", "p")
	if got := fmt.Sprint(r.hub.obsLaunchArgs()); got != "[--profile Tylko]" {
		t.Fatalf("%s", got)
	}
}

// Hak w ServiceManager: argumenty dodawane przy starcie procesu, hak preStart nie dotyczy automatycznych restartów.
func TestServiceManagerAppliesExtraArgsAndPreStartHook(t *testing.T) {
	useRunDir(t)
	dump := filepath.Join(t.TempDir(), "args.txt")
	port := freePort(t)
	sm := newTestSM(t)
	cfg := svcCfg("obs", "http", port, "HELPER_ARGS_FILE="+dump)
	cfg.Args = append(cfg.Args, "--") // binarz testowy: po "--" dodatkowe argumenty nie są flagami
	if err := sm.Add(cfg); err != nil {
		t.Fatal(err)
	}
	var hooks []string
	sm.preStart = func(id string, c ServiceConfig) { hooks = append(hooks, id) }
	sm.extraArgs = func(id string) []string { return []string{"--profile", "Liga Żółtych Kaczek", "--collection", "NALF"} }
	if err := sm.Start("obs"); err != nil {
		t.Fatal(err)
	}
	waitCond(t, "plik z argumentami", 10*time.Second, func() bool { _, err := os.Stat(dump); return err == nil })
	data, _ := os.ReadFile(dump)
	args := strings.Split(string(data), "\x00")
	n := len(args)
	if n < 4 || args[n-4] != "--profile" || args[n-3] != "Liga Żółtych Kaczek" || args[n-2] != "--collection" || args[n-1] != "NALF" {
		t.Fatalf("argumenty procesu: %q", args)
	}
	if args[0] != "-test.run=TestServiceHelper" {
		t.Fatalf("dotychczasowe argumenty zostają przed dodatkowymi: %q", args)
	}
	if len(hooks) != 1 || hooks[0] != "obs" {
		t.Fatalf("preStart: %v", hooks)
	}
}
