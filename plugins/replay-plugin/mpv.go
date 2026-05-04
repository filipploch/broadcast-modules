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
	kernel32        = syscall.NewLazyDLL("kernel32.dll")
	procCreateFileW = kernel32.NewProc("CreateFileW")
	procWriteFile   = kernel32.NewProc("WriteFile")
	procCloseHandle = kernel32.NewProc("CloseHandle")
)

const (
	GENERIC_WRITE  = 0x40000000
	OPEN_EXISTING  = 3
	INVALID_HANDLE = ^uintptr(0)
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

	var lastErr error
	for attempt := 1; attempt <= 5; attempt++ {
		written := uint32(0)
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

		lastErr = fmt.Errorf("WriteFile failed: %w", callErr)
		if ret != 0 {
			lastErr = fmt.Errorf("WriteFile incomplete: wrote %d/%d bytes", written, len(data))
		}

		errno, ok := callErr.(syscall.Errno)
		if ok && (errno == 231 || errno == 232 || errno == 233) {
			// ERROR_PIPE_BUSY / ERROR_NO_DATA / ERROR_PIPE_NOT_CONNECTED.
			// Po długich sekwencjach frame-step mpv potrafi chwilowo nie odbierać IPC.
			time.Sleep(time.Duration(attempt*50) * time.Millisecond)
			continue
		}

		if ret == 0 {
			time.Sleep(time.Duration(attempt*50) * time.Millisecond)
			continue
		}
	}

	return lastErr
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

	// Przed załadowaniem kolejnego replaya twardo czyścimy stan mpv.
	// To zapobiega pozostawieniu starej klatki po długim frame-step/frame-back-step.
	if err := mc.ipc.Send([]interface{}{"set_property", "pause", true}); err != nil {
		return fmt.Errorf("pre-pause failed: %w", err)
	}
	if err := mc.DisableAbLoop(); err != nil {
		return fmt.Errorf("pre-disable ab-loop failed: %w", err)
	}

	startArg := fmt.Sprintf("start=%.3f", startSec)
	if err := mc.ipc.Send([]interface{}{
		"loadfile", videoPath, "replace", 0, startArg,
	}); err != nil {
		return fmt.Errorf("loadfile failed: %w", err)
	}

	time.Sleep(300 * time.Millisecond)

	if err := mc.ipc.Send([]interface{}{"set_property", "speed", speed}); err != nil {
		return fmt.Errorf("set speed failed: %w", err)
	}
	if err := mc.ipc.Send([]interface{}{"set_property", "ab-loop-a", startSec}); err != nil {
		return fmt.Errorf("set ab-loop-a failed: %w", err)
	}
	if err := mc.ipc.Send([]interface{}{"set_property", "ab-loop-b", endSec}); err != nil {
		return fmt.Errorf("set ab-loop-b failed: %w", err)
	}

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
	if err := mc.DisableAbLoop(); err != nil {
		return err
	}
	return mc.ipc.Send([]interface{}{"set_property", "pause", true})
}

func (mc *MpvController) DisableAbLoop() error {
	if !mc.isReady() {
		return nil
	}
	if err := mc.ipc.Send([]interface{}{"set_property", "ab-loop-a", "no"}); err != nil {
		return err
	}
	return mc.ipc.Send([]interface{}{"set_property", "ab-loop-b", "no"})
}

func (mc *MpvController) FrameStepForward() error {
	if !mc.isReady() {
		return nil
	}
	if err := mc.ipc.Send([]interface{}{"set_property", "pause", true}); err != nil {
		return err
	}
	return mc.ipc.Send([]interface{}{"frame-step"})
}

func (mc *MpvController) FrameStepBack() error {
	if !mc.isReady() {
		return nil
	}
	if err := mc.ipc.Send([]interface{}{"set_property", "pause", true}); err != nil {
		return err
	}
	return mc.ipc.Send([]interface{}{"frame-back-step"})
}

func (mc *MpvController) Close() {
	mc.ipc.Close()
}
