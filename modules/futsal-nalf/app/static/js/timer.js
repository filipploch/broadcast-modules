/**
 * Frontend Timer Control - JavaScript Examples
 * Add this to your app.js or create timer.js
 */

// ============================================================================
// WEBSOCKET CONNECTION
// ============================================================================

//const socket = io();

// ============================================================================
// BASIC TIMER OPERATIONS
// ============================================================================

/**
 * Create a new timer
 */
function createTimer(timerId, type = 'independent', options = {}) {
    socket.emit('timer_create', {
        timer_id: timerId,
        type: type,
        ...options
    });
}

/**
 * Start a timer
 */
function startTimer(timerId) {
    socket.emit('timer_start', { timer_id: timerId });
}

/**
 * Pause a timer
 */
function pauseTimer(timerId) {
    socket.emit('timer_pause', { timer_id: timerId });
}

/**
 * Resume a timer
 */
function resumeTimer(timerId) {
    socket.emit('timer_resume', { timer_id: timerId });
}

/**
 * Stop a timer
 */
function stopTimer(timerId) {
    socket.emit('timer_stop', { timer_id: timerId });
}

// ============================================================================
// TIME SYNCHRONIZATION (Buttons +/-)
// ============================================================================

/**
 * Adjust timer time by offset
 */
function adjustTimer(timerId, offsetMs) {
    socket.emit('timer_adjust', {
        timer_id: timerId,
        offset_ms: offsetMs
    });
}

/**
 * Set specific elapsed time
 */
function setTimerTime(timerId, elapsedMs) {
    socket.emit('timer_set_time', {
        timer_id: timerId,
        elapsed_time: elapsedMs
    });
}

// ============================================================================
// BUTTON CLICK HANDLERS
// ============================================================================

// +1 minute button
document.getElementById('btn-plus-1min')?.addEventListener('click', () => {
    const timerId = getCurrentTimerId();
    adjustTimer(timerId, 60000); // +60 seconds
});

// +10 seconds button
document.getElementById('btn-plus-10s')?.addEventListener('click', () => {
    const timerId = getCurrentTimerId();
    adjustTimer(timerId, 10000); // +10 seconds
});

// +1 second button
document.getElementById('btn-plus-1s')?.addEventListener('click', () => {
    const timerId = getCurrentTimerId();
    adjustTimer(timerId, 1000); // +1 second
});

// -1 minute button
document.getElementById('btn-minus-1min')?.addEventListener('click', () => {
    const timerId = getCurrentTimerId();
    adjustTimer(timerId, -60000); // -60 seconds
});

// -10 seconds button
document.getElementById('btn-minus-10s')?.addEventListener('click', () => {
    const timerId = getCurrentTimerId();
    adjustTimer(timerId, -10000); // -10 seconds
});

// -1 second button
document.getElementById('btn-minus-1s')?.addEventListener('click', () => {
    const timerId = getCurrentTimerId();
    adjustTimer(timerId, -1000); // -1 second
});

// ============================================================================
// MATCH CONTROL
// ============================================================================

/**
 * Create match timer with penalties support
 */
function createMatchTimer(matchId, durationMinutes = 40) {
    socket.emit('match_timer_create', {
        game_id: matchId,
        duration_minutes: durationMinutes
    });
}

/**
 * Create penalty timer
 */
function createPenaltyTimer(matchTimerId, playerNumber, playerName, durationMinutes = 2) {
    socket.emit('penalty_timer_create', {
        match_timer_id: matchTimerId,
        player_number: playerNumber,
        player_name: playerName,
        duration_minutes: durationMinutes
    });
}

// Example: Start match
document.getElementById('btn-start-match')?.addEventListener('click', () => {
    const matchId = document.getElementById('current-match-id').value;
    
    // Create match timer
    createMatchTimer(matchId, 40);
    
    // Start it after creation (wait for confirmation)
    socket.once('match_timer_created', (data) => {
        startTimer(data.timer_id);
    });
});

// Example: Add penalty
document.getElementById('btn-add-penalty')?.addEventListener('click', () => {
    const matchTimerId = document.getElementById('match-timer-id').value;
    const playerNumber = document.getElementById('penalty-player-number').value;
    const playerName = document.getElementById('penalty-player-name').value;
    
    createPenaltyTimer(matchTimerId, playerNumber, playerName, 2);
    
    // Start penalty timer after creation
    socket.once('penalty_timer_created', (data) => {
        startTimer(data.timer_id);
    });
});

// ============================================================================
// RAFTING CONTROL
// ============================================================================

/**
 * Start rafting team
 */
function startRaftingTeam(teamName, startNumber) {
    socket.emit('rafting_timer_create', {
        team_name: teamName,
        start_number: startNumber
    });
    
    // Auto-start after creation
    socket.once('rafting_timer_created', (data) => {
        startTimer(data.timer_id);
    });
}

// Example: Rafting start sequence
let raftingStartNumber = 1;
document.getElementById('btn-start-next-raft')?.addEventListener('click', () => {
    const teamName = document.getElementById('next-team-name').value;
    startRaftingTeam(teamName, raftingStartNumber);
    raftingStartNumber++;
});

// ============================================================================
// SKIING CONTROL
// ============================================================================

/**
 * Start parallel skiing race
 */
function startSkiingRace(skierBlue, skierRed) {
    socket.emit('skiing_timers_create', {
        skier_blue: skierBlue,
        skier_red: skierRed
    });
    
    // Auto-start both simultaneously
    socket.once('skiing_timers_created', (data) => {
        socket.emit('skiing_start_simultaneous', {
            blue_timer_id: data.blue_timer_id,
            red_timer_id: data.red_timer_id
        });
    });
}

// Example: Start skiing race
document.getElementById('btn-start-ski-race')?.addEventListener('click', () => {
    const skierBlue = {
        name: document.getElementById('skier-blue-name').value,
        country: document.getElementById('skier-blue-country').value
    };
    
    const skierRed = {
        name: document.getElementById('skier-red-name').value,
        country: document.getElementById('skier-red-country').value
    };
    
    startSkiingRace(skierBlue, skierRed);
});

// ============================================================================
// WEBSOCKET EVENT LISTENERS
// ============================================================================

/**
 * Timer update (real-time)
 */
socket.on('timer_updated', (data) => {
    console.log(data);
//    const { timer_id, state } = data;  // ✅

    const timer_id = data.timer_id;
    const elapsed_time = data.elapsed_time;
    const timerState = data.state;

    updateTimerDisplay(timer_id, elapsed_time, timerState);
});

socket.onAny((event, ...args) => {
    console.log(`📨 Event received: ${event}`, args);
});

/**
 * Timer event (paused, stopped, limit_reached, etc.)
 */
socket.on('timer_event', (data) => {
    const { timer_id, event, elapsed_time } = data;
    
    console.log(`Timer ${timer_id}: ${event} at ${elapsed_time}ms`);
    
    // Handle specific events
    switch(event) {
        case 'limit_reached':
            showNotification(`Timer ${timer_id} reached its limit!`);
            break;
        case 'paused':
            updateTimerState(timer_id, 'paused');
            break;
        case 'stopped':
            updateTimerState(timer_id, 'stopped');
            break;
    }
});

/**
 * Timer created
 */
socket.on('timer_created', (data) => {
    console.log('Timer created:', data.timer_id);
    addTimerToUI(data.timer_id);
});

/**
 * Timer adjusted
 */
socket.on('timer_adjusted', (data) => {
    console.log(`Timer ${data.timer_id} adjusted by ${data.offset_ms}ms`);
});

// ============================================================================
// UI UPDATE FUNCTIONS
// ============================================================================

/**
 * Update timer display in UI
 */
function updateTimerDisplay(timerId, elapsedMs, state) {
    const timerElement = document.getElementById('newTimer');
    if (!timerElement) return;
    console.log(elapsedMs);
    // Format time as MM:SS.CS
    const minutes = Math.floor(elapsedMs / 60000);
    const seconds = Math.floor((elapsedMs % 60000) / 1000);
    const centiseconds = Math.floor((elapsedMs % 1000) / 10);
    
    const timeString = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}.${centiseconds.toString().padStart(2, '0')}`;
    
    timerElement.textContent = timeString;
//    timerElement.querySelector('.timer-state').textContent = state;
//
//    // Add state class for styling
//    timerElement.className = `timer timer-${state}`;
}

/**
 * Update timer state indicator
 */
function updateTimerState(timerId, state) {
    const stateElement = document.getElementById(`timer-${timerId}-state`);
    if (stateElement) {
        stateElement.textContent = state;
        stateElement.className = `state state-${state}`;
    }
}

/**
 * Add new timer to UI
 */
function addTimerToUI(timerId) {
    const timerContainer = document.getElementById('timers-container');
    if (!timerContainer) return;
    
    const timerDiv = document.createElement('div');
    timerDiv.id = `timer-${timerId}`;
    timerDiv.className = 'section-timer timer timer-idle';
    timerDiv.innerHTML = `
        <div class="timer-header">
            <span class="timer-id">${timerId}</span>
            <span class="timer-state" id="timer-newTimer-state">idle</span>
        </div>
        <div class="main-timer">
            <div id="timer-min-setting">
                <button class="small-button" id="btn-plus-1min">+</button>
                <button class="small-button" id="btn-minus-1min">-</button>
            </div>
            <div id="newTimer" class="panel-time-display timer-time data-time-seconds data-time-added-seconds" style="background-color:rgb(247,52,52)">20:00</div>
            <div id="timer-sec-setting">
                <button class="small-button" id="btn-plus-1s">+</button>
                <button class="small-button" id="btn-minus-1s">-</button>
            </div>
           </div>
        <div class="timer-controls">
            <div>
                <button id="start-btn" onclick="startTimer('newTimer');">Start</button>
                <button id="pause-btn" onclick="pauseTimer('newTimer');">Pause</button>
                <button id="reset-btn" onclick="resumeTimer('newTimer');">Resume</button>
            </div>
            <div>
                <button id="btn-start-match">Start:Mecz</button>
                <button id="btn-stop-match" onclick="stopTimer('newTimer');">Stop:Mecz</button>
            </div>
        </div>
    `;
    
    timerContainer.appendChild(timerDiv);
}

/**
 * Show notification
 */
function showNotification(message) {
    // Simple alert - replace with better notification system
    console.log('NOTIFICATION:', message);
    
    // Or use a toast library like Toastify
    // Toastify({ text: message }).showToast();
}

/**
 * Get current timer ID (from UI)
 */
function getCurrentTimerId() {
    // Example: get from selected timer or input field
    const selectedTimer = document.querySelector('.timer.selected');
    if (selectedTimer) {
        return selectedTimer.id.replace('timer-', '');
    }
    
    // Or from input field
    return document.getElementById('current-timer-id')?.value || 'match-main';
}

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('Timer controls initialized');
    
    // Request initial timer list
    socket.emit('timers_get_all');
    
    socket.on('timers_list', (data) => {
        console.log(`Loaded ${data.count} timers`);
        if(!data.count) {
            createTimer('newTimer', type = 'independent', options = {
                "limit_time": 300000,
                "pause_at_limit": true,
                "initial_time": 0,
                "metadata": {
                  "description": "Main game timer",
                  "period": 1
                }
          })
        }
        data.timers.forEach(timer => {
            addTimerToUI(timer.id);
            updateTimerDisplay(timer.id, timer.elapsed_time, timer.state);
        });
    });
});
