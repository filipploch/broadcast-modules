package main

import (
	"testing"
	"time"
)

// E2d1: po starcie OBS (ostatniego w kolejności) plugin ma połączyć się w kilka sekund, nie po pół minuty.
func TestOBSReconnectBackoffIsShort(t *testing.T) {
	if obsMaxBackoff > 5*time.Second {
		t.Fatalf("maksymalny odstęp ponawiania %v > 5 s", obsMaxBackoff)
	}
	if obsInitialBackoff > obsMaxBackoff {
		t.Fatalf("odstęp początkowy %v większy niż maksymalny %v", obsInitialBackoff, obsMaxBackoff)
	}
}
