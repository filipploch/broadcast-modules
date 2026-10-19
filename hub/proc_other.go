//go:build !windows

package main

import (
	"os"
	"syscall"
)

func detachedAttr() *syscall.SysProcAttr { return &syscall.SysProcAttr{Setsid: true} }

func windowedAttr() *syscall.SysProcAttr { return &syscall.SysProcAttr{Setsid: true} }

func killTree(pid int) error {
	if err := syscall.Kill(-pid, syscall.SIGKILL); err == nil {
		return nil
	}
	return syscall.Kill(pid, syscall.SIGKILL)
}

func openShared(path string) (*os.File, error) { return os.Open(path) }
