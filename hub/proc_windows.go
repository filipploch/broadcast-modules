//go:build windows

package main

import (
	"os"
	"os/exec"
	"strconv"
	"syscall"
)

const (
	createNewProcessGroup = 0x00000200
	createNoWindow        = 0x08000000
)

// detachedAttr: proces bez konsoli HUB-a i we własnej grupie procesów. Nie ginie przy zamknięciu okna HUB-a,
// przy Ctrl+C w jego konsoli ani po jego awarii (bez obiektu zadania, który zabijałby procesy potomne razem z HUB-em).
// Proces dostaje własną, UKRYTĄ konsolę (CREATE_NO_WINDOW), a nie żadną (DETACHED_PROCESS): moduł (venv python.exe) uruchamia
// prawdziwy interpreter jako proces potomny, który bez konsoli rodzica dostawał nową, widoczną i pustą (próba ręczna E2d3c2;
// test TestDetachedChildOfServiceGetsNoVisibleConsoleWindow). Ukrytą konsolę dziedziczy potomek, więc okno się nie pojawia.
func detachedAttr() *syscall.SysProcAttr {
	return &syscall.SysProcAttr{CreationFlags: createNewProcessGroup | createNoWindow}
}

// killTree kończy proces wraz z całym drzewem procesów potomnych (wymuszenie).
// Samo kończenie procesu głównego nie wystarcza: venv uruchamia prawdziwy interpreter jako proces potomny.
func killTree(pid int) error {
	return exec.Command("taskkill", "/F", "/T", "/PID", strconv.Itoa(pid)).Run()
}

// openShared otwiera plik do czytania tak, żeby nie blokować jego zmiany nazwy ani usunięcia przez zapisującego
// (rotacja logu po stronie Pythona). Domyślne os.Open w Go nie ustawia FILE_SHARE_DELETE.
func openShared(path string) (*os.File, error) {
	p, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return nil, err
	}
	h, err := syscall.CreateFile(p, syscall.GENERIC_READ,
		syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE|syscall.FILE_SHARE_DELETE,
		nil, syscall.OPEN_EXISTING, syscall.FILE_ATTRIBUTE_NORMAL, 0)
	if err != nil {
		return nil, &os.PathError{Op: "open", Path: path, Err: err}
	}
	return os.NewFile(uintptr(h), path), nil
}
