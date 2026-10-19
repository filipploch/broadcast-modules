package main

import (
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	configFlag := flag.String("config", "", "ścieżka do pliku konfiguracji HUB-a (domyślnie hub/config/hub.json, a bez niego hub.example.json)")
	moduleFlag := flag.String("module", "", "moduł do uruchomienia (nadpisuje pole \"module\" z konfiguracji)")
	flag.Parse()

	hubCfg, cfgErr := loadHubConfig(*configFlag, *moduleFlag, "")
	if cfgErr != nil {
		log.Fatalf("❌ Konfiguracja HUB-a: %v", cfgErr)
	}

	runDir, closeLogs, logErr := setupRunLogs(logsRoot(), time.Now())
	// Pierwszy wiersz logu: wybrany moduł i skąd ta wartość
	if hubCfg.Module == "" {
		log.Printf("Moduł: (brak; HUB nie uruchamia modułu) (źródło: %s)", hubCfg.ModuleSource)
	} else {
		log.Printf("Moduł: %s (źródło: %s)", hubCfg.ModuleLabel(), hubCfg.ModuleSource)
	}
	commit := buildCommit
	if commit == "" {
		commit = "nieznany (hub.exe zbudowany bez hub\\build.bat)"
	}
	log.Printf("Wersja HUB-a: commit %s, protokół kanału sterującego %d", commit, controlProtocolVersion)
	for _, n := range hubCfg.Notes {
		log.Print(n)
	}
	if logErr != nil {
		log.Printf("⚠️  Nie można założyć folderu logów (logi tylko w konsoli): %v", logErr)
	} else {
		defer closeLogs()
		log.Printf("📝 Logi tego uruchomienia: %s", runDir)
	}
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("🚀 BROADCAST HUB STARTING")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	// Configuration
	port := hubCfg.HubPort
	enablePluginManager := true
	enableHealthMonitor := true

	// Create Hub
	hub := NewHub(port, enablePluginManager, enableHealthMonitor)

	// Plik konfiguracji pluginów z hub.json (próby ręczne: tylko pluginy lokalne, bez Debiana i kamer)
	if hub.PluginManager != nil && hubCfg.PluginsConfig != "" {
		hub.PluginManager.configPath = hubCfg.abs(hubCfg.PluginsConfig)
		log.Printf("Konfiguracja pluginów: %s", hub.PluginManager.configPath)
	}

	// Load plugin configurations
	if hub.PluginManager != nil {
		if err := hub.PluginManager.LoadConfig(); err != nil {
			log.Fatalf("❌ Failed to load plugin config: %v", err)
		}
		// Pluginy NIE są startowane tutaj.
		// Są startowane dopiero gdy main_module wyśle declare_required_plugins.
		// AutoStart w plugins.json oznacza tylko że plugin MOŻE być automatycznie
		// uruchomiony gdy zostanie zadeklarowany — nie że hub startuje go sam z siebie.
		log.Printf("✅ Plugin configurations loaded — waiting for main_module to declare required plugins")
	}

	if hub.PluginManager != nil {
		go hub.PluginManager.RunSupervisor(5 * time.Second)
	}

	// Usługi: moduł główny (z hub.json) i wpisy "type": "service" z plugins.json
	hub.Services = NewServiceManager()
	hub.Services.graceful = hub.gracefulStopService
	if hub.PluginManager != nil {
		if err := hub.Services.LoadFromPluginsJSON(hub.PluginManager.configPath); err != nil {
			log.Fatalf("❌ Failed to load services from plugin config: %v", err)
		}
	}
	if svc, ok := hubCfg.moduleService(); ok {
		if err := hub.Services.Add(svc); err != nil {
			log.Fatalf("❌ Moduł: %v", err)
		}
	}
	if svc, ok := hubCfg.obsService(); ok {
		if err := hub.Services.Add(svc); err != nil {
			log.Fatalf("❌ OBS: %v", err)
		}
		log.Printf("OBS uruchamia HUB (%s); OBS uruchomiony ręcznie jest \"obcy\": HUB go nie restartuje ani nie zamyka", svc.ExecutablePath)
		if hub.PluginManager != nil {
			if msg := obsPortMismatch(hubCfg.Obs.WsPort, hub.PluginManager.GetAllConfigs()["obs-ws-plugin"].WorkingDir); msg != "" {
				log.Printf("⚠️  OBS: %s", msg)
			}
		}
	} else {
		log.Printf("OBS: HUB go nie uruchamia (sekcja obs.enabled = false albo brak ścieżki)")
	}

	// Plik stanu usług (E2d2): przejęcie działających usług i zakończenie sierot PRZED startem pętli HUB-a i pluginów
	hub.State = NewStateStore(hubCfg.StatePath())
	hub.Services.persist = hub.persistState
	hub.Services.sessionOpen = func() bool { return hub.SessionStatus().OpenForRestart() }
	hub.Services.pluginGate = hub.pluginGate
	hub.Services.notify = hub.notifyService
	if hub.PluginManager != nil {
		hub.PluginManager.persist = hub.persistState
	}
	hub.session.onChange = func(SessionStatus) { hub.persistState() }
	// Moduł z pliku stanu jest przejmowany także przy --module none albo innym module w konfiguracji (E2d3c1)
	hub.prepareModuleAdoption(hubCfg)
	for _, id := range hub.RestoreFromState() {
		if hub.Services.RestartPolicy(id) == restartSessionOpen && !hub.SessionStatus().OpenForRestart() {
			hub.Services.SkipInitialStart(id, "proces zakończył się, gdy HUB nie działał (kod wyjścia nieznany), a ostatni znany status sesji nie jest otwarty")
		}
	}

	// Start hub event loop
	// Initialize FallbackWriter
	hub.FallbackWriter = NewFallbackWriter(hub, fallbackRules())
	log.Println("✅ FallbackWriter initialized")

	// Start hub event loop
	go hub.Run()

	// Setup HTTP server
	http.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		serveWs(hub, w, r)
	})

	http.HandleFunc("/status", func(w http.ResponseWriter, r *http.Request) {
		serveStatus(hub, w, r)
	})

	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		serveHealth(hub, w, r)
	})

	// Start HTTP server using setupHTTPServer
	log.Printf("🌐 Starting HTTP server on port %d", port)
	server := setupHTTPServer(hub)

	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("❌ HTTP server error: %v", err)
		}
	}()

	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("✅ HUB IS READY!")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Printf("   HTTP:      http://0.0.0.0:%d", port)
	log.Printf("   WebSocket: ws://0.0.0.0:%d/ws", port)
	log.Printf("   Status:    http://0.0.0.0:%d/status", port)
	log.Printf("   Health:    http://0.0.0.0:%d/health", port)
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("")
	log.Println("Features enabled:")
	log.Printf("   PluginManager:   %v", enablePluginManager)
	log.Printf("   HealthMonitor:   %v", enableHealthMonitor)
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	// Start reverse discovery for external plugins
	hub.StartReverseDiscovery()

	// Budzenie Debiana w tle: HUB na niego nie czeka (recorder-plugin zgłosi się sam, gdy system wstanie)
	hub.wol = newWolSender(hubCfg.Wol)
	hub.wakeDebianOnStart()

	// Kanał sterujący managera (E2d3c1): osobny serwer tylko na 127.0.0.1, niezależny od WebSocketu pluginów
	control := newControlServer(hub, hubCfg)
	control.Listen(hubCfg.ControlPort)

	// Usługi startują po HUB-ie (moduł łączy się z nim od razu); pluginy lokalne startują dalej na deklarację modułu
	hub.Services.StartAll()

	// Wait for interrupt signal albo polecenia zamknięcia z kanału sterującego (te same reguły zamykania)
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	select {
	case <-sigChan:
	case <-control.StopRequested():
		log.Println("🎛️  Zamknięcie HUB-a zlecone przez kanał sterujący managera")
	}

	log.Println("")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
	log.Println("⏹️  Shutting down gracefully...")
	log.Println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

	hub.Shutdown()

	log.Println("✅ Shutdown complete. Goodbye!")
}
