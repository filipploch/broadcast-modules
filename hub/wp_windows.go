//go:build windows

package main

import (
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"
)

var (
	iphlpapi                = syscall.NewLazyDLL("iphlpapi.dll")
	procGetExtendedTcpTable = iphlpapi.NewProc("GetExtendedTcpTable")
	kernel32wp              = syscall.NewLazyDLL("kernel32.dll")
	procQueryImageName      = kernel32wp.NewProc("QueryFullProcessImageNameW")
)

const (
	afInet                  = 2
	tcpTableOwnerPidListen  = 3 // TCP_TABLE_OWNER_PID_LISTENER
	errorInsufficientBuffer = 122
)

// mibTCPRowOwnerPID to MIB_TCPROW_OWNER_PID.
type mibTCPRowOwnerPID struct {
	State      uint32
	LocalAddr  uint32
	LocalPort  uint32
	RemoteAddr uint32
	RemotePort uint32
	OwningPID  uint32
}

// listenerPIDOnPort zwraca PID procesu nasłuchującego (IPv4) na porcie. Nie zależy od języka systemu (bez netstat).
func listenerPIDOnPort(port int) (int, bool) {
	var size uint32
	for i := 0; i < 3; i++ {
		var buf []byte
		if size > 0 {
			buf = make([]byte, size)
		}
		var ptr uintptr
		if len(buf) > 0 {
			ptr = uintptr(unsafe.Pointer(&buf[0]))
		}
		r, _, _ := procGetExtendedTcpTable.Call(ptr, uintptr(unsafe.Pointer(&size)), 0, afInet, tcpTableOwnerPidListen, 0)
		if r == errorInsufficientBuffer {
			continue
		}
		if r != 0 || len(buf) < 4 {
			return 0, false
		}
		n := *(*uint32)(unsafe.Pointer(&buf[0]))
		rowSize := unsafe.Sizeof(mibTCPRowOwnerPID{})
		for k := uint32(0); k < n; k++ {
			off := 4 + uintptr(k)*rowSize
			if off+rowSize > uintptr(len(buf)) {
				break
			}
			row := (*mibTCPRowOwnerPID)(unsafe.Pointer(&buf[off]))
			p := (row.LocalPort&0xff)<<8 | (row.LocalPort>>8)&0xff
			if int(p) == port {
				return int(row.OwningPID), true
			}
		}
		return 0, false
	}
	return 0, false
}

// processImageEquals sprawdza, czy proces o danym PID to dokładnie ten plik wykonywalny (np. php.exe z folderu WP).
func processImageEquals(pid int, want string) bool {
	h, err := syscall.OpenProcess(processQueryLimited, false, uint32(pid))
	if err != nil {
		return false
	}
	defer syscall.CloseHandle(h)
	buf := make([]uint16, 1024)
	size := uint32(len(buf))
	r, _, _ := procQueryImageName.Call(uintptr(h), 0, uintptr(unsafe.Pointer(&buf[0])), uintptr(unsafe.Pointer(&size)))
	if r == 0 {
		return false
	}
	got := syscall.UTF16ToString(buf[:size])
	return strings.EqualFold(filepath.Clean(got), filepath.Clean(want))
}
