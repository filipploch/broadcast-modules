package main

import "fmt"

// launchWpProcess uruchamia proces WP odłączony od konsoli HUB-a, z wyjściem prosto do pliku w folderze logów uruchomienia
// (proces przeżywa awarię HUB-a, jak usługi z service_manager.go).
func launchWpProcess(c wpCommand, outName string) (*wpProc, error) {
	out, outPath, err := openServiceOutput(outName)
	if err != nil {
		return nil, fmt.Errorf("nie można otworzyć pliku wyjścia %s: %v", outPath, err)
	}
	cmd := c.exec()
	cmd.Stdin = nil
	cmd.Stdout, cmd.Stderr = out, out
	cmd.SysProcAttr = detachedAttr()
	if err := cmd.Start(); err != nil {
		out.Close()
		return nil, err
	}
	out.Close() // proces ma własny uchwyt
	return &wpProc{pid: cmd.Process.Pid, wait: func() error { return cmd.Wait() }}, nil
}
