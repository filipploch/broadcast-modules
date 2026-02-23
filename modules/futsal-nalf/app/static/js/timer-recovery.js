/**
 * Timer Recovery Module - FOR UI-JINJA.HTML
 * Handles timer recovery after system crash/restart
 * 
 * COMPATIBILITY: Works with ui-jinja.html + ui-jinja.js architecture
 * 
 * FLOW:
 * 1. On UI load, fetch settings from /api/settings
 * 2. Check if timers exist in settings.current_timers
 * 3. Query timer-plugin for actual timer states
 * 4. Compare and restore any missing timers
 */

class TimerRecovery {
    constructor(socket) {
        this.socket = socket;
        this.settings = null;
        this.pluginTimers = null;
        this.recoveryInProgress = false;
    }

    /**
     * Initialize recovery process
     * Called when UI loads
     */
    async init() {
        console.log('🔄 Starting timer recovery check...');
        
        try {
            // Step 1: Fetch settings from database
            await this.fetchSettings();
            
            if (!this.settings || !this.settings.current_timers) {
                console.log('ℹ️  No timers in settings - nothing to recover');
                return;
            }

            const mainTimer = this.settings.current_timers.main;
            const penalties = this.settings.current_timers.penalties || [];
            
            if (!mainTimer && penalties.length === 0) {
                console.log('ℹ️  No active timers - nothing to recover');
                return;
            }

            // Step 2: Request timer states from plugin
            await this.requestPluginTimers();
            
            // Step 3: Wait for plugin response, then compare and restore
            // This happens in handlePluginTimersResponse()
            
        } catch (error) {
            console.error('❌ Timer recovery failed:', error);
        }
    }

    /**
     * Fetch current settings from API
     */
    async fetchSettings() {
        try {
            const response = await fetch('/api/settings');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            this.settings = await response.json();
            console.log('✅ Settings fetched:', this.settings);
            
            return this.settings;
        } catch (error) {
            console.error('❌ Failed to fetch settings:', error);
            throw error;
        }
    }

    /**
     * Request all timers from timer-plugin
     */
    requestPluginTimers() {
        return new Promise((resolve) => {
            // Set timeout in case plugin doesn't respond
            const timeout = setTimeout(() => {
                console.warn('⚠️  Plugin did not respond within 3 seconds');
                resolve(null);
            }, 3000);

            // Listen for response
            this.socket.once('timer_plugin_all_timers', (data) => {
                clearTimeout(timeout);
                this.handlePluginTimersResponse(data);
                resolve(data);
            });

            // Send request
            this.socket.emit('timer_plugin_request_all_timers');
            console.log('📤 Requested all timers from plugin');
        });
    }

    /**
     * Handle response from timer-plugin with all timers
     */
    handlePluginTimersResponse(data) {
        console.log('📥 Received plugin timers:', data);
        
        if (!data || !data.timers) {
            console.warn('⚠️  No timers data from plugin');
            this.performRecovery([]);
            return;
        }

        this.pluginTimers = data.timers;
        this.performRecovery(this.pluginTimers);
    }

    /**
     * Compare settings timers with plugin timers and restore missing ones
     */
    performRecovery(pluginTimers) {
        if (this.recoveryInProgress) {
            console.log('⚠️  Recovery already in progress');
            return;
        }

        this.recoveryInProgress = true;
        console.log('🔧 Starting timer recovery...');

        const settingsTimers = this.settings.current_timers;
        const mainTimer = settingsTimers.main;
        const homePenaltyTimers = settingsTimers.penalties['home'] || [];
        const awayPenaltyTimers = settingsTimers.penalties['away'] || [];
        const penaltyTimers = homePenaltyTimers.concat(awayPenaltyTimers) || [];

        // Create a map of plugin timer IDs for quick lookup
        const pluginTimerIds = new Set(
            pluginTimers.map(t => t.timer_id)
        );

        const timersToRestore = [];

        // Check main timer
        if (mainTimer && !pluginTimerIds.has(mainTimer.timer_id)) {
            console.log(`⚠️  Main timer missing in plugin: ${mainTimer.timer_id}`);
            timersToRestore.push({
                type: 'main',
                data: mainTimer
            });
        }

        // Check penalty timers
        penaltyTimers.forEach(penalty => {
            if (!pluginTimerIds.has(penalty.timer_id)) {
                console.log(`⚠️  Penalty timer missing in plugin: ${penalty.timer_id}`);
                timersToRestore.push({
                    type: 'penalty',
                    data: penalty
                });
            }
        });

        // Restore missing timers
        if (timersToRestore.length > 0) {
            console.log(`🔄 Restoring ${timersToRestore.length} timer(s)...`);
            this.restoreTimers(timersToRestore);
        } else {
            console.log('✅ All timers are present - no recovery needed');
        }

        this.recoveryInProgress = false;
    }

    /**
     * Restore missing timers in timer-plugin
     */
    restoreTimers(timersToRestore) {
        timersToRestore.forEach(({ type, data }) => {
            if (type === 'main') {
                this.restoreMainTimer(data);
            } else if (type === 'penalty') {
                this.restorePenaltyTimer(data);
            }
        });
    }

    /**
     * Restore main timer
     */
    restoreMainTimer(timerData) {
        console.log('🔧 Restoring main timer:', timerData.timer_id);
        
        const payload = {
            timer_id: timerData.timer_id,
            timer_type: timerData.timer_type || 'independent',
            initial_time: timerData.initial_time || 0,
            limit: timerData.limit,
            pause_at_limit: timerData.pause_at_limit !== false,
            metadata: timerData.metadata || {}
        };

        // Send create_timer event
        this.socket.emit('timer_plugin_create_timer', payload);
        
        // If timer was running, restore its state
        if (timerData.state === 'running') {
            // Wait a bit for timer to be created, then start it
            setTimeout(() => {
                this.socket.emit('timer_plugin_start_timer', {
                    timer_id: timerData.timer_id
                });
                console.log(`▶️  Started restored timer: ${timerData.timer_id}`);
            }, 100);
        }
    }

    /**
     * Restore penalty timer
     */
    restorePenaltyTimer(timerData) {
        console.log('🔧 Restoring penalty timer:', timerData.timer_id);
        
        const payload = {
            timer_id: timerData.timer_id,
            timer_type: 'dependent',
            parent_id: timerData.parent_id,
            initial_time: timerData.initial_time || 0,
            limit: timerData.limit || 120000,
            metadata: timerData.metadata || {}
        };

        // Send create_timer event
        this.socket.emit('timer_plugin_create_timer', payload);
        
        // If timer was running, restore its state
        if (timerData.state === 'running') {
            setTimeout(() => {
                this.socket.emit('timer_plugin_start_timer', {
                    timer_id: timerData.timer_id
                });
                console.log(`▶️  Started restored penalty timer: ${timerData.timer_id}`);
            }, 100);
        }
    }

    /**
     * Manual recovery trigger (for debugging)
     */
    manualRecovery() {
        console.log('🔄 Manual recovery triggered');
        this.init();
    }
}

// Initialize on DOM ready
let timerRecovery = null;

// NOTE: ui-jinja.js already defines socket, so we reuse it
document.addEventListener('DOMContentLoaded', () => {
    // Wait for socket to connect
    socket.on('connect', () => {
        console.log('✅ Socket connected - initializing timer recovery');
        
        // Initialize recovery after a short delay to ensure everything is ready
        setTimeout(() => {
            timerRecovery = new TimerRecovery(socket);
            timerRecovery.init();
        }, 500);
    });
});

// Export for global access (debugging)
window.timerRecovery = timerRecovery;