//go:build windows

package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"
)

// Zgłoszone w próbie ręcznej E2d3c2 (2026-10-19): przy uruchamianiu modułu pojawiało się puste okno terminala. Moduł (venv python.exe)
// uruchamia prawdziwy interpreter jako proces potomny; gdy sam nie ma konsoli (proces odłączony), Windows daje potomkowi NOWĄ, widoczną
// konsolę. Usługi i pluginy mają więc dostawać własną, ukrytą konsolę (dziedziczy ją potomek), a nie żadną.
//
// Tryby pomocnika (GO_CONSOLE_HELPER): "parent" uruchamia siebie w trybie "report" bez żadnych flag (jak venv python.exe) i czeka;
// "report" zapisuje do HELPER_OUT, czy jego okno konsoli jest widoczne.
func TestConsoleHelper(t *testing.T) {
	switch os.Getenv("GO_CONSOLE_HELPER") {
	case "parent":
		child := exec.Command(os.Args[0], "-test.run=TestConsoleHelper")
		child.Env = append(os.Environ(), "GO_CONSOLE_HELPER=report")
		_ = child.Run()
		os.Exit(0)
	case "report":
		k32 := syscall.NewLazyDLL("kernel32.dll")
		u32 := syscall.NewLazyDLL("user32.dll")
		hwnd, _, _ := k32.NewProc("GetConsoleWindow").Call()
		visible := uintptr(0)
		if hwnd != 0 {
			visible, _, _ = u32.NewProc("IsWindowVisible").Call(hwnd)
		}
		os.WriteFile(os.Getenv("HELPER_OUT"), []byte(fmt.Sprintf("hwnd=%d visible=%d", hwnd, visible)), 0o644)
		os.Exit(0)
	}
}

func TestDetachedChildOfServiceGetsNoVisibleConsoleWindow(t *testing.T) {
	out := filepath.Join(t.TempDir(), "konsola.txt")
	cmd := exec.Command(os.Args[0], "-test.run=TestConsoleHelper")
	cmd.Env = append(os.Environ(), "GO_CONSOLE_HELPER=parent", "HELPER_OUT="+out)
	cmd.SysProcAttr = detachedAttr() // tak HUB uruchamia usługi (moduł) i pluginy
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	select {
	case <-done:
	case <-time.After(20 * time.Second):
		killTree(cmd.Process.Pid)
		t.Fatal("pomocnik nie zakończył się w 20 s")
	}
	data, err := os.ReadFile(out)
	if err != nil {
		t.Fatalf("potomek nie zapisał stanu konsoli: %v", err)
	}
	if !strings.Contains(string(data), "visible=0") {
		t.Fatalf("potomek usługi dostał widoczne okno konsoli (%s): przy uruchamianiu modułu pojawia się puste okno terminala", data)
	}
}
