//go:build windows

package main

import (
	"fmt"
	"strings"
	"syscall"
	"time"
)

const (
	processQueryLimited = 0x1000
	processSynchronize  = 0x00100000
	stillActive         = 259
)

// processCreationTime zwraca czas utworzenia procesu (FILETIME jako liczba) albo false, gdy procesu nie ma / brak dostępu.
// Para (numer procesu, czas utworzenia) rozpoznaje proces jednoznacznie: numery są używane ponownie.
func processCreationTime(pid int) (uint64, bool) {
	h, err := syscall.OpenProcess(processQueryLimited, false, uint32(pid))
	if err != nil {
		return 0, false
	}
	defer syscall.CloseHandle(h)
	var code uint32
	if err := syscall.GetExitCodeProcess(h, &code); err != nil || code != stillActive {
		return 0, false // proces już się zakończył (uchwyt może jeszcze istnieć u kogoś innego)
	}
	var c, e, k, u syscall.Filetime
	if err := syscall.GetProcessTimes(h, &c, &e, &k, &u); err != nil {
		return 0, false
	}
	return uint64(c.HighDateTime)<<32 | uint64(c.LowDateTime), true
}

// processHandle trzyma uchwyt cudzego procesu (nie dziecka HUB-a), żeby poznać jego kod wyjścia po zakończeniu.
type processHandle struct{ h syscall.Handle }

// openProcessIdentity otwiera uchwyt procesu tylko wtedy, gdy żyje i jego czas utworzenia zgadza się z oczekiwanym.
func openProcessIdentity(pid int, created uint64) (*processHandle, error) {
	h, err := syscall.OpenProcess(processQueryLimited|processSynchronize, false, uint32(pid))
	if err != nil {
		return nil, err
	}
	var code uint32
	if err := syscall.GetExitCodeProcess(h, &code); err != nil || code != stillActive {
		syscall.CloseHandle(h)
		return nil, fmt.Errorf("proces %d już się zakończył", pid)
	}
	var c, e, k, u syscall.Filetime
	if err := syscall.GetProcessTimes(h, &c, &e, &k, &u); err != nil {
		syscall.CloseHandle(h)
		return nil, err
	}
	if got := uint64(c.HighDateTime)<<32 | uint64(c.LowDateTime); got != created {
		syscall.CloseHandle(h)
		return nil, fmt.Errorf("proces %d ma inny czas utworzenia (to nie ten sam proces)", pid)
	}
	return &processHandle{h}, nil
}

// wait czeka na zakończenie procesu i zwraca jego kod wyjścia (znany, bo trzymamy uchwyt od czasu, gdy proces żył).
func (p *processHandle) wait() (int, error) {
	if ev, err := syscall.WaitForSingleObject(p.h, syscall.INFINITE); err != nil || ev != syscall.WAIT_OBJECT_0 {
		return 0, fmt.Errorf("oczekiwanie na proces: %v (zdarzenie %d)", err, ev)
	}
	var code uint32
	if err := syscall.GetExitCodeProcess(p.h, &code); err != nil {
		return 0, err
	}
	return int(code), nil
}

func (p *processHandle) close() { syscall.CloseHandle(p.h) }

// findProcessesByName zwraca numery procesów o danej nazwie pliku (bez rozróżniania wielkości liter).
func findProcessesByName(name string) []int {
	snap, err := syscall.CreateToolhelp32Snapshot(syscall.TH32CS_SNAPPROCESS, 0)
	if err != nil {
		return nil
	}
	defer syscall.CloseHandle(snap)
	var entry syscall.ProcessEntry32
	entry.Size = uint32(unsafeSizeofProcessEntry())
	var pids []int
	if err := syscall.Process32First(snap, &entry); err != nil {
		return nil
	}
	for {
		if strings.EqualFold(syscall.UTF16ToString(entry.ExeFile[:]), name) {
			pids = append(pids, int(entry.ProcessID))
		}
		if err := syscall.Process32Next(snap, &entry); err != nil {
			break
		}
	}
	return pids
}

// sleepShort: krótka przerwa używana przy sprawdzaniu zakończenia procesu.
func sleepShort() { time.Sleep(50 * time.Millisecond) }
