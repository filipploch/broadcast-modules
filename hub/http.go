package main

import (
	"encoding/json"
	"net/http"
)

// serveHome serves a simple home page
func serveHome(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")

	html := `
<!DOCTYPE html>
<html>
<head>
    <title>Broadcast Hub</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .container {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }
        .status {
            background: #4CAF50;
            color: white;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }
        .endpoints {
            list-style: none;
            padding: 0;
        }
        .endpoints li {
            padding: 10px;
            margin: 5px 0;
            background: #f9f9f9;
            border-left: 4px solid #2196F3;
        }
        .endpoints a {
            color: #2196F3;
            text-decoration: none;
        }
        .endpoints a:hover {
            text-decoration: underline;
        }
        code {
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌐 Broadcast Hub</h1>
        <div class="status">
            <strong>✅ Hub is running</strong>
        </div>
        
        <h2>Available Endpoints</h2>
        <ul class="endpoints">
            <li>
                <strong>WebSocket:</strong> <code>ws://[host]/ws</code><br>
                Connect your modules and plugins here
            </li>
            <li>
                <strong>Status:</strong> <a href="/status">/status</a><br>
                View connected modules and plugins
            </li>
            <li>
                <strong>Health:</strong> <a href="/health">/health</a><br>
                View plugin health monitoring
            </li>
        </ul>
        
        <h2>mDNS Discovery</h2>
        <p>
            This hub is also available via mDNS at:<br>
            <code>ws://broadcast-hub.local:[port]/ws</code>
        </p>
        
        <h2>Features</h2>
        <ul>
            <li>✅ WebSocket message routing</li>
            <li>✅ Plugin process management</li>
            <li>✅ Health monitoring with auto-restart</li>
            <li>✅ mDNS service discovery</li>
        </ul>
    </div>
</body>
</html>
`
	w.Write([]byte(html))
}

// serveStatus serves hub status as JSON
func serveStatus(hub *Hub, w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	hub.mu.RLock()
	status := map[string]interface{}{
		"main_module_connected": hub.MainModule != nil && hub.MainModule.IsActive,
		"total_plugins":         len(hub.Plugins),
		"expected_plugins":      len(hub.ExpectedPlugins),
	}

	// List connected plugins
	connectedPlugins := make([]string, 0, len(hub.Plugins))
	for id := range hub.Plugins {
		connectedPlugins = append(connectedPlugins, id)
	}
	status["connected_plugins"] = connectedPlugins

	// List expected plugins
	expectedPlugins := make([]string, 0, len(hub.ExpectedPlugins))
	for id := range hub.ExpectedPlugins {
		expectedPlugins = append(expectedPlugins, id)
	}
	status["expected_plugins"] = expectedPlugins
	hub.mu.RUnlock()

	// Add plugin manager status if available
	if hub.PluginManager != nil {
		status["plugin_manager"] = hub.PluginManager.GetAllStatus()
	}

	json.NewEncoder(w).Encode(status)
}

// serveHealth serves health monitoring status as JSON
func serveHealth(hub *Hub, w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	if hub.HealthMonitor == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"error": "Health monitoring not enabled",
		})
		return
	}

	health := map[string]interface{}{
		"summary": hub.HealthMonitor.GetHealthSummary(),
		"plugins": hub.HealthMonitor.GetAllHealth(),
	}

	json.NewEncoder(w).Encode(health)
}
