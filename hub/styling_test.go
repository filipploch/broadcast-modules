package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCopyStyleFile_CopiesContent(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "style.css")
	dst := filepath.Join(dir, "nested", "style-override.css")

	if err := os.WriteFile(src, []byte(".foo{color:red}"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := copyStyleFile(src, dst); err != nil {
		t.Fatalf("copyStyleFile: %v", err)
	}
	got, err := os.ReadFile(dst)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != ".foo{color:red}" {
		t.Errorf("got %q, want %q", got, ".foo{color:red}")
	}
}

func TestCopyStyleFile_MissingSourceWritesEmpty(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "does-not-exist.css")
	dst := filepath.Join(dir, "style-override.css")

	// Motyw nie definiuje tego pliku wcale — ma to zadziałać jak "nic nie
	// nadpisuj", nie jak błąd.
	if err := copyStyleFile(src, dst); err != nil {
		t.Fatalf("copyStyleFile should not error on missing src: %v", err)
	}
	got, err := os.ReadFile(dst)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 0 {
		t.Errorf("expected empty dst, got %q", got)
	}
}

func TestWriteFileEnsureDir_Zeroes(t *testing.T) {
	dir := t.TempDir()
	dst := filepath.Join(dir, "a", "b", "style-override.js")

	if err := writeFileEnsureDir(dst, []byte("function foo(){}")); err != nil {
		t.Fatal(err)
	}
	if err := writeFileEnsureDir(dst, nil); err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(dst)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 0 {
		t.Errorf("expected file to be zeroed, got %q", got)
	}
}

func TestSafeTokenPattern(t *testing.T) {
	valid := []string{"nalf", "garbarnia", "futsal-nalf", "theme_2"}
	invalid := []string{"../etc", "a/b", "", "with space"}

	for _, v := range valid {
		if !safeTokenPattern.MatchString(v) {
			t.Errorf("expected %q to be valid", v)
		}
	}
	for _, v := range invalid {
		if safeTokenPattern.MatchString(v) {
			t.Errorf("expected %q to be rejected", v)
		}
	}
}
