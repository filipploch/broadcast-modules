package obs

import (
	"sync/atomic"
	"testing"
	"time"
)

func TestGateOpenByDefault(t *testing.T) {
	g := NewRequestGate()
	if g.Paused() || !g.Wait(10*time.Millisecond) {
		t.Fatal("nowa bramka jest otwarta")
	}
}

func TestGateBlocksBetweenChangingAndChanged(t *testing.T) {
	g := NewRequestGate()
	g.Changing()
	if !g.Paused() {
		t.Fatal("po Changing bramka jest zamknięta")
	}
	var released int32
	go func() {
		if g.Wait(2 * time.Second) {
			atomic.StoreInt32(&released, 1)
		}
	}()
	time.Sleep(50 * time.Millisecond)
	if atomic.LoadInt32(&released) != 0 {
		t.Fatal("żądanie przeszło przez zamkniętą bramkę")
	}
	g.Changed()
	deadline := time.Now().Add(time.Second)
	for atomic.LoadInt32(&released) == 0 && time.Now().Before(deadline) {
		time.Sleep(5 * time.Millisecond)
	}
	if atomic.LoadInt32(&released) == 0 || g.Paused() {
		t.Fatal("po Changed żądania są wznawiane")
	}
}

func TestGateWaitTimesOutWhenStillPaused(t *testing.T) {
	g := NewRequestGate()
	g.Changing()
	if g.Wait(30 * time.Millisecond) {
		t.Fatal("zamknięta bramka nie może przepuścić po limicie czasu")
	}
}

// Zdarzenia w odwrotnej kolejności: Changed przed Changing nie może zostawić bramki zamkniętej.
func TestGateChangedBeforeChangingDoesNotLeaveItClosed(t *testing.T) {
	g := NewRequestGate()
	g.Changed()
	g.Changing()
	if g.Paused() {
		t.Fatal("późne Changing tuż po Changed ma być zignorowane")
	}
	if !g.Wait(20 * time.Millisecond) {
		t.Fatal("bramka ma być otwarta")
	}
}

// Normalna kolejność po upływie okna: kolejna zmiana zbioru scen znów zamyka bramkę.
func TestGateSecondChangeAfterWindowPausesAgain(t *testing.T) {
	g := NewRequestGate()
	now := time.Now()
	g.now = func() time.Time { return now }
	g.Changing()
	g.Changed()
	now = now.Add(5 * time.Second)
	g.Changing()
	if !g.Paused() {
		t.Fatal("druga zmiana zbioru scen po dłuższej chwili wstrzymuje żądania")
	}
	g.Changed()
	if g.Paused() {
		t.Fatal("po Changed otwarte")
	}
}

// Utracone Changed: bramka sama się otwiera, żeby plugin nie zamilkł na stałe.
func TestGateOpensItselfWhenChangedIsLost(t *testing.T) {
	g := NewRequestGate()
	g.maxPause = 60 * time.Millisecond
	g.Changing()
	if !g.Wait(time.Second) {
		t.Fatal("bramka powinna otworzyć się sama po maxPause")
	}
	if g.Paused() {
		t.Fatal("po maxPause nie jest wstrzymana")
	}
}

// Zegar bezpieczeństwa starej pauzy nie otwiera nowej.
func TestGateStaleTimerDoesNotReleaseNewPause(t *testing.T) {
	g := NewRequestGate()
	g.maxPause = 80 * time.Millisecond
	now := time.Now()
	g.now = func() time.Time { return now }
	g.Changing()
	g.Changed()
	now = now.Add(10 * time.Second)
	g.Changing() // nowa pauza (generacja 2)
	time.Sleep(40 * time.Millisecond)
	if !g.Paused() {
		t.Fatal("nowa pauza trwa")
	}
	time.Sleep(120 * time.Millisecond) // zegar generacji 2 otwiera
	if g.Paused() {
		t.Fatal("nowa pauza też kończy się zegarem bezpieczeństwa")
	}
}
