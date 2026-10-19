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

// OBS (program okienkowy) jest jawnie wyłączony z ukrytej konsoli: dostaje dawne atrybuty (własna grupa, bez konsoli).
// Ukrytą konsolę dostają wyłącznie programy konsolowe: moduł (usługa) i pluginy lokalne.
func TestObsIsWindowedWithoutHiddenConsole(t *testing.T) {
	c := &LoadedHubConfig{HubConfig: defaultHubConfig(), Root: t.TempDir()}
	obs, ok := c.obsService()
	if !ok || !obs.WindowedApp {
		t.Fatalf("usługa OBS powinna być oznaczona jako program okienkowy: %+v", obs)
	}
	if f := serviceAttr(obs).CreationFlags; f&createNoWindow != 0 || f&detachedProcess == 0 || f&createNewProcessGroup == 0 {
		t.Fatalf("OBS: flagi %#x, oczekiwano grupy procesów i DETACHED_PROCESS bez CREATE_NO_WINDOW", f)
	}
	mod := c.moduleServiceFor(ModuleManifest{Format: 1, ID: "nalf", Button: "N", Script: "modules/nalf.py", Port: 8081})
	if mod.WindowedApp {
		t.Fatal("moduł nie jest programem okienkowym")
	}
	if f := serviceAttr(mod).CreationFlags; f&createNoWindow == 0 || f&detachedProcess != 0 {
		t.Fatalf("moduł: flagi %#x, oczekiwano ukrytej konsoli (CREATE_NO_WINDOW) bez DETACHED_PROCESS", f)
	}
	if f := detachedAttr().CreationFlags; f&createNoWindow == 0 { // pluginy lokalne (plugin_manager.go) używają detachedAttr
		t.Fatalf("pluginy lokalne: flagi %#x bez ukrytej konsoli", f)
	}
}
