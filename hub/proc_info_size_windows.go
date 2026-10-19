//go:build windows

package main

import (
	"syscall"
	"unsafe"
)

func unsafeSizeofProcessEntry() uintptr { return unsafe.Sizeof(syscall.ProcessEntry32{}) }
