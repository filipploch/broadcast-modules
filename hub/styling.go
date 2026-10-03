package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"regexp"
)

// safeTokenPattern restricts overlay_dir/styling_class to simple identifiers
// (letters, digits, hyphen, underscore) — these values come straight from
// the Flask backend over the hub's own websocket, but get concatenated into
// filesystem paths below, so a defensive allowlist costs nothing and rules
// out path traversal ("..", "/", etc.) by construction.
var safeTokenPattern = regexp.MustCompile(`^[A-Za-z0-9_-]+$`)

// handleApplyStylingClass switches the "skin" of one module's overlay.
//
// It copies ./overlays/<overlay_dir>/style/<styling_class>/{css/style.css,
// js/style.js} onto the fixed "slot" ./overlays/<overlay_dir>/{css/
// style-override.css, js/style-override.js} — the one overlay.html always
// loads, right after the baseline mechanism — so no overlay.html edit is
// ever needed to switch styles. An empty styling_class means "revert to the
// baseline mechanism": both slot files are zeroed out (overwritten with
// empty content), nothing is copied.
func (h *Hub) handleApplyStylingClass(msg *Message) {
	overlayDir, _ := msg.Payload["overlay_dir"].(string)
	stylingClass, _ := msg.Payload["styling_class"].(string)

	if overlayDir == "" || !safeTokenPattern.MatchString(overlayDir) {
		h.replyStylingClassResult(msg, false, fmt.Sprintf("nieprawidłowy overlay_dir: %q", overlayDir))
		return
	}

	destCSS := filepath.Join("overlays", overlayDir, "css", "style-override.css")
	destJS := filepath.Join("overlays", overlayDir, "js", "style-override.js")

	if stylingClass == "" {
		if err := writeFileEnsureDir(destCSS, nil); err != nil {
			h.replyStylingClassResult(msg, false, err.Error())
			return
		}
		if err := writeFileEnsureDir(destJS, nil); err != nil {
			h.replyStylingClassResult(msg, false, err.Error())
			return
		}
		log.Printf("🎨 Styling class cleared for %s (reverted to baseline)", overlayDir)
		h.replyStylingClassResult(msg, true, "")
		return
	}

	if !safeTokenPattern.MatchString(stylingClass) {
		h.replyStylingClassResult(msg, false, fmt.Sprintf("nieprawidłowy styling_class: %q", stylingClass))
		return
	}

	srcCSS := filepath.Join("overlays", overlayDir, "style", stylingClass, "css", "style.css")
	srcJS := filepath.Join("overlays", overlayDir, "style", stylingClass, "js", "style.js")

	if err := copyStyleFile(srcCSS, destCSS); err != nil {
		h.replyStylingClassResult(msg, false, err.Error())
		return
	}
	if err := copyStyleFile(srcJS, destJS); err != nil {
		h.replyStylingClassResult(msg, false, err.Error())
		return
	}

	log.Printf("🎨 Styling class '%s' applied to %s", stylingClass, overlayDir)
	h.replyStylingClassResult(msg, true, "")
}

func (h *Hub) replyStylingClassResult(msg *Message, success bool, errMsg string) {
	reply := NewMessage("hub", msg.From, "styling_class_applied", map[string]interface{}{
		"overlay_dir":   msg.Payload["overlay_dir"],
		"styling_class": msg.Payload["styling_class"],
		"success":       success,
		"error":         errMsg,
	})
	data, err := reply.ToJSON()
	if err != nil {
		return
	}

	h.mu.RLock()
	defer h.mu.RUnlock()
	if h.MainModule != nil && h.MainModule.IsActive {
		select {
		case h.MainModule.Send <- data:
		default:
			log.Printf("⚠️  styling_class_applied: main module send buffer full")
		}
	}
}

// handleCreateStylingClass creates a brand-new theme folder:
// ./overlays/<overlay_dir>/style/<new_name>/{css/style.css,js/style.js}.
// With source_name set, both files are copied from that existing theme
// (same semantics as copyStyleFile: a missing source file becomes empty).
// Without source_name, both files are created with a short header comment
// only — an empty scaffold, since we can't guess which containers a future
// theme will want to override.
func (h *Hub) handleCreateStylingClass(msg *Message) {
	overlayDir, _ := msg.Payload["overlay_dir"].(string)
	newName, _ := msg.Payload["new_name"].(string)
	sourceName, _ := msg.Payload["source_name"].(string)

	if overlayDir == "" || !safeTokenPattern.MatchString(overlayDir) {
		h.replyStylingClassCreated(msg, false, fmt.Sprintf("nieprawidłowy overlay_dir: %q", overlayDir))
		return
	}
	if newName == "" || !safeTokenPattern.MatchString(newName) {
		h.replyStylingClassCreated(msg, false, fmt.Sprintf("nieprawidłowa nazwa motywu: %q", newName))
		return
	}

	destDir := filepath.Join("overlays", overlayDir, "style", newName)
	if _, err := os.Stat(destDir); err == nil {
		h.replyStylingClassCreated(msg, false, fmt.Sprintf("motyw %q już istnieje", newName))
		return
	}

	destCSS := filepath.Join(destDir, "css", "style.css")
	destJS := filepath.Join(destDir, "js", "style.js")

	if sourceName != "" {
		if !safeTokenPattern.MatchString(sourceName) {
			h.replyStylingClassCreated(msg, false, fmt.Sprintf("nieprawidłowa nazwa motywu źródłowego: %q", sourceName))
			return
		}
		srcCSS := filepath.Join("overlays", overlayDir, "style", sourceName, "css", "style.css")
		srcJS := filepath.Join("overlays", overlayDir, "style", sourceName, "js", "style.js")
		if err := copyStyleFile(srcCSS, destCSS); err != nil {
			h.replyStylingClassCreated(msg, false, err.Error())
			return
		}
		if err := copyStyleFile(srcJS, destJS); err != nil {
			h.replyStylingClassCreated(msg, false, err.Error())
			return
		}
	} else {
		cssHeader := fmt.Sprintf("/* Motyw \"%s\" — style.css specyficzny dla kontenerów tego motywu. */\n", newName)
		jsHeader := fmt.Sprintf("// Motyw \"%s\" — style.js specyficzny dla kontenerów tego motywu.\n", newName)
		if err := writeFileEnsureDir(destCSS, []byte(cssHeader)); err != nil {
			h.replyStylingClassCreated(msg, false, err.Error())
			return
		}
		if err := writeFileEnsureDir(destJS, []byte(jsHeader)); err != nil {
			h.replyStylingClassCreated(msg, false, err.Error())
			return
		}
	}

	log.Printf("🎨 Styling class '%s' created for %s (source: %q)", newName, overlayDir, sourceName)
	h.replyStylingClassCreated(msg, true, "")
}

func (h *Hub) replyStylingClassCreated(msg *Message, success bool, errMsg string) {
	reply := NewMessage("hub", msg.From, "styling_class_created", map[string]interface{}{
		"overlay_dir": msg.Payload["overlay_dir"],
		"new_name":    msg.Payload["new_name"],
		"success":     success,
		"error":       errMsg,
	})
	data, err := reply.ToJSON()
	if err != nil {
		return
	}

	h.mu.RLock()
	defer h.mu.RUnlock()
	if h.MainModule != nil && h.MainModule.IsActive {
		select {
		case h.MainModule.Send <- data:
		default:
			log.Printf("⚠️  styling_class_created: main module send buffer full")
		}
	}
}

// copyStyleFile copies src -> dst, creating the destination directory if
// needed. A missing src (the theme doesn't override this particular file)
// is not an error — it's treated like an empty file, i.e. "this file
// overrides nothing".
func copyStyleFile(src, dst string) error {
	content, err := os.ReadFile(src)
	if err != nil {
		if os.IsNotExist(err) {
			content = nil
		} else {
			return fmt.Errorf("odczyt %s: %w", src, err)
		}
	}
	return writeFileEnsureDir(dst, content)
}

func writeFileEnsureDir(dst string, content []byte) error {
	if err := os.MkdirAll(filepath.Dir(dst), 0755); err != nil {
		return fmt.Errorf("mkdir %s: %w", filepath.Dir(dst), err)
	}
	if err := os.WriteFile(dst, content, 0644); err != nil {
		return fmt.Errorf("zapis %s: %w", dst, err)
	}
	return nil
}
