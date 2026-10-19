package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func writePluginConfig(t *testing.T, body string) string {
	t.Helper()
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "config.json"), []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	return dir
}

func TestObsPortMismatchReported(t *testing.T) {
	dir := writePluginConfig(t, `{"obs": {"host": "localhost", "port": 4445}}`)
	msg := obsPortMismatch(4455, dir)
	if !strings.Contains(msg, "4455") || !strings.Contains(msg, "4445") {
		t.Fatalf("oczekiwano opisu rozbieżności 4455/4445, jest %q", msg)
	}
}

func TestObsPortMatchOrMissingConfigIsSilent(t *testing.T) {
	if msg := obsPortMismatch(4445, writePluginConfig(t, `{"obs": {"port": 4445}}`)); msg != "" {
		t.Fatalf("zgodne porty: oczekiwano ciszy, jest %q", msg)
	}
	if msg := obsPortMismatch(4455, t.TempDir()); msg != "" {
		t.Fatalf("brak config.json: oczekiwano ciszy, jest %q", msg)
	}
	if msg := obsPortMismatch(4455, writePluginConfig(t, `{ uszkodzony`)); msg != "" {
		t.Fatalf("uszkodzony config.json: oczekiwano ciszy, jest %q", msg)
	}
	if msg := obsPortMismatch(4455, ""); msg != "" {
		t.Fatalf("brak folderu pluginu: oczekiwano ciszy, jest %q", msg)
	}
}

// Konfiguracja z repozytorium: plik obs-ws-pluginu jest czytany z jego working_dir (względem folderu hub/, jak przy starcie pluginu).
func TestObsPortMismatchReadsRepoPluginConfig(t *testing.T) {
	data, err := os.ReadFile(filepath.Join("..", "plugins", "obs-ws-plugin", "config.json"))
	if err != nil {
		t.Skip("brak plugins/obs-ws-plugin/config.json")
	}
	if !strings.Contains(string(data), `"port"`) {
		t.Skip("config.json bez portu")
	}
	if obsPortMismatch(1, filepath.Join("..", "plugins", "obs-ws-plugin")) == "" {
		t.Fatal("port 1 na pewno różni się od portu w config.json obs-ws-pluginu: oczekiwano ostrzeżenia")
	}
}
