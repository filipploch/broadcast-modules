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

var homeScoreLabel = document.getElementById('scoreHome');
var awayScoreLabel = document.getElementById('scoreAway');
var homeFoulsLabel = document.getElementById('foulsHome');
var awayFoulsLabel = document.getElementById('foulsAway');
var currentSequenceId = null;



socket.on('connect', () => {
    console.log('✅ WebSocket connected');
    socket.emit('request_initial_data');
    getObsWsConnection()
});

socket.on('disconnect', () => {
    console.log('❌ WebSocket disconnected');
});

socket.on('sequence_started', ({ sequence_id }) => {
    currentSequenceId = sequence_id;
});

socket.on('sequence_stopped', ({ sequence_id }) => {
    if(currentSequenceId === sequence_id) {
        currentSequenceId = null;
    }
});

socket.on('all_sequences_stopped', ({}) => {
    currentSequenceId = null;
});

function runSequence(){
    socket.emit('trigger_sequence', { sequence: 'halftime_start', context: {} });
}

function startRecording(){
    socket.emit('start_recording');
}

function stopRecording(){
    socket.emit('stop_recording');
}

function getObsWsConnection() {
    socket.emit('get_obs_ws_connection');
}

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

function updateTimerDisplay(timerData) {
    console.log("timerData:", timerData);
    const timerId = timerData.timer_id;
    const elapsedMs = timerData.elapsed_time;
    let timerLimit = timerData.limit   || 0;
    const initialMs  = timerData.initial_time || 0;
    const timerState = timerData.state;
    const minutesDisplay  = document.querySelector(`[data-display-for="${timerId}-min-display"]`);
    const secondsDisplay  = document.querySelector(`[data-display-for="${timerId}-sec-display"]`);
    const dsecondsDisplay = document.querySelector(`[data-display-for="${timerId}-ds-display"]`);
    if (!minutesDisplay || !secondsDisplay || !dsecondsDisplay) return;

    const elapsed = (elapsedMs != null && !isNaN(elapsedMs)) ? elapsedMs : 0;

    let displayTime;

    // if (timerLimit > 0) {
    //     displayTime = Math.max(0, timerLimit - elapsed - 1);
    //     if(timerState === 'idle'){
    //         displayTime = timerLimit - elapsed;
    //     }
    // } else {
    //     displayTime = elapsed;
    // }

    if (timerLimit > 0) {
        // Count down: show remaining = limit - (initialTime + elapsed)
        // Subtract 1ms so display changes exactly on the second boundary
        const shown = elapsed;
        timerLimit = timerLimit - initialTime;
        // const shown = initialMs + elapsed;
        displayTime = timerState === 'idle'
            ? Math.max(0, timerLimit - shown)
            : Math.max(0, timerLimit - shown - 1);
    } else {
        // Count up: show initialTime + elapsed
        displayTime = initialMs + elapsed;
    }

    const minutes  = Math.floor(displayTime / 60000);
    const seconds  = Math.floor((displayTime % 60000) / 1000);
    const dseconds = Math.floor((displayTime % 1000) / 100);

    minutesDisplay.textContent  = minutes.toString().padStart(2, '0');
    secondsDisplay.textContent  = seconds.toString().padStart(2, '0');
    dsecondsDisplay.textContent = dseconds.toString();
}


// function updateTimerDisplay(timerId, elapsedMs, timerLimit = 0) {
//     const minutesDisplay  = document.querySelector(`[data-display-for="${timerId}-min-display"]`);
//     const secondsDisplay  = document.querySelector(`[data-display-for="${timerId}-sec-display"]`);
//     const dsecondsDisplay = document.querySelector(`[data-display-for="${timerId}-ds-display"]`);
//     if (!minutesDisplay || !secondsDisplay || !dsecondsDisplay) return;

//     const elapsed = (elapsedMs != null && !isNaN(elapsedMs)) ? elapsedMs : 0;

//     let displayTime;
//     if (timerLimit > 0) {
//         // Odliczanie malejąco — pokaż następną pełną sekundę która będzie wyświetlona
//         // Math.floor na elapsed zaokrągla w dół do pełnej sekundy, więc display zmienia się
//         // dokładnie co sekundę i jest spójny przy pauzie/resume
//         const elapsedSeconds = Math.floor(elapsed / 100) * 100;
//         displayTime = Math.max(0, timerLimit - elapsedSeconds - 1);
//     } else {
//         displayTime = elapsed;
//     }

//     const minutes  = Math.floor(displayTime / 60000);
//     const seconds  = Math.floor((displayTime % 60000) / 1000);
//     const dseconds = Math.floor((displayTime % 1000) / 100);

//     minutesDisplay.textContent  = minutes.toString().padStart(2, '0');
//     secondsDisplay.textContent  = seconds.toString().padStart(2, '0');
//     dsecondsDisplay.textContent = dseconds.toString();
// }

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

function updatePenaltyTimerDisplay(timerId, elapsedMs, timerLimit, initialTime=0) {
    // console.log('updatePenaltyTimerDisplay');
    const penaltyDisplay = document.querySelector(`[data-display-for="${timerId}"]`);
    // Penalties count down: remaining = limit - (initialTime + elapsed)
    const elapsedTime = timerLimit > 0
        ? Math.max(0, timerLimit - initialTime - elapsedMs)
        : initialTime + elapsedMs;
    console.log('updatePenalty', elapsedTime);
    if (!penaltyDisplay) return;
    // Format time as MM:SS.CS
    const minutes = Math.floor(elapsedTime / 60000);
    const seconds = Math.floor((elapsedTime % 60000) / 1000);
    
    const minutesString = minutes.toString();
    const secondsString = seconds.toString().padStart(2, '0');
    
    penaltyDisplay.textContent = `${minutesString}:${secondsString}`;
}

// function updatePenaltyTimerDisplay(timerId, elapsedMs, timerLimit) {
//     // console.log('updatePenaltyTimerDisplay');
//     const penaltyDisplay = document.querySelector(`[data-display-for="${timerId}"]`);
//     let elapsedTime = elapsedMs;
//     if(timerLimit>0){
//         elapsedTime = timerLimit - elapsedMs;
//     }
//     console.log('updatePenalty', elapsedTime);
//     if (!penaltyDisplay) return;
//     // Format time as MM:SS.CS
//     const minutes = Math.floor(elapsedTime / 60000);
//     const seconds = Math.floor((elapsedTime % 60000) / 1000);
    
//     const minutesString = minutes.toString();
//     const secondsString = seconds.toString().padStart(2, '0');
    
//     penaltyDisplay.textContent = `${minutesString}:${secondsString}`;
// }

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
            updateTimerDisplay(data);
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
    document.querySelectorAll('.ds-element').forEach(el => addClassName(el, 'hidden'));
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
        updateTimerDisplay(data);
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
        updateTimerDisplay(data);
    if (data.state) {
        updateTimerState(data.timer_id, data.state);
    }
});

/**
 * Handle timer adjusted event
 */
socket.on('timer_adjusted', (data) => {
    console.log('Timer adjusted:', data);
    if (data.elapsed_time !== undefined) {
        if (data.timer_id.startsWith('penalty')) {
            updatePenaltyTimerDisplay(data.timer_id, data.elapsed_time, data.limit, data.initial_time || 0);
        } else {
            updateTimerDisplay(data);
        }
    }
    if (data.state) {
        updateTimerState(data.timer_id, data.state);
    }
});

socket.on('timer_resumed', (data) => {
    console.log('Timer resumed:', data);
    document.querySelectorAll('.ds-element').forEach(el => addClassName(el, 'hidden'));
    if (data.elapsed_time !== undefined) {
        if (data.timer_id.startsWith('penalty')) {
            updatePenaltyTimerDisplay(data.timer_id, data.elapsed_time, data.limit, data.initial_time || 0);
        } else {
            updateTimerDisplay(data);
        }
    }
    if (data.state) {
        updateTimerState(data.timer_id, data.state);
    }
});

/**
 * Handle limit reached event
 */
socket.on('limit_reached', (data) => {
    console.log('Timer limit reached:', data);
    if (data.elapsed_time !== undefined) {
        updateTimerDisplay(data);
    }
    if (data.state) {
        updateTimerState(data.timer_id, data.state);
    }
    
    // Optional: Show notification
    if (data.timer_id === appState.mainTimer?.timer_id) {
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

socket.on('home_penalty_timer_created', (data) => {
    // 1. Pobierz element div id="away"
    console.log("socket.on 'home_penalty_timer_created'");
    const homeDiv = document.getElementById('home-team-penalties-timers-container');
    
    if (!homeDiv) {
        console.error('Nie znaleziono elementu div id="home-(...)"');
        return;
    }
    
    // 2. Sprawdź ile divów class="penalty-timer" jest wewnątrz pobranego diva
    const penaltyTimers = homeDiv.querySelectorAll('.penalty-element');
    const timerCount = penaltyTimers.length;
    
    console.log(`Liczba timerów kary: ${timerCount}`);
    
    // 3. Jeśli ilość divów o klasie "penalty-timer" jest mniejsza od 2
    if (timerCount < 2) {
        // Generuj unikalne ID dla timera (możesz użyć data.timer_id lub timestamp)
        const timerId = data?.timer_id || `penalty_home_${Date.now()}`;
        
        // Tworzenie nowego diva penalty-timer z pełną strukturą
        const newPenaltyTimer = document.createElement('div');
        // newPenaltyTimer.className = 'timer-card penalty-timer';
        
        // Wypełnienie wewnętrznej struktury HTML
        newPenaltyTimer.innerHTML = `
            <div class="penalty-element" data-timer-id="${timerId}">
                <div class="penalty-element-content">
                    <button class="penalty-modal-button bg_red remove-penalty-button" onclick="removeTimer('${timerId}')">X</button>
                    <div class="penalty-display"></div>
                </div>
                <div class="penalty-element-controllers">
                    <div class="gap"></div>
                    <button class="penalty-modal-button adjust-penalty-time-button" onclick="adjustTimer('${timerId}', -1000);">-</button>
                    <button class="penalty-modal-button adjust-penalty-time-button" onclick="adjustTimer('${timerId}', 1000);">+</button>
                </div>
            </div>
        `;
        
        // Dodaj nowy timer do diva away
        homeDiv.appendChild(newPenaltyTimer);
        
        console.log(`Dodano nowy timer kary z ID: ${timerId}`);
        return timerId;
    } else {
        console.log('Osiągnięto maksymalną liczbę timerów kary (2)');
        return false;
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

socket.on('away_penalty_timer_created', (data) => {

    // 1. Pobierz element div id="away"
    const awayDiv = document.getElementById('away-team-penalties-timers-container');
    
    if (!awayDiv) {
        console.error('Nie znaleziono elementu div id="away-(...)"');
        return;
    }
    
    // 2. Sprawdź ile divów class="penalty-timer" jest wewnątrz pobranego diva
    const penaltyTimers = awayDiv.querySelectorAll('.penalty-element');
    const timerCount = penaltyTimers.length;

    const addPenaltyButton = awayDiv.querySelector('add-penalty-button');
    
    console.log(`Liczba timerów kary: ${timerCount}`);
    
    // 3. Jeśli ilość divów o klasie "penalty-timer" jest mniejsza od 2
    // Generuj unikalne ID dla timera (możesz użyć data.timer_id lub timestamp)
    const timerId = data?.timer_id || `penalty_away_${Date.now()}`;
    
    // Tworzenie nowego diva penalty-timer z pełną strukturą
    const newPenaltyTimer = document.createElement('div');
    newPenaltyTimer.className = 'timer-card penalty-timer';
    
    if (timerCount === 0) {
        // Wypełnienie wewnętrznej struktury HTML
        newPenaltyTimer.innerHTML = `
            <div class="penalty-element" data-timer-id="${timerId}">
                <div class="penalty-element-content">
                    <button class="penalty-modal-button bg_red remove-penalty-button" onclick="removeTimer('${timerId}')">X</button>
                    <div class="penalty-display"></div>
                </div>
                <div class="penalty-element-controllers">
                    <div class="gap"></div>
                    <button class="penalty-modal-button adjust-penalty-time-button" onclick="adjustTimer('${timerId}', -1000);">-</button>
                    <button class="penalty-modal-button adjust-penalty-time-button" onclick="adjustTimer('${timerId}', 1000);">+</button>
                </div>
            </div>
            ${addPenaltyButton.getHTML}
        `;
        
    } else if(timerCount < 2) {
        newPenaltyTimer.innerHTML = `
            <div class="penalty-element" data-timer-id="${timerId}">
                <div class="penalty-element-content">
                    <button class="penalty-modal-button bg_red remove-penalty-button" onclick="removeTimer('${timerId}')">X</button>
                    <div class="penalty-display"></div>
                </div>
                <div class="penalty-element-controllers">
                    <div class="gap"></div>
                    <button class="penalty-modal-button adjust-penalty-time-button" onclick="adjustTimer('${timerId}', -1000);">-</button>
                    <button class="penalty-modal-button adjust-penalty-time-button" onclick="adjustTimer('${timerId}', 1000);">+</button>
                </div>
            </div>
        `;
    } else {
        console.log('Osiągnięto maksymalną liczbę timerów kary (2)');
        return false;
    }
    // Dodaj nowy timer do diva away
    awayDiv.appendChild(newPenaltyTimer);
    addPenaltyButton.remove();
    console.log(`Dodano nowy timer kary z ID: ${timerId}`);
    return timerId;
});

socket.on('recording_status_response', data => {
    console.log(data);
});

socket.on('recording_started', cameras => {
    updateCamerasIndicators(cameras);
});

socket.on('recording_stopped', cameras => {
    updateCamerasIndicators(cameras);
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
    appState.home_penalties = data.penalties['home'];
    appState.away_penalties = data.penalties['away'];

    fillPenaltiesTimersContainer(appState.home_penalties, 'home');
    fillPenaltiesTimersContainer(appState.away_penalties, 'away');
});

socket.on('scoreboard_data', (data) => {
    let gameData = data['payload'];
    homeScoreLabel.innerText = gameData['home_team_goals'];
    awayScoreLabel.innerText = gameData['away_team_goals'];
    homeFoulsLabel.innerText = gameData['home_team_fouls'];
    awayFoulsLabel.innerText = gameData['away_team_fouls'];
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
    let _penalties = appState.home_penalties;
    if(team === 'away') _penalties = appState.away_penalties;
    const duration = penaltyDuration;
    
    if (_penalties.length >= 2) return;
    if (!appState.mainTimer) {
        alert('Brak aktywnego głównego timera!');
        return;
    }
    
    // Get team name
    let teamName = '';
    if (game) {
        teamName = team === 'home' ? game.home_team_name : game.away_team_name;
    }
    
    console.log('Adding penalty:', { team, teamName, duration });
    
    socket.emit('penalty_timer_create', {
        game_timer_id: appState.mainTimer.timer_id,
        team: team,
        team_name: teamName,
        duration_minutes: duration
    });
    
    
    // Show loading message
    // alert(`Dodawanie kary dla drużyny ${team}...`);
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



function reorderReversible(onLoad=false) {
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
  console.log('is onload', onLoad);
  if(onLoad === false){      
    // Zmień stan flagi globalnej
    appState.isReversed = !appState.isReversed;
    console.log('isReversed:', appState.isReversed);
    socket.emit('reverse_scoreboard', {is_scoreboard_reversed: appState.isReversed});
  }
  
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


document.querySelectorAll('.game-field-cell').forEach(element => {
    element.addEventListener('mouseover', () => {
        element.style.backgroundColor = 'rgba(0, 0, 0, 0.1)';
    });
});

document.querySelectorAll('.game-field-cell').forEach(element => {
    element.addEventListener('mouseout', () => {
        element.style.backgroundColor = 'rgba(0, 0, 0, 0)';
    });
});



// ============================================================================
// DEBUG HELPERS
// ============================================================================

function showUiMonitorContent(_contentType=null, _payload=null){
    socket.emit('request_ui_monitor_content', {type: _contentType, payload: _payload});
}

function gameEventPlayerNameGenerator(_gameEvent) {
    if(_gameEvent.is_reported === true && _gameEvent.player_id === null){
        return `<span style="color: red;" onclick="openGameEventEditForm(${_gameEvent.id})">WYBIERZ ZAWODNIKA</span>`
    } else if (_gameEvent.is_reported === true) {
        return `<span class="events-td-player-number">${_gameEvent.player_number}</span> ${_gameEvent.player_name}`
    } else {
        return ''
    }
}

function gameEventTeamShortNameGenerator(_gameEvent) {
    if(_gameEvent.team_short_name !== null) {
        return `(${_gameEvent.team_short_name})`;
    }else{
        return '';
    }
}

function gameEventInfoBtnGenerator(_gameEvent) {
    const whiteIcon = `<svg height="13" viewBox="0 -960 481.49437 361.12079" width="11" fill="#ffffff"
        version="1.1" id="svg1" xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg">
        <defs id="defs1" />
        <path
            d="m 90.28019,-689.1594 h 210.65379 v -45.1401 H 90.28019 Z m 255.79389,0 h 45.14009 v -45.1401 H 346.07408 Z M 90.28019,-779.4396 h 45.1401 v -45.1401 h -45.1401 z m 90.2802,0 h 210.65378 v -45.1401 H 180.56039 Z M 45.1401,-598.87921 q -18.62029,0 -31.8802,-13.26617 Q 9.9999998e-7,-625.41156 9.9999998e-7,-644.04439 v -270.99104 q 0,-18.63283 13.25989900000002,-31.79869 13.25991,-13.16587 31.8802,-13.16587 h 391.21417 q 18.62029,0 31.88019,13.26618 13.25991,13.26617 13.25991,31.899 v 270.99105 q 0,18.63283 -13.25991,31.79869 -13.2599,13.16586 -31.88019,13.16586 z m 0,-45.1401 H 436.35427 V -914.85989 H 45.1401 Z m 0,0 v -270.84058 z"
            id="path1"
            style="stroke-width:1" />
        </svg>`;
    if(_gameEvent.is_reported === true && _gameEvent.player_id === null){
        return `<button type="button" class="event-btn events-info-btn" style="background-color:red; padding: 1px 3.6px;"
        onclick="showInfo(${_gameEvent.id}, ${_gameEvent.team_id})">${whiteIcon}</button>`
    } else if (_gameEvent.is_reported === true) {
        return `<button type="button" class="event-btn events-info-btn" style="background-color:green; padding: 1px 3.6px;"
        onclick="showInfo(${_gameEvent.id}, ${_gameEvent.player_id})">${whiteIcon}</button>`
    } else {
        return ''
    }
}


function obsReplayBtnGenerator(_gameEvent) {
    if(_gameEvent.video_path) {
        return `<button type="button" class="event-btn events-obs-replay-btn"
        style="background-color:green; color: white; font-weight: 700;"
        onclick="showReplay('${_gameEvent.video_path}', ${_gameEvent.replay_start_time}, ${_gameEvent.replay_end_time})">O</button>`
    } else {
        return ''
    }
}

function closeReplayPopupBtnGenerator() {
    return `<button type="button" class="event-btn events-close-replays-popup-btn"
    style="background-color:red; color: white; font-weight: 700;"
    onclick="closeReplaysPopup();">X</button>`
}

function camerasReplaysBtnsGenerator(_gameEvent) {
    const eventCameras = _gameEvent.event_cameras;
    console.log(eventCameras);
    if(!_gameEvent.event_cameras) return ''
    btns = '';
    eventCameras.forEach(camera => {
        btns += `<button type="button"
        class="event-btn event-camera-replay-btn"
        style="background-color:green; color: white; font-weight: 700;"
        onclick="showReplay('${camera.video_path}', ${camera.replay_start_time}, ${camera.replay_end_time})">
        ${camera.camera_id.substr(camera.camera_id.length - 1)}</button>`
    });
    return btns
}

function replaysPopupGenerator(_gameEvent) {
    const obsReplayBtn = obsReplayBtnGenerator(_gameEvent);
    const camerasReplaysBtns = camerasReplaysBtnsGenerator(_gameEvent);
    const closeReplaysPopupBtn = closeReplayPopupBtnGenerator();
    return obsReplayBtn.concat(camerasReplaysBtns).concat(closeReplaysPopupBtn);
}

function replaysPopupGen(_gameEvent) {
    const eventId = _gameEvent.id;
    const gameEventJson = JSON.stringify(_gameEvent).replace(/'/g, "&#39;").replace(/"/g, '&quot;');
    return `<button type="button" class="event-btn events-show-replays-btn"
        data-event-id="${eventId}" data-game-event="${gameEventJson}"
        style="background-color:green; color: white; font-weight: 700;"
        onclick="handleReplayButtonClick(this, event)">R</button>`
}

window.handleReplayButtonClick = function(button, event) {
    event.preventDefault();
    event.stopPropagation();
    
    const row = button.closest('tr');
    const gameEventData = button.dataset.gameEvent;
    
    if (row && gameEventData) {
        try {
            const gameEvent = JSON.parse(gameEventData);
            window.showReplaysPopup(gameEvent, row, button);
        } catch (e) {
            console.error('Błąd parsowania danych wydarzenia:', e);
        }
    }
};

// function replaysPopupBtn(gameEvent) {
//     // const eventId = gameEvent.id || gameEvent.event_id;
//     const eventId = gameEvent.id;
//     const eventData = JSON.stringify(gameEvent).replace(/'/g, "&#39;");
    
//     return `
//         <button 
//             type="button" 
//             class="replays-popup-trigger event-btn events-replays-popup-btn"
//             data-event-id="${eventId}"
//             onclick="handleReplayButtonClick(this, '${gameEvent}', event)"
//             style="background-color:green; color: white; font-weight: 700;">
//             📹 Replay
//         </button>
//     `;
// }

// // Globalna funkcja obsługująca kliknięcie
// window.handleReplayButtonClick = function(button, gameEvent, event) {
//     event.preventDefault();
//     event.stopPropagation();
    
//     // Znajdź wiersz
//     const row = button.closest('tr');
    
//     if (row && gameEvent.id) {
//         window.showReplaysPopup(gameEvent, row, button);
//     }
// };


function gameEventEditBtnGenerator(_gameEvent) {
    return `<button type="button" class="event-btn event-edit-btn"
            style="font-size: 9px; padding: 0 0 2px 0; height: 17px; width: 17px"
            onclick="openGameEventEditForm(${_gameEvent.id})">✏️</button>`
}

function openGameEventEditForm(gameEventID){
    const payload = {
        'game_event_id': gameEventID
    };
    showUiMonitorContent('edit_event', payload);
}

function getGameEventSquadByEventType(_gameEventId, _newEventTypeId) {
    const payload = {
        'game_event_id': _gameEventId,
        'new_event_type_id': _newEventTypeId
    }
    showUiMonitorContent('get_event_squad', payload);
}

function showReplay(videoPath, replayStartTime, replayEndTime) {
    socket.emit('trigger_sequence', { sequence: 'replay', context: {
        'video_path': videoPath,
        'replay_start_time': replayStartTime,
        'replay_end_time': replayEndTime
    }});
    closeReplaysPopup();
}

function showInfo(_gameEventId, _teamId) {
    socket.emit('show_info', {game_event_id: _gameEventId, team_id: _teamId});
}

// function showReplay(videoPath, replayStartTime, replayEndTime) {
//     socket.emit('show_replay', {
//         video_path: videoPath,
//         replay_start_time: replayStartTime,
//         replay_end_time: replayEndTime
//     });
// }

function fieldSvgGenerator(cellId, color) {
    // Mapowanie liter kolumn na indeksy (0–7)
    const colMap = { A: 0, B: 1, C: 2, D: 3, E: 4, F: 5, G: 6, H: 7 };

    // Walidacja i parsowanie parametru cellId (np. "A3", "H5")
    const colLetter = cellId.charAt(0).toUpperCase();
    const rowNumber = parseInt(cellId.slice(1), 10);

    if (!(colLetter in colMap) || rowNumber < 1 || rowNumber > 5) {
        throw new Error('Nieprawidłowy identyfikator komórki. Użyj formatu A1-H5.');
    }

    const colIndex = colMap[colLetter];      // 0 – A, 1 – B, ..., 7 – H
    const rowIndex = rowNumber - 1;           // 0 – wiersz 1, 1 – wiersz 2, ..., 4 – wiersz 5

    // Wymiary viewBox: szerokość = 8 (kolumny), wysokość = 5 (wiersze)
    const width = 8;
    const height = 5;
    const cellSize = 1;                       // bok kwadratu = 1 jednostka

    // Pozycja kwadratu w viewBox
    const x = colIndex * cellSize;
    const y = rowIndex * cellSize;

    // Generowanie kodu SVG (dodano atrybuty width/height w px dla wygody)
    return `<svg class="svg-field" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="24" height="15">
    <rect width="${width}" height="${height}" fill="white" stroke="none" />
    <rect x="${x}" y="${y}" width="${cellSize}" height="${cellSize}" fill="#${color}" stroke="none" />
    </svg>`;
}

function filterEvents(_element, _className) {
    let tableRowsToShow = document.querySelectorAll(`#game-events-table .${_className}`);
    let allTableRows = document.querySelectorAll(`#game-events-table .game-event-table-row`);
    let filterEventButtons = document.querySelectorAll('.filter-event-button');
    // let isClicked = _element.dataset.isClicked;
    if(_element.dataset.isClicked === 'false'){
        filterEventButtons.forEach(btn => {
            btn.dataset.isClicked = 'false';
            btn.style.backgroundColor = "buttonface";
        });
        _element.dataset.isClicked = 'true';
        _element.style.backgroundColor = "#cdfeb5";
        allTableRows.forEach(tr => {
            tr.style.display = 'none';
        });
        tableRowsToShow.forEach(tr => {
            tr.style.display = 'table-row';
        });
    }else{
        filterEventButtons.forEach(btn => {
            btn.dataset.isClicked = 'false';
            btn.style.backgroundColor = "#cdfeb5";
        });
        allTableRows.forEach(tr => {
            tr.style.display = 'table-row';
        });
    }
}

function filterSelectElements(element) {
    const playerFromOpponent = element.dataset.playerFromOpponent;
    const selectElement = document.querySelector('#event-edit-team-squad-select');
    
    if (!selectElement) return; // Zabezpieczenie przed brakującym elementem
    
    const options = selectElement.querySelectorAll('[data-player-from-opponent]');
    
    if (playerFromOpponent === null) {
        selectElement.style.display = 'none';
    } else {
        // Konwersja string na boolean
        const isPlayerFromOpponent = playerFromOpponent === 'true';
        
        options.forEach(option => {
            const optionValue = option.dataset.playerFromOpponent === 'true';
            option.style.display = optionValue === isPlayerFromOpponent ? 'block' : 'none';
        });
    }
}

function eventEditRadioGenerator(_gameEvent, _eventTypes) {
    const eTypes = _eventTypes;
    const gEvent = _gameEvent;
    let eventTypeRadioGroup = document.createElement('div');
    eventTypeRadioGroup.style.display = 'flex';
    eventTypeRadioGroup.style.height = '8vh';
    
    addClassName(eventTypeRadioGroup, 'event-type-radio-group');
    let radios = '';
    let checked = '';
    // let playerFromOpponent = null;
    eTypes.forEach(et => {
        // if(gEvent.team_id !== null && et.player_from_opponent === true) {
        //     playerFromOpponent = true;
        // } else if(gEvent.team_id !== null && et.player_from_opponent === false) {
        //     playerFromOpponent = false;
        // }
        if(et.id === gEvent.event_id) {
            checked = 'checked';
            let currentGameEventData = document.getElementById('current-game-event-data');
            currentGameEventData.dataset.eventTypeId = gEvent.event_id;
        }else{checked = ''};
        radios += `<input type="radio" name="eventType" id="event${et.id}" value="1" ${checked}>
                   <label style="width: calc(100vw/${eTypes.length});"
                   onclick="getGameEventSquadByEventType(${gEvent.id}, ${et.id});"
                   for="event${et.id}">${et.short_name}</label>`
    });
    eventTypeRadioGroup.innerHTML = radios;
    return eventTypeRadioGroup;
}

function toggleGameFieldCell(selectedCell) {
    console.log('toggleGameFieldCell');
    // let field = document.querySelector('#event-edit-game-field');
    let field = document.querySelector('#new-game-event-data');
    let allCells = document.querySelectorAll('.event-edit-game-field-cell');
    let selectedGameFieldCell = selectedCell;
    let selectedGameFieldCellId = selectedGameFieldCell.dataset.cellId;
    if (!selectedGameFieldCell.classList.contains('selected-game-field-cell')) {
        allCells.forEach(cell => {
            removeClassName(cell, 'selected-game-field-cell');
        });
        addClassName(selectedGameFieldCell, 'selected-game-field-cell');
        field.dataset.cellId = selectedGameFieldCellId;
    } else {
        allCells.forEach(cell => {
            removeClassName(cell, 'selected-game-field-cell');
        });
        field.dataset.cellId = '';
    }
}

function eventEditGameFieldGenerator(_eventCellID, cols = 8, rows = 5) {
    let _cellId = ''
    let html = `<div id="event-edit-game-field"
    class="game-field-selector" data-cell-id="none">`;
    for (let row = 1; row <= rows; row++) {
        html += `<div class="game-field-row" style="display: flex;">`;
        for (let col = 0; col < cols; col++) {
            let eventCellID = _eventCellID;
            const letter = String.fromCharCode(65 + col);
            const cellId = letter + row;
            let _class = '';
            if(cellId === eventCellID) {
                _class = 'selected-game-field-cell current-game-field-cell';
                _cellId = cellId;
            }
            html += `<div ondblclick="toggleGameFieldCell(this);" style="background-image: url(/static/images/field/empty.png)"
            data-cell-id="${cellId}" class="event-edit-game-field-cell ${_class}"></div>`;
        }
        html += `</div>`;
    }
    html += `</div>`;
    let currentGameEventData = document.getElementById('current-game-event-data');
    currentGameEventData.dataset.cellId = _cellId;
    return html.replace('data-cell-id="none"', `data-cell-id="${_cellId}"`);
}

function eventEditGameResultGenerator(_homeTeamGoals, _awayTeamGoals) {
    let html = `
    <div id="game-event-edit-result">
        <div id="game-event-edit-result-home-team-controllers">
            <button type="button"
                class="game-event-edit-result-controller-btn"
                onclick="changeGameEventResult('home', 1);"
            >+</button>
            <button type="button"
                class="game-event-edit-result-controller-btn"
                onclick="changeGameEventResult('home', -1);"
            >-</button>
        </div>
        <div id="game-event-edit-result-content">
            <div id="game-event-current-result">${_homeTeamGoals}:${_awayTeamGoals}</div>
            <div id="game-event-new-result">
                <span id="game-event-home-team-new-result">
                    ${_homeTeamGoals}</span>:<span id="game-event-away-team-new-result">${_awayTeamGoals}
                </span>
            </div>
        </div>
        <div id="game-event-edit-result-away-team-controllers">
            <button type="button"
                class="game-event-edit-result-controller-btn"
                onclick="changeGameEventResult('away', 1);"
            >+</button>
            <button type="button"
                class="game-event-edit-result-controller-btn"
                onclick="changeGameEventResult('away', -1);"
            >-</button>
        </div>
    </div>
    `;

    return html;
}

function changeGameEventResult(teamType, value) {
    let teamNewResultSpan = document.querySelector(`#game-event-${teamType}-team-new-result`);
    let teamNewResult = parseInt(teamNewResultSpan.textContent);
    let teamChangedResult = teamNewResult + value;
    if(teamChangedResult < 0){
        teamChangedResult = teamNewResult;
    }
    teamNewResultSpan.innerHTML = teamChangedResult;
    let updatedDataContainer = document.querySelector('#new-game-event-data');
    let teamDataResult;
    if(teamType === 'home'){
        teamDataResult = updatedDataContainer.dataset.homeTeamGoals = teamChangedResult;
    }else{
        teamDataResult = updatedDataContainer.dataset.awayTeamGoals = teamChangedResult;
    }
}

// function eventEditGetTeamByGameEvent(_gameData, _gameEvent, _eventTypes) {
//         const gameData = _gameData;
//         const homeTeamSquad = gameData.home_team_squad;
//         const awayTeamSquad = gameData.away_team_squad;
//         const gameEvent = _gameEvent;
//         const teamId = gameEvent.team_id;
//         const eventTypes = _eventTypes;
//         const eventTypeId = gameEvent.event_id;
//         const event = eventTypes.find(e => e.id === eventTypeId);
//         if (event?.player_from_opponent === 1) {
//             return teamId === gameData.home_team_id ? awayTeamSquad : homeTeamSquad;
//         }
//         return teamId === gameData.home_team_id ? homeTeamSquad : awayTeamSquad;
// }
function updateNewGameEventPlayer(_this){
    let newDataElement = document.querySelector('#new-game-event-data');
    let newPlayerElement = document.querySelector('#edit-event-new-player');
    console.log('_this.value:', _this.value);
    if(_this.value !== 'null') {
        let selEl = document.getElementById(_this.id);
        newDataElement.dataset.selectedPlayerId = _this.options[selEl.selectedIndex].dataset.playerId;
        newPlayerElement.innerHTML = _this.options[selEl.selectedIndex].text;
    }
}

function eventEditTeamsSquadSelectGenerator(_gameEvent, _teamSquad) {
    const gameEvent = _gameEvent;
    const teamSquad = _teamSquad;
    let currentGameEventData = document.querySelector('#current-game-event-data');
    let currentPlayerElement = document.querySelector('#edit-event-current-player');
    let newGameEventData = document.querySelector('#new-game-event-data');
    let newPlayerElement = document.querySelector('#edit-event-new-player');
    newPlayerElement.innerHTML = '';
    // let thisGameEventSquad;
    // let oppositeSquad;
    let squadSelect = document.createElement("select");
    squadSelect.id = 'event-edit-team-squad-select';
    squadSelect.dataset.selectedPlayerId = '';
    squadSelect.setAttribute('onchange', 'updateNewGameEventPlayer(this)');
    squadSelect.style.display = 'none';
    if(gameEvent.team_id !== null) {
        squadSelect.style.display = 'inline-block';
        // if(homeTeamId === gameEvent.team_id){
        //     thisGameEventSquad = homeTeamSquad;
        //     oppositeSquad = awayTeamSquad;
        // } else {
        //     thisGameEventSquad = awayTeamSquad;
        //     oppositeSquad = homeTeamSquad;
        // }
        let _option = document.createElement("option");
        _option.text = '';
        _option.value = 'null';
        if(gameEvent.player_id === null) {
            _option.selected = true;
            squadSelect.dataset.selectedPlayerId = '';
        }
        squadSelect.add(_option);
        if(teamSquad === null) return;
        teamSquad.forEach(player => {
            let isCaptain = '';
            if(player.is_captain) isCaptain = 'C';
            let isGK = '';
            if(player.is_goalkeeper) isGK = 'B';
            let option = document.createElement("option");
            // option.dataset.squadType = 'eventSquad';
            option.dataset.playerId = player.player_id;
            option.value = player.player_id;
            option.text = `${player.number} ${player.player_name} ${isGK} ${isCaptain}`;
            if(newGameEventData.dataset.selectedPlayerId !== '' && gameEvent.player_id === player.player_id) {
                option.selected = true;
                squadSelect.dataset.selectedPlayerId = player.player_id;
            }
            console.log(`${newGameEventData.dataset.selectedPlayerId} -|- ${player.player_id}`)
            if(parseInt(newGameEventData.dataset.selectedPlayerId) === player.player_id) {
                option.selected = true;
                squadSelect.dataset.selectedPlayerId = player.player_id;
                newPlayerElement.innerHTML = option.text;
            }
            // option.style.display = 'none';
            // if(gameEvent.player_from_opponent !== 1) option.style.display = 'block';
            squadSelect.add(option);
        });
    }
    return squadSelect;
}

function eventEditGameFieldListeners(){
    document.querySelectorAll('.event-edit-game-field-cell').forEach(element => {
        element.addEventListener('mouseover', () => {
            element.style.backgroundColor = 'rgba(0, 0, 0, 0.1)';
        });
    });

    document.querySelectorAll('.event-edit-game-field-cell').forEach(element => {
        element.addEventListener('mouseout', () => {
            element.style.backgroundColor = 'rgba(0, 0, 0, 0)';
        });
    });
}

function updateGameEvent(_contentType = '') {
    let gameEventupdatedDataContainer = document.querySelector('#new-game-event-data');
    let gameEventId = parseInt(gameEventupdatedDataContainer.dataset.gameEventId);
    let eventId = parseInt(gameEventupdatedDataContainer.dataset.eventTypeId);
    let gameTime = null;
    let replayEndTime = null;
    let replayStartTime = null;
    let videoPath = null;
    let eventPlace = gameEventupdatedDataContainer.dataset.cellId;
    let teamId = gameEventupdatedDataContainer.dataset.teamId;
    if(teamId !== 'null') {teamId = parseInt(teamId);}else{teamId = null;}
    let playerId = gameEventupdatedDataContainer.dataset.selectedPlayerId;
    if(playerId !== 'null') {playerId = parseInt(playerId);}else{playerId = null;}
    let homeTeamGoals = gameEventupdatedDataContainer.dataset.homeTeamGoals;
    let awayTeamGoals = gameEventupdatedDataContainer.dataset.awayTeamGoals;
    socket.emit('update_game_event',
        {
            'game_event_id': gameEventId,
            'event_id': eventId,
            'game_time': gameTime,
            'replay_end_time': replayEndTime,
            'replay_start_time': replayStartTime,
            'video_path': videoPath,
            'event_place': eventPlace,
            'team_id': teamId,
            'player_id': playerId,
            'home_team_goals': homeTeamGoals,
            'away_team_goals': awayTeamGoals,
            'content_type': _contentType
        }
    );
}

socket.on('show_ui_monitor_content', data => {
    console.log('data', data);
    let uiMonitorContent = document.getElementById('ui-monitor-content');
    if (data.content_type === null) {
        uiMonitorContent.innerHTML = '';
        uiMonitorContent.dataset.isEventsUpdateBlocked = 'false';
    } else if (data.content_type === 'events') {
        uiMonitorContent.innerHTML = '';
        let eventsTypeSelectorsContainer = document.createElement('div');
        eventsTypeSelectorsContainer.style.display = 'flex';
        eventsTypeSelectorsContainer.style.height = '8vh';
        eventsTypeSelectorsContainer.innerHTML = `
          <button type="button" class="filter-event-button" data-is-clicked="false" onclick="filterEvents(this, 'goal')">GOLE</button>
          <button type="button" class="filter-event-button" data-is-clicked="false" onclick="filterEvents(this, 'save')">OBRONY</button>
          <button type="button" class="filter-event-button" data-is-clicked="false" onclick="filterEvents(this, 'miss')">PUDŁA</button>
          <button type="button" class="filter-event-button" data-is-clicked="false" onclick="filterEvents(this, 'foul')">FAULE</button>
          <button type="button" class="filter-event-button" data-is-clicked="false" onclick="filterEvents(this, 'yellow_card')">Ż.KARTKI</button>
          <button type="button" class="filter-event-button" data-is-clicked="false" onclick="filterEvents(this, 'red_card')">CZ.KARTKI</button>
          <button type="button" class="filter-event-button" data-is-clicked="false" onclick="filterEvents(this, 'var')">VARY</button>`
        ;
        let gameEventsContainer = document.createElement('div');
        gameEventsContainer.id = 'game-events-container';
        gameEventsContainer.style.height = '84vh';
        gameEventsContainer.style.overflowY = 'auto';
        gameEventsContainer.innerHTML = '';
        let gameEventPopup = document.createElement('div');
        gameEventPopup.id = 'popup';
        gameEventsContainer.append(gameEventPopup);
        let gameEventsTable = document.createElement('table');
        gameEventsTable.id = 'game-events-table';
        let gameEvents = data.game_events.reverse();
        gameEvents.forEach(gameEvent => {
            console.log('gameEvent:', gameEvent);
            console.log('typeof:', typeof gameEvent);
            let gameEventTableRow = document.createElement('tr');
            if(typeof gameEvent === 'string'){
                gameEventTableRow.className = 'perriod-tr';
                gameEventTableRow.innerHTML = `<td></td><td></td><td></td><td></td><td></td>
                <td class="period-td" style="color: white;">${gameEvent}</td>`
            }else{
                if(gameEvent.event_place !== null){
                    const svgCode = fieldSvgGenerator(gameEvent.event_place, gameEvent.event_color);
                    const playerName = gameEventPlayerNameGenerator(gameEvent);
                    const teamShortName = gameEventTeamShortNameGenerator(gameEvent);
                    console.log(gameEvent.event_cameras);
                    const replaysPopupBtn = replaysPopupGen(gameEvent);
                    const eventInfoBtn = gameEventInfoBtnGenerator(gameEvent);
                    const eventEditBtn = gameEventEditBtnGenerator(gameEvent);
                    gameEventTableRow.className = gameEvent.filter_class;
                    addClassName(gameEventTableRow, 'game-event-table-row')
                    gameEventTableRow.style.color = gameEvent.event_color;
                    gameEventTableRow.innerHTML = `
                    <td class="events-td-svg-field">${svgCode}</td>
                    <td class="events-td-game-time">${gameEvent.game_time_formatted}</td>
                    <td class="events-td-event-name">${gameEvent.event_short_name}</td>
                    <td class="events-td-team-short-name">${teamShortName}</td>
                    <td class="events-td-result">${gameEvent.home_team_goals}:${gameEvent.away_team_goals}</td>
                    <td class="events-td-player-name">${playerName}</td>
                    <td class="events-td-open-replays-popup">${replaysPopupBtn}</td>
                    <td class="events-td-event-info">${eventInfoBtn}</td>
                    <td class="events-td-event-edit">${eventEditBtn}</td>
                    `;
                }
            }
            gameEventsTable.appendChild(gameEventTableRow);
        });
        gameEventsContainer.append(gameEventsTable);
        uiMonitorContent.append(eventsTypeSelectorsContainer);
        uiMonitorContent.append(gameEventsContainer);
        uiMonitorContent.dataset.isEventsUpdateBlocked = 'false';
    } else if(data.content_type === 'edit_event') {
        const eventsTypes = data.events_types;
        const gameEvent = data.game_event;
        const teamSquad = data.team_squad;
        uiMonitorContent.innerHTML = '';
        let gameEventDataContainer = document.createElement('div');
        gameEventDataContainer.innerHTML = `
        <div id="current-game-event-data" style="background-color: gray;"
            data-event-type-id="${gameEvent.event_id}"
            data-game-event-id="${gameEvent.id}"
            data-cell-id="${gameEvent.event_place}"
            data-team-id="${gameEvent.team_id}"
            data-home-team-goals="${gameEvent.home_team_goals}"
            data-away-team-goals="${gameEvent.away_team_goals}"
            data-selected-player-id="${gameEvent.player_id}">
            <span id="edit-event-current-event-type">${gameEvent.event_short_name}</span> 
            <span id="edit-event-current-team-short-name">(${gameEvent.team_short_name})</span>
            <span id="edit-event-current-player">${gameEvent.player_number} ${gameEvent.player_name}</span>
        </div>
        <div id="new-game-event-data" style="background-color: darkgoldenrod;"
            data-event-type-id="${gameEvent.event_id}"
            data-game-event-id="${gameEvent.id}"
            data-cell-id="${gameEvent.event_place}"
            data-team-id="${gameEvent.team_id}"
            data-home-team-goals="${gameEvent.home_team_goals}"
            data-away-team-goals="${gameEvent.away_team_goals}"
            data-selected-player-id="${gameEvent.player_id}">
            <span id="edit-event-new-event-type">${gameEvent.event_short_name}</span> 
            <span id="edit-event-new-team-short-name">(${gameEvent.team_short_name})</span>       
            <span id="edit-event-new-player">${gameEvent.player_number} ${gameEvent.player_name}</span>       
        </div>
        `;
        uiMonitorContent.append(gameEventDataContainer);
        let isScoreboardReversed = data.is_scoreboard_reversed;
        eventEditEventTypeRadios = eventEditRadioGenerator(gameEvent, eventsTypes);
        let eventEditContainer = document.createElement('div');
        eventEditContainer.style.height = '84vh';
        eventEditContainer.style.overflowY = 'auto';
        eventEditContainer.style.display = 'flex';
        eventEditContainer.innerHTML = '';
        let eventEditLeftColumn = document.createElement('div');
        eventEditLeftColumn.style.width = '160px';
        eventEditLeftColumn.innerHTML = eventEditGameFieldGenerator(gameEvent.event_place);
        eventEditLeftColumn.innerHTML += eventEditGameResultGenerator(gameEvent.home_team_goals, gameEvent.away_team_goals);
        eventEditLeftColumn.innerHTML += `
        <div style="display: flex;">
            <button type"button" class="flex1" onclick="updateGameEvent()">ZACHOWAJ</button>
            <button type"button" class="flex1" onclick="updateGameEvent('events')"> ZAPISZ </button>
        </div>`;
        let eventEditRightColumn = document.createElement('div');
        eventEditRightColumn.id = 'event-edit-right-column';
        eventEditRightColumn.style.width = '260px';
        teamSelect = eventEditTeamsSquadSelectGenerator(gameEvent, teamSquad);
        uiMonitorContent.append(eventEditEventTypeRadios);
        uiMonitorContent.append(eventEditContainer);
        eventEditContainer.append(eventEditLeftColumn);
        eventEditContainer.append(eventEditRightColumn);
        eventEditRightColumn.append(teamSelect);
        eventEditGameFieldListeners();
        uiMonitorContent.dataset.isEventsUpdateBlocked = 'true';
    } else if(data.content_type === 'get_event_squad') {
        const gameEvent = data.game_event;
        const teamSquad = data.team_squad;
        let eventEditRightColumn = document.getElementById('event-edit-right-column');
        let eventEditTeamSquadSelect = document.getElementById('event-edit-team-squad-select');
        let newGameEventData = document.getElementById('new-game-event-data');
        newGameEventData.dataset.eventTypeId = gameEvent.event_id;
        newGameEventData.dataset.cellId = gameEvent.event_place;
        newGameEventData.dataset.teamId = gameEvent.team_id;
        // newGameEventData.dataset.selectedPlayerId = gameEvent.player_id;
        document.getElementById('edit-event-new-event-type').innerHTML = gameEvent.event_short_name;
        document.getElementById('edit-event-new-team-short-name').innerHTML = `(${gameEvent.team_short_name})`;
        if(eventEditTeamSquadSelect !== null) {
            eventEditTeamSquadSelect.remove();
        }
        if(teamSquad !== null){
            teamSelect = eventEditTeamsSquadSelectGenerator(gameEvent, teamSquad);
            eventEditRightColumn.append(teamSelect);
        }
    }
});

socket.on('game_event_updated', data => {
    let gameEventId = data.game_event_id;
    let contentType = data.content_type;
    if(contentType !== ''){
        showUiMonitorContent(contentType);
    }else{
        openGameEventEditForm(gameEventId);
    }
});


// ============================================================================
// DEBUG HELPERS
// ============================================================================

window.debugTimers = () => {
    console.log('=== TIMER DEBUG ===');
    console.log('Period:', period);
    console.log('Main timer data:', appState.mainTimer);
    console.log('home_penalties data:', appState.home_penalties);
    console.log('away_penalties data:', appState.away_penalties);
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