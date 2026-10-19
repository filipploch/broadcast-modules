//go:build !windows

package main

import "os"

func runWindowAtrapa() { os.Exit(4) }
