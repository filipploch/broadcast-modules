//go:build !windows

package main

import "fmt"

func windowsOfProcess(pid int) []windowInfo { return nil }

func closeMainWindow(pid int) error { return fmt.Errorf("zamykanie okna OBS jest obsługiwane tylko na Windowsie") }
