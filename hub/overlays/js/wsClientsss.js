/**
 * Universal WebSocket Client for Broadcast Hub Overlays
 * 
 * Features:
 * - Auto-reconnect on disconnect
 * - Automatic registration as overlay
 * - Class subscription support
 * - Event-based message handling
 * - Connection status management
 */

class WSClient {
    constructor(config = {}) {
        // Configuration
        this.overlayId = config.overlayId || this.generateOverlayId();
        this.overlayName = config.overlayName || 'Overlay';
        this.moduleOwner = config.moduleOwner || 'unknown';  // e.g., 'futsal-nalf'
        this.hubUrl = config.hubUrl || this.getHubUrlFromQueryParams();
        this.subscribeClasses = config.subscribeClasses || [];
        this.autoReconnect = config.autoReconnect !== false;
        this.reconnectDelay = config.reconnectDelay || 3000;
        this.debug = config.debug || false;
        
        // State
        this.ws = null;
        this.connected = false;
        this.reconnectTimer = null;
        this.messageHandlers = {};
        this.connectionCallbacks = [];
        this.disconnectionCallbacks = [];
        
        // Bind methods
        this.connect = this.connect.bind(this);
        this.disconnect = this.disconnect.bind(this);
        this.send = this.send.bind(this);
        this.on = this.on.bind(this);
        
        this.log('Initialized', { overlayId: this.overlayId, hubUrl: this.hubUrl });
    }

    /**
     * Generate unique overlay ID based on module and timestamp
     */
    generateOverlayId() {
        const timestamp = Date.now();
        const random = Math.random().toString(36).substring(7);
        return `overlay-${this.moduleOwner}-${random}-${timestamp}`;
    }

    /**
     * Get HUB URL from query parameters or use default
     */
    getHubUrlFromQueryParams() {
        const params = new URLSearchParams(window.location.search);
        const hubParam = params.get('hub');
        
        if (hubParam) {
            return hubParam;
        }
        
        // Default to same host
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.hostname;
        const port = params.get('port') || '8080';
        
        return `${protocol}//${host}:${port}/ws`;
    }

    /**
     * Connect to HUB
     */
    connect() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.log('Already connected');
            return;
        }

        this.log('Connecting to HUB...', this.hubUrl);

        try {
            this.ws = new WebSocket(this.hubUrl);
            
            this.ws.onopen = this.handleOpen.bind(this);
            this.ws.onmessage = this.handleMessage.bind(this);
            this.ws.onerror = this.handleError.bind(this);
            this.ws.onclose = this.handleClose.bind(this);
            
        } catch (error) {
            this.logError('Failed to create WebSocket', error);
            this.scheduleReconnect();
        }
    }

    /**
     * Handle WebSocket open
     */
    handleOpen() {
        this.connected = true;
        this.log('✅ Connected to HUB');
        
        // Clear any pending reconnect
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        
        // Register with HUB
        this.register();
        
        // Notify connection callbacks
        this.connectionCallbacks.forEach(cb => {
            try {
                cb();
            } catch (e) {
                this.logError('Connection callback error', e);
            }
        });
    }

    /**
     * Register overlay with HUB
     */
    register() {
        this.log('📝 Registering as overlay...');
        
        this.send({
            type: 'register',
            payload: {
                id: this.overlayId,
                name: this.overlayName,
                component_type: 'overlay',
                type: 'overlay',
                module_owner: this.moduleOwner
            }
        });
        
        // Subscribe to classes after a short delay (wait for registration to complete)
        setTimeout(() => {
            if (this.subscribeClasses.length > 0) {
                this.subscribeToClasses(this.subscribeClasses);
            }
        }, 100);
    }

    /**
     * Subscribe to broadcast classes
     */
    subscribeToClasses(classes) {
        if (!Array.isArray(classes)) {
            classes = [classes];
        }
        
        this.log('📢 Subscribing to classes:', classes);
        
        this.send({
            type: 'subscribe',
            payload: {
                class: classes
            }
        });
        
        // Update stored subscriptions
        this.subscribeClasses = classes;
    }

    /**
     * Unsubscribe from broadcast classes
     */
    unsubscribeFromClasses(classes) {
        if (!Array.isArray(classes)) {
            classes = [classes];
        }
        
        this.log('🔕 Unsubscribing from classes:', classes);
        
        this.send({
            type: 'unsubscribe',
            payload: {
                classes: classes
            }
        });
    }

    /**
     * Handle incoming WebSocket message
     */
    handleMessage(event) {
        try {
            const message = JSON.parse(event.data);
            
            if (this.debug) {
                this.log('📨 Received:', message.type, message);
            }
            
            // Handle system messages
            this.handleSystemMessage(message);
            
            // Trigger registered handlers
            const handlers = this.messageHandlers[message.type] || [];
            handlers.forEach(handler => {
                try {
                    handler(message.payload, message);
                } catch (e) {
                    this.logError(`Handler error for ${message.type}`, e);
                }
            });
            
            // Trigger wildcard handlers
            const wildcardHandlers = this.messageHandlers['*'] || [];
            wildcardHandlers.forEach(handler => {
                try {
                    handler(message.payload, message);
                } catch (e) {
                    this.logError('Wildcard handler error', e);
                }
            });
            
        } catch (error) {
            this.logError('Failed to parse message', error);
        }
    }

    /**
     * Handle system messages
     */
    handleSystemMessage(message) {
        switch (message.type) {
            case 'registered':
                this.log('✅ Registered with HUB');
                break;
                
            case 'subscribed':
                const classes = message.payload?.classes || [];
                this.log('✅ Subscribed to classes:', classes);
                break;
                
            case 'unsubscribed':
                const unsubClasses = message.payload?.classes || [];
                this.log('✅ Unsubscribed from classes:', unsubClasses);
                break;
        }
    }

    /**
     * Handle WebSocket error
     */
    handleError(error) {
        this.logError('WebSocket error', error);
    }

    /**
     * Handle WebSocket close
     */
    handleClose(event) {
        this.connected = false;
        this.log(`❌ Disconnected from HUB (code: ${event.code})`);
        
        // Notify disconnection callbacks
        this.disconnectionCallbacks.forEach(cb => {
            try {
                cb(event);
            } catch (e) {
                this.logError('Disconnection callback error', e);
            }
        });
        
        // Auto-reconnect if enabled
        if (this.autoReconnect) {
            this.scheduleReconnect();
        }
    }

    /**
     * Schedule reconnection attempt
     */
    scheduleReconnect() {
        if (this.reconnectTimer) {
            return; // Already scheduled
        }
        
        this.log(`🔄 Reconnecting in ${this.reconnectDelay / 1000}s...`);
        
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();
        }, this.reconnectDelay);
    }

    /**
     * Send message to HUB
     */
    send(message) {
        if (!this.connected || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            this.logError('Cannot send - not connected');
            return false;
        }
        
        // Add default fields
        if (!message.from) {
            message.from = this.overlayId;
        }
        if (!message.to) {
            message.to = 'hub';
        }
        if (!message.timestamp) {
            message.timestamp = new Date().toISOString();
        }
        
        try {
            this.ws.send(JSON.stringify(message));
            
            if (this.debug) {
                this.log('📤 Sent:', message.type, message);
            }
            
            return true;
        } catch (error) {
            this.logError('Failed to send message', error);
            return false;
        }
    }

    /**
     * Register message handler
     * 
     * @param {string} type - Message type to handle, or '*' for all messages
     * @param {function} handler - Handler function (payload, fullMessage) => void
     */
    on(type, handler) {
        if (!this.messageHandlers[type]) {
            this.messageHandlers[type] = [];
        }
        
        this.messageHandlers[type].push(handler);
        
        this.log(`📝 Registered handler for: ${type}`);
        
        // Return unsubscribe function
        return () => {
            this.off(type, handler);
        };
    }

    /**
     * Remove message handler
     */
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

    /**
     * Register connection callback
     */
    onConnect(callback) {
        this.connectionCallbacks.push(callback);
        
        // If already connected, call immediately
        if (this.connected) {
            try {
                callback();
            } catch (e) {
                this.logError('Connection callback error', e);
            }
        }
    }

    /**
     * Register disconnection callback
     */
    onDisconnect(callback) {
        this.disconnectionCallbacks.push(callback);
    }

    /**
     * Disconnect from HUB
     */
    disconnect() {
        this.autoReconnect = false;
        
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        
        this.connected = false;
        this.log('Disconnected');
    }

    /**
     * Check if connected
     */
    isConnected() {
        return this.connected && this.ws && this.ws.readyState === WebSocket.OPEN;
    }

    /**
     * Log helper
     */
    log(...args) {
        if (this.debug) {
            console.log(`[WSClient:${this.overlayId}]`, ...args);
        }
    }

    /**
     * Error log helper
     */
    logError(...args) {
        console.error(`[WSClient:${this.overlayId}]`, ...args);
    }
}

// Export for use in modules (if using modules)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WSClient;
}