package main

import (
	"fmt"
	"regexp"
)

// Instancje WordPressa/SportsPressa modułów (WP-1). Każdy moduł może mieć blok "wp" w module.json: port, nazwę bazy i szablon.
// To jedyne źródło parametrów: plik .bat (hub.exe wp <id>) i uruchamianie przez HUB budują polecenie tą samą funkcją (wp_launch.go),
// więc nie mogą się rozjechać. Działa jedna instancja naraz.

const (
	wpDefaultTemplate = "_szablon"
	wpDefaultDir      = "wp-local"
)

// WpConfig to blok "wp" z module.json.
type WpConfig struct {
	Port     int    `json:"port"`               // port instancji WP (127.0.0.1); baza wybierana po porcie przez bm-multidb.php
	DB       string `json:"db,omitempty"`       // folder bazy w <wp_dir>/databases; domyślnie p<port>
	Template string `json:"template,omitempty"` // folder szablonu, z którego powstaje brakująca baza; domyślnie _szablon
	Title    string `json:"title,omitempty"`    // tytuł strony WP nowej bazy (odróżnia rozgrywki w panelu)
}

var wpNameRE = regexp.MustCompile(`^[A-Za-z0-9_-]+$`)

// EffectiveDB: nazwa folderu bazy (db albo p<port>).
func (w WpConfig) EffectiveDB() string {
	if w.DB != "" {
		return w.DB
	}
	return fmt.Sprintf("p%d", w.Port)
}

// EffectiveTemplate: nazwa folderu szablonu bazy.
func (w WpConfig) EffectiveTemplate() string {
	if w.Template != "" {
		return w.Template
	}
	return wpDefaultTemplate
}

// problem zwraca opis błędu bloku albo "". modulePort: port modułu, który nie może się pokrywać z portem WP.
func (w WpConfig) problem(modulePort int) string {
	switch {
	case w.Port < 1024 || w.Port > 65535:
		return fmt.Sprintf("port %d poza zakresem 1024-65535", w.Port)
	case w.Port == modulePort:
		return fmt.Sprintf("port %d jest też portem modułu", w.Port)
	case !wpNameRE.MatchString(w.EffectiveDB()):
		return fmt.Sprintf("nazwa bazy %q może zawierać tylko litery, cyfry, _ i -", w.EffectiveDB())
	case !wpNameRE.MatchString(w.EffectiveTemplate()):
		return fmt.Sprintf("nazwa szablonu %q może zawierać tylko litery, cyfry, _ i -", w.EffectiveTemplate())
	case w.EffectiveDB() == w.EffectiveTemplate():
		return "baza nie może być szablonem"
	}
	return ""
}
