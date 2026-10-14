//go:build !windows

package main

import "fmt"

func processCreationTime(pid int) (uint64, bool) { return 0, false }

type processHandle struct{}

func openProcessIdentity(pid int, created uint64) (*processHandle, error) {
	return nil, fmt.Errorf("przejmowanie procesów jest obsługiwane tylko na Windowsie")
}
func (p *processHandle) wait() (int, error) { return 0, fmt.Errorf("nieobsługiwane") }
func (p *processHandle) close()             {}
func findProcessesByName(name string) []int { return nil }
