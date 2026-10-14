package main

import "strings"

// Rozpoznawanie okna głównego OBS (E2d2). Komunikat zamknięcia (WM_CLOSE) wolno wysłać wyłącznie do okna głównego, nigdy do odpiętych
// doków ani okien pomocniczych: zamknięcie doku zmieniłoby układ interfejsu OBS.

// windowInfo opisuje okno najwyższego poziomu procesu.
type windowInfo struct {
	Hwnd       uintptr
	Title      string
	Class      string
	Visible    bool
	Owner      uintptr // 0 = brak właściciela
	ToolWindow bool    // styl WS_EX_TOOLWINDOW
}

// selectMainWindow wybiera okno główne OBS spośród okien procesu: widoczne, bez właściciela, nie narzędziowe, klasy okna Qt
// ("...QWindowIcon") i z tytułem zaczynającym się od "OBS " (np. "OBS 31.0.2 - Profil: ... - Sceny: ..."). Odpięte doki to okna
// narzędziowe albo mają właściciela (okno główne), więc odpadają.
func selectMainWindow(wins []windowInfo) (uintptr, bool) {
	for _, w := range wins {
		if !w.Visible || w.Owner != 0 || w.ToolWindow {
			continue
		}
		if !strings.HasSuffix(w.Class, "QWindowIcon") || !strings.HasPrefix(w.Title, "OBS ") {
			continue
		}
		return w.Hwnd, true
	}
	return 0, false
}
