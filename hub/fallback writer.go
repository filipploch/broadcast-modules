package main

import (
	"database/sql"
	"log"
	"strings"
	"sync"

	_ "modernc.org/sqlite"
)

// FallbackRule defines when and what to write to SQLite
// when the target main_module is offline.
type FallbackRule struct {
	// Message matching
	FromModule string                  // e.g. "obs-ws-plugin" (empty = any)
	MsgType    string                  // e.g. "obs_event"
	MatchFunc  func(msg *Message) bool // optional extra condition

	// What to write — DB path is provided dynamically by FallbackWriter
	ValueFunc func(msg *Message) (table, column, whereCol, whereVal, value string)
}

// FallbackWriter checks rules and writes to SQLite when main_module is offline.
type FallbackWriter struct {
	hub          *Hub
	rules        []FallbackRule
	databasePath string
	mu           sync.RWMutex
}

// NewFallbackWriter creates a FallbackWriter with the given rules.
func NewFallbackWriter(hub *Hub, rules []FallbackRule) *FallbackWriter {
	return &FallbackWriter{hub: hub, rules: rules}
}

// SetDatabasePath updates the target SQLite path.
// Called by Hub when main_module registers or re-registers.
func (fw *FallbackWriter) SetDatabasePath(path string) {
	fw.mu.Lock()
	fw.databasePath = path
	fw.mu.Unlock()
	log.Printf("📂 FallbackWriter: database path set to %s", path)
}

// Handle is called by Hub after every broadcastToClass.
// It checks whether main_module was skipped (offline) and applies fallback rules.
func (fw *FallbackWriter) Handle(msg *Message) {
	// Only act when main_module is offline or inactive
	fw.hub.mu.RLock()
	mainOffline := fw.hub.MainModule == nil || !fw.hub.MainModule.IsActive
	fw.hub.mu.RUnlock()

	if !mainOffline {
		return
	}

	fw.mu.RLock()
	dbPath := fw.databasePath
	fw.mu.RUnlock()

	if dbPath == "" {
		log.Printf("⚠️  FallbackWriter: no database path set, cannot write fallback")
		return
	}

	for _, rule := range fw.rules {
		if !fw.matches(msg, rule) {
			continue
		}

		table, column, whereCol, whereVal, value := rule.ValueFunc(msg)
		if value == "" {
			log.Printf("⚠️  FallbackWriter: empty value for rule %s/%s, skipping", rule.MsgType, rule.FromModule)
			continue
		}

		if err := fw.writeToSQLite(dbPath, table, column, whereCol, whereVal, value); err != nil {
			log.Printf("❌ FallbackWriter: SQLite write failed: %v", err)
		} else {
			log.Printf("✅ FallbackWriter: %s.%s=%q [main_module offline]", table, column, value)
		}
	}
}

func (fw *FallbackWriter) matches(msg *Message, rule FallbackRule) bool {
	if rule.FromModule != "" && msg.From != rule.FromModule {
		return false
	}
	if rule.MsgType != "" && msg.Type != rule.MsgType {
		return false
	}
	if rule.MatchFunc != nil && !rule.MatchFunc(msg) {
		return false
	}
	return true
}

func (fw *FallbackWriter) writeToSQLite(dbPath, table, column, whereCol, whereVal, value string) error {
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return err
	}
	defer db.Close()

	query := "UPDATE " + table + " SET " + column + " = ? WHERE " + whereCol + " = ?"
	_, err = db.Exec(query, value, whereVal)
	return err
}

// ============================================================================
// Helper: extract nested string value from payload using dot notation
// e.g. getNestedString(msg.Payload, "eventData.outputPath")
// ============================================================================

func getNestedString(obj map[string]interface{}, dotKey string) string {
	keys := strings.SplitN(dotKey, ".", 2)
	val, ok := obj[keys[0]]
	if !ok {
		return ""
	}
	if len(keys) == 1 {
		if s, ok := val.(string); ok {
			return s
		}
		return ""
	}
	nested, ok := val.(map[string]interface{})
	if !ok {
		return ""
	}
	return getNestedString(nested, keys[1])
}
