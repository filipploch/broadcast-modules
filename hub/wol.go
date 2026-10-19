package main

import (
	"errors"
	"fmt"
	"log"
	"net"
	"time"
)

// Wake-on-LAN Debiana (E2d3a, punkt 16 L1 koncepcji). HUB wysyła sygnał budzenia przy starcie (gdy wol.enabled) i na prośbę modułu
// (dwuklik szarej ikony recorder-pluginu). HUB nigdy nie czeka na Debiana: recorder-plugin zgłasza się sam, gdy system wstanie,
// a do tego czasu ikona w panelu jest szara, bez paska (reguła z E2c). Adres MAC jest wyłącznie w konfiguracji HUB-a (sekcja "wol").

const (
	wolRepeats  = 3           // ile razy wysłać sygnał (pojedynczy pakiet UDP bywa gubiony)
	wolInterval = time.Second // odstęp między powtórzeniami
)

var (
	errWolDisabled = errors.New("budzenie Debiana wyłączone w konfiguracji HUB-a (wol.enabled = false)")
	errWolNoMac    = errors.New("brak adresu MAC Debiana w konfiguracji HUB-a (wol.mac)")
)

// wolSender wysyła sygnał budzenia według konfiguracji. send i interval podmieniają testy.
type wolSender struct {
	cfg      WolConfig
	send     func(addr string, packet []byte) error
	repeats  int
	interval time.Duration
}

func newWolSender(cfg WolConfig) *wolSender {
	return &wolSender{cfg: cfg, send: sendUDP, repeats: wolRepeats, interval: wolInterval}
}

// magicPacket: 6 bajtów 0xFF i 16 powtórzeń adresu MAC.
func magicPacket(mac net.HardwareAddr) []byte {
	pkt := make([]byte, 0, 6+16*len(mac))
	for i := 0; i < 6; i++ {
		pkt = append(pkt, 0xFF)
	}
	for i := 0; i < 16; i++ {
		pkt = append(pkt, mac...)
	}
	return pkt
}

// parseMac przyjmuje zapis z dwukropkami albo myślnikami; wymaga adresu 6-bajtowego.
func parseMac(s string) (net.HardwareAddr, error) {
	mac, err := net.ParseMAC(s)
	if err != nil {
		return nil, fmt.Errorf("niepoprawny adres MAC Debiana %q w konfiguracji HUB-a (wol.mac): %v", s, err)
	}
	if len(mac) != 6 {
		return nil, fmt.Errorf("adres MAC Debiana %q w konfiguracji HUB-a (wol.mac) nie ma 6 bajtów", s)
	}
	return mac, nil
}

// sendUDP wysyła jeden datagram (Go ustawia SO_BROADCAST na gniazdach UDP, więc adres rozgłoszeniowy działa bez dodatkowych opcji).
func sendUDP(addr string, packet []byte) error {
	conn, err := net.Dial("udp4", addr)
	if err != nil {
		return err
	}
	defer conn.Close()
	_, err = conn.Write(packet)
	return err
}

// wake wysyła sygnał budzenia (wolRepeats razy) i wraca po ostatnim powtórzeniu. Błąd tylko wtedy, gdy żadne wysłanie się nie udało
// albo konfiguracja nie pozwala wysłać. Nie czeka na odpowiedź Debiana (sygnał budzenia jej nie ma).
func (w *wolSender) wake(reason string) error {
	if w == nil || !w.cfg.Enabled {
		return errWolDisabled
	}
	if w.cfg.Mac == "" {
		return errWolNoMac
	}
	mac, err := parseMac(w.cfg.Mac)
	if err != nil {
		return err
	}
	addr := w.cfg.BroadcastAddr
	if addr == "" {
		addr = defaultHubConfig().Wol.BroadcastAddr
	}
	pkt := magicPacket(mac)
	sent := 0
	var lastErr error
	for i := 0; i < w.repeats; i++ {
		if i > 0 {
			time.Sleep(w.interval)
		}
		if err := w.send(addr, pkt); err != nil {
			lastErr = err
			log.Printf("⚠️  Budzenie Debiana (%s): wysłanie %d/%d na %s nie powiodło się: %v", reason, i+1, w.repeats, addr, err)
			continue
		}
		sent++
	}
	if sent == 0 {
		return fmt.Errorf("sygnał budzenia nie został wysłany na %s: %v", addr, lastErr)
	}
	log.Printf("📡 Budzenie Debiana (%s): sygnał wysłany %d/%d razy na %s (MAC %s); HUB nie czeka na Debiana",
		reason, sent, w.repeats, addr, mac)
	return nil
}

// wakeDebianOnStart budzi Debiana w tle i wraca od razu: start HUB-a nie czeka ani na wysłanie, ani na Debiana.
// Wyłączone budzenie i brak adresu MAC to tylko wpis w logu, nie błąd startu. Kanał zamyka się po zakończeniu próby (dla testów).
func (h *Hub) wakeDebianOnStart() <-chan struct{} {
	done := make(chan struct{})
	w := h.wol
	go func() {
		defer close(done)
		switch err := w.wake("start HUB-a"); {
		case err == nil:
		case errors.Is(err, errWolDisabled):
			log.Printf("Budzenie Debiana przy starcie: wyłączone (wol.enabled = false)")
		default:
			log.Printf("⚠️  Budzenie Debiana przy starcie: %v. Start HUB-a trwa dalej", err)
		}
	}()
	return done
}

// handleWakeHost obsługuje prośbę modułu o obudzenie Debiana (dwuklik szarej ikony recorder-pluginu).
// Odpowiedź wake_host_result {ok, error} wraca do modułu po wysłaniu wszystkich powtórzeń (ok. 2 s).
func (h *Hub) handleWakeHost(msg *Message) {
	src := msg.Source
	if src == nil || src.ComponentType != "main_module" {
		log.Printf("⚠️  wake_host odrzucone: prośba tylko od modułu głównego (od: %s)", msg.From)
		return
	}
	w := h.wol
	go func() {
		err := w.wake("prośba z panelu")
		payload := map[string]interface{}{"ok": err == nil}
		if err != nil {
			payload["error"] = err.Error()
			log.Printf("❌ Budzenie Debiana (prośba z panelu): %v", err)
		}
		h.sendSafely(src, NewMessage("hub", src.ID, "wake_host_result", payload))
	}()
}
