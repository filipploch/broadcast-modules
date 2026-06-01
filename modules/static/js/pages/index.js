/**
 * INDEX.JS — Kontrola timera i tablicy wyników
 *
 * Używane przez: index.html  (endpoint /)
 * Zawiera:
 *   – WebSocket setup + initial_data
 *   – wyświetlanie timera głównego i kar
 *   – przyciski start / pauza / wznów / reset / adjust
 *   – reorderReversible (odwracanie tablicy)
 *   – addTeamEvent (kartki)
 * NIE zawiera: nakładek OBS, kontrolera zdarzeń, monitoringu pluginów
 */

// ============================================================================
// WEBSOCKET
// ============================================================================

var socket = (typeof socket !== 'undefined') ? socket : io();

// Flaga pochodzi z config.py modułu (HAS_PENALTY_TIMERS) → wstrzyknięta przez
// context_processor → index.html jako stała JS. Gdy false, wywołania
// fillPenaltiesTimersContainer() są pomijane (ui-modal.js nie jest wtedy ładowane).
const _hasPenalties = (typeof HAS_PENALTY_TIMERS !== 'undefined') && HAS_PENALTY_TIMERS;

var homeScoreLabel = document.getElementById('scoreHome');
var awayScoreLabel = document.getElementById('scoreAway');
var homeFoulsLabel = document.getElementById('value2Home');
var awayFoulsLabel = document.getElementById('value2Away');

// ============================================================================
// CAMERA ICONS
// ============================================================================

const _CAMERA_ICON_MAP = {
    'camera1-icon': 'camera1',
    'camera2-icon': 'camera2',
    'camera3-icon': 'camera3',
    'camera4-icon': 'camera4',
};

let _cameraAssignments = null; // null = not yet received; {camera1: bool, ...} once received
let _cameraRecording   = {};   // {camera1: bool, ...}

function _applyOneCameraIconColor(iconId) {
    const cameraId = _CAMERA_ICON_MAP[iconId];
    if (!cameraId) return;
    console.log(`[_applyOneCameraIconColor] iconId=${iconId} cameraId=${cameraId} assignments=`, _cameraAssignments);
    if (_cameraAssignments !== null) {
        const assigned = _cameraAssignments[cameraId];
        console.log(`[_applyOneCameraIconColor] assigned=${assigned} → colorizeSvgBackground(${iconId}, ${assigned ? 'black' : '#666666'})`);
        colorizeSvgBackground(iconId, assigned ? 'black' : '#666666');
    }
    if (_cameraRecording[cameraId] !== undefined) {
        colorizeSvgBody(iconId, _cameraRecording[cameraId] ? 'red' : '#cccccc');
    }
}

function _applyCameraIconColors() {
    for (const iconId of Object.keys(_CAMERA_ICON_MAP)) {
        _applyOneCameraIconColor(iconId);
    }
}

socket.on('camera_assignments', (data) => {
    console.log('[camera_assignments] received:', data);
    if (data && data.cameras) {
        _cameraAssignments = data.cameras;
    }
    console.log('[camera_assignments] _cameraAssignments:', _cameraAssignments);
    _applyCameraIconColors();
});

socket.on('recording_status_response', (data) => {
    const cameras = data.cameras || {};
    for (const [cameraId, isRecording] of Object.entries(cameras)) {
        _cameraRecording[cameraId] = isRecording;
    }
    _applyCameraIconColors();
});

socket.on('recording_started', (data) => {
    if (data.camera_id) {
        _cameraRecording[data.camera_id] = true;
        _applyCameraIconColors();
    }
});

socket.on('recording_stopped', (data) => {
    if (data.camera_id) {
        _cameraRecording[data.camera_id] = false;
        _applyCameraIconColors();
    }
});

// ============================================================================
// STREAM ICON
// ============================================================================

let _streamState = 'disabled';

socket.on('obs_stream_state', (data) => {
    _streamState = data.state || 'disabled';
    const bodyColor = _streamState === 'active'   ? 'red'
                    : _streamState === 'changing'  ? 'yellow'
                    : '#cccccc';
    colorizeSvgBody('stream-icon', bodyColor);
});

function onStreamIconDblClick() {
    if (_streamState === 'active') {
        stopStream();
    } else {
        startStream();
    }
}

// ============================================================================
// RECORD ICON
// ============================================================================

let _recordState = 'disabled';

socket.on('obs_record_state', (data) => {
    _recordState = data.state || 'disabled';
    const bodyColor = _recordState === 'active'  ? 'red'
                    : _recordState === 'changing' ? 'yellow'
                    : '#cccccc';
    colorizeSvgBody('record-icon', bodyColor);
});

function onRecordIconDblClick() {
    if (_recordState === 'active') {
        stopRecording();
    } else {
        startRecording();
    }
}

// ============================================================================
// MICROPHONE ICON
// ============================================================================

function _applyMicrophoneColor(enabled) {
    colorizeSvgBody('microphone-icon', enabled ? '#00FF00' : '#cccccc');
}

socket.on('source_visibility_response', (data) => {
    if (data.scene_name === 'AUDIO_SOURCES' && data.source_name === 'MICROPHONES') {
        _applyMicrophoneColor(data.enabled);
    }
});

socket.on('source_visibility_changed', (data) => {
    if (data.scene_name === 'AUDIO_SOURCES' && data.source_name === 'MICROPHONES') {
        _applyMicrophoneColor(data.enabled);
    }
});

function onMicrophoneIconDblClick() {
    socket.emit('toggle_source_visibility', {
        scene_name:  'AUDIO_SOURCES',
        source_name: 'MICROPHONES',
    });
}

// ============================================================================
// STREAM OVERLAY ICON
// ============================================================================

function onStreamOverlayIconDblClick() {
    socket.emit('refresh_overlay_and_switch_scene');
}

// ============================================================================
// PLUGIN ICONS
// ============================================================================

const _PLUGIN_ICON_MAP = {
    'timer-plugin-icon':          'timer-plugin',
    'recorder-plugin-icon':       'recorder-plugin',
    'obs-ws-plugin-icon':         'obs-ws-plugin',
    'replay-plugin-icon':         'replay-plugin',
    'controller-plugin-icon':     'controller-plugin',
    'stream-overlay-plugin-icon': 'stream-overlay',
};

let _pluginStates = {};

function _applyOnePluginIconColor(iconId) {
    const pluginId = _PLUGIN_ICON_MAP[iconId];
    if (!pluginId) return;
    const state = _pluginStates[pluginId];
    if (!state) return;
    colorizeSvgBackground(iconId, state.is_active  ? 'black'   : '#666666');
    colorizeSvgBody(iconId,       state.is_healthy ? '#00FF00' : '#cccccc');
}

socket.on('plugins_states', (data) => {
    _pluginStates = data;
    for (const iconId of Object.keys(_PLUGIN_ICON_MAP)) {
        _applyOnePluginIconColor(iconId);
    }
});

// ============================================================================
// WEBSOCKET
// ============================================================================

socket.on('connect', () => {
    console.log('✅ WebSocket connected');
    socket.emit('request_initial_data');
    socket.emit('get_camera_assignments');
    socket.emit('get_obs_record_status');
    socket.emit('get_obs_stream_status');
    socket.emit('get_camera_recording_status');
    socket.emit('get_source_visibility', { scene_name: 'AUDIO_SOURCES', source_name: 'MICROPHONES' });
});

socket.on('disconnect', () => {
    console.log('❌ WebSocket disconnected');
});

socket.on('initial_data', (data) => {
    appState.home_team_goals   = data.home_team_goals;
    appState.home_team_value2  = data.home_team_value2;
    appState.home_penalties    = data.home_penalties;
    appState.away_team_goals   = data.away_team_goals;
    appState.away_team_value2  = data.away_team_value2;
    appState.away_penalties    = data.away_penalties;
    appState.mainTimer        = data.main_timer;
    appState.isReversed       = data.is_reversed;
    appState.isReordering     = false;

    applyReversedState(appState.isReversed);
    if (appState.mainTimer) {
        window.initialTime = appState.mainTimer.initial_time;
        updateTimerDisplay(appState.mainTimer);
    }
    if (_hasPenalties) {
        fillPenaltiesTimersContainer(appState.home_penalties, 'home');
        fillPenaltiesTimersContainer(appState.away_penalties, 'away');
    }
});

function fillIndexWithShootoutContent() {
    let columnControls = document.querySelector('#column-controls');
    if (!columnControls) return;
    columnControls.innerHTML = '';
    columnControls.innerHTML = `
    <div class="top-bar">
        <button id="nav-to-game-settings" class="top-bar-element wingdings">
            <a href="/game-period-choice">Û</a>
        </button>
    </div>
    <div id="shootout-teams-short-name-container" style="display:flex;">
        <div id="shootout-home-team-short-name" class="shootout-teams-short-name">${appState.home_team_short_name}</div>
        <div id="shootout-away-team-short-name" class="shootout-teams-short-name">${appState.away_team_short_name}</div>
        </div>
    <div id="shootout-teams-result-container" style="display:flex;">
        <div id="shootout-home-team-resut" class="shootout-teams-resut">${appState.home_team_shootouts}</div>
        <div id="shootout-away-team-resut" class="shootout-teams-resut">${appState.away_team_shootouts}</div>
    </div>
    `;
}


socket.on('shootout_initial_data', (data) => {
    appState.home_team_short_name = data.home_team_short_name;
    appState.away_team_short_name = data.away_team_short_name;
    appState.home_team_shootouts  = data.home_team_shootouts;
    appState.away_team_shootouts  = data.away_team_shootouts;
    appState.score_string         = data.score_string;
    fillIndexWithShootoutContent();
});

// Przeładuj stronę gdy zmienił się mecz transmisji — nowe dane period
// zostaną wczytane przez Jinja przy odświeżeniu zamiast nawigować z dala.
socket.on('game_changed', function() {
    window.location.reload();
});

function startRecording(){
    socket.emit('start_recording');
}

function stopRecording(){
    socket.emit('stop_recording');
}

function startStream(){
    socket.emit('trigger_sequence', { sequence: 'start_live', context: {}});
}

function stopStream(){
    socket.emit('trigger_sequence', { sequence: 'end_live', context: {}});
}


// ============================================================================
// TIMER DISPLAY
// ============================================================================

function formatTime(milliseconds) {
    const totalSeconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

// function updateTimerDisplay(timerData) {
//     if (!timerData) return;
//     const timerId   = timerData.timer_id;
//     const elapsed   = timerData.elapsed_time ?? 0;
//     const minEl     = document.querySelector(`[data-display-for="${timerId}-min-display"]`);
//     const secEl     = document.querySelector(`[data-display-for="${timerId}-sec-display"]`);
//     const dsEl      = document.querySelector(`[data-display-for="${timerId}-ds-display"]`);

//     const totalSec  = Math.floor(elapsed / 1000);
//     const ds        = Math.floor((elapsed % 1000) / 100);
//     if (minEl) minEl.textContent = String(Math.floor(totalSec / 60)).padStart(2, '0');
//     if (secEl) secEl.textContent = String(totalSec % 60).padStart(2, '0');
//     if (dsEl)  dsEl.textContent  = ds;

//     updateTimerState(timerId, timerData.state);
// }

function updateTimerState(timerId, state) {
    const buttons = document.querySelectorAll(`[data-timer-id="${timerId}"]`);
    buttons.forEach(btn => {
        const btnState = btn.dataset.timerState;
        if (!btnState) return;
        if (btnState === state) {
            btn.classList.remove('nodisplayed');
        } else {
            btn.classList.add('nodisplayed');
        }
    });
    const header = document.querySelector(`[data-state-for="${timerId}"]`);
    if (header) {
        header.className = `main-timer-header state-${state}`;
    }
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
    const initialTime  = timerData.initial_time || 0;
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

    if (TIMER_DESC) {
        // Count down: show remaining = limit - (initialTime + elapsed)
        // Subtract 1ms so display changes exactly on the second boundary
        const shown = elapsed;
        // timerLimit = timerLimit - initialTime;
        // const shown = initialMs + elapsed;
        displayTime = timerState === 'idle'
            ? Math.max(0, timerLimit - shown)
            : Math.max(0, timerLimit - shown - 1);
    } else {
        // Count up: show initialTime + elapsed
        displayTime = initialTime + elapsed;
    }

    const minutes  = Math.floor(displayTime / 60000);
    const seconds  = Math.floor((displayTime % 60000) / 1000);
    const dseconds = Math.floor((displayTime % 1000) / 100);

    minutesDisplay.textContent  = minutes.toString().padStart(2, '0');
    secondsDisplay.textContent  = seconds.toString().padStart(2, '0');
    dsecondsDisplay.textContent = dseconds.toString();
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

socket.on('timer_created', (data) => {
    if (data.timer_id && !data.timer_id.startsWith('penalty_')) {
        appState.mainTimer = data;
        if (data.initial_time !== undefined) window.initialTime = data.initial_time;
        updateTimerDisplay(data);
        updateTimerState(data.timer_id, data.state);
    }
});

socket.on('timer_ensured', (data) => {
    if (data.timer_id && !data.timer_id.startsWith('penalty_')) {
        appState.mainTimer = data;
        if (data.initial_time !== undefined) window.initialTime = data.initial_time;
        updateTimerDisplay(data);
        updateTimerState(data.timer_id, data.state);
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

// socket updates
socket.on('timer_update', (timerData) => updateTimerDisplay(timerData));

socket.on('game_state_update', (data) => {
    if (data.home_team_goals !== undefined && homeScoreLabel)
        homeScoreLabel.textContent = data.home_team_goals;
    if (data.away_team_goals !== undefined && awayScoreLabel)
        awayScoreLabel.textContent = data.away_team_goals;
    if (data.home_team_value2 !== undefined && homeFoulsLabel)
        homeFoulsLabel.textContent = data.home_team_value2;
    if (data.away_team_value2 !== undefined && awayFoulsLabel)
        awayFoulsLabel.textContent = data.away_team_value2;
});

socket.on('penalty_timer_update', (timerData) => {
    updatePenaltyTimerDisplay(
        timerData.timer_id,
        timerData.elapsed_time,
        timerData.limit,
        timerData.initial_time
    );
});

socket.on('penalty_timer_added', (data) => {
    const team = data.team_type;
    if (team === 'home') appState.home_penalties.push(data);
    else                 appState.away_penalties.push(data);
    if (_hasPenalties) {
        fillPenaltiesTimersContainer(
            team === 'home' ? appState.home_penalties : appState.away_penalties,
            team
        );
    }
});

socket.on('penalty_timer_removed', (data) => {
    appState.home_penalties = appState.home_penalties.filter(p => p.timer_id !== data.timer_id);
    appState.away_penalties = appState.away_penalties.filter(p => p.timer_id !== data.timer_id);
    if (_hasPenalties) {
        fillPenaltiesTimersContainer(appState.home_penalties, 'home');
        fillPenaltiesTimersContainer(appState.away_penalties, 'away');
    }
});

// ============================================================================
// PENALTY TIMER DISPLAY
// ============================================================================

function updatePenaltyTimerDisplay(timerId, elapsedMs, timerLimit, initialTime = 0) {
    const remaining = Math.max(0, timerLimit - elapsedMs);
    const displayEl = document.querySelector(`[data-display-for="${timerId}"]`);
    if (displayEl) {
        const s = Math.floor(remaining / 1000);
        displayEl.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
    }
}

// ============================================================================
// TIMER CONTROLS
// ============================================================================

function startTimer(timerId) {
    socket.emit('start_timer', { timer_id: timerId });
}

function pauseTimer(timerId) {
    socket.emit('pause_timer', { timer_id: timerId });
}

function resumeTimer(timerId) {
    socket.emit('resume_timer', { timer_id: timerId });
}

function resetTimer(timerId) {
    socket.emit('reset_timer', { timer_id: timerId });
}

function onStartPeriodClick(timerId) {
    if (!window.period || !window.period.id) return;
    fetch(`/api/period/${window.period.id}/start`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                window.period.status = 1;
                // Zmień onclick przycisku na startTimer dla kolejnych kliknięć
                document.querySelectorAll(
                    '.timer-main-controller[data-timer-state="idle"]'
                ).forEach(btn => {
                    btn.removeAttribute('disabled');
                    btn.onclick = () => startTimer(timerId);
                });
                // Uruchom odliczanie — do czasu HTTP round-trip plugin zdąży
                // przetworzyć ensure_timer, więc start_timer trafi na istniejący timer
                startTimer(timerId);
            } else {
                alert(`Błąd uruchamiania okresu: ${data.error || 'Nieznany błąd'}`);
            }
        })
        .catch(err => alert(`Błąd uruchamiania okresu: ${err}`));
}

function _showPeriodChoiceFrame() {
    const f = document.getElementById('left-frame');
    f.contentWindow.location.reload();
    f.style.display = 'block';
}

function onResetPeriodDblClick(timerId) {
    if (!window.period || !window.period.id) return;
    fetch(`/api/period/${window.period.id}/reset`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                resetTimer(timerId);
            } else {
                alert(`Błąd resetu okresu: ${data.error || 'Nieznany błąd'}`);
                _showPeriodChoiceFrame();
            }
        })
        .catch(err => {
            alert(`Błąd resetu okresu: ${err}`);
            _showPeriodChoiceFrame();
        });
}

function onFinishPeriodDblClick() {
    if (!window.period || !window.period.id) return;
    fetch(`/api/period/${window.period.id}/finish`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (!data.ok) {
                alert(`Błąd kończenia okresu: ${data.error || 'Nieznany błąd'}`);
            }
            _showPeriodChoiceFrame();
        })
        .catch(err => {
            alert(`Błąd kończenia okresu: ${err}`);
            _showPeriodChoiceFrame();
        });
}

function adjustTimer(timerId, delta, isPenalty = false) {
    socket.emit('adjust_timer', { timer_id: timerId, delta: delta, is_penalty: isPenalty });
}

function addPenaltyTimer(teamType, penaltyDuration = 2) {
    socket.emit('add_penalty_timer', { team_type: teamType, duration: penaltyDuration });
}

function removeTimer(timerId) {
    socket.emit('remove_timer', { timer_id: timerId });
}


// ---------------------------------------------------------------------------
// Reversible layout — deterministic, anchor-based
// ---------------------------------------------------------------------------


// Keep in sync when the other page triggers a reverse
socket.on('scoreboard_reversed', function(data) {
    applyReversedState(data.is_reversed);
});

function onReverseButtonClick() {
    applyReversedState(!appState.isReversed);
    socket.emit('set_reversed', { is_reversed: appState.isReversed });
}

// ============================================================================
// TEAM EVENTS
// ============================================================================


function addTeamEvent(teamType, eventName) {
    socket.emit('add_team_event', { team_type: teamType, event_name: eventName });
}

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
}

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
    const effectiveDelta = (!isPenalty && !TIMER_DESC) ? -delta : delta;
    if(isPenalty == true){
        socket.emit('timer_adjust', {
            timer_id: timerId,
            delta: effectiveDelta
        });
    } else {
        let allTimersIds = getAllTimerIds();
        allTimersIds.forEach(tmrId => {
            socket.emit('timer_adjust', {
                timer_id: tmrId,
                delta: effectiveDelta
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

    if (_hasPenalties) {
        fillPenaltiesTimersContainer(appState.home_penalties, 'home');
        fillPenaltiesTimersContainer(appState.away_penalties, 'away');
    }
});

socket.on('scoreboard_data', (data) => {
    let gameData = data['payload'];
    homeScoreLabel.innerText = gameData['home_team_goals'];
    awayScoreLabel.innerText = gameData['away_team_goals'];
    homeFoulsLabel.innerText = gameData['home_team_value2'];
    awayFoulsLabel.innerText = gameData['away_team_value2'];
})

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

function exportReplays(){
    socket.emit('replay_export_run', {game_id: null});
}