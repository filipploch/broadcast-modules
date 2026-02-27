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

var homeScoreLabel = document.getElementById('labelScoreHome');
var awayScoreLabel = document.getElementById('labelScoreAway');
var homeFoulsLabel = document.getElementById('labelFoulsHome');
var awayFoulsLabel = document.getElementById('labelFoulsAway');



socket.on('connect', () => {
    console.log('✅ WebSocket connected');
    socket.emit('request_initial_data');
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
// function updateTimerDisplay(timerId, elapsedTime) {
//     // Use data attribute selector instead of ID
//     const displayElement = document.querySelector(`[data-display-for="${timerId}"]`);
//     if (displayElement) {
//         displayElement.textContent = formatTime(elapsedTime);
//     } else {
//         console.warn(`Display element not found for timer: ${timerId}`);
//     }
// }

function updateTimerDisplay(timerId, elapsedMs, timerLimit=0) {
    let elapsedTime = elapsedMs;
    if(!timerLimit==0){
        elapsedTime = timerLimit - elapsedMs;
    }
    const minutesDisplay = document.querySelector(`[data-display-for="${timerId}-min-display"]`);
    const secondsDisplay = document.querySelector(`[data-display-for="${timerId}-sec-display"]`);
    const dsecondsDisplay = document.querySelector(`[data-display-for="${timerId}-ds-display"]`);
    if (!minutesDisplay || !secondsDisplay || !dsecondsDisplay) return;
    console.log(elapsedMs);
    // Format time as MM:SS.CS
    const minutes = Math.ceil(elapsedTime / 60000);
    const seconds = Math.ceil((elapsedTime % 60000) / 1000);
    let dseconds = Math.ceil((elapsedTime % 1000) / 100);
    if(dseconds === 10){
        dseconds = 0;
    }
    
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
 * Update timer state badge
 */
function updateTimerState(timerId, state) {
    const timerStateFor = document.querySelector(`[data-state-for="${timerId}"]`);
    const timerMainControllers = document.querySelectorAll('.timer-main-controller')
    
    if (!timerStateFor || !timerMainControllers) return;

    timerStateFor.classList.remove('timer-state-idle', 'timer-state-running', 
                                   'timer-state-paused', 'timer-state-limit_reached');

    timerStateFor.classList.add(`timer-state-${state}`);
    
    timerMainControllers.forEach(controller =>{
        addClassName(controller, 'nodisplayed');
        if(controller.getAttribute('data-timer-state')===state){
            removeClassName(controller, 'nodisplayed');
        }
    });
}

function updatePenaltyTimerDisplay(timerId, elapsedMs, timerLimit) {
    // console.log('updatePenaltyTimerDisplay');
    const penaltyDisplay = document.querySelector(`[data-display-for="${timerId}"]`);
    let elapsedTime = elapsedMs;
    if(!timerLimit==0){
        elapsedTime = timerLimit - elapsedMs;
    }
    if (!penaltyDisplay) return;
    // Format time as MM:SS.CS
    const minutes = Math.floor(elapsedTime / 60000);
    const seconds = Math.floor((elapsedTime % 60000) / 1000);
    
    const minutesString = minutes.toString();
    const secondsString = seconds.toString().padStart(2, '0');
    
    penaltyDisplay.textContent = `${minutesString}:${secondsString}`;
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
        if(data.timer_id.startsWith('penalty')){
            updatePenaltyTimerDisplay(data.timer_id, data.elapsed_time, data.limit);
        } else {
            updateTimerDisplay(data.timer_id, data.elapsed_time, data.limit);
        }
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
        let dsElements = document.querySelectorAll('.ds-element');
        dsElements.forEach(element => {
            addClassName(element, 'hidden');
        })
        updateTimerDisplay(data.timer_id, data.elapsed_time, data.limit);
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
        let dsElements = document.querySelectorAll('.ds-element');
        dsElements.forEach(element => {
            removeClassName(element, 'hidden');
        })
        updateTimerDisplay(data.timer_id, data.elapsed_time, data.limit);
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
        updateTimerDisplay(data.timer_id, data.elapsed_time, data.limit);
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
        updateTimerDisplay(data.timer_id, data.elapsed_time, data.limit);
    }
    if (data.state) {
        updateTimerState(data.timer_id, data.state);
    }
    
    // Optional: Show notification
    if (data.timer_id === appState.mainTimer?.timer_id) {
        console.log('⏰ Główny timer osiągnął limit!');
    }
});


socket.on('flash_msg', (data) => {
    
    // Pobranie elementu flash-msg-display
    const flashElement = document.getElementById('flash-msg-display');
    
    if (flashElement) {
        
        // Wyświetlenie elementu
        flashElement.style.display = 'block';
        
        // Usunięcie poprzednich klas typu (opcjonalne)
        flashElement.className = '';
        
        // Dodanie nowej klasy typu
        addClassName(flashElement, data.type);
        
        // Ustawienie tekstu
        flashElement.textContent = data.text;
        
        // Ukrycie po 3 sekundach (nieblokujące)
        setTimeout(() => {
            flashElement.style.display = 'none';
        }, 3000);
    }
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
function removeTimer(timerId) {
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

socket.on('reload_penalty_timers', (data) => {
    appState.penalties = data.penalties;

    fillPenaltiesTimersContainer('home');
    fillPenaltiesTimersContainer('away');
});

socket.on('game_data', (data) => {
    let gameData = data['payload'];
    homeScoreLabel.innerText = gameData['home_team'].goals;
    awayScoreLabel.innerText = gameData['away_team'].goals;
    homeFoulsLabel.innerText = gameData['home_team'].fouls;
    awayFoulsLabel.innerText = gameData['away_team'].fouls;
})

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
function addPenaltyTimer(teamType, penaltyDuration=2) {
    const team = teamType;
    const duration = penaltyDuration;
    
    if (appState.penalties[team].length >= 2) return;
    if (!appState.mainTimer) {
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
        game_timer_id: appState.mainTimer.timer_id,
        team: team,
        team_name: teamName,
        duration_minutes: duration
    });
    
    
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



function reorderReversible() {
  // Zapobiegnij równoczesnym wywołaniom
  if (appState.isReordering) {
    return;
  }
  
  appState.isReordering = true;
  
  // Pobierz wszystkie elementy z klasą "reversible"
  const reversibleElements = document.querySelectorAll('.reversible');

  // Dla każdego takiego elementu
  reversibleElements.forEach(element => {
    // Pobierz wszystkie bezpośrednie dzieci
    const children = Array.from(element.children);
    
    // Odwróć kolejność tablicy
    const reversedChildren = children.reverse();
    
    // Wstaw dzieci z powrotem w odwróconej kolejności
    reversedChildren.forEach(child => element.appendChild(child));
  });

  // Zmień stan flagi globalnej
  appState.isReversed = !appState.isReversed;
  
  // Odblokuj możliwość ponownego wywołania
  appState.isReordering = false;
}

// document.addEventListener('DOMContentLoaded', () => {
//     console.log('UI initialized with Jinja2 rendering');
//     console.log('Period:', period);
//     console.log('Main timer:', appState.mainTimer);
//     console.log('Penalties:', appState.penalties);
    
//     // Initialize displays with current data
//     if (appState.mainTimer) {
//         updateTimerDisplay(appState.mainTimer.timer_id, appState.mainTimer.initial_time, appState.mainTimer.limit);
//         updateTimerState(appState.mainTimer.timer_id, appState.mainTimer.state || 'idle');
//     }
    
//     // if (penaltiesData && penaltiesData.length > 0) {
//     //     penaltiesData.forEach(penalty => {
//     //         updateTimerDisplay(penalty.timer_id, penalty.initial_time || 0);
//     //         updateTimerState(penalty.timer_id, penalty.state || 'idle');
//     //     });
//     // }
    
//     console.log('✅ UI ready - listening for WebSocket updates');
// });

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
    console.log('Main timer data:', appState.mainTimer);
    console.log('Penalties data:', appState.penalties);
    console.log('DOM timer IDs:', getAllTimerIds());
    console.log('Socket connected:', socket.connected);
};

// Expose functions to global scope for onclick handlers
window.startTimer = startTimer;
window.pauseTimer = pauseTimer;
window.resumeTimer = resumeTimer;
window.resetTimer = resetTimer;
window.adjustTimer = adjustTimer;
window.removeTimer = removeTimer;
window.showAddPenaltyDialog = showAddPenaltyDialog;
window.hideAddPenaltyDialog = hideAddPenaltyDialog;
window.addPenaltyTimer = addPenaltyTimer;
window.finishPeriod = finishPeriod;