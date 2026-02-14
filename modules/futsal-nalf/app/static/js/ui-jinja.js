/**
 * UI-JINJA.JS - Simplified timer UI with Jinja2 rendering
 * 
 * This file handles:
 * - WebSocket updates for existing timers
 * - User interactions (buttons)
 * - Timer display formatting
 * 
 * It does NOT:
 * - Create timers in backend (done by period_manager)
 * - Build DOM elements (done by Jinja2)
 * - Manage timer list (done server-side)
 */

// ============================================================================
// WEBSOCKET SETUP
// ============================================================================

const socket = io();

socket.on('connect', () => {
    console.log('✅ WebSocket connected');
});

socket.on('disconnect', () => {
    console.log('❌ WebSocket disconnected');
});

// ============================================================================
// TIMER DISPLAY FORMATTING
// ============================================================================

/**
 * Format milliseconds to MM:SS display
 */
function formatTime(milliseconds) {
    const totalSeconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

/**
 * Update timer display element
 */
function updateTimerDisplay(timerId, elapsedTime) {
    // Use data attribute selector instead of ID
    const displayElement = document.querySelector(`[data-display-for="${timerId}"]`);
    if (displayElement) {
        displayElement.textContent = formatTime(elapsedTime);
    } else {
        console.warn(`Display element not found for timer: ${timerId}`);
    }
}

/**
 * Update timer state badge
 */
function updateTimerState(timerId, state) {
    const timerCard = document.querySelector(`[data-timer-id="${timerId}"]`);
    if (!timerCard) return;
    
    const badge = timerCard.querySelector('.timer-badge');
    if (badge && state) {
        // Remove all state classes
        badge.classList.remove('timer-badge-idle', 'timer-badge-running', 
                              'timer-badge-paused', 'timer-badge-limit_reached');
        
        // Add new state class
        badge.classList.add(`timer-badge-${state}`);
        badge.textContent = state.toUpperCase();
    }
}

// ============================================================================
// WEBSOCKET EVENT HANDLERS - UPDATES ONLY
// ============================================================================

/**
 * Handle timer updated event
 */
socket.on('timer_updated', (data) => {
    console.log('Timer updated:', data);
    if (data.elapsed_time !== undefined) {
        updateTimerDisplay(data.timer_id, data.elapsed_time);
    }
    if (data.state) {
        updateTimerState(data.timer_id, data.state);
    }
});

/**
 * Handle timer started event
 */
socket.on('timer_started', (data) => {
    console.log('Timer started:', data);
    if (data.elapsed_time !== undefined) {
        updateTimerDisplay(data.timer_id, data.elapsed_time);
    }
    if (data.state) {
        updateTimerState(data.timer_id, data.state);
    }
});

/**
 * Handle timer paused event
 */
socket.on('timer_paused', (data) => {
    console.log('Timer paused:', data);
    if (data.elapsed_time !== undefined) {
        updateTimerDisplay(data.timer_id, data.elapsed_time);
    }
    if (data.state) {
        updateTimerState(data.timer_id, data.state);
    }
});

/**
 * Handle timer reset event
 */
socket.on('timer_reset', (data) => {
    console.log('Timer reset:', data);
    updateTimerDisplay(data.timer_id, data.elapsed_time || 0);
    if (data.state) {
        updateTimerState(data.timer_id, data.state);
    }
});

/**
 * Handle timer adjusted event
 */
socket.on('timer_adjusted', (data) => {
    console.log('Timer adjusted:', data);
    // Timer will send updated event with new elapsed_time
});

/**
 * Handle limit reached event
 */
socket.on('limit_reached', (data) => {
    console.log('Timer limit reached:', data);
    if (data.elapsed_time !== undefined) {
        updateTimerDisplay(data.timer_id, data.elapsed_time);
    }
    if (data.state) {
        updateTimerState(data.timer_id, data.state);
    }
    
    // Optional: Show notification
    if (data.timer_id === mainTimerData?.timer_id) {
        console.log('⏰ Główny timer osiągnął limit!');
    }
});

/**
 * Handle timer created event (for penalties added during period)
 */
socket.on('penalty_timer_created', (data) => {
    console.log('Penalty timer created:', data);
    
    // Reload page to get new penalty in DOM
    // Alternative: Could dynamically create DOM element, but Jinja2 is cleaner
    setTimeout(() => {
        window.location.reload();
    }, 500);
});

// ============================================================================
// TIMER CONTROL FUNCTIONS
// ============================================================================

/**
 * Start a timer
 */
function startTimer(timerId) {
    console.log('Starting timer:', timerId);
    socket.emit('timer_start', { timer_id: timerId });
}

/**
 * Pause a timer
 */
function pauseTimer(timerId) {
    console.log('Pausing timer:', timerId);
    socket.emit('timer_pause', { timer_id: timerId });
}

/**
 * Resume a paused timer
 */
function resumeTimer(timerId) {
    console.log('Resuming timer:', timerId);
    socket.emit('timer_resume', { timer_id: timerId });
}

/**
 * Reset a timer
 */
function resetTimer(timerId) {
    if (!confirm('Czy na pewno chcesz zresetować timer?')) {
        return;
    }
    console.log('Resetting timer:', timerId);
    socket.emit('timer_reset', { timer_id: timerId });
}

/**
 * Adjust timer time
 */
function adjustTimer(timerId, delta, isPenalty=false) {
    if(isPenalty == true){
        console.log(`Adjusting timer ${timerId} by ${delta}ms`);
        socket.emit('timer_adjust', {
            timer_id: timerId,
            delta: delta
        });
    } else {
        let allTimersIds = getAllTimerIds();
        allTimersIds.forEach(tmrId => {
            console.log(`Adjusting timer ${tmrId} by ${delta}ms`);
            socket.emit('timer_adjust', {
                timer_id: tmrId,
                delta: delta
            });
        });
    }
}

/**
 * Remove timer from UI and backend
 */
function removeTimerFromUI(timerId) {
    if (!confirm('Czy na pewno chcesz usunąć ten timer?')) {
        return;
    }
    
    console.log('🗑️  Removing timer:', timerId);
    socket.emit('timer_remove', { timer_id: timerId });
}

/**
 * Handle timer removed event
 */
socket.on('timer_removed', (data) => {
    console.log('✅ Timer removed from backend:', data.timer_id);
    
    // Remove from DOM
    const timerCard = document.querySelector(`[data-timer-id="${data.timer_id}"]`);
    if (timerCard) {
        console.log('Removing timer card from DOM');
        timerCard.remove();
    } else {
        console.warn('⚠️  Timer card not found in DOM:', data.timer_id);
    }
});

/**
 * Handle error event
 */
socket.on('error', (data) => {
    console.error('❌ Socket error:', data);
    alert(`Błąd: ${data.message}`);
});

// ============================================================================
// PENALTY MANAGEMENT
// ============================================================================

/**
 * Show add penalty dialog
 */
function showAddPenaltyDialog() {
    document.getElementById('penalty-dialog').style.display = 'block';
    document.getElementById('penalty-overlay').style.display = 'block';
}

/**
 * Hide add penalty dialog
 */
function hideAddPenaltyDialog() {
    document.getElementById('penalty-dialog').style.display = 'none';
    document.getElementById('penalty-overlay').style.display = 'none';
}

/**
 * Add penalty timer
 */
function addPenalty(event) {
    event.preventDefault();
    
    const team = document.getElementById('penalty-team').value;
    const duration = parseInt(document.getElementById('penalty-duration').value);
    
    if (!mainTimerData) {
        alert('Brak aktywnego głównego timera!');
        return;
    }
    
    // Get team name
    let teamName = '';
    if (game) {
        teamName = team === 'home' ? game.home_team.name : game.away_team.name;
    }
    
    console.log('Adding penalty:', { team, teamName, duration });
    
    socket.emit('penalty_timer_create', {
        match_timer_id: mainTimerData.timer_id,
        team: team,
        team_name: teamName,
        duration_minutes: duration
    });
    
    hideAddPenaltyDialog();
    
    // Show loading message
    alert(`Dodawanie kary dla drużyny ${team}...`);
}

// ============================================================================
// PERIOD FINISH
// ============================================================================

/**
 * Finish current period
 */
function finishPeriod() {
    if (!period) {
        alert('Brak aktywnego okresu!');
        return;
    }
    
    if (!confirm('Czy na pewno chcesz zakończyć tę część meczu?')) {
        return;
    }
    
    console.log('Finishing period:', period.id);
    window.location.href = `/period/${period.id}/finish`;
}

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('UI initialized with Jinja2 rendering');
    console.log('Period:', period);
    console.log('Main timer:', mainTimerData);
    console.log('Penalties:', penaltiesData);
    
    // Initialize displays with current data
    if (mainTimerData) {
        updateTimerDisplay(mainTimerData.timer_id, mainTimerData.initial_time || 0);
        updateTimerState(mainTimerData.timer_id, mainTimerData.state || 'idle');
    }
    
    if (penaltiesData && penaltiesData.length > 0) {
        penaltiesData.forEach(penalty => {
            updateTimerDisplay(penalty.timer_id, penalty.initial_time || 0);
            updateTimerState(penalty.timer_id, penalty.state || 'idle');
        });
    }
    
    console.log('✅ UI ready - listening for WebSocket updates');
});

// ============================================================================
// ERROR HANDLING
// ============================================================================

// Error handler moved to removeTimerFromUI section

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Get timer element by ID
 */
function getTimerElement(timerId) {
    return document.querySelector(`[data-timer-id="${timerId}"]`);
}

/**
 * Check if timer exists in DOM
 */
function timerExists(timerId) {
    return getTimerElement(timerId) !== null;
}

/**
 * Get all timer IDs currently in DOM
 */
function getAllTimerIds() {
    const timerElements = document.querySelectorAll('[data-timer-id]');
    return [...new Set(Array.from(timerElements).map(el => el.getAttribute('data-timer-id')))];
}

// ============================================================================
// DEBUG HELPERS
// ============================================================================

window.debugTimers = () => {
    console.log('=== TIMER DEBUG ===');
    console.log('Period:', period);
    console.log('Main timer data:', mainTimerData);
    console.log('Penalties data:', penaltiesData);
    console.log('DOM timer IDs:', getAllTimerIds());
    console.log('Socket connected:', socket.connected);
};

// Expose functions to global scope for onclick handlers
window.startTimer = startTimer;
window.pauseTimer = pauseTimer;
window.resumeTimer = resumeTimer;
window.resetTimer = resetTimer;
window.adjustTimer = adjustTimer;
window.removeTimerFromUI = removeTimerFromUI;
window.showAddPenaltyDialog = showAddPenaltyDialog;
window.hideAddPenaltyDialog = hideAddPenaltyDialog;
window.addPenalty = addPenalty;
window.finishPeriod = finishPeriod;