/**
 * Timer Overlay Logic for Futsal NALF
 * 
 * Handles timer display and updates from HUB
 */

class TimerOverlay {
    constructor(wsClient, formatters) {
        this.wsClient = wsClient;
        this.formatters = formatters;
        
        // DOM elements
        this.timerDisplay = document.getElementById('timer-display');
        this.statusIndicator = document.getElementById('connection-status');
        this.stateElement = document.getElementById('timer-state');
        
        // State
        this.currentState = 'stopped';
        this.elapsedTime = 0;
        this.limit = 0;
        
        // Format options (can be configured per module)
        this.formatOptions = {
            format: 'mm:ss',      // Format type
            showMilliseconds: false,
            padZeros: true
        };
        
        this.init();
    }

    init() {
        // Register WebSocket handlers
        this.wsClient.on('timer_updated', (payload) => {
            this.handleTimerUpdate(payload);
        });
        
        // Connection status handlers
        this.wsClient.onConnect(() => {
            this.updateConnectionStatus(true);
        });
        
        this.wsClient.onDisconnect(() => {
            this.updateConnectionStatus(false);
        });
        
        console.log('✅ Timer overlay initialized');
    }

    /**
     * Handle timer update from HUB
     */
    handleTimerUpdate(payload) {
        console.log('📨 Timer update received:', payload);
        
        // Extract data
        this.currentState = payload.state || 'stopped';
        this.elapsedTime = payload.elapsed_time || 0;
        this.limit = payload.limit || 0;
        
        // Update display
        this.updateDisplay();
    }

    /**
     * Update timer display
     */
    updateDisplay() {
        if (!this.timerDisplay) return;
        
        // Format elapsed time using module-specific formatter
        const formattedTime = this.formatters.formatElapsedTime(
            this.elapsedTime,
            this.formatOptions
        );
        
        // Update display
        this.timerDisplay.textContent = formattedTime;
        
        // Update state styling
        if (this.stateElement) {
            this.stateElement.textContent = this.currentState.toUpperCase();
            
            // Remove old state classes
            this.timerDisplay.classList.remove('timer-running', 'timer-paused', 'timer-stopped');
            
            // Add current state class
            this.timerDisplay.classList.add(`timer-${this.currentState}`);
        }
        
        // Check if overtime
        if (this.limit > 0 && this.formatters.isOvertime(this.elapsedTime, this.limit)) {
            this.timerDisplay.classList.add('timer-overtime');
        } else {
            this.timerDisplay.classList.remove('timer-overtime');
        }
    }

    /**
     * Update connection status indicator
     */
    updateConnectionStatus(connected) {
        if (!this.statusIndicator) return;
        
        if (connected) {
            this.statusIndicator.classList.add('connected');
        } else {
            this.statusIndicator.classList.remove('connected');
        }
    }

    /**
     * Change format options (can be called externally)
     */
    setFormatOptions(options) {
        this.formatOptions = { ...this.formatOptions, ...options };
        this.updateDisplay(); // Re-render with new format
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Initialize WebSocket client with UNIQUE ID per instance
    const wsClient = new WSClient({
        // overlayId: auto-generated unique ID
        overlayName: 'Timer Overlay',
        moduleOwner: 'futsal-nalf',
        subscribeClasses: ['timer'],
        debug: true
    });
    
    // Initialize timer overlay with formatters
    const timerOverlay = new TimerOverlay(wsClient, window.FutsalFormatters);
    
    // Connect to HUB
    wsClient.connect();
    
    // Make available globally for debugging
    window.timerOverlay = timerOverlay;
    window.wsClient = wsClient;
    
    console.log('🚀 Timer overlay ready');
});
