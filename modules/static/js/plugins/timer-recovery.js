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
        this.recoveryDone = false; // Guard against multiple runs (e.g. socket reconnects)
    }

    /**
     * Initialize recovery process
     * Called when UI loads
     */
    async init() {
        // Only run once per page load - reconnects should not trigger recovery again
        if (this.recoveryDone) {
            console.log('ℹ️  Recovery already completed this session - skipping');
            return;
        }

        console.log('🔄 Starting timer recovery check...');
        
        try {
            // Step 1: Fetch settings from database
            await this.fetchSettings();
            
            if (!this.settings || !this.settings.current_timers) {
                console.log('ℹ️  No timers in settings - nothing to recover');
                this.recoveryDone = true;
                return;
            }

            const mainTimer = this.settings.current_timers.main;
            const penalties = this.settings.current_timers.penalties || { home: [], away: [] };
            const hasPenalties = penalties.home.length > 0 || penalties.away.length > 0;
            
            if (!mainTimer && !hasPenalties) {
                console.log('ℹ️  No active timers - nothing to recover');
                this.recoveryDone = true;
                return;
            }

            // Step 2: Request timer states from plugin
            await this.requestPluginTimers();
            
        } catch (error) {
            console.error('❌ Timer recovery failed:', error);
        } finally {
            this.recoveryDone = true;
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
                console.warn('⚠️  Plugin did not respond within 3 seconds - treating as offline');
                this.socket.off('timer_plugin_offline', offlineHandler);
                this.socket.off('timer_plugin_all_timers', allTimersHandler);
                // Plugin offline/unresponsive - skip restore, timers will be
                // recreated when plugin comes back online via timer_plugin_online event
                console.warn('⚠️  Skipping restore - plugin is not available');
                resolve(null);
            }, 3000);

            // Handle immediate offline response from backend
            const offlineHandler = () => {
                clearTimeout(timeout);
                this.socket.off('timer_plugin_all_timers', allTimersHandler);
                console.warn('⚠️  Timer plugin is offline - skipping restore');
                // Do NOT call performRecovery([]) here - plugin is offline so
                // create_timer events would be lost. Recovery will run when plugin reconnects.
                resolve(null);
            };

            // Listen for successful response
            const allTimersHandler = (data) => {
                clearTimeout(timeout);
                this.socket.off('timer_plugin_offline', offlineHandler);
                this.handlePluginTimersResponse(data);
                resolve(data);
            };

            this.socket.once('timer_plugin_all_timers', allTimersHandler);
            this.socket.once('timer_plugin_offline', offlineHandler);

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
        const penaltyTimers = homePenaltyTimers.concat(awayPenaltyTimers);

        // Create a set of plugin timer IDs for quick lookup
        const pluginTimerIds = new Set(pluginTimers.map(t => t.timer_id));

        console.log('🔍 Plugin has timers:', [...pluginTimerIds]);

        const timersToRestore = [];

        // Check main timer
        if (mainTimer) {
            if (pluginTimerIds.has(mainTimer.timer_id)) {
                console.log(`✅ Main timer already in plugin: ${mainTimer.timer_id}`);
            } else {
                console.log(`⚠️  Main timer missing in plugin: ${mainTimer.timer_id}`);
                timersToRestore.push({ type: 'main', data: mainTimer });
            }
        }

        // Check penalty timers
        penaltyTimers.forEach(penalty => {
            if (pluginTimerIds.has(penalty.timer_id)) {
                console.log(`✅ Penalty timer already in plugin: ${penalty.timer_id}`);
            } else {
                console.log(`⚠️  Penalty timer missing in plugin: ${penalty.timer_id}`);
                timersToRestore.push({ type: 'penalty', data: penalty });
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
            initial_time: timerData.elapsed_time || timerData.initial_time || 0,
            limit: timerData.limit,
            pause_at_limit: timerData.pause_at_limit !== false,
            metadata: timerData.metadata || {}
        };

        this.socket.emit('timer_plugin_create_timer', payload);
        
        if (timerData.state === 'running') {
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
            initial_time: timerData.elapsed_time || timerData.initial_time || 0,
            limit: timerData.limit || 120000,
            metadata: timerData.metadata || {}
        };

        this.socket.emit('timer_plugin_create_timer', payload);
        
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
        this.recoveryDone = false;
        this.recoveryInProgress = false;
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
        
        if (!timerRecovery) {
            // First connection - create instance and run recovery
            setTimeout(() => {
                timerRecovery = new TimerRecovery(socket);
                timerRecovery.init();
                window.timerRecovery = timerRecovery;
            }, 500);
        }
        // Subsequent reconnects - instance already exists, recoveryDone=true blocks re-run
    });
});