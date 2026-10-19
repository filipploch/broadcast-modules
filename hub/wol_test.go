package main

import (
	"bytes"
	"log"
	"net"
	"os"
	"strings"
	"sync"
	"testing"
	"time"
)

func testWolCfg() WolConfig {
	return WolConfig{Enabled: true, Mac: "6c:2b:59:f4:29:85", BroadcastAddr: "255.255.255.255:9"}
}

// recordingSender zapamiętuje wysłane pakiety zamiast wysyłać je w sieć.
type recordingSender struct {
	mu      sync.Mutex
	addrs   []string
	packets [][]byte
}

func (r *recordingSender) send(addr string, pkt []byte) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.addrs = append(r.addrs, addr)
	r.packets = append(r.packets, append([]byte(nil), pkt...))
	return nil
}

// lockedBuffer: bufor logu bezpieczny dla zapisu z innej gorutyny.
type lockedBuffer struct {
	mu  sync.Mutex
	buf bytes.Buffer
}

func (b *lockedBuffer) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.Write(p)
}

func (b *lockedBuffer) String() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.String()
}

func captureLog(t *testing.T) *lockedBuffer {
	b := &lockedBuffer{}
	log.SetOutput(b)
	t.Cleanup(func() { log.SetOutput(os.Stderr) })
	return b
}

func fastSender(cfg WolConfig, send func(string, []byte) error) *wolSender {
	w := newWolSender(cfg)
	w.send = send
	w.interval = time.Millisecond
	return w
}

func TestMagicPacketFormat(t *testing.T) {
	mac, err := parseMac("6c-2b-59-f4-29-85")
	if err != nil {
		t.Fatal(err)
	}
	pkt := magicPacket(mac)
	if len(pkt) != 102 {
		t.Fatalf("długość pakietu %d, oczekiwano 102", len(pkt))
	}
	if !bytes.Equal(pkt[:6], bytes.Repeat([]byte{0xFF}, 6)) {
		t.Fatalf("pakiet nie zaczyna się od 6 x 0xFF: % x", pkt[:6])
	}
	for i := 0; i < 16; i++ {
		if !bytes.Equal(pkt[6+6*i:12+6*i], mac) {
			t.Fatalf("powtórzenie %d adresu MAC niepoprawne", i)
		}
	}
}

func TestParseMacRejectsBadAddress(t *testing.T) {
	for _, s := range []string{"nie-mac", "6c:2b:59:f4:29", "00:00:00:00:fe:80:00:00:00:00:00:00:02:00:5e:10:00:00:00:01"} {
		if _, err := parseMac(s); err == nil {
			t.Errorf("adres %q powinien być odrzucony", s)
		}
	}
}

func TestWakeSendsThreeTimesToConfiguredAddress(t *testing.T) {
	rec := &recordingSender{}
	cfg := testWolCfg()
	cfg.BroadcastAddr = "192.168.1.255:9"
	if err := fastSender(cfg, rec.send).wake("test"); err != nil {
		t.Fatal(err)
	}
	if len(rec.packets) != wolRepeats {
		t.Fatalf("wysłano %d razy, oczekiwano %d", len(rec.packets), wolRepeats)
	}
	for _, a := range rec.addrs {
		if a != "192.168.1.255:9" {
			t.Fatalf("adres %q, oczekiwano 192.168.1.255:9", a)
		}
	}
}

func TestWakeDisabledOrWithoutMacSendsNothing(t *testing.T) {
	rec := &recordingSender{}
	off := testWolCfg()
	off.Enabled = false
	if err := fastSender(off, rec.send).wake("test"); err != errWolDisabled {
		t.Fatalf("wyłączone budzenie: błąd %v, oczekiwano errWolDisabled", err)
	}
	noMac := testWolCfg()
	noMac.Mac = ""
	if err := fastSender(noMac, rec.send).wake("test"); err != errWolNoMac {
		t.Fatalf("brak MAC: błąd %v, oczekiwano errWolNoMac", err)
	}
	if err := (*wolSender)(nil).wake("test"); err != errWolDisabled {
		t.Fatalf("brak konfiguracji: błąd %v, oczekiwano errWolDisabled", err)
	}
	if len(rec.packets) != 0 {
		t.Fatalf("nie powinno nic wysłać, wysłano %d", len(rec.packets))
	}
}

// Prawdziwe gniazdo UDP: pakiet dociera do odbiorcy pod adresem z konfiguracji.
func TestWakeOverRealUDP(t *testing.T) {
	pc, err := net.ListenPacket("udp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer pc.Close()
	cfg := testWolCfg()
	cfg.BroadcastAddr = pc.LocalAddr().String()
	w := newWolSender(cfg)
	w.interval = time.Millisecond
	if err := w.wake("test"); err != nil {
		t.Fatal(err)
	}
	buf := make([]byte, 200)
	pc.SetReadDeadline(time.Now().Add(2 * time.Second))
	n, _, err := pc.ReadFrom(buf)
	if err != nil {
		t.Fatalf("pakiet nie dotarł: %v", err)
	}
	mac, _ := parseMac(cfg.Mac)
	if !bytes.Equal(buf[:n], magicPacket(mac)) {
		t.Fatalf("odebrany pakiet różni się od oczekiwanego")
	}
}

// Reguła z koncepcji (punkt 16, L1): HUB nie czeka na Debiana. Start wraca od razu, nawet gdy wysyłanie stoi.
func TestWakeOnStartDoesNotBlockHubStart(t *testing.T) {
	hub := NewHub(0, false, false)
	release := make(chan struct{})
	hub.wol = fastSender(testWolCfg(), func(string, []byte) error { <-release; return nil })
	start := time.Now()
	done := hub.wakeDebianOnStart()
	if d := time.Since(start); d > 100*time.Millisecond {
		t.Fatalf("start HUB-a czekał na budzenie %v", d)
	}
	select {
	case <-done:
		t.Fatal("budzenie zakończyło się, choć wysyłanie stoi: wywołanie nie poszło w tle")
	default:
	}
	close(release)
	<-done
}

// Brak adresu MAC przy włączonym budzeniu: wpis w logu, bez błędu startu.
func TestWakeOnStartWithoutMacOnlyLogs(t *testing.T) {
	logs := captureLog(t)
	hub := NewHub(0, false, false)
	cfg := testWolCfg()
	cfg.Mac = ""
	hub.wol = newWolSender(cfg)
	<-hub.wakeDebianOnStart()
	if !strings.Contains(logs.String(), "brak adresu MAC") {
		t.Fatalf("w logu brak wpisu o braku adresu MAC: %q", logs.String())
	}
}

// Po budzeniu przy starcie, dopóki recorder-plugin się nie zgłosi, HUB nie wysyła modułowi niczego o recorderze
// (żadnego plugin_status ani plugin_gave_up), więc w panelu ikona zostaje szara bez paska (reguła z E2c).
func TestWakeOnStartSendsNothingAboutRecorderToModule(t *testing.T) {
	hub := NewHub(0, false, false)
	main := newMainModule(hub)
	rec := &recordingSender{}
	hub.wol = fastSender(testWolCfg(), rec.send)
	<-hub.wakeDebianOnStart()
	if got := readSent(t, main); got != nil {
		t.Fatalf("moduł nie powinien dostać komunikatu po budzeniu przy starcie, dostał %s %v", got.Type, got.Payload)
	}
	if len(rec.packets) != wolRepeats {
		t.Fatalf("wysłano %d razy, oczekiwano %d", len(rec.packets), wolRepeats)
	}
}

func waitSent(t *testing.T, m *Module) *Message {
	t.Helper()
	select {
	case data := <-m.Send:
		msg, err := FromJSON(data)
		if err != nil {
			t.Fatal(err)
		}
		return msg
	case <-time.After(2 * time.Second):
		t.Fatal("brak odpowiedzi HUB-a w 2 s")
		return nil
	}
}

func TestWakeHostRequestFromModuleGetsResult(t *testing.T) {
	hub := NewHub(0, false, false)
	main := newMainModule(hub)
	rec := &recordingSender{}
	hub.wol = fastSender(testWolCfg(), rec.send)

	msg := NewMessage(main.ID, "hub", "wake_host", nil)
	msg.Source = main
	hub.handleMessage(msg)

	got := waitSent(t, main)
	if got.Type != "wake_host_result" || got.Payload["ok"] != true {
		t.Fatalf("oczekiwano wake_host_result ok=true, jest %s %v", got.Type, got.Payload)
	}
	if len(rec.packets) != wolRepeats {
		t.Fatalf("wysłano %d razy, oczekiwano %d", len(rec.packets), wolRepeats)
	}
}

func TestWakeHostRequestReportsDisabledWol(t *testing.T) {
	hub := NewHub(0, false, false)
	main := newMainModule(hub)
	cfg := testWolCfg()
	cfg.Enabled = false
	hub.wol = newWolSender(cfg)

	msg := NewMessage(main.ID, "hub", "wake_host", nil)
	msg.Source = main
	hub.handleMessage(msg)

	got := waitSent(t, main)
	if got.Type != "wake_host_result" || got.Payload["ok"] != false {
		t.Fatalf("oczekiwano wake_host_result ok=false, jest %s %v", got.Type, got.Payload)
	}
	if e, _ := got.Payload["error"].(string); !strings.Contains(e, "wyłączone") {
		t.Fatalf("komunikat błędu nie mówi o wyłączonym budzeniu: %q", e)
	}
}

func TestWakeHostRequestOnlyFromMainModule(t *testing.T) {
	hub := NewHub(0, false, false)
	rec := &recordingSender{}
	hub.wol = fastSender(testWolCfg(), rec.send)
	p := NewModule(hub, nil)
	p.ID = "timer-plugin"
	p.ComponentType = "plugin"
	msg := NewMessage(p.ID, "hub", "wake_host", nil)
	msg.Source = p
	hub.handleMessage(msg)
	time.Sleep(50 * time.Millisecond)
	if len(rec.packets) != 0 {
		t.Fatalf("prośba od pluginu nie powinna budzić Debiana")
	}
}
