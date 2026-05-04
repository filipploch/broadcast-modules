package main

import (
	"encoding/json"
	"fmt"
	"log"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
	"unsafe"
)

var (
	kernel32        = syscall.NewLazyDLL("kernel32.dll")
	procCreateFileW = kernel32.NewProc("CreateFileW")
	procWriteFile   = kernel32.NewProc("WriteFile")
	procReadFile    = kernel32.NewProc("ReadFile")
	procCloseHandle = kernel32.NewProc("CloseHandle")
)

const (
	GENERIC_READ_WRITE = 0xC0000000
	OPEN_EXISTING      = 3
	INVALID_HANDLE     = ^uintptr(0)
)

// frameStepSec — czas jednej klatki w sekundach (30fps).
const frameStepSec = 1.0 / 30.0

// seekTimeout — maksymalny czas oczekiwania na potwierdzenie seeku od mpv.
const seekTimeout = 3 * time.Second

// ── MpvIPC ────────────────────────────────────────────────────────────────────

// MpvIPC obsługuje komunikację z mpv przez Named Pipe w trybie read-write.
//
// Architektura:
//   - Jedno połączenie przez cały czas życia pluginu (bez Reconnect).
//   - Jedna goroutyna readPump startuje przy Connect i nigdy się nie restartuje.
//   - send()        — fire-and-forget, używane w LoadAndPlay / SetSpeed / Pause / Resume
//   - SendAndWait() — czeka na potwierdzenie, używane TYLKO w FrameStep
//
// Dzięki temu nigdy nie mamy dwóch readPump na tym samym handle.

type mpvResponse struct {
	RequestID int64  `json:"request_id"`
	Error     string `json:"error"`
}

type MpvIPC struct {
	pipeName string

	mu     sync.Mutex // chroni handle i operacje WriteFile
	handle uintptr

	nextID    atomic.Int64
	pendingMu sync.Mutex
	pending   map[int64]chan mpvResponse
}

func NewMpvIPC(pipeName string) *MpvIPC {
	return &MpvIPC{
		pipeName: pipeName,
		pending:  make(map[int64]chan mpvResponse),
	}
}

// Connect otwiera połączenie z pipe mpv i startuje readPump.
// Powinno być wywołane dokładnie raz — przy starcie pluginu.
func (m *MpvIPC) Connect(timeout time.Duration) error {
	namePtr, err := syscall.UTF16PtrFromString(m.pipeName)
	if err != nil {
		return fmt.Errorf("invalid pipe name: %w", err)
	}

	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		handle, _, _ := procCreateFileW.Call(
			uintptr(unsafe.Pointer(namePtr)),
			GENERIC_READ_WRITE,
			0, 0,
			OPEN_EXISTING,
			0, 0,
		)
		if handle != INVALID_HANDLE {
			m.handle = handle
			log.Printf("✅ mpv IPC connected (rw): %s", m.pipeName)
			go m.readPump()
			return nil
		}
		time.Sleep(100 * time.Millisecond)
	}
	return fmt.Errorf("timeout connecting to mpv pipe: %s", m.pipeName)
}

// readPump czyta odpowiedzi JSON z mpv i przekazuje je do oczekujących SendAndWait.
// Uruchamiana raz przez Connect — działa przez cały czas życia pluginu.
func (m *MpvIPC) readPump() {
	buf := make([]byte, 4096)
	var partial []byte

	log.Printf("📡 readPump: start")
	for {
		m.mu.Lock()
		handle := m.handle
		m.mu.Unlock()

		if handle == 0 || handle == INVALID_HANDLE {
			time.Sleep(20 * time.Millisecond)
			continue
		}

		var bytesRead uint32
		ret, _, _ := procReadFile.Call(
			handle,
			uintptr(unsafe.Pointer(&buf[0])),
			uintptr(len(buf)),
			uintptr(unsafe.Pointer(&bytesRead)),
			0,
		)

		if ret == 0 || bytesRead == 0 {
			time.Sleep(20 * time.Millisecond)
			continue
		}

		partial = append(partial, buf[:bytesRead]...)

		// mpv wysyła po jednym JSON per linia.
		for {
			idx := -1
			for i, b := range partial {
				if b == '\n' {
					idx = i
					break
				}
			}
			if idx < 0 {
				break
			}
			line := make([]byte, idx)
			copy(line, partial[:idx])
			partial = append(partial[:0], partial[idx+1:]...)

			var resp mpvResponse
			if err := json.Unmarshal(line, &resp); err != nil {
				continue
			}

			if resp.RequestID > 0 {
				m.pendingMu.Lock()
				ch, ok := m.pending[resp.RequestID]
				if ok {
					delete(m.pending, resp.RequestID)
				}
				m.pendingMu.Unlock()
				if ok {
					select {
					case ch <- resp:
					default:
					}
				}
			}
			// RequestID==0: odpowiedź na komendę bez request_id lub event — ignorujemy.
		}
	}
}

// send wysyła komendę bez czekania na odpowiedź (fire-and-forget).
func (m *MpvIPC) send(command []interface{}) error {
	data, err := json.Marshal(map[string]interface{}{"command": command})
	if err != nil {
		return err
	}
	data = append(data, '\n')

	m.mu.Lock()
	defer m.mu.Unlock()
	return m.writeUnlocked(data)
}

// SendAndWait wysyła komendę i czeka na potwierdzenie od mpv.
// Używane tylko w FrameStep — gwarantuje serialne przetwarzanie seeków.
func (m *MpvIPC) SendAndWait(command []interface{}, timeout time.Duration) error {
	id := m.nextID.Add(1)
	ch := make(chan mpvResponse, 1)

	m.pendingMu.Lock()
	m.pending[id] = ch
	m.pendingMu.Unlock()

	data, err := json.Marshal(map[string]interface{}{
		"command":    command,
		"request_id": id,
	})
	if err != nil {
		m.pendingMu.Lock()
		delete(m.pending, id)
		m.pendingMu.Unlock()
		return err
	}
	data = append(data, '\n')

	m.mu.Lock()
	if m.handle == 0 || m.handle == INVALID_HANDLE {
		m.mu.Unlock()
		m.pendingMu.Lock()
		delete(m.pending, id)
		m.pendingMu.Unlock()
		return fmt.Errorf("mpv IPC not connected")
	}
	writeErr := m.writeUnlocked(data)
	m.mu.Unlock()

	if writeErr != nil {
		m.pendingMu.Lock()
		delete(m.pending, id)
		m.pendingMu.Unlock()
		return fmt.Errorf("write failed: %w", writeErr)
	}

	select {
	case resp, ok := <-ch:
		if !ok {
			return fmt.Errorf("channel closed")
		}
		if resp.Error != "" && resp.Error != "success" {
			return fmt.Errorf("mpv error: %s", resp.Error)
		}
		return nil
	case <-time.After(timeout):
		m.pendingMu.Lock()
		delete(m.pending, id)
		m.pendingMu.Unlock()
		return fmt.Errorf("timeout (%v) waiting for mpv: %v", timeout, command[0])
	}
}

// writeUnlocked wykonuje WriteFile — wymaga trzymanego m.mu.
func (m *MpvIPC) writeUnlocked(data []byte) error {
	if m.handle == 0 || m.handle == INVALID_HANDLE {
		return fmt.Errorf("mpv IPC not connected")
	}
	var written uint32
	ret, _, callErr := procWriteFile.Call(
		m.handle,
		uintptr(unsafe.Pointer(&data[0])),
		uintptr(len(data)),
		uintptr(unsafe.Pointer(&written)),
		0,
	)
	if ret != 0 && written == uint32(len(data)) {
		return nil
	}
	if ret != 0 {
		return fmt.Errorf("WriteFile incomplete: %d/%d bytes", written, len(data))
	}
	return fmt.Errorf("WriteFile failed: %w", callErr)
}

func (m *MpvIPC) Close() {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.handle != 0 && m.handle != INVALID_HANDLE {
		procCloseHandle.Call(m.handle)
		m.handle = 0
	}
}

// ── MpvController ─────────────────────────────────────────────────────────────

type MpvController struct {
	ipc   *MpvIPC
	ready bool
	mu    sync.Mutex
}

func NewMpvController(pipeName string) *MpvController {
	return &MpvController{
		ipc: NewMpvIPC(pipeName),
	}
}

func (mc *MpvController) WaitForIPC(timeout time.Duration) error {
	if err := mc.ipc.Connect(timeout); err != nil {
		return err
	}
	mc.mu.Lock()
	mc.ready = true
	mc.mu.Unlock()
	return nil
}

func (mc *MpvController) isReady() bool {
	mc.mu.Lock()
	defer mc.mu.Unlock()
	return mc.ready
}

// LoadAndPlay ładuje plik i odtwarza powtórkę.
//
// Używa wyłącznie fire-and-forget (send), tak jak oryginalny kod.
// Jedyna zmiana vs oryginał: pause zamiast stop przed loadfile,
// żeby OBS (Window Capture po tytule) nie tracił źródła.
func (mc *MpvController) LoadAndPlay(videoPath string, startMs, endMs int64, speed float64) error {
	if !mc.isReady() {
		return fmt.Errorf("mpv IPC not ready")
	}

	startSec := float64(startMs) / 1000.0
	log.Printf("▶ replay: %s [start=%.3fs] x%.2f", videoPath, startSec, speed)

	// Zatrzymaj bieżące odtwarzanie i zresetuj speed.
	// pause zamiast stop — stop resetuje tytuł okna mpv, przez co
	// OBS (Window Capture po tytule "replay-plugin-mpv") traci źródło.
	if err := mc.ipc.send([]interface{}{"set_property", "pause", true}); err != nil {
		log.Printf("⚠️  pre-pause: %v", err)
	}
	if err := mc.ipc.send([]interface{}{"set_property", "speed", 1.0}); err != nil {
		log.Printf("⚠️  pre-speed: %v", err)
	}

	startArg := fmt.Sprintf("start=%.3f", startSec)
	if err := mc.ipc.send([]interface{}{
		"loadfile", videoPath, "replace", 0, startArg,
	}); err != nil {
		return fmt.Errorf("loadfile failed: %w", err)
	}

	// Czekaj aż mpv otworzy plik, potem ustaw speed i odtwarzaj.
	time.Sleep(300 * time.Millisecond)

	if err := mc.ipc.send([]interface{}{"set_property", "speed", speed}); err != nil {
		return fmt.Errorf("set speed failed: %w", err)
	}
	if err := mc.ipc.send([]interface{}{"set_property", "pause", false}); err != nil {
		return fmt.Errorf("unpause failed: %w", err)
	}

	log.Printf("✅ LoadAndPlay: sent all commands")
	return nil
}

func (mc *MpvController) SetSpeed(speed float64) error {
	if !mc.isReady() {
		return fmt.Errorf("mpv IPC not ready")
	}
	log.Printf("⚡ speed → %.2f", speed)
	return mc.ipc.send([]interface{}{"set_property", "speed", speed})
}

func (mc *MpvController) Pause() error {
	if !mc.isReady() {
		return nil
	}
	return mc.ipc.send([]interface{}{"set_property", "pause", true})
}

func (mc *MpvController) Resume() error {
	if !mc.isReady() {
		return nil
	}
	return mc.ipc.send([]interface{}{"set_property", "pause", false})
}

func (mc *MpvController) Stop() error {
	if !mc.isReady() {
		return nil
	}
	return mc.ipc.send([]interface{}{"set_property", "pause", true})
}

// FrameStepForward przesuwa o jedną klatkę do przodu (seek +1/30s).
//
// Używa SendAndWait — blokuje aż mpv potwierdzi wykonanie.
// Worker w main.go naturalnie czeka na powrót funkcji przed obsłużeniem
// kolejnego kroku — gwarantuje serialne przetwarzanie bez race condition.
func (mc *MpvController) FrameStepForward() error {
	if !mc.isReady() {
		return nil
	}
	if err := mc.ipc.SendAndWait(
		[]interface{}{"set_property", "pause", true},
		seekTimeout,
	); err != nil {
		return fmt.Errorf("pause before fwd: %w", err)
	}
	if err := mc.ipc.SendAndWait(
		[]interface{}{"seek", fmt.Sprintf("%.6f", frameStepSec), "relative+exact"},
		seekTimeout,
	); err != nil {
		return fmt.Errorf("fwd seek: %w", err)
	}
	log.Printf("⏩  frame fwd: done")
	return nil
}

// FrameStepBack przesuwa o jedną klatkę do tyłu (seek -1/30s).
func (mc *MpvController) FrameStepBack() error {
	if !mc.isReady() {
		return nil
	}
	if err := mc.ipc.SendAndWait(
		[]interface{}{"set_property", "pause", true},
		seekTimeout,
	); err != nil {
		return fmt.Errorf("pause before back: %w", err)
	}
	if err := mc.ipc.SendAndWait(
		[]interface{}{"seek", fmt.Sprintf("%.6f", -frameStepSec), "relative+exact"},
		seekTimeout,
	); err != nil {
		return fmt.Errorf("back seek: %w", err)
	}
	log.Printf("⏪  frame back: done")
	return nil
}

func (mc *MpvController) Close() {
	mc.ipc.Close()
}
