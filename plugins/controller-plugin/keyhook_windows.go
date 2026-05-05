package main

// Windows low-level keyboard hook (WH_KEYBOARD_LL).
//
// Plik kompilowany WYŁĄCZNIE pod Windows (sufix _windows.go w nazwie pliku
// to wbudowane build constraint Go).
//
// Działanie:
//   1. SetWindowsHookExW instaluje globalny hook na klawiaturę.
//   2. Każde naciśnięcie klawisza trafia do hookProc PRZED dotarciem do innych
//      aplikacji (włącznie z OBS / mpv / przeglądarką).
//   3. Jeśli vkCode jest w mapie (klawisze przypisane do kontrolera), event
//      jest pochłaniany (return 1) i logiczna nazwa trafia do eventCh.
//   4. Inne klawisze są przekazywane dalej (CallNextHookEx).
//
// Uwagi techniczne:
//   - Hook musi działać w wątku z pętlą wiadomości Win32 (GetMessage/Dispatch),
//     dlatego runKeyHook robi runtime.LockOSThread() i sam pompuje wiadomości.
//   - hookProc jest wołany przez Windows w kontekście naszego wątku — może
//     bezpiecznie pisać do mapy keysDown bez locka, bo nikt inny jej nie tyka.
//   - Wysyłka do eventCh jest non-blocking (select default → drop) żeby
//     hookProc nigdy nie zablokował systemowej pompy klawiatury.
//   - Auto-repeat klawiszy (gdy operator trzyma przycisk) jest dedupowany:
//     drugi i kolejny KEYDOWN przed KEYUP są ignorowane, ale dalej blokowane,
//     żeby nie przeciekały do innych aplikacji.

import (
	"fmt"
	"log"
	"runtime"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
)

const (
	whKeyboardLL = 13
	hcAction     = 0
	wmKeyDown    = 0x0100
	wmKeyUp      = 0x0101
	wmSysKeyDown = 0x0104
	wmSysKeyUp   = 0x0105
	wmQuit       = 0x0012

	vkShift   = 0x10
	vkControl = 0x11
	vkMenu    = 0x12 // Alt
	vkLWin    = 0x5B
	vkRWin    = 0x5C
)

type kbdllhookstruct struct {
	VkCode      uint32
	ScanCode    uint32
	Flags       uint32
	Time        uint32
	DwExtraInfo uintptr
}

// msg — układ struktury MSG z user32.h. Pola muszą być w tej kolejności
// i z dokładnymi rozmiarami, bo GetMessageW wypełnia je przez wskaźnik.
type msg struct {
	Hwnd    uintptr
	Message uint32
	WParam  uintptr
	LParam  uintptr
	Time    uint32
	PtX     int32
	PtY     int32
}

var (
	user32   = windows.NewLazySystemDLL("user32.dll")
	kernel32 = windows.NewLazySystemDLL("kernel32.dll")
	ntdll    = windows.NewLazySystemDLL("ntdll.dll")

	procSetWindowsHookExW   = user32.NewProc("SetWindowsHookExW")
	procUnhookWindowsHookEx = user32.NewProc("UnhookWindowsHookEx")
	procCallNextHookEx      = user32.NewProc("CallNextHookEx")
	procGetMessageW         = user32.NewProc("GetMessageW")
	procTranslateMessage    = user32.NewProc("TranslateMessage")
	procDispatchMessageW    = user32.NewProc("DispatchMessageW")
	procPostThreadMessageW  = user32.NewProc("PostThreadMessageW")
	procGetAsyncKeyState    = user32.NewProc("GetAsyncKeyState")
	procGetCurrentThreadId  = kernel32.NewProc("GetCurrentThreadId")
	procGetModuleHandleW    = kernel32.NewProc("GetModuleHandleW")
	procRtlMoveMemory       = ntdll.NewProc("RtlMoveMemory")
)

// ── Globalne stany hook'a ────────────────────────────────────────────────────
// Ustawiane raz przed startem hook'a; potem czytane wyłącznie w hookProc.

var (
	keyMap     map[uint32][]HookBinding // vkCode → jedno albo więcej wiązań z modyfikatorami
	eventCh    chan ControllerEvent
	hookHandle uintptr
	hookThread uint32
	keysDown   = make(map[uint32]bool) // dedup auto-repeat
)

// ControllerEvent jest produkowany przez hookProc i konsumowany w main.go.
type ControllerEvent struct {
	Logical string
}

// runKeyHook instaluje globalny hook i blokuje na pompie wiadomości.
// Wywoływać w dedykowanej goroutine — zajmuje cały OS-wątek do końca życia.
func runKeyHook(bindings []HookBinding, ch chan ControllerEvent) error {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()

	keyMap = make(map[uint32][]HookBinding)
	for _, b := range bindings {
		keyMap[b.VK] = append(keyMap[b.VK], b)
	}
	eventCh = ch

	tid, _, _ := procGetCurrentThreadId.Call()
	hookThread = uint32(tid)

	hMod, _, e := procGetModuleHandleW.Call(0)
	if hMod == 0 {
		return fmt.Errorf("GetModuleHandleW: %v", e)
	}

	cb := syscall.NewCallback(hookProc)
	h, _, e := procSetWindowsHookExW.Call(
		uintptr(whKeyboardLL),
		cb,
		hMod,
		0,
	)
	if h == 0 {
		return fmt.Errorf("SetWindowsHookEx: %v", e)
	}
	hookHandle = h
	log.Printf("🎹 Keyboard hook installed (handle=0x%x, thread=%d)", hookHandle, hookThread)
	log.Printf("   Capturing %d keys", len(keyMap))

	// Pompa wiadomości — trzyma hook'a aktywnym dopóki nie dostanie WM_QUIT.
	var m msg
	for {
		r, _, _ := procGetMessageW.Call(uintptr(unsafe.Pointer(&m)), 0, 0, 0)
		// GetMessage zwraca:
		//   0  → WM_QUIT (kończymy)
		//   -1 → błąd
		//   >0 → normalna wiadomość
		if int32(r) <= 0 {
			break
		}
		procTranslateMessage.Call(uintptr(unsafe.Pointer(&m)))
		procDispatchMessageW.Call(uintptr(unsafe.Pointer(&m)))
	}

	procUnhookWindowsHookEx.Call(hookHandle)
	log.Printf("⏹  Keyboard hook removed")
	return nil
}

// stopKeyHook wybudza pętlę wiadomości w wątku hook'a.
// Wywoływać z innego wątku przy zatrzymaniu pluginu.
func stopKeyHook() {
	if hookThread != 0 {
		procPostThreadMessageW.Call(uintptr(hookThread), wmQuit, 0, 0)
	}
}

func isKeyDown(vk uintptr) bool {
	r, _, _ := procGetAsyncKeyState.Call(vk)
	return r&0x8000 != 0
}

func modifiersMatch(b HookBinding) bool {
	if b.Ctrl && !isKeyDown(vkControl) {
		return false
	}
	if b.Shift && !isKeyDown(vkShift) {
		return false
	}
	if b.Alt && !isKeyDown(vkMenu) {
		return false
	}
	if b.Win && !(isKeyDown(vkLWin) || isKeyDown(vkRWin)) {
		return false
	}
	return true
}

func matchingBinding(bindings []HookBinding) (HookBinding, bool) {
	for _, b := range bindings {
		if modifiersMatch(b) {
			return b, true
		}
	}
	return HookBinding{}, false
}

// hookProc — callback wołany przez Windows na każde naciśnięcie klawisza.
// MUSI być szybki (timeout systemowy ~300ms — przekroczenie powoduje że
// Windows pomija hook dla tego eventu i może go całkiem wyłączyć).
func hookProc(nCode int32, wParam uintptr, lParam uintptr) uintptr {
	if nCode != hcAction {
		r, _, _ := procCallNextHookEx.Call(0, uintptr(nCode), wParam, lParam)
		return r
	}

	// lParam dla WH_KEYBOARD_LL wskazuje na KBDLLHOOKSTRUCT. Kopiujemy strukturę
	// do lokalnej zmiennej zamiast robić konwersję uintptr -> unsafe.Pointer,
	// żeby uniknąć ostrzeżenia go vet: "possible misuse of unsafe.Pointer".
	var kb kbdllhookstruct
	procRtlMoveMemory.Call(
		uintptr(unsafe.Pointer(&kb)),
		lParam,
		unsafe.Sizeof(kb),
	)

	bindings, mineVK := keyMap[kb.VkCode]
	if !mineVK {
		// To nie nasz klawisz — przepuść go normalną drogą.
		r, _, _ := procCallNextHookEx.Call(0, uintptr(nCode), wParam, lParam)
		return r
	}

	switch wParam {
	case wmKeyDown, wmSysKeyDown:
		b, ok := matchingBinding(bindings)
		if !ok {
			// To jest np. samo F1 bez Ctrl — przepuść normalnie.
			r, _, _ := procCallNextHookEx.Call(0, uintptr(nCode), wParam, lParam)
			return r
		}

		if !keysDown[kb.VkCode] {
			keysDown[kb.VkCode] = true
			// Non-blocking wysyłka — jeśli kanał pełny, droppujemy żeby nie
			// zablokować systemowej pompy klawiatury.
			select {
			case eventCh <- ControllerEvent{Logical: b.Logical}:
			default:
				// Brak miejsca — strata jednego eventu lepsze niż zablokowanie hook'a.
			}
		}
		return 1 // pochłoń tylko dopasowaną kombinację, np. Ctrl+F1

	case wmKeyUp, wmSysKeyUp:
		if keysDown[kb.VkCode] {
			keysDown[kb.VkCode] = false
			return 1
		}
		// KEYUP dla klawisza, którego KEYDOWN nie spełnił modyfikatorów, przepuszczamy.
		r, _, _ := procCallNextHookEx.Call(0, uintptr(nCode), wParam, lParam)
		return r
	}

	r, _, _ := procCallNextHookEx.Call(0, uintptr(nCode), wParam, lParam)
	return r
}
