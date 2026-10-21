package main

import (
	"fmt"
	"log"
	"time"

	"obs-ws-plugin/internal/hub"
)

// Przełączanie profilu i zbioru scen OBS (E2d3c3). HUB zleca ApplyObsProfile z nazwami z module.json aktywnego modułu; plugin sprawdza
// stan wyjść, istnienie profilu i zbioru, przełącza tylko to, co się różni (dokładne porównanie nazw), czeka na skutek i odpowiada
// strukturą z wynikiem dla każdej z dwóch rzeczy osobno.

const requestApplyObsProfile = "ApplyObsProfile"

// Wyniki dla profilu i dla zbioru scen.
const (
	profNone      = "none"      // nie wymagane (puste pole w module.json)
	profUnchanged = "unchanged" // już ustawione
	profSwitched  = "switched"  // przełączone
	profMissing   = "missing"   // nie ma takiego profilu / zbioru scen w OBS
	profTimeout   = "timeout"   // przełączenie nie zakończyło się w limicie czasu
	profError     = "error"     // OBS zwrócił błąd
	profSkipped   = "skipped"   // nie próbowano (trwa stream/nagrywanie albo stan wyjść nieznany)
)

// obsRequester to to, czego potrzebuje przełączanie od klienta OBS (w testach: atrapa).
type obsRequester interface {
	SendRequest(requestType string, requestData map[string]interface{}) (map[string]interface{}, error)
}

type applyOptions struct {
	poll              time.Duration // odstęp między sprawdzeniami, czy przełączenie się udało
	profileTimeout    time.Duration
	collectionTimeout time.Duration
}

func defaultApplyOptions() applyOptions {
	return applyOptions{poll: 300 * time.Millisecond, profileTimeout: 8 * time.Second, collectionTimeout: 15 * time.Second}
}

// switchSpec opisuje jedną z dwóch rzeczy do przełączenia.
type switchSpec struct {
	label        string // do logu
	listRequest  string
	listKey      string // pole z listą nazw w odpowiedzi
	currentKey   string // pole z nazwą bieżącą
	setRequest   string
	setKey       string // pole z nazwą w żądaniu ustawienia
}

var (
	profileSpec = switchSpec{label: "profil", listRequest: "GetProfileList", listKey: "profiles", currentKey: "currentProfileName",
		setRequest: "SetCurrentProfile", setKey: "profileName"}
	collectionSpec = switchSpec{label: "zbiór scen", listRequest: "GetSceneCollectionList", listKey: "sceneCollections",
		currentKey: "currentSceneCollectionName", setRequest: "SetCurrentSceneCollection", setKey: "sceneCollectionName"}
)

func itemResult(wanted, current, status, detail string) map[string]interface{} {
	r := map[string]interface{}{"wanted": wanted, "current": current, "status": status}
	if detail != "" {
		r["detail"] = detail
	}
	return r
}

// readList pyta OBS o listę i bieżącą nazwę.
func readList(api obsRequester, spec switchSpec) (names []string, current string, err error) {
	resp, err := api.SendRequest(spec.listRequest, nil)
	if err != nil {
		return nil, "", err
	}
	if raw, ok := resp[spec.listKey].([]interface{}); ok {
		for _, v := range raw {
			if s, ok := v.(string); ok {
				names = append(names, s)
			}
		}
	}
	current, _ = resp[spec.currentKey].(string)
	return names, current, nil
}

func contains(list []string, name string) bool {
	for _, n := range list {
		if n == name {
			return true
		}
	}
	return false
}

// switchOne przełącza jedną rzecz (profil albo zbiór scen), jeśli się różni od wymaganej.
func switchOne(api obsRequester, spec switchSpec, wanted string, timeout time.Duration, poll time.Duration) map[string]interface{} {
	if wanted == "" {
		return itemResult("", "", profNone, "")
	}
	names, current, err := readList(api, spec)
	if err != nil {
		return itemResult(wanted, "", profError, err.Error())
	}
	if !contains(names, wanted) {
		return itemResult(wanted, current, profMissing, fmt.Sprintf("nie ma %s %q w OBS", spec.label, wanted))
	}
	if current == wanted {
		return itemResult(wanted, current, profUnchanged, "")
	}
	log.Printf("🔀 Przełączam %s OBS: %q → %q", spec.label, current, wanted)
	if _, err := api.SendRequest(spec.setRequest, map[string]interface{}{spec.setKey: wanted}); err != nil {
		return itemResult(wanted, current, profError, err.Error())
	}
	deadline := time.Now().Add(timeout)
	for {
		_, now, err := readList(api, spec) // żądanie czeka za bramką, jeśli OBS jeszcze zmienia zbiór scen
		if err == nil && now == wanted {
			return itemResult(wanted, now, profSwitched, "")
		}
		if time.Now().After(deadline) {
			detail := "przełączenie nie zakończyło się w limicie czasu"
			if err != nil {
				detail += ": " + err.Error()
			}
			return itemResult(wanted, now, profTimeout, detail)
		}
		time.Sleep(poll)
	}
}

// applyProfile wykonuje całe zlecenie. Zwraca zawsze strukturę (błąd pojedynczej rzeczy nie przerywa drugiej).
// Przy trwającym streamie lub nagrywaniu — albo gdy nie da się tego ustalić — niczego nie przełącza (zmiana zbioru scen na antenie
// zepsułaby transmisję).
func applyProfile(api obsRequester, wantProfile, wantCollection string, opt applyOptions) map[string]interface{} {
	res := map[string]interface{}{}
	for _, rt := range []string{"GetStreamStatus", "GetRecordStatus"} {
		resp, err := api.SendRequest(rt, nil)
		if err != nil {
			res["skipped"] = "unknown"
			res["detail"] = fmt.Sprintf("nie udało się ustalić stanu wyjść OBS (%s): %v", rt, err)
			res["profile"] = itemResult(wantProfile, "", profSkipped, "")
			res["collection"] = itemResult(wantCollection, "", profSkipped, "")
			return res
		}
		if active, _ := resp["outputActive"].(bool); active {
			res["skipped"] = "active"
			res["detail"] = "trwa stream lub nagrywanie w OBS"
			res["profile"] = itemResult(wantProfile, "", profSkipped, "")
			res["collection"] = itemResult(wantCollection, "", profSkipped, "")
			return res
		}
	}
	res["skipped"] = ""
	res["profile"] = switchOne(api, profileSpec, wantProfile, opt.profileTimeout, opt.poll)
	res["collection"] = switchOne(api, collectionSpec, wantCollection, opt.collectionTimeout, opt.poll)
	return res
}

// handleApplyObsProfile obsługuje zlecenie z HUB-a i odpowiada obs_response (z requestID, jak inne polecenia obs_command).
func (p *Plugin) handleApplyObsProfile(msg *hub.Message) {
	requestID := msg.Payload["request_id"]
	if !p.obsClient.IsConnected() {
		p.hubClient.Send(&hub.Message{From: p.config.Plugin.ID, To: msg.From, Context: msg.Context, Type: "obs_error",
			Payload: map[string]interface{}{"error": "OBS not connected", "command": msg.Payload, "requestType": requestApplyObsProfile}})
		return
	}
	var data map[string]interface{}
	if rd, ok := msg.Payload["requestData"].(map[string]interface{}); ok {
		data = rd
	}
	profile, _ := data["profile"].(string)
	collection, _ := data["collection"].(string)
	result := applyProfile(p.obsClient, profile, collection, defaultApplyOptions())
	log.Printf("🔀 ApplyObsProfile(profil=%q, zbiór=%q): %v", profile, collection, result)
	p.hubClient.Send(&hub.Message{From: p.config.Plugin.ID, To: msg.From, Context: msg.Context, Type: "obs_response",
		Payload: map[string]interface{}{"requestType": requestApplyObsProfile, "requestID": requestID, "responseData": result}})
}
