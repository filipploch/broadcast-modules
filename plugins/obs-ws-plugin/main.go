package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"obs-ws-plugin/internal/hub"
	"obs-ws-plugin/internal/obs"
)

// ─────────────────────────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────────────────────────

type Config struct {
	Plugin struct {
		ID      string `json:"id"`
		Name    string `json:"name"`
		Version string `json:"version"`
	} `json:"plugin"`
	OBS      obs.Config `json:"obs"`
	SceneMap struct {
		// Ścieżka do pliku JSON przechowującego mapę scen między restartami.
		// Plugin wczytuje ją przy starcie (jeśli istnieje) i nadpisuje
		// po każdym odświeżeniu z OBS.
		// Powinna być dostępna dla main_module jeśli chce odczytać mapę z pliku,
		// ale w tej architekturze to plugin rozwiązuje nazwy — plik służy tylko
		// jako trwały cache dla pluginu.
		Path string `json:"path"`
	} `json:"scene_map"`
	Logging struct {
		Level string `json:"level"`
	} `json:"logging"`
}

// ─────────────────────────────────────────────────────────────────────────────
// SceneMap — thread-safe mapa: sceneName → { sourceName → sceneItemId }
// ─────────────────────────────────────────────────────────────────────────────

type SceneMap struct {
	mu   sync.RWMutex
	data map[string]map[string]int // sceneName → sourceName → sceneItemId
}

func newSceneMap() *SceneMap {
	return &SceneMap{data: make(map[string]map[string]int)}
}

// resolve zwraca sceneItemId dla podanej sceny i nazwy źródła.
func (sm *SceneMap) resolve(sceneName, sourceName string) (int, bool) {
	sm.mu.RLock()
	defer sm.mu.RUnlock()
	sources, ok := sm.data[sceneName]
	if !ok {
		return 0, false
	}
	id, ok := sources[sourceName]
	return id, ok
}

// set atomowo zastępuje całą mapę i zapisuje do pliku.
func (sm *SceneMap) set(data map[string]map[string]int, savePath string) {
	sm.mu.Lock()
	sm.data = data
	sm.mu.Unlock()

	if savePath != "" {
		if err := sm.saveToFile(savePath); err != nil {
			log.Printf("⚠️  Failed to save scene map to %s: %v", savePath, err)
		} else {
			log.Printf("💾 Scene map saved to %s", savePath)
		}
	}
}

// loadFromFile wczytuje mapę z pliku JSON. Błąd = mapa pusta (nie fatal).
func (sm *SceneMap) loadFromFile(path string) {
	data, err := os.ReadFile(path)
	if err != nil {
		if !os.IsNotExist(err) {
			log.Printf("⚠️  Failed to read scene map from %s: %v", path, err)
		}
		return
	}
	var loaded map[string]map[string]int
	if err := json.Unmarshal(data, &loaded); err != nil {
		log.Printf("⚠️  Failed to parse scene map from %s: %v", path, err)
		return
	}
	sm.mu.Lock()
	sm.data = loaded
	sm.mu.Unlock()

	total := 0
	for _, sources := range loaded {
		total += len(sources)
	}
	log.Printf("📂 Scene map loaded from %s: %d scene(s), %d source(s)",
		path, len(loaded), total)
}

// saveToFile zapisuje aktualną mapę do pliku JSON.
func (sm *SceneMap) saveToFile(path string) error {
	sm.mu.RLock()
	data := sm.data
	sm.mu.RUnlock()

	raw, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, raw, 0644)
}

// toRaw zwraca kopię danych (do wysyłki przez hub).
func (sm *SceneMap) toRaw() map[string]map[string]int {
	sm.mu.RLock()
	defer sm.mu.RUnlock()
	cp := make(map[string]map[string]int, len(sm.data))
	for scene, sources := range sm.data {
		srcCp := make(map[string]int, len(sources))
		for src, id := range sources {
			srcCp[src] = id
		}
		cp[scene] = srcCp
	}
	return cp
}

// ─────────────────────────────────────────────────────────────────────────────
// Plugin
// ─────────────────────────────────────────────────────────────────────────────

type Plugin struct {
	config    *Config
	hubClient *hub.HubClient
	obsClient *obs.Client
	sceneMap  *SceneMap
}

func main() {
	log.SetFlags(log.Ldate | log.Ltime | log.Lmicroseconds)
	log.Println("🎬 OBS WebSocket Plugin starting...")

	config, err := loadConfig()
	if err != nil {
		log.Fatalf("❌ Failed to load config: %v", err)
	}
	if pluginID := os.Getenv("PLUGIN_ID"); pluginID != "" {
		config.Plugin.ID = pluginID
	}
	hubURL := os.Getenv("HUB_URL")
	if hubURL == "" {
		hubURL = "ws://localhost:8080/ws"
	}

	sceneMap := newSceneMap()

	// Wczytaj mapę z pliku (trwały cache z poprzedniej sesji).
	// Dzięki temu plugin jest gotowy do rozwiązywania nazw natychmiast po starcie,
	// nawet jeśli OBS nie zdążył jeszcze odpowiedzieć na GetSceneItemList.
	if config.SceneMap.Path != "" {
		sceneMap.loadFromFile(config.SceneMap.Path)
	}

	plugin := &Plugin{
		config:    config,
		hubClient: hub.NewHubClient(hubURL, config.Plugin.ID, config.Plugin.Name),
		obsClient: obs.NewClient(&config.OBS),
		sceneMap:  sceneMap,
	}

	plugin.hubClient.ConnectWithRetry()

	// Połącz z OBS w tle z automatycznym retry — plugin nie wymaga,
	// żeby OBS był uruchomiony przed jego startem.
	go plugin.connectToOBSWithRetry()

	go plugin.routeHubToOBS()
	go plugin.routeOBSToHub()
	go plugin.monitorOBSStatus()

	log.Println("✅ OBS WebSocket Plugin is running")
	log.Printf("   Plugin ID: %s", config.Plugin.ID)
	log.Printf("   HUB: %s", hubURL)
	log.Printf("   OBS: %s:%d", config.OBS.Host, config.OBS.Port)

	waitForShutdown(plugin)
}

func loadConfig() (*Config, error) {
	data, err := os.ReadFile("config.json")
	if err != nil {
		return nil, fmt.Errorf("failed to read config.json: %w", err)
	}
	var config Config
	if err := json.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse config.json: %w", err)
	}
	return &config, nil
}

// ─────────────────────────────────────────────────────────────────────────────
// refreshSceneMap — odpytuje OBS i aktualizuje mapę w pamięci + plik
// ─────────────────────────────────────────────────────────────────────────────

func (p *Plugin) refreshSceneMap() {
	log.Println("🗺️  Refreshing OBS scene map...")

	scenesResp, err := p.obsClient.SendRequest("GetSceneList", nil)
	if err != nil {
		log.Printf("❌ GetSceneList failed: %v", err)
		return
	}
	scenes, ok := scenesResp["scenes"].([]interface{})
	if !ok {
		log.Printf("⚠️  GetSceneList: unexpected response format")
		return
	}

	newMap := make(map[string]map[string]int)

	for _, s := range scenes {
		scene, ok := s.(map[string]interface{})
		if !ok {
			continue
		}
		sceneName, _ := scene["sceneName"].(string)
		if sceneName == "" {
			continue
		}

		itemsResp, err := p.obsClient.SendRequest("GetSceneItemList",
			map[string]interface{}{"sceneName": sceneName})
		if err != nil {
			log.Printf("⚠️  GetSceneItemList(%s) failed: %v", sceneName, err)
			continue
		}
		items, ok := itemsResp["sceneItems"].([]interface{})
		if !ok {
			continue
		}

		sourceMap := make(map[string]int)
		for _, it := range items {
			item, ok := it.(map[string]interface{})
			if !ok {
				continue
			}
			sourceName, _ := item["sourceName"].(string)
			idF, ok := item["sceneItemId"].(float64)
			if !ok || sourceName == "" {
				continue
			}
			sourceMap[sourceName] = int(idF)
		}
		newMap[sceneName] = sourceMap
		log.Printf("   ✅ '%s': %d source(s)", sceneName, len(sourceMap))
	}

	p.sceneMap.set(newMap, p.config.SceneMap.Path)

	total := 0
	for _, sources := range newMap {
		total += len(sources)
	}
	log.Printf("🗺️  Scene map ready: %d scene(s), %d source(s) total", len(newMap), total)

	// Wyślij mapę do main_module — tylko informacyjnie (np. do UI /api/obs/scene-map)
	p.hubClient.Send(&hub.Message{
		From:    p.config.Plugin.ID,
		To:      "main_module",
		Type:    "obs_scene_map",
		Payload: map[string]interface{}{"scene_map": p.sceneMap.toRaw()},
	})
}

// ─────────────────────────────────────────────────────────────────────────────
// routeHubToOBS — obsługuje obs_command i obs_command_by_name
// ─────────────────────────────────────────────────────────────────────────────

func (p *Plugin) routeHubToOBS() {
	log.Println("🔀 Starting Hub → OBS routing")

	for msg := range p.hubClient.Messages {
		// request_scene_map — main module asks us to re-send the current map.
		// Useful when main module (re)starts after obs-ws-plugin is already up.
		if msg.Type == "request_scene_map" {
			log.Printf("📨 Hub → OBS: request_scene_map from %s", msg.From)
			if p.obsClient.IsConnected() {
				go p.refreshSceneMap()
			} else {
				// OBS not yet connected — send whatever we have cached in memory
				p.hubClient.Send(&hub.Message{
					From:    p.config.Plugin.ID,
					To:      "main-module",
					Type:    "obs_scene_map",
					Payload: map[string]interface{}{"scene_map": p.sceneMap.toRaw()},
				})
			}
			continue
		}

		if msg.Type != "obs_command" && msg.Type != "obs_command_by_name" &&
			msg.Type != "recording_command" {
			continue
		}

		// Each OBS request runs in its own goroutine so that a slow command
		// (e.g. StartStream waiting for RTMP handshake) never blocks subsequent
		// commands (e.g. StartRecord arriving 200 ms later).
		go p.handleObsCommand(msg)
	}
}

func (p *Plugin) handleObsCommand(msg *hub.Message) {
	requestID := msg.Payload["request_id"]
	log.Printf("📨 Hub → OBS: %s from %s", msg.Type, msg.From)

	if !p.obsClient.IsConnected() {
		log.Printf("⚠️  OBS not connected, cannot forward command")
		p.hubClient.Send(&hub.Message{
			From: p.config.Plugin.ID, To: msg.From, Type: "obs_error",
			Payload: map[string]interface{}{
				"error": "OBS not connected", "command": msg.Payload,
			},
		})
		return
	}

	requestType, ok := msg.Payload["requestType"].(string)
	if !ok || requestType == "" {
		log.Printf("⚠️  obs_command missing requestType")
		p.hubClient.Send(&hub.Message{
			From: p.config.Plugin.ID, To: msg.From, Type: "obs_error",
			Payload: map[string]interface{}{"error": "obs_command payload must contain requestType"},
		})
		return
	}

	var requestData map[string]interface{}
	if rd, ok := msg.Payload["requestData"].(map[string]interface{}); ok {
		requestData = rd
	}

	// obs_command_by_name: wstrzyknij sceneItemId na podstawie sourceName
	if msg.Type == "obs_command_by_name" {
		resolved, err := p.resolveSceneItemId(msg.Payload, requestData)
		if err != nil {
			log.Printf("❌ Cannot resolve source name: %v", err)
			p.hubClient.Send(&hub.Message{
				From: p.config.Plugin.ID, To: msg.From, Type: "obs_error",
				Payload: map[string]interface{}{
					"error":       err.Error(),
					"requestType": requestType,
				},
			})
			return
		}
		requestData = resolved
	}

	responseData, err := p.obsClient.SendRequest(requestType, requestData)
	if err != nil {
		log.Printf("❌ OBS request failed (%s): %v", requestType, err)
		p.hubClient.Send(&hub.Message{
			From: p.config.Plugin.ID, To: msg.From, Type: "obs_error",
			Payload: map[string]interface{}{
				"error": err.Error(), "requestType": requestType,
			},
		})
		return
	}

	log.Printf("✅ OBS response received for %s", requestType)
	p.hubClient.Send(&hub.Message{
		From: p.config.Plugin.ID, To: msg.From, Type: "obs_response",
		Payload: map[string]interface{}{
			"requestType":  requestType,
			"requestID":    requestID,
			"responseData": responseData,
		},
	})
}

// resolveSceneItemId wstrzykuje sceneItemId do requestData na podstawie
// sceneName + sourceName z payloadu wiadomości.
func (p *Plugin) resolveSceneItemId(
	payload map[string]interface{},
	requestData map[string]interface{},
) (map[string]interface{}, error) {

	sceneName, _ := payload["sceneName"].(string)
	sourceName, _ := payload["sourceName"].(string)

	if sceneName == "" || sourceName == "" {
		return nil, fmt.Errorf(
			"obs_command_by_name requires 'sceneName' and 'sourceName' in payload, got: sceneName=%q sourceName=%q",
			sceneName, sourceName)
	}

	sceneItemId, ok := p.sceneMap.resolve(sceneName, sourceName)
	if !ok {
		return nil, fmt.Errorf(
			"source %q not found in scene %q — scene map may be stale, check OBS structure",
			sourceName, sceneName)
	}

	// Zbuduj nowe requestData z wstrzykniętym sceneItemId
	resolved := make(map[string]interface{}, len(requestData)+1)
	for k, v := range requestData {
		resolved[k] = v
	}
	resolved["sceneItemId"] = sceneItemId

	log.Printf("🔍 Resolved '%s' in scene '%s' → sceneItemId=%d", sourceName, sceneName, sceneItemId)
	return resolved, nil
}

// ─────────────────────────────────────────────────────────────────────────────
// routeOBSToHub — przekazuje eventy OBS do huba
// ─────────────────────────────────────────────────────────────────────────────

func (p *Plugin) routeOBSToHub() {
	log.Println("🔀 Starting OBS → Hub routing")
	for event := range p.obsClient.Events {
		log.Printf("📨 OBS → Hub: event received")
		p.hubClient.Send(&hub.Message{
			From:    p.config.Plugin.ID,
			To:      "broadcast:obs_messages_receiver",
			Type:    "obs_event",
			Payload: event,
		})
	}
}

// ─────────────────────────────────────────────────────────────────────────────
// monitorOBSStatus — przy każdym (re)połączeniu odświeża mapę scen
// ─────────────────────────────────────────────────────────────────────────────

func (p *Plugin) monitorOBSStatus() {
	log.Println("📡 Starting OBS status monitor")
	for status := range p.obsClient.StatusChanged {
		log.Printf("📊 OBS Status changed: %s", status)
		p.hubClient.Send(&hub.Message{
			From: p.config.Plugin.ID,
			To:   "main_module",
			Type: "obs_status",
			Payload: map[string]interface{}{
				"status":    status,
				"obs_host":  fmt.Sprintf("%s:%d", p.config.OBS.Host, p.config.OBS.Port),
				"timestamp": time.Now().Unix(),
			},
		})
		// Przy każdym (re)połączeniu z OBS odśwież mapę scen —
		// struktura scen mogła się zmienić podczas rozłączenia.
		if status == "connected" {
			go p.refreshSceneMap()
		}
	}
}

// connectToOBSWithRetry próbuje połączyć się z OBS w pętli z exponential backoff.
// Po udanym połączeniu oddaje kontrolę wewnętrznemu mechanizmowi reconnect
// w obs/client.go (który obsługuje zerwania połączenia podczas działania).
func (p *Plugin) connectToOBSWithRetry() {
	backoff := 3 * time.Second
	maxBackoff := 30 * time.Second
	attempt := 0

	for {
		attempt++
		log.Printf("🎬 Connecting to OBS (attempt %d): %s:%d",
			attempt, p.config.OBS.Host, p.config.OBS.Port)

		if err := p.obsClient.Connect(); err == nil {
			log.Printf("✅ Connected to OBS on attempt %d", attempt)
			go p.refreshSceneMap()
			return // dalej reconnectami zarządza obs/client.go przez StatusChanged
		} else {
			log.Printf("⚠️  OBS connection failed: %v — retrying in %v", err, backoff)
		}

		time.Sleep(backoff)
		backoff *= 2
		if backoff > maxBackoff {
			backoff = maxBackoff
		}
	}
}

func waitForShutdown(plugin *Plugin) {
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan
	log.Println("🛑 Shutdown signal received, cleaning up...")
	plugin.obsClient.Close()
	plugin.hubClient.Close()
	log.Println("👋 OBS WebSocket Plugin stopped")
	os.Exit(0)
}
