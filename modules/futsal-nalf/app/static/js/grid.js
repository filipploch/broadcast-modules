var timerStates = ['idle', 'running', 'stopped', 'paused', 'limit_reached'];


// Wersja addClassName z obsługą błędów


function adjustMainControlButtonsToTimerState(timerId, state) {
	const className = "timer-main-controller";
	if (state === 'stopped' || state === 'limit_reached') {
		state = 'paused';
	}
	const singleButton = document.querySelector(`button.${className}[data-timer-id="${timerId}"][data-timer-state="${state}"]`);

	const allButtons = document.querySelectorAll(`button.${className}[data-timer-id="${timerId}"]`);

	  allButtons.forEach(button => {
	  addClassName(button, 'nodisplayed');
	});
	  
	removeClassName(singleButton, 'nodisplayed');
}

function adjustDsElementsToState(timerId, state) {
	const className = `ds-${timerId}-element`;
	dsElements = document.querySelectorAll(`.${className}`);
	if(state === 'stopped' || state === 'limit_reached') {
	    state = 'paused'
	}
	dsElements.forEach(element => {
		if(state === 'paused') {
			removeClassName(element, 'invisible');
		}else{
			addClassName(element, 'invisible');
		}
	});
}


/**
 * Update timer state indicator
 */
function updateTimerStateIndicator(timerId, state) {
    const stateElement = document.getElementById(`${timerId}-header`);
	if (state === 'limit_reached' || state === 'stopped') {
		state = 'paused';
	}
    if (stateElement) {
        stateElement.setAttribute('class', '');
        stateElement.className = state;
    }
}

function updateTimerUI(timerId, state) {
	updateTimerStateIndicator(timerId, state);
	adjustMainControlButtonsToTimerState(timerId, state);
    adjustDsElementsToState(timerId, state);
}

/**
 * Create a new timer
 */
function createTimer(timerId, timer_type = 'independent', options = {}) {
    socket.emit('timer_create', {
        timer_id: timerId,
        timer_type: timer_type,
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
function adjustTimer(timerId, deltaMs) {
    console.log(`timer: ${timerId} // deltaMs: ${deltaMs}`)
    socket.emit('timer_adjust', {
        timer_id: timerId,
        delta: deltaMs
    });
}

/**
 * Reset timer
 */
function resetTimer(timerId) {
    console.log(`timer: ${timerId}`)
    socket.emit('timer_reset', {
        timer_id: timerId
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

/**
 * Create match timer with penalties support
 */
function createMatchTimer(matchId, durationMinutes = 40) {
    socket.emit('match_timer_create', {
        match_id: matchId,
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
            updateTimerUI(timer_id, 'paused');
            break;
        case 'stopped':
            updateTimerUI(timer_id, 'stopped');
            break;
		case 'running':
            updateTimerUI(timer_id, 'running');
            break;
		case 'idle':
            updateTimerUI(timer_id, 'idle');
            break;
    }
});

/**
 * Timer created
 */
socket.on('timer_created', (timer) => {
    console.log('Timer created:', timer.timer_id);
    addTimerToUI(timer);
    console.log('po addTimerToUI - socket.on timer_created');
    updateTimerDisplay(timer.timer_id, timer.initial_time)
    console.log('po updateTimerDisplay - socket.on timer_created');
	updateTimerUI(timer.timer_id, timer.state);
    console.log('po updateTimerUI - socket.on timer_created');
});

/**
 * Timer adjusted
 */
// socket.on('timer_adjusted', (data) => {
//     console.log(data);

//     const timer_id = data.timer_id;
//     const elapsed_time = data.elapsed_time;
//     const timerState = data.state;

//     updateTimerDisplay(timer_id, elapsed_time, timerState);
// });

socket.on('timer_started', (data) => {
    console.log('⏱️ Timer started');
    updateTimerUI(data.timer_id,'running');
});

socket.on('timer_paused', (data) => {
    console.log(data);
    const timer_id = data.timer_id;
    const elapsed_time = data.elapsed_time;
    const timerState = data.state;
    updateTimerDisplay(timer_id, elapsed_time, timerState);
    updateTimerUI(data.timer_id,'paused');
});

socket.on('limit_reached', (data) => {
    console.log(data);
    const timer_id = data.timer_id;
    const elapsed_time = data.elapsed_time;
    const timerState = data.state;
    updateTimerDisplay(timer_id, elapsed_time, timerState);
    updateTimerUI(data.timer_id,'paused');
});

socket.on('timer_reset', (data) => {
    console.log('⏱️ Timer reset');
    const timer_id = data.timer_id;
    const elapsed_time = data.elapsed_time;
    const timerState = data.state;
    updateTimerDisplay(timer_id, elapsed_time, timerState);
    updateTimerUI(data.timer_id,'idle');
});

socket.on('timer_stopped', (data) => {
    console.log('⏱️ Timer stopped');
    updateTimerUI(data.timer_id,'stopped');
});

socket.on('timer_resumed', (data) => {
    console.log('⏱️ Timer resumed');
    updateTimerUI(data.timer_id,'running');
});

// ============================================================================
// UI UPDATE FUNCTIONS
// ============================================================================

/**
 * Update timer display in UI
 */
function updateTimerDisplay(timerId, elapsedMs) {
    const minutesDisplay = document.getElementById(`${timerId}-min-display`);
    const secondsDisplay = document.getElementById(`${timerId}-sec-display`);
    const dsecondsDisplay = document.getElementById(`${timerId}-ds-display`);
    if (!minutesDisplay || !secondsDisplay || !dsecondsDisplay) return;
    console.log(elapsedMs);
    // Format time as MM:SS.CS
    const minutes = Math.floor(elapsedMs / 60000);
    const seconds = Math.floor((elapsedMs % 60000) / 1000);
    const dseconds = Math.floor((elapsedMs % 1000) / 100);
    
    const minutesString = minutes.toString().padStart(2, '0');
    const secondsString = seconds.toString().padStart(2, '0');
    const dsecondsString = dseconds.toString();
    
    minutesDisplay.textContent = minutesString;
    secondsDisplay.textContent = secondsString;
    dsecondsDisplay.textContent = dsecondsString;
//    timerElement.querySelector('.timer-state').textContent = state;
//
//    // Add state class for styling
//    timerElement.className = `timer timer-${state}`;
}



/**
 * Add new timer to UI
 */
function addTimerToUI(timer) {
    const timerContainer = document.getElementById('timers-container');
    if (!timerContainer) return;
    console.log(timer);
    const timerDiv = document.createElement('div');
    timerDiv.className = 'timer-container';
    timerDiv.innerHTML = `
        <div id="${timer.timer_id}-header" class="timer-header">${timer.timer_id}</div>
      <div class="timer-content">
        <div class="timer-display-container">
          <button onclick="adjustTimer('${timer.timer_id}', 60000);" class="timer-button" data-timer-id="${timer.timer_id}"></button>
          <button onclick="adjustTimer('${timer.timer_id}', 1000);" class="timer-button" data-timer-id="${timer.timer_id}"></button>
          <button onclick="adjustTimer('${timer.timer_id}', 100);" class="timer-button ds-${timer.timer_id}-element" data-timer-id="${timer.timer_id}"></button>
          <div id="${timer.timer_id}-min-display" class="timer-display">102</div>
          <div id="${timer.timer_id}-sec-display" class="timer-display">27</div>
          <div id="${timer.timer_id}-ds-display" class="timer-display ds-${timer.timer_id}-element">4</div>
          <button onclick="adjustTimer('${timer.timer_id}', -60000);" class="timer-button" data-timer-id="${timer.timer_id}"></button>
          <button onclick="adjustTimer('${timer.timer_id}', -1000);" class="timer-button" data-timer-id="${timer.timer_id}"></button>
          <button onclick="adjustTimer('${timer.timer_id}', -100);" class="timer-button ds-${timer.timer_id}-element" data-timer-id="${timer.timer_id}"></button>
        </div>
        <div class="timer-controllers-container">
          <div class="timer-small-controllers">
           <button id="btn-reset-timer" ondblclick="resetTimer('${timer.timer_id}');">0</button>
            <button></button>
            <button id="btn-close-timer">X</button>
          </div>
          <div class="timer-main-controllers">
            <button class="timer-main-controller"
                    data-timer-id="${timer.timer_id}"
                    data-timer-state="idle"
                    onclick="startTimer('${timer.timer_id}');">START</button>
            <button class="timer-main-controller nodisplayed"
                    data-timer-id="${timer.timer_id}"
                    data-timer-state="running"
                    onclick="pauseTimer('${timer.timer_id}');">PAUZA</button>
            <button class="timer-main-controller nodisplayed"
                    data-timer-id="${timer.timer_id}"
                    data-timer-state="paused"
                    onclick="resumeTimer('${timer.timer_id}');">WZNÓW</button>
          </div>
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
/* function getCurrentTimerId() {
    // Example: get from selected timer or input field
    const selectedTimer = document.querySelector('.timer.selected');
    if (selectedTimer) {
        return selectedTimer.id.replace('timer-', '');
    }
    
    // Or from input field
    return document.getElementById('current-timer-id')?.value || 'match-main';
} */

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('Timer controls initialized');
    
    // Request initial timer list
    socket.emit('timers_get_all');
    
    socket.on('all_timers', (data) => {
        console.log(`Loaded ${data.count} timers`);
        if(!data.count) {
            createTimer('newTimer', timer_type = 'independent', options = {
                "limit_time": 3000000,
                "pause_at_limit": false,
                "initial_time": 0,
                "state": "idle",
                "metadata": {
                  "description": "Main game timer",
                  "period": 1
                }
          })
        }
        data.timers.forEach(timer => {
            addTimerToUI(timer);
            updateTimerDisplay(timer.timer_id, timer.elapsed_time);
            updateTimerUI(timer.timer_id, timer.state);
        });
    });
});
