/**
 * Simple SSE Client for Overlays
 * 
 * NO REGISTRATION - just subscribes to SSE stream
 */

class SSEOverlayClient {
    constructor(config = {}) {
        this.hubUrl = config.hubUrl || this.getHubUrl();
        this.autoReconnect = config.autoReconnect !== false;
        this.reconnectDelay = config.reconnectDelay || 3000;
        this.debug = config.debug || false;
        
        // State
        this.eventSource = null;
        this.connected = false;
        this.reconnectTimer = null;
        this.messageHandlers = {};
        this.connectionCallbacks = [];
        this.disconnectionCallbacks = [];
        
        this.log('Initialized', { hubUrl: this.hubUrl });
    }

    getHubUrl() {
        const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
        const host = window.location.hostname;
        const port = new URLSearchParams(window.location.search).get('port') || '8080';
        
        return `${protocol}//${host}:${port}/overlay/stream`;
    }

    connect() {
        if (this.eventSource && this.eventSource.readyState === EventSource.OPEN) {
            this.log('Already connected');
            return;
        }

        this.log('Connecting to SSE stream...', this.hubUrl);

        try {
            this.eventSource = new EventSource(this.hubUrl);
            
            this.eventSource.addEventListener('connected', (e) => {
                this.handleConnected(e);
            });
            
            this.eventSource.addEventListener('message', (e) => {
                this.handleMessage(e);
            });
            
            this.eventSource.onerror = (e) => {
                this.handleError(e);
            };
            
        } catch (error) {
            this.logError('Failed to create EventSource', error);
            this.scheduleReconnect();
        }
    }

    handleConnected(event) {
        this.connected = true;
        this.log('✅ Connected to SSE stream');
        
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        
        this.connectionCallbacks.forEach(cb => {
            try {
                cb();
            } catch (e) {
                this.logError('Connection callback error', e);
            }
        });
    }

    handleMessage(event) {
        try {
            const message = JSON.parse(event.data);
            
            if (this.debug) {
                this.log('📨 Received:', message.type, message);
            }
            
            // Trigger registered handlers
            const handlers = this.messageHandlers[message.type] || [];
            handlers.forEach(handler => {
                try {
                    handler(message.payload || message.data, message);
                } catch (e) {
                    this.logError(`Handler error for ${message.type}`, e);
                }
            });
            
            // Trigger wildcard handlers
            const wildcardHandlers = this.messageHandlers['*'] || [];
            wildcardHandlers.forEach(handler => {
                try {
                    handler(message.payload || message.data, message);
                } catch (e) {
                    this.logError('Wildcard handler error', e);
                }
            });
            
        } catch (error) {
            this.logError('Failed to parse message', error);
        }
    }

    handleError(error) {
        this.connected = false;
        this.logError('SSE error', error);
        
        this.disconnectionCallbacks.forEach(cb => {
            try {
                cb(error);
            } catch (e) {
                this.logError('Disconnection callback error', e);
            }
        });
        
        if (this.autoReconnect) {
            this.scheduleReconnect();
        }
    }

    scheduleReconnect() {
        if (this.reconnectTimer) {
            return;
        }
        
        this.log(`🔄 Reconnecting in ${this.reconnectDelay / 1000}s...`);
        
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.disconnect();
            this.connect();
        }, this.reconnectDelay);
    }

    on(type, handler) {
        if (!this.messageHandlers[type]) {
            this.messageHandlers[type] = [];
        }
        
        this.messageHandlers[type].push(handler);
        this.log(`📝 Registered handler for: ${type}`);
        
        return () => {
            this.off(type, handler);
        };
    }

    off(type, handler) {
        if (!this.messageHandlers[type]) {
            return;
        }
        
        const index = this.messageHandlers[type].indexOf(handler);
        if (index > -1) {
            this.messageHandlers[type].splice(index, 1);
            this.log(`🗑️  Removed handler for: ${type}`);
        }
    }

    onConnect(callback) {
        this.connectionCallbacks.push(callback);
        
        if (this.connected) {
            try {
                callback();
            } catch (e) {
                this.logError('Connection callback error', e);
            }
        }
    }

    onDisconnect(callback) {
        this.disconnectionCallbacks.push(callback);
    }

    disconnect() {
        this.autoReconnect = false;
        
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        
        this.connected = false;
        this.log('Disconnected');
    }

    isConnected() {
        return this.connected && this.eventSource && this.eventSource.readyState === EventSource.OPEN;
    }

    log(...args) {
        if (this.debug) {
            console.log(`[SSEOverlay:${this.className}]`, ...args);
        }
    }

    logError(...args) {
        console.error(`[SSEOverlay:${this.className}]`, ...args);
    }
}

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SSEOverlayClient;
}
