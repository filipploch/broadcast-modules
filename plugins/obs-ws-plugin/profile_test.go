package main

import (
	"fmt"
	"sync"
	"testing"
	"time"
)

// fakeOBS udaje OBS: profile, zbiory scen, stan wyjść. Przełączenie można opóźnić (switchDelay) albo uniemożliwić (neverSwitch).
type fakeOBS struct {
	mu            sync.Mutex
	profiles      []string
	profile       string
	collections   []string
	collection    string
	streaming     bool
	recording     bool
	failRequest   map[string]bool
	neverSwitch   map[string]bool
	switchAfter   map[string]int // po ilu kolejnych odczytach listy przełączenie jest widoczne
	pendingSwitch map[string]*pendingSw
	calls         []string
}

type pendingSw struct {
	target string
	reads  int
}

func newFakeOBS() *fakeOBS {
	return &fakeOBS{
		profiles: []string{"NALF", "Garbarnia", "Bez nazwy"}, profile: "Bez nazwy",
		collections: []string{"NALF", "Garbarnia"}, collection: "Garbarnia",
		failRequest: map[string]bool{}, neverSwitch: map[string]bool{}, switchAfter: map[string]int{}, pendingSwitch: map[string]*pendingSw{},
	}
}

func (f *fakeOBS) SendRequest(rt string, data map[string]interface{}) (map[string]interface{}, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls = append(f.calls, rt)
	if f.failRequest[rt] {
		return nil, fmt.Errorf("OBS error: %s", rt)
	}
	list := func(names []string) []interface{} {
		out := make([]interface{}, len(names))
		for i, n := range names {
			out[i] = n
		}
		return out
	}
	settle := func(kind string, cur *string) {
		if p := f.pendingSwitch[kind]; p != nil {
			p.reads--
			if p.reads <= 0 && !f.neverSwitch[kind] {
				*cur = p.target
				delete(f.pendingSwitch, kind)
			}
		}
	}
	switch rt {
	case "GetStreamStatus":
		return map[string]interface{}{"outputActive": f.streaming}, nil
	case "GetRecordStatus":
		return map[string]interface{}{"outputActive": f.recording}, nil
	case "GetProfileList":
		settle("profile", &f.profile)
		return map[string]interface{}{"profiles": list(f.profiles), "currentProfileName": f.profile}, nil
	case "GetSceneCollectionList":
		settle("collection", &f.collection)
		return map[string]interface{}{"sceneCollections": list(f.collections), "currentSceneCollectionName": f.collection}, nil
	case "SetCurrentProfile":
		f.pendingSwitch["profile"] = &pendingSw{target: data["profileName"].(string), reads: f.switchAfter["profile"] + 1}
		return map[string]interface{}{}, nil
	case "SetCurrentSceneCollection":
		f.pendingSwitch["collection"] = &pendingSw{target: data["sceneCollectionName"].(string), reads: f.switchAfter["collection"] + 1}
		return map[string]interface{}{}, nil
	}
	return nil, fmt.Errorf("nieobsługiwane żądanie %s", rt)
}

func (f *fakeOBS) called(rt string) int {
	f.mu.Lock()
	defer f.mu.Unlock()
	n := 0
	for _, c := range f.calls {
		if c == rt {
			n++
		}
	}
	return n
}

func fastOpts() applyOptions {
	return applyOptions{poll: 5 * time.Millisecond, profileTimeout: 200 * time.Millisecond, collectionTimeout: 200 * time.Millisecond}
}

func status(res map[string]interface{}, key string) string {
	m, _ := res[key].(map[string]interface{})
	s, _ := m["status"].(string)
	return s
}

func TestApplySwitchesBothWhenDifferent(t *testing.T) {
	f := newFakeOBS()
	res := applyProfile(f, "NALF", "NALF", fastOpts())
	if status(res, "profile") != profSwitched || status(res, "collection") != profSwitched {
		t.Fatalf("oczekiwano dwóch przełączeń: %v", res)
	}
	if f.profile != "NALF" || f.collection != "NALF" {
		t.Fatalf("OBS: profil=%q zbiór=%q", f.profile, f.collection)
	}
}

func TestApplyDoesNotSwitchWhenNamesAlreadyMatch(t *testing.T) {
	f := newFakeOBS()
	f.profile, f.collection = "Garbarnia", "Garbarnia"
	res := applyProfile(f, "Garbarnia", "Garbarnia", fastOpts())
	if status(res, "profile") != profUnchanged || status(res, "collection") != profUnchanged {
		t.Fatalf("już ustawione: %v", res)
	}
	if f.called("SetCurrentProfile")+f.called("SetCurrentSceneCollection") != 0 {
		t.Fatal("nie wolno przełączać, gdy nazwy się zgadzają")
	}
}

func TestApplyComparesExactNamesNotCaseInsensitive(t *testing.T) {
	f := newFakeOBS()
	f.profiles = append(f.profiles, "nalf")
	f.profile = "nalf"
	res := applyProfile(f, "NALF", "", fastOpts())
	if status(res, "profile") != profSwitched || f.profile != "NALF" {
		t.Fatalf("„nalf” to inny profil niż „NALF”: %v", res)
	}
}

func TestApplyOnlyTheDifferingOneIsSwitched(t *testing.T) {
	f := newFakeOBS()
	f.profile = "NALF"
	res := applyProfile(f, "NALF", "NALF", fastOpts())
	if status(res, "profile") != profUnchanged || status(res, "collection") != profSwitched {
		t.Fatalf("%v", res)
	}
	if f.called("SetCurrentProfile") != 0 || f.called("SetCurrentSceneCollection") != 1 {
		t.Fatal("przełączyć trzeba tylko zbiór scen")
	}
}

func TestApplyMissingProfileDoesNotBlockCollection(t *testing.T) {
	f := newFakeOBS()
	f.profiles = []string{"Bez nazwy"}
	res := applyProfile(f, "NALF", "NALF", fastOpts())
	if status(res, "profile") != profMissing {
		t.Fatalf("brak profilu: %v", res)
	}
	if status(res, "collection") != profSwitched || f.collection != "NALF" {
		t.Fatalf("zbiór scen ma się przełączyć mimo braku profilu: %v", res)
	}
	if f.called("SetCurrentProfile") != 0 {
		t.Fatal("nie przełączamy na profil, którego nie ma")
	}
}

func TestApplyMissingCollectionDoesNotBlockProfile(t *testing.T) {
	f := newFakeOBS()
	f.collections = []string{"Garbarnia"}
	res := applyProfile(f, "NALF", "NALF", fastOpts())
	if status(res, "collection") != profMissing {
		t.Fatalf("brak zbioru scen: %v", res)
	}
	if status(res, "profile") != profSwitched || f.profile != "NALF" {
		t.Fatalf("profil ma się przełączyć mimo braku zbioru: %v", res)
	}
}

func TestApplyNamesWithSpacesAndPolishLetters(t *testing.T) {
	f := newFakeOBS()
	f.profiles = append(f.profiles, "Liga Żółtych Kaczek")
	f.collections = append(f.collections, "Zbiór scen — wiosna")
	res := applyProfile(f, "Liga Żółtych Kaczek", "Zbiór scen — wiosna", fastOpts())
	if status(res, "profile") != profSwitched || status(res, "collection") != profSwitched {
		t.Fatalf("%v", res)
	}
	if f.profile != "Liga Żółtych Kaczek" || f.collection != "Zbiór scen — wiosna" {
		t.Fatalf("OBS: %q / %q", f.profile, f.collection)
	}
}

func TestApplySkipsWhenStreaming(t *testing.T) {
	f := newFakeOBS()
	f.streaming = true
	res := applyProfile(f, "NALF", "NALF", fastOpts())
	if res["skipped"] != "active" || status(res, "profile") != profSkipped {
		t.Fatalf("trwa stream: %v", res)
	}
	if f.called("SetCurrentProfile")+f.called("SetCurrentSceneCollection") != 0 || f.profile != "Bez nazwy" {
		t.Fatal("przy streamie nie wolno przełączać")
	}
}

func TestApplySkipsWhenRecording(t *testing.T) {
	f := newFakeOBS()
	f.recording = true
	res := applyProfile(f, "NALF", "NALF", fastOpts())
	if res["skipped"] != "active" {
		t.Fatalf("trwa nagrywanie: %v", res)
	}
}

func TestApplyNoAnswerAboutOutputsCountsAsActive(t *testing.T) {
	for _, rt := range []string{"GetStreamStatus", "GetRecordStatus"} {
		f := newFakeOBS()
		f.failRequest[rt] = true
		res := applyProfile(f, "NALF", "NALF", fastOpts())
		if res["skipped"] != "unknown" || status(res, "profile") != profSkipped {
			t.Fatalf("%s bez odpowiedzi: %v", rt, res)
		}
		if f.called("SetCurrentProfile")+f.called("SetCurrentSceneCollection") != 0 {
			t.Fatalf("%s bez odpowiedzi: nie wolno przełączać", rt)
		}
	}
}

func TestApplyWaitsForSlowSwitch(t *testing.T) {
	f := newFakeOBS()
	f.switchAfter["collection"] = 5 // przełączenie widoczne po kilku odczytach
	res := applyProfile(f, "", "NALF", fastOpts())
	if status(res, "collection") != profSwitched || f.collection != "NALF" {
		t.Fatalf("%v", res)
	}
	if status(res, "profile") != profNone {
		t.Fatalf("pusty profil w module.json = nie wymagany: %v", res)
	}
}

func TestApplyTimeoutWhenSwitchNeverCompletes(t *testing.T) {
	f := newFakeOBS()
	f.neverSwitch["collection"] = true
	started := time.Now()
	res := applyProfile(f, "", "NALF", fastOpts())
	if status(res, "collection") != profTimeout {
		t.Fatalf("%v", res)
	}
	if time.Since(started) > 2*time.Second {
		t.Fatal("limit czasu przełączenia nie zadziałał")
	}
}

func TestApplyOBSErrorOnSetIsReported(t *testing.T) {
	f := newFakeOBS()
	f.failRequest["SetCurrentSceneCollection"] = true
	res := applyProfile(f, "", "NALF", fastOpts())
	if status(res, "collection") != profError {
		t.Fatalf("%v", res)
	}
}
