//go:build !windows

package main

// Poza Windowsem instancje WP nie są wykrywane po porcie (HUB działa na Windowsie); testy podmieniają wpOS.

func listenerPIDOnPort(port int) (int, bool) { return 0, false }

func processImageEquals(pid int, want string) bool { return false }
