//go:build windows

// Program pomocniczy prób (nie wchodzi do wersji transmisyjnej): atrapa OBS z oknami i portem, do prób z HUB-em bez prawdziwego OBS.
// Zmienne: OBS_ATRAPA_PORT (port nasłuchu jak obs-websocket), OBS_ATRAPA_LOG (plik, do którego trafiają argumenty startu, katalog
// roboczy i zdarzenia WM_CLOSE), OBS_ATRAPA_IGNORE_CLOSE=1 (okno główne ignoruje zamknięcie).
package main

import (
	"fmt"
	"net"
	"net/http"
	"os"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

// Atrapa OBS z oknami (tylko testy): okno główne (klasa Qt6QWindowIcon, tytuł "OBS 30.0 - Profile: test"), okno pomocnicze z właścicielem
// (jak dok przypięty do okna głównego) i okno narzędziowe bez właściciela (jak odpięty dok). Okna leżą poza ekranem (-32000), nic nie
// miga na pulpicie. Reakcja na WM_CLOSE jest zapisywana jako plik w HELPER_MARKER_DIR; okno główne kończy proces kodem 0
// (chyba że OBS_ATRAPA_IGNORE_CLOSE=1). Atrapa nasłuchuje też na OBS_ATRAPA_PORT jak port obs-websocket.

var (
	atrUser32            = syscall.NewLazyDLL("user32.dll")
	atrKernel32          = syscall.NewLazyDLL("kernel32.dll")
	atrRegisterClassExW  = atrUser32.NewProc("RegisterClassExW")
	atrCreateWindowExW   = atrUser32.NewProc("CreateWindowExW")
	atrDefWindowProcW    = atrUser32.NewProc("DefWindowProcW")
	atrGetMessageW       = atrUser32.NewProc("GetMessageW")
	atrTranslateMessage  = atrUser32.NewProc("TranslateMessage")
	atrDispatchMessageW  = atrUser32.NewProc("DispatchMessageW")
	atrPostQuitMessage   = atrUser32.NewProc("PostQuitMessage")
	atrGetModuleHandleW  = atrKernel32.NewProc("GetModuleHandleW")
	atrGetWindowTextWLen = atrUser32.NewProc("GetWindowTextW")
)

type wndClassEx struct {
	cbSize        uint32
	style         uint32
	lpfnWndProc   uintptr
	cbClsExtra    int32
	cbWndExtra    int32
	hInstance     uintptr
	hIcon         uintptr
	hCursor       uintptr
	hbrBackground uintptr
	lpszMenuName  *uint16
	lpszClassName *uint16
	hIconSm       uintptr
}

type winMsg struct {
	hwnd    uintptr
	message uint32
	wParam  uintptr
	lParam  uintptr
	time    uint32
	ptX     int32
	ptY     int32
}

func atrapaTitle(hwnd uintptr) string {
	buf := make([]uint16, 256)
	n, _, _ := atrGetWindowTextWLen.Call(hwnd, uintptr(unsafe.Pointer(&buf[0])), uintptr(len(buf)))
	return syscall.UTF16ToString(buf[:n])
}

func atrapaMarker(name string) {
	if path := os.Getenv("OBS_ATRAPA_LOG"); path != "" {
		if f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644); err == nil {
			fmt.Fprintf(f, "%s %s\n", time.Now().Format("15:04:05.000"), name)
			f.Close()
		}
	}
}

func main() {
	runtime.LockOSThread()
	cwd, _ := os.Getwd()
	atrapaMarker(fmt.Sprintf("start pid=%d cwd=%s args=%v", os.Getpid(), cwd, os.Args[1:]))
	ignore := os.Getenv("OBS_ATRAPA_IGNORE_CLOSE") == "1"

	wndProc := syscall.NewCallback(func(hwnd, msg, wParam, lParam uintptr) uintptr {
		if msg == 0x0010 { // WM_CLOSE
			title := atrapaTitle(hwnd)
			if strings.HasPrefix(title, "OBS ") {
				atrapaMarker("main-got-close")
				if !ignore {
					atrPostQuitMessage.Call(0)
				}
			} else {
				atrapaMarker("dock-got-close-" + strings.ReplaceAll(title, " ", "_"))
			}
			return 0
		}
		r, _, _ := atrDefWindowProcW.Call(hwnd, msg, wParam, lParam)
		return r
	})
	hInst, _, _ := atrGetModuleHandleW.Call(0)
	className, _ := syscall.UTF16PtrFromString("Qt6QWindowIcon")
	wc := wndClassEx{lpfnWndProc: wndProc, hInstance: hInst, lpszClassName: className}
	wc.cbSize = uint32(unsafe.Sizeof(wc))
	if r, _, _ := atrRegisterClassExW.Call(uintptr(unsafe.Pointer(&wc))); r == 0 {
		fmt.Println("NO_WINDOW class")
		os.Exit(4)
	}
	create := func(exStyle uintptr, title string, style uintptr, owner uintptr) uintptr {
		t, _ := syscall.UTF16PtrFromString(title)
		h, _, _ := atrCreateWindowExW.Call(exStyle, uintptr(unsafe.Pointer(className)), uintptr(unsafe.Pointer(t)), style,
			uintptr(0xFFFF8300), uintptr(0xFFFF8300), 120, 80, owner, 0, hInst, 0) // -32000 poza ekranem
		return h
	}
	const wsVisible, wsPopup, wsOverlapped, wsExTool = 0x10000000, 0x80000000, 0x00CF0000, 0x80
	main := create(0, "OBS 30.0 - Profile: test - Scenes: test", wsOverlapped|wsVisible, 0)
	if main == 0 {
		fmt.Println("NO_WINDOW main")
		os.Exit(4)
	}
	create(wsExTool, "Dok przypiety", wsPopup|wsVisible, main) // okno narzędziowe z właścicielem (okno główne)
	create(wsExTool, "Dok odpiety", wsPopup|wsVisible, 0)      // okno narzędziowe bez właściciela (odpięty dok)

	if port := os.Getenv("OBS_ATRAPA_PORT"); port != "" {
		ln, err := net.Listen("tcp", "127.0.0.1:"+port)
		if err != nil {
			fmt.Println("NO_PORT", err)
			os.Exit(2)
		}
		mux := http.NewServeMux()
		mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("ok")) })
		mux.HandleFunc("/exit", func(w http.ResponseWriter, r *http.Request) {
			code, _ := strconv.Atoi(r.URL.Query().Get("code"))
			go func() { time.Sleep(50 * time.Millisecond); os.Exit(code) }()
		})
		go http.Serve(ln, mux)
	}
	var m winMsg
	for {
		r, _, _ := atrGetMessageW.Call(uintptr(unsafe.Pointer(&m)), 0, 0, 0)
		if int32(r) <= 0 {
			break
		}
		atrTranslateMessage.Call(uintptr(unsafe.Pointer(&m)))
		atrDispatchMessageW.Call(uintptr(unsafe.Pointer(&m)))
	}
	os.Exit(0)
}
