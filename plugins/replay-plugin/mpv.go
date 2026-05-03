package main

import (
	"encoding/json"
	"fmt"
	"log"
	"sync"
	"syscall"
	"time"
	"unsafe"
)

var (
	kernel32                    = syscall.NewLazyDLL("kernel32.dll")
	procCreateFileW             = kernel32.NewProc("CreateFileW")
	procWriteFile               = kernel32.NewProc("WriteFile")
	procCloseHandle             = kernel32.NewProc("CloseHandle")
	procSetNamedPipeHandleState = kernel32.NewProc("SetNamedPipeHandleState")
)

const (
	GENERIC_WRITE  = 0x40000000
	OPEN_EXISTING  = 3
	INVALID_HANDLE = ^uintptr(0)
	PIPE_NOWAIT    = uintptr(0x00000001) // tryb nieblokujący
)

type MpvIPC struct {
	pipeName string
	handle   uintptr
	mu       sync.Mutex
}

func NewMpvIPC(pipeName string) *MpvIPC {
	return &MpvIPC{pipeName: pipeName}
}

func (m *MpvIPC) Connect(timeout time.Duration) error {
	namePtr, err := syscall.UTF16PtrFromString(m.pipeName)
	if err != nil {
		return fmt.Errorf("invalid pipe name: %w", err)
	}

	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		handle, _, _ := procCreateFileW.Call(
			uintptr(unsafe.Pointer(namePtr)),
			GENERIC_WRITE,
			0, 0,
			OPEN_EXISTING,
			0, 0,
		)
		if handle != INVALID_HANDLE {
			m.handle = handle

			// Ustaw tryb nieblokujący — WriteFile zwraca natychmiast
			// zamiast czekać gdy bufor pipe jest pełny
			mode := PIPE_NOWAIT
			procSetNamedPipeHandleState.Call(handle,
				uintptr(unsafe.Pointer(&mode)), 0, 0)

			log.Printf("✅ mpv IPC connected: %s", m.pipeName)
			return nil
		}
		time.Sleep(100 * time.Millisecond)
	}
	return fmt.Errorf("timeout connecting to mpv pipe: %s", m.pipeName)
}

func (m *MpvIPC) Send(command []interface{}) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.handle == 0 || m.handle == INVALID_HANDLE {
		return fmt.Errorf("mpv IPC not connected")
	}

	data, err := json.Marshal(map[string]interface{}{"command": command})
	if err != nil {
		return err
	}
	data = append(data, '\n')

	written := uint32(0)
	ret, _, callErr := procWriteFile.Call(
		m.handle,
		uintptr(unsafe.Pointer(&data[0])),
		uintptr(len(data)),
		uintptr(unsafe.Pointer(&written)),
		0,
	)
	if ret == 0 {
		// W trybie NOWAIT błąd ERROR_NO_DATA (232) oznacza że bufor pełny
		// — ignoruj, komenda zostanie pominięta (lepsza niż blokada)
		errCode := callErr.(syscall.Errno)
		if errCode == 232 { // ERROR_NO_DATA
			log.Printf("⚠️  mpv IPC busy — komenda pominięta: %v", command[0])
			return nil
		}
		return fmt.Errorf("WriteFile failed: %w", callErr)
	}
	return nil
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

func (mc *MpvController) LoadAndPlay(videoPath string, startMs, endMs int64, speed float64) error {
	if !mc.isReady() {
		return fmt.Errorf("mpv IPC not ready")
	}

	startSec := float64(startMs) / 1000.0
	endSec := float64(endMs) / 1000.0

	log.Printf("▶ replay: %s [%.1fs → %.1fs] x%.2f", videoPath, startSec, endSec, speed)

	startArg := fmt.Sprintf("start=%.3f", startSec)
	if err := mc.ipc.Send([]interface{}{
		"loadfile", videoPath, "replace", 0, startArg,
	}); err != nil {
		return fmt.Errorf("loadfile failed: %w", err)
	}

	time.Sleep(300 * time.Millisecond)

	mc.ipc.Send([]interface{}{"set_property", "speed", speed})
	mc.ipc.Send([]interface{}{"set_property", "ab-loop-a", startSec})
	mc.ipc.Send([]interface{}{"set_property", "ab-loop-b", endSec})

	if err := mc.ipc.Send([]interface{}{"set_property", "pause", false}); err != nil {
		return fmt.Errorf("unpause failed: %w", err)
	}

	return nil
}

func (mc *MpvController) SetSpeed(speed float64) error {
	if !mc.isReady() {
		return fmt.Errorf("mpv IPC not ready")
	}
	log.Printf("⚡ speed → %.2f", speed)
	return mc.ipc.Send([]interface{}{"set_property", "speed", speed})
}

func (mc *MpvController) Pause() error {
	if !mc.isReady() {
		return nil
	}
	return mc.ipc.Send([]interface{}{"set_property", "pause", true})
}

func (mc *MpvController) Resume() error {
	if !mc.isReady() {
		return nil
	}
	return mc.ipc.Send([]interface{}{"set_property", "pause", false})
}

func (mc *MpvController) Stop() error {
	if !mc.isReady() {
		return nil
	}
	mc.ipc.Send([]interface{}{"set_property", "ab-loop-a", "no"})
	mc.ipc.Send([]interface{}{"set_property", "ab-loop-b", "no"})
	return mc.ipc.Send([]interface{}{"set_property", "pause", true})
}

func (mc *MpvController) DisableAbLoop() {
	mc.ipc.Send([]interface{}{"set_property", "ab-loop-a", "no"})
	mc.ipc.Send([]interface{}{"set_property", "ab-loop-b", "no"})
}

func (mc *MpvController) FrameStepForward() error {
	if !mc.isReady() {
		return nil
	}
	return mc.ipc.Send([]interface{}{"frame-step"})
}

func (mc *MpvController) FrameStepBack() error {
	if !mc.isReady() {
		return nil
	}
	return mc.ipc.Send([]interface{}{"frame-back-step"})
}

func (mc *MpvController) Close() {
	mc.ipc.Close()
}
