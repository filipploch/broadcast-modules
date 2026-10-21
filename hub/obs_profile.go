package main

import (
	"fmt"
	"log"
	"strings"
	"sync"
	"time"
)

// Profil i zbiór scen OBS przypisane do modułu (E2d3c3). module.json aktywnego modułu może podać obs_profile i obs_scene_collection
// (dwa niezależne pola). HUB dba o to, by OBS używał tych nazw, w trzech sytuacjach przy starcie modułu:
//
//	(a) OBS i obs-ws-plugin już działają: przełączenie PRZED startem procesu modułu (łącznie najwyżej obsApplyBudget);
//	(b) działa tylko OBS (plugin dopiero wstaje): moduł startuje od razu, a wymaganie realizuje pętla w tle, gdy plugin się zgłosi;
//	(c) nic nie działa: OBS startuje po module i pluginie z argumentami --profile i --collection (extraArgs), a pętla w tle
//	    sprawdza po starcie (przełączenie tylko przy różnicy, a przy braku profilu lub zbioru — ostrzeżenie).
//
// Wymaganie realizowane jest RAZ na uruchomienie modułu (nie przy restarcie pluginu ani HUB-a: nie cofamy ręcznej zmiany operatora)
// i RAZ na uruchomienie procesu OBS przez HUB (argumenty). Wymaganie bierzemy zawsze z module.json aktywnego modułu.
// Przy trwającym streamie lub nagrywaniu (albo bez odpowiedzi o ich stanie) plugin niczego nie przełącza: moduł startuje z ostrzeżeniem.

const (
	obsApplyBudget = 25 * time.Second // łączny limit przełączania przed startem modułu (przypadek a)
	obsApplyWindow = 90 * time.Second // jak długo pętla w tle czeka na OBS i obs-ws-plugin po starcie modułu (przypadki b, c)
	obsApplyRetry  = 2 * time.Second

	obsProfileServiceID = "obs-profile" // identyfikator w service_status (pasek w panelu modułu)
)

// Stany realizacji wymagania.
const (
	obsProfNone     = ""        // moduł nie wymaga profilu ani zbioru scen
	obsProfPending  = "pending" // czeka na OBS lub obs-ws-plugin
	obsProfApplying = "applying"
	obsProfApplied  = "applied"
	obsProfWarning  = "warning" // moduł działa, ale OBS nie ma wymaganych ustawień (stream/nagrywanie, brak odpowiedzi, limit czasu)
	obsProfError    = "error"   // nie ma profilu lub zbioru scen w OBS albo OBS zwrócił błąd
)

type obsRequirement struct {
	ModuleID   string
	Profile    string
	Collection string
}

func (r obsRequirement) empty() bool { return r.Profile == "" && r.Collection == "" }

func (r obsRequirement) describe() string {
	var parts []string
	if r.Profile != "" {
		parts = append(parts, fmt.Sprintf("profil %q", r.Profile))
	}
	if r.Collection != "" {
		parts = append(parts, fmt.Sprintf("zbiór scen %q", r.Collection))
	}
	return strings.Join(parts, ", ")
}

// obsProfileStatus to stan realizacji wymagania dla bieżącego uruchomienia modułu.
type obsProfileStatus struct {
	mu      sync.Mutex
	gen     int // zmienia się przy każdym starcie modułu; unieważnia pętlę z poprzedniego
	req     obsRequirement
	state   string
	message string
}

type obsProfileView struct {
	ModuleID   string
	Profile    string
	Collection string
	State      string
	Message    string
}

func (s *obsProfileStatus) view() obsProfileView {
	s.mu.Lock()
	defer s.mu.Unlock()
	return obsProfileView{ModuleID: s.req.ModuleID, Profile: s.req.Profile, Collection: s.req.Collection, State: s.state, Message: s.message}
}

func (s *obsProfileStatus) set(gen int, state, message string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	if gen != s.gen {
		return false
	}
	s.state, s.message = state, message
	return true
}

// requirementFor czyta wymaganie z module.json modułu o danym id (za każdym razem z dysku).
func (h *Hub) requirementFor(moduleID string) obsRequirement {
	req := obsRequirement{ModuleID: moduleID}
	if h.catalogFn == nil || moduleID == "" {
		return req
	}
	if m, ok := h.catalogFn().Get(moduleID); ok {
		req.Profile, req.Collection = m.ObsProfile, m.ObsSceneCollection
	}
	return req
}

// obsReachable: OBS działa (uruchomiony przez HUB albo obcy).
func (h *Hub) obsReachable() bool {
	if h.Services == nil || !h.Services.Has("obs") {
		return false
	}
	st := h.Services.Status("obs")
	return st == "online" || st == "external"
}

func (h *Hub) pluginConnected(id string) bool {
	h.mu.RLock()
	defer h.mu.RUnlock()
	p, ok := h.Plugins[id]
	return ok && p.IsActive
}

// onModuleStarting jest wołane tuż przed uruchomieniem procesu modułu (start jawny albo pierwszy, nie automatyczny restart po awarii).
// Przypadek (a) blokuje start modułu najwyżej na obsApplyBudget; pozostałe zostawiają realizację pętli w tle.
func (h *Hub) onModuleStarting(moduleID string) {
	req := h.requirementFor(moduleID)
	st := &h.obsProfile
	st.mu.Lock()
	st.gen++
	gen := st.gen
	st.req = req
	st.state, st.message = obsProfNone, ""
	st.mu.Unlock()

	if req.empty() {
		h.notifyObsProfile(obsProfNone, "")
		return
	}
	log.Printf("🎛️  Moduł %s wymaga w OBS: %s", moduleID, req.describe())
	if h.obsReachable() && h.pluginConnected("obs-ws-plugin") {
		if h.tryApplyObsProfile(gen, req, h.applyBudget()) {
			return
		}
	}
	st.set(gen, obsProfPending, "OBS albo obs-ws-plugin jeszcze nie działa: "+req.describe()+" zostaną ustawione po ich uruchomieniu")
	log.Printf("ℹ️  OBS: %s zostaną ustawione po uruchomieniu OBS i obs-ws-plugin (moduł startuje bez czekania)", req.describe())
	go h.obsProfileLoop(gen, req)
}

// obsProfileLoop próbuje zrealizować wymaganie w tle, aż OBS i obs-ws-plugin będą gotowe (najwyżej obsApplyWindow).
func (h *Hub) obsProfileLoop(gen int, req obsRequirement) {
	deadline := time.Now().Add(h.applyWindow())
	for time.Now().Before(deadline) {
		time.Sleep(h.applyRetry())
		if !h.obsProfile.current(gen) || h.isShuttingDown() {
			return
		}
		if !h.obsReachable() || !h.pluginConnected("obs-ws-plugin") {
			continue
		}
		if h.tryApplyObsProfile(gen, req, h.applyBudget()) {
			return
		}
	}
	if h.obsProfile.set(gen, obsProfWarning, "nie udało się ustawić: "+req.describe()+" (OBS albo obs-ws-plugin nie odpowiedział w "+h.applyWindow().String()+")") {
		log.Printf("⚠️  OBS: nie udało się ustawić %s w %s", req.describe(), h.applyWindow())
		h.notifyObsProfile(obsProfWarning, h.obsProfile.view().Message)
	}
}

func (s *obsProfileStatus) current(gen int) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.gen == gen
}

func (h *Hub) applyBudget() time.Duration {
	if h.obsApplyBudget > 0 {
		return h.obsApplyBudget
	}
	return obsApplyBudget
}

func (h *Hub) applyWindow() time.Duration {
	if h.obsApplyWindow > 0 {
		return h.obsApplyWindow
	}
	return obsApplyWindow
}

func (h *Hub) applyRetry() time.Duration {
	if h.obsApplyRetry > 0 {
		return h.obsApplyRetry
	}
	return obsApplyRetry
}

func (h *Hub) isShuttingDown() bool {
	select {
	case <-h.shutdown:
		return true
	default:
		return false
	}
}

// tryApplyObsProfile wysyła zlecenie do obs-ws-plugin i zapisuje wynik. Zwraca true, gdy wynik jest ostateczny (nie ma po co
// ponawiać); false, gdy plugin nie jest jeszcze połączony z OBS albo nie odpowiedział (pętla w tle spróbuje ponownie).
func (h *Hub) tryApplyObsProfile(gen int, req obsRequirement, budget time.Duration) bool {
	if !h.obsProfile.set(gen, obsProfApplying, "przełączanie OBS…") {
		return true
	}
	resp, err := h.RequestPlugin("obs-ws-plugin", "obs_command", "ApplyObsProfile",
		map[string]interface{}{"profile": req.Profile, "collection": req.Collection}, budget)
	if err != nil {
		log.Printf("⚠️  OBS: przełączanie profilu nie powiodło się: %v", err)
		h.obsProfile.set(gen, obsProfPending, "przełączanie OBS nie zakończone: "+err.Error())
		if strings.Contains(err.Error(), "brak odpowiedzi") {
			// limit 25 s wyczerpany: moduł startuje z ostrzeżeniem, a pętla w tle już nie ponawia (plugin nie odpowiada)
			h.obsProfile.set(gen, obsProfWarning, "przełączanie OBS nie zakończone: obs-ws-plugin nie odpowiedział w "+budget.String())
			h.notifyObsProfile(obsProfWarning, h.obsProfile.view().Message)
			return true
		}
		return false
	}
	if resp.Type == "obs_error" {
		// najczęściej: plugin jeszcze nie jest połączony z OBS — pętla w tle ponowi
		errText, _ := resp.Payload["error"].(string)
		log.Printf("ℹ️  OBS: obs-ws-plugin nie może jeszcze przełączyć profilu: %s", errText)
		h.obsProfile.set(gen, obsProfPending, "OBS jeszcze nie odpowiada: "+errText)
		return false
	}
	data, _ := resp.Payload["responseData"].(map[string]interface{})
	state, msg := interpretApplyResult(req, data)
	if h.obsProfile.set(gen, state, msg) {
		switch state {
		case obsProfApplied:
			log.Printf("✅ OBS: %s", msg)
		case obsProfWarning:
			log.Printf("⚠️  OBS: %s", msg)
		default:
			log.Printf("❌ OBS: %s", msg)
		}
		h.notifyObsProfile(state, msg)
	}
	return true
}

// itemStatus czyta pole status z wyniku dla profilu lub zbioru scen.
func itemStatus(data map[string]interface{}, key string) (status, detail string) {
	m, _ := data[key].(map[string]interface{})
	status, _ = m["status"].(string)
	detail, _ = m["detail"].(string)
	return
}

// interpretApplyResult przekłada wynik pluginu na stan i komunikat dla operatora.
func interpretApplyResult(req obsRequirement, data map[string]interface{}) (state, message string) {
	if skipped, _ := data["skipped"].(string); skipped != "" {
		detail, _ := data["detail"].(string)
		switch skipped {
		case "active":
			return obsProfWarning, "nie przełączono OBS (trwa stream lub nagrywanie); wymagane: " + req.describe()
		default:
			return obsProfWarning, "nie przełączono OBS (stan streamu i nagrywania nieznany: " + detail + "); wymagane: " + req.describe()
		}
	}
	pst, pdet := itemStatus(data, "profile")
	cst, cdet := itemStatus(data, "collection")
	var problems []string
	level := obsProfApplied
	raise := func(l string) {
		if l == obsProfError || level == obsProfApplied {
			level = l
		}
	}
	check := func(label, wanted, st, det string) {
		switch st {
		case "missing":
			problems = append(problems, fmt.Sprintf("nie ma %s %q w OBS", label, wanted))
			raise(obsProfError)
		case "timeout":
			problems = append(problems, "przełączanie OBS nie zakończone ("+label+" "+fmt.Sprintf("%q", wanted)+")")
			raise(obsProfWarning)
		case "error":
			problems = append(problems, fmt.Sprintf("błąd OBS przy przełączaniu %s %q: %s", label, wanted, det))
			raise(obsProfError)
		}
	}
	check("profilu", req.Profile, pst, pdet)
	check("zbioru scen", req.Collection, cst, cdet)
	if len(problems) > 0 {
		return level, strings.Join(problems, "; ")
	}
	return obsProfApplied, "OBS ustawiony: " + req.describe()
}

// notifyObsProfile przekazuje modułowi stan (pasek w panelu): ostrzeżenie żółte, błąd czerwony, "applied" zdejmuje poprzedni komunikat.
func (h *Hub) notifyObsProfile(state, msg string) {
	switch state {
	case obsProfWarning:
		h.notifyService(obsProfileServiceID, "warning", msg)
	case obsProfError:
		h.notifyService(obsProfileServiceID, "error", msg)
	default:
		h.notifyService(obsProfileServiceID, "recovered", "")
	}
}

// replayObsProfileNotice: moduł połączył się z HUB-em po przełączeniu (przypadek a) — dostaje bieżące ostrzeżenie.
func (h *Hub) replayObsProfileNotice() {
	v := h.obsProfile.view()
	if v.State == obsProfWarning || v.State == obsProfError {
		h.notifyObsProfile(v.State, v.Message)
	}
}

// obsLaunchArgs: argumenty OBS uruchamianego przez HUB z wymaganiem aktywnego modułu (przypadek c i każdy restart procesu OBS).
// Moduł bierzemy z usługi "module" (id z module.json), nie z pamięci o poprzednim uruchomieniu.
func (h *Hub) obsLaunchArgs() []string {
	if h.Services == nil {
		return nil
	}
	status, _, modID, _, _, _ := h.Services.Info("module")
	if status != "starting" && status != "online" {
		return nil // moduł nie działa: nie ma aktywnego modułu, którego wymaganie mielibyśmy spełniać
	}
	req := h.requirementFor(modID)
	var args []string
	if req.Profile != "" {
		args = append(args, "--profile", req.Profile)
	}
	if req.Collection != "" {
		args = append(args, "--collection", req.Collection)
	}
	if len(args) > 0 {
		log.Printf("🎛️  OBS zostanie uruchomiony z: %s (wymaganie modułu %s)", strings.Join(args, " "), modID)
	}
	return args
}
