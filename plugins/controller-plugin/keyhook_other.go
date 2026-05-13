//go:build !windows

package main

// Stub niedostępny pod nie-Windows. Plugin i tak odmówi startu w main.go
// (sprawdzenie runtime.GOOS), ale dzięki temu plikowi 'go vet' / 'go build'
// nie wywala się przy kompilacji krzyżowej.

import "fmt"

type ControllerEvent struct {
	Logical string
}

func runKeyHook(bindings []HookBinding, ch chan ControllerEvent) error {
	return fmt.Errorf("keyboard hook only supported on Windows")
}

func stopKeyHook() {}
