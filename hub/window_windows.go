//go:build windows

package main

import (
	"fmt"
	"syscall"
	"unsafe"
)

var (
	user32                       = syscall.NewLazyDLL("user32.dll")
	procEnumWindows              = user32.NewProc("EnumWindows")
	procGetWindowThreadProcessID = user32.NewProc("GetWindowThreadProcessId")
	procIsWindowVisible          = user32.NewProc("IsWindowVisible")
	procGetWindow                = user32.NewProc("GetWindow")
	procGetWindowLongW           = user32.NewProc("GetWindowLongW")
	procGetWindowTextW           = user32.NewProc("GetWindowTextW")
	procGetClassNameW            = user32.NewProc("GetClassNameW")
	procPostMessageW             = user32.NewProc("PostMessageW")
)

const (
	gwOwner         = 4
	gwlExStyle      = ^uintptr(19) // -20
	wsExToolWindow  = 0x00000080
	wmClose         = 0x0010
	windowTextLimit = 512
)

// windowsOfProcess zwraca okna najwyższego poziomu należące do procesu.
func windowsOfProcess(pid int) []windowInfo {
	var out []windowInfo
	cb := syscall.NewCallback(func(hwnd uintptr, _ uintptr) uintptr {
		var wpid uint32
		procGetWindowThreadProcessID.Call(hwnd, uintptr(unsafe.Pointer(&wpid)))
		if int(wpid) != pid {
			return 1
		}
		visible, _, _ := procIsWindowVisible.Call(hwnd)
		owner, _, _ := procGetWindow.Call(hwnd, gwOwner)
		style, _, _ := procGetWindowLongW.Call(hwnd, gwlExStyle)
		out = append(out, windowInfo{
			Hwnd:       hwnd,
			Title:      windowText(procGetWindowTextW, hwnd),
			Class:      windowText(procGetClassNameW, hwnd),
			Visible:    visible != 0,
			Owner:      owner,
			ToolWindow: uint32(style)&wsExToolWindow != 0,
		})
		return 1 // dalej
	})
	procEnumWindows.Call(cb, 0)
	return out
}

func windowText(proc *syscall.LazyProc, hwnd uintptr) string {
	buf := make([]uint16, windowTextLimit)
	n, _, _ := proc.Call(hwnd, uintptr(unsafe.Pointer(&buf[0])), uintptr(len(buf)))
	return syscall.UTF16ToString(buf[:n])
}

// closeMainWindow wysyła WM_CLOSE (jak kliknięcie X) wyłącznie do okna głównego procesu OBS. Błąd, gdy okna nie znaleziono.
func closeMainWindow(pid int) error {
	hwnd, ok := selectMainWindow(windowsOfProcess(pid))
	if !ok {
		return fmt.Errorf("nie znaleziono okna głównego procesu %d", pid)
	}
	if r, _, err := procPostMessageW.Call(hwnd, wmClose, 0, 0); r == 0 {
		return fmt.Errorf("PostMessage(WM_CLOSE) nie powiodło się: %v", err)
	}
	return nil
}
