package timer

import (
	"sync"
	"testing"
	"time"
)

func noopCallbacks() *Callbacks {
	return &Callbacks{
		OnStart:      func(time.Duration, string) {},
		OnSecondTick: func(time.Duration, string) {},
		OnPause:      func(time.Duration, string) {},
		OnResume:     func(time.Duration, string) {},
		OnLimit:      func(time.Duration, string) {},
	}
}

func almostEqual(a, b, tolerance time.Duration) bool {
	diff := a - b
	if diff < 0 {
		diff = -diff
	}
	return diff <= tolerance
}

// TestDependentTimerFollowsParentPause sprawdza kluczową właściwość poprawki:
// dependent timer (kara) powinien zamrażać się, gdy pauzowany jest jego
// rodzic (główny timer), i wznawiać razem z nim — bez żadnej osobnej
// komendy pauzy/wznowienia dla samej kary.
func TestDependentTimerFollowsParentPause(t *testing.T) {
	m := NewManager()
	tol := 60 * time.Millisecond

	m.Create("main", TimerConfig{
		Type:           TimerTypeIndependent,
		UpdateInterval: 20 * time.Millisecond,
		Callbacks:      noopCallbacks(),
	})
	if err := m.Start("main"); err != nil {
		t.Fatalf("start main: %v", err)
	}

	// Kara utworzona zaraz po starcie głównego timera — parentOffset ~ 0.
	m.Create("penalty", TimerConfig{
		Type:           TimerTypeDependent,
		ParentID:       "main",
		Limit:          10 * time.Second,
		PauseAtLimit:   true,
		UpdateInterval: 20 * time.Millisecond,
		Callbacks:      noopCallbacks(),
	})
	if err := m.Start("penalty"); err != nil {
		t.Fatalf("start penalty: %v", err)
	}

	time.Sleep(200 * time.Millisecond)

	infoBefore, err := m.GetState("penalty")
	if err != nil {
		t.Fatalf("get state: %v", err)
	}
	if !almostEqual(infoBefore.ElapsedTime, 200*time.Millisecond, tol) {
		t.Fatalf("expected ~200ms elapsed before pause, got %v", infoBefore.ElapsedTime)
	}

	// Pauzujemy TYLKO główny timer — kara nie dostaje żadnej komendy.
	if err := m.Pause("main"); err != nil {
		t.Fatalf("pause main: %v", err)
	}

	frozenAt, err := m.GetState("penalty")
	if err != nil {
		t.Fatalf("get state: %v", err)
	}

	time.Sleep(250 * time.Millisecond)

	infoDuringPause, err := m.GetState("penalty")
	if err != nil {
		t.Fatalf("get state: %v", err)
	}
	if !almostEqual(infoDuringPause.ElapsedTime, frozenAt.ElapsedTime, tol) {
		t.Fatalf(
			"penalty should freeze while parent is paused: at-pause=%v after-250ms=%v",
			frozenAt.ElapsedTime, infoDuringPause.ElapsedTime,
		)
	}

	// Wznawiamy główny timer — kara powinna znów zacząć płynąć.
	if err := m.Resume("main"); err != nil {
		t.Fatalf("resume main: %v", err)
	}

	time.Sleep(200 * time.Millisecond)

	infoAfterResume, err := m.GetState("penalty")
	if err != nil {
		t.Fatalf("get state: %v", err)
	}
	expected := frozenAt.ElapsedTime + 200*time.Millisecond
	if !almostEqual(infoAfterResume.ElapsedTime, expected, tol) {
		t.Fatalf("expected ~%v after resume, got %v", expected, infoAfterResume.ElapsedTime)
	}
}

// TestDependentTimerExplicitPauseIsIndependentOfParent sprawdza, że jawne
// zapauzowanie SAMEJ kary zamraża ją niezależnie od tego, czy główny timer
// dalej biegnie.
func TestDependentTimerExplicitPauseIsIndependentOfParent(t *testing.T) {
	m := NewManager()
	tol := 60 * time.Millisecond

	m.Create("main2", TimerConfig{
		Type:           TimerTypeIndependent,
		UpdateInterval: 20 * time.Millisecond,
		Callbacks:      noopCallbacks(),
	})
	_ = m.Start("main2")

	m.Create("penalty2", TimerConfig{
		Type:           TimerTypeDependent,
		ParentID:       "main2",
		Limit:          10 * time.Second,
		PauseAtLimit:   true,
		UpdateInterval: 20 * time.Millisecond,
		Callbacks:      noopCallbacks(),
	})
	_ = m.Start("penalty2")

	time.Sleep(150 * time.Millisecond)

	if err := m.Pause("penalty2"); err != nil {
		t.Fatalf("pause penalty2: %v", err)
	}
	frozen, _ := m.GetState("penalty2")

	// Główny timer płynie dalej.
	time.Sleep(200 * time.Millisecond)

	after, err := m.GetState("penalty2")
	if err != nil {
		t.Fatalf("get state: %v", err)
	}
	if !almostEqual(after.ElapsedTime, frozen.ElapsedTime, tol) {
		t.Fatalf(
			"explicitly paused penalty should stay frozen even though parent keeps running: frozen=%v after=%v",
			frozen.ElapsedTime, after.ElapsedTime,
		)
	}
}

// TestDependentTimerAdjustTime sprawdza, że ręczna korekta (+/-) dependent
// timera poprawnie przesuwa jego wyliczaną wartość.
func TestDependentTimerAdjustTime(t *testing.T) {
	m := NewManager()
	tol := 60 * time.Millisecond

	m.Create("main3", TimerConfig{
		Type:           TimerTypeIndependent,
		UpdateInterval: 20 * time.Millisecond,
		Callbacks:      noopCallbacks(),
	})
	_ = m.Start("main3")

	m.Create("penalty3", TimerConfig{
		Type:           TimerTypeDependent,
		ParentID:       "main3",
		Limit:          10 * time.Second,
		PauseAtLimit:   true,
		UpdateInterval: 20 * time.Millisecond,
		Callbacks:      noopCallbacks(),
	})
	_ = m.Start("penalty3")

	time.Sleep(150 * time.Millisecond)

	if err := m.AdjustTime("penalty3", 1000*time.Millisecond); err != nil {
		t.Fatalf("adjust: %v", err)
	}

	info, err := m.GetState("penalty3")
	if err != nil {
		t.Fatalf("get state: %v", err)
	}
	if !almostEqual(info.ElapsedTime, 1150*time.Millisecond, tol) {
		t.Fatalf("expected ~1150ms after +1000ms adjust, got %v", info.ElapsedTime)
	}

	// Kolejny tick głównego timera powinien nadal poprawnie przesuwać karę.
	time.Sleep(200 * time.Millisecond)
	info2, err := m.GetState("penalty3")
	if err != nil {
		t.Fatalf("get state: %v", err)
	}
	if !almostEqual(info2.ElapsedTime, 1350*time.Millisecond, tol) {
		t.Fatalf("expected ~1350ms after further 200ms, got %v", info2.ElapsedTime)
	}
}

// TestDependentTimerResumesAfterAdjustBelowLimit sprawdza błąd 3 zgłoszony
// przez użytkownika: kara, która osiągnęła 0:00 (automatyczna pauza po
// przekroczeniu limitu), powinna dać się skorygować i WZNOWIĆ odliczanie,
// zamiast zostać trwale zamrożona mimo poprawnej wartości po korekcie.
func TestDependentTimerResumesAfterAdjustBelowLimit(t *testing.T) {
	m := NewManager()
	tol := 80 * time.Millisecond

	m.Create("main5", TimerConfig{
		Type:           TimerTypeIndependent,
		UpdateInterval: 20 * time.Millisecond,
		Callbacks:      noopCallbacks(),
	})
	_ = m.Start("main5")

	// Limit 200ms — łatwo osiągalny w krótkim teście.
	m.Create("penalty5", TimerConfig{
		Type:           TimerTypeDependent,
		ParentID:       "main5",
		Limit:          200 * time.Millisecond,
		PauseAtLimit:   true,
		UpdateInterval: 20 * time.Millisecond,
		Callbacks:      noopCallbacks(),
	})
	_ = m.Start("penalty5")

	// Poczekaj aż kara naturalnie osiągnie limit i się zapauzuje.
	deadline := time.Now().Add(2 * time.Second)
	var atLimit *TimerInfo
	for time.Now().Before(deadline) {
		info, err := m.GetState("penalty5")
		if err != nil {
			t.Fatalf("get state: %v", err)
		}
		if info.State == StatePaused && info.HasReachedLimit {
			atLimit = info
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if atLimit == nil {
		t.Fatal("kara nigdy nie osiągnęła limitu (paused+hasReachedLimit)")
	}
	if !almostEqual(atLimit.ElapsedTime, 200*time.Millisecond, tol) {
		t.Fatalf("expected elapsed ~200ms at limit, got %v", atLimit.ElapsedTime)
	}

	// Korekta "+100ms pozostałego czasu" = -100ms elapsed (jak przycisk "+"
	// w UI po poprawce błędu 2).
	if err := m.AdjustTime("penalty5", -100*time.Millisecond); err != nil {
		t.Fatalf("adjust: %v", err)
	}

	afterAdjust, err := m.GetState("penalty5")
	if err != nil {
		t.Fatalf("get state: %v", err)
	}
	if afterAdjust.State != StateRunning {
		t.Fatalf("expected penalty to resume (state=running) after adjusting below limit, got state=%s", afterAdjust.State)
	}
	if afterAdjust.HasReachedLimit {
		t.Fatal("expected hasReachedLimit=false after adjusting below limit")
	}
	if !almostEqual(afterAdjust.ElapsedTime, 100*time.Millisecond, tol) {
		t.Fatalf("expected elapsed ~100ms right after adjust, got %v", afterAdjust.ElapsedTime)
	}

	// I powinna dalej realnie płynąć (nie zostać zamrożona).
	time.Sleep(150 * time.Millisecond)
	later, err := m.GetState("penalty5")
	if err != nil {
		t.Fatalf("get state: %v", err)
	}
	if later.ElapsedTime <= afterAdjust.ElapsedTime {
		t.Fatalf(
			"penalty should keep advancing after resume: right-after-adjust=%v, 150ms-later=%v",
			afterAdjust.ElapsedTime, later.ElapsedTime,
		)
	}
}

// TestOnSecondTickReportsRawElapsedNotIncludingInitialTime jest regresją dla
// buga znalezionego przy testach 2. połowy meczu: OnSecondTick doliczał
// t.initialTime do zgłaszanego elapsed, mimo że initial_time jest już osobnym
// polem w payloadzie broadcastowanym przez plugin.go — klienci (overlay/UI)
// doliczali je więc DRUGI RAZ, co przy niezerowym initial_time (np. 2. połowa
// dziedzicząca czas 1. połowy) dawało podwójnie zawyżony wynik.
func TestOnSecondTickReportsRawElapsedNotIncludingInitialTime(t *testing.T) {
	m := NewManager()

	var mu sync.Mutex
	var receivedElapsed time.Duration
	gotTick := false

	m.Create("main4", TimerConfig{
		Type:           TimerTypeIndependent,
		InitialTime:    5000 * time.Millisecond, // np. odziedziczone z 1. połowy
		UpdateInterval: 20 * time.Millisecond,
		Callbacks: &Callbacks{
			OnStart: func(time.Duration, string) {},
			OnSecondTick: func(elapsed time.Duration, id string) {
				mu.Lock()
				receivedElapsed = elapsed
				gotTick = true
				mu.Unlock()
			},
			OnPause:  func(time.Duration, string) {},
			OnResume: func(time.Duration, string) {},
			OnLimit:  func(time.Duration, string) {},
		},
	})

	if err := m.Start("main4"); err != nil {
		t.Fatalf("start: %v", err)
	}

	time.Sleep(150 * time.Millisecond)

	mu.Lock()
	defer mu.Unlock()
	if !gotTick {
		t.Fatal("OnSecondTick never fired")
	}
	// Raw elapsed powinien być bliski 0 (mieści się w pierwszej sekundzie),
	// NIE ~5s (initial_time błędnie doliczony do elapsed przez plugin).
	if receivedElapsed >= 2*time.Second {
		t.Fatalf(
			"OnSecondTick reported %v — initial_time (5s) wygląda na doliczone do elapsed (podwójne liczenie)",
			receivedElapsed,
		)
	}
}
