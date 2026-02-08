/**
 * Timer Overlay Logic for Futsal NALF
 * 
 * Uses SSE instead of WebSocket - NO REGISTRATION needed!
 */

class TimerOverlay {
    constructor(sseClient, formatters) {
        this.sseClient = sseClient;
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
            format: 'mm:ss',
            showMilliseconds: false,
            padZeros: true
        };
        
        this.init();
    }

    init() {
        // Register SSE handlers
        this.sseClient.on('timer_updated', (payload) => {
            this.handleTimerUpdate(payload);
        });
        
        // Connection status handlers
        this.sseClient.onConnect(() => {
            this.updateConnectionStatus(true);
        });
        
        this.sseClient.onDisconnect(() => {
            this.updateConnectionStatus(false);
        });
        
        console.log('✅ Timer overlay initialized (SSE mode)');
    }

    handleTimerUpdate(payload) {
        console.log('📨 Timer update received:', payload);
        
        // Extract data
        this.currentState = payload.state || 'stopped';
        this.elapsedTime = payload.elapsed_time || 0;
        this.limit = payload.limit || 0;
        
        // Update display
        this.updateDisplay();
    }

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

    updateConnectionStatus(connected) {
        if (!this.statusIndicator) return;
        
        if (connected) {
            this.statusIndicator.classList.add('connected');
        } else {
            this.statusIndicator.classList.remove('connected');
        }
    }

    setFormatOptions(options) {
        this.formatOptions = { ...this.formatOptions, ...options };
        this.updateDisplay();
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Initialize SSE client (receives ALL timer_updated messages)
    const sseClient = new SSEOverlayClient({
        debug: true
    });
    
    // Initialize timer overlay with formatters
    const timerOverlay = new TimerOverlay(sseClient, window.FutsalFormatters);
    
    // Connect to SSE stream
    sseClient.connect();
    
    // Make available globally for debugging
    window.timerOverlay = timerOverlay;
    window.sseClient = sseClient;
    
    console.log('🚀 Timer overlay ready (SSE mode)');
});
