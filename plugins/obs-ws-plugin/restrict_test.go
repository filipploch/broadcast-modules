package main

import "testing"

func TestRequestAllowedWithoutListAllowsEverything(t *testing.T) {
	c := &Config{}
	for _, rt := range []string{"StartStream", "StartRecord", "SetCurrentProgramScene", "ApplyObsProfile", ""} {
		if !c.requestAllowed(rt) {
			t.Fatalf("bez listy żądanie %q powinno być dozwolone", rt)
		}
	}
}

func TestRequestAllowedWithListAllowsOnlyListedExactNames(t *testing.T) {
	c := &Config{AllowedRequests: []string{"GetStreamStatus", "PressInputPropertiesButton"}}
	if !c.requestAllowed("GetStreamStatus") || !c.requestAllowed("PressInputPropertiesButton") {
		t.Fatal("wymienione żądania mają być dozwolone")
	}
	for _, rt := range []string{"StartStream", "StopStream", "StartRecord", "StopRecord", "SetCurrentProgramScene", "SetSceneItemEnabled",
		"SetInputSettings", "SetSourceFilterEnabled", "ApplyObsProfile", "getstreamstatus", "GetStreamStatus ", ""} {
		if c.requestAllowed(rt) {
			t.Fatalf("żądanie %q ma być zablokowane w trybie ograniczonym", rt)
		}
	}
}
