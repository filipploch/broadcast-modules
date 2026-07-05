// ── Konfiguracja siatki boiska (musi być spójna z events-controllers.js) ─────
// Używamy var, żeby nie kolidować z const w events-controllers.js
var FIELD_COLS = 15;
var FIELD_ROWS = 9;


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




var socket = (typeof socket !== 'undefined') ? socket : io();

var homeScoreLabel = document.getElementById('scoreHome');
var awayScoreLabel = document.getElementById('scoreAway');
var homeFoulsLabel = document.getElementById('foulsHome');
var awayFoulsLabel = document.getElementById('foulsAway');
var currentSequenceId = null;

var replayResumeElement = document.querySelector('#replay-resume-element');
var replayPauseElement = document.querySelector('#replay-pause-element');



const _MONITOR_TAB_DEFS = {
    events:        { label: 'AKCJE',  action: () => showUiMonitorContent('events') },
    substitutions: { label: 'ZMIANY', action: () => showUiMonitorContent('substitutions') },
    games:         { label: 'MECZE',  action: () => showUiMonitorContent('games') },
    banners:       { label: 'BANERY',    action: () => showUiMonitorContent('banners') },
    backgrounds:   { label: 'TŁA',       action: () => showUiMonitorContent('backgrounds') },
};

function buildMonitorControls() {
    const container = document.getElementById('ui-monitor-controlls');
    if (!container) return;

    const config = MODULE_REGISTRY[MODULE_NAME] || {};
    const tabs = config.monitorTabs || [];

    tabs.forEach(key => {
        const def = _MONITOR_TAB_DEFS[key];
        if (!def) return;
        const div = document.createElement('div');
        div.className = 'flex1';
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = def.label;
        btn.addEventListener('click', def.action);
        div.appendChild(btn);
        container.appendChild(div);
    });

    const closeDiv = document.createElement('div');
    closeDiv.className = 'flex1';
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.textContent = 'X';
    closeBtn.addEventListener('click', () => showUiMonitorContent());
    closeDiv.appendChild(closeBtn);
    container.appendChild(closeDiv);
}

buildMonitorControls();

socket.on('connect', () => {
    console.log('✅ WebSocket connected');
    socket.emit('request_initial_data');
    socket.emit('get_record_status');
    socket.emit('get_obs_record_status');
    getObsWsConnection()
});

socket.on('disconnect', () => {
    console.log('❌ WebSocket disconnected');
});

socket.on('initial_data', (data) => {
    applyReversedState(data.is_reversed);
    if (data.home_team_uniform) {
        setMultiColorBackground(
            'home-side-events-controllers-container',
            JSON.parse(data.home_team_uniform)
        );
    }
    if (data.away_team_uniform) {
        setMultiColorBackground(
            'away-side-events-controllers-container',
            JSON.parse(data.away_team_uniform)
        );
    }
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

// Redirect to period choice when broadcast game changes
socket.on('reload_ui_dashboard', function() {
    window.location.href = '/ui';
});


function runSequence(){
    socket.emit('trigger_sequence', { sequence: 'halftime_start', context: {} });
}

// function startRecording(){
//     socket.emit('start_recording');
// }

// function stopRecording(){
//     socket.emit('stop_recording');
// }

// function startStream(){
//     socket.emit('trigger_sequence', { sequence: 'start_live', context: {}});
// }

// function stopStream(){
//     socket.emit('trigger_sequence', { sequence: 'end_live', context: {}});
// }

function getObsWsConnection() {
    socket.emit('get_obs_ws_connection');
}



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



socket.on('recording_status_response', data => {
    console.log(data);
});

socket.on('recording_started', cameras => {
    updateCamerasIndicators(cameras);
});

socket.on('recording_stopped', cameras => {
    updateCamerasIndicators(cameras);
});

socket.on('recording_status_updated', cameras => {
    updateRecordingIndicators(cameras);
});

socket.on('obs_recording_status_updated', responseData => {
    updateObsRecordingIndicator(responseData);
});



/**
 * Handle error event
 */
socket.on('error', (data) => {
    console.error('❌ Socket error:', data);
    alert(`Błąd: ${data.message}`);
});



// ============================================================================
// PERIOD FINISH
// ============================================================================

/**
 * Finish current period
 */
// function finishPeriod() {
//     if (!period) {
//         alert('Brak aktywnego okresu!');
//         return;
//     }
    
//     if (!confirm('Czy na pewno chcesz zakończyć tę część meczu?')) {
//         return;
//     }
    
//     console.log('Finishing period:', period.id);
//     window.location.href = `/period/${period.id}/finish`;
// }

// ============================================================================
// INITIALIZATION
// ============================================================================



// function onReverseButtonClick() {
//     applyReversedState(!appState.isReversed);
//     socket.emit('set_reversed', { is_reversed: appState.isReversed });
// }

// // ---------------------------------------------------------------------------
// // Reversible layout — deterministic, anchor-based
// // ---------------------------------------------------------------------------

// function applyReversedState(isReversed) {
//     document.querySelectorAll('.reversible').forEach(function(el) {
//         var children = Array.from(el.children);
//         if (children.length < 2) return;

//         var anchor = children.find(function(c) {
//             return c.hasAttribute('data-reverse-anchor');
//         });
//         if (!anchor) return;

//         var anchorIsFirst = children[0] === anchor;
//         var shouldFlip = (isReversed && anchorIsFirst) || (!isReversed && !anchorIsFirst);

//         if (shouldFlip) {
//             children.reverse().forEach(function(c) {
//                 el.appendChild(c);
//             });
//         }
//     });

//     appState.isReversed = isReversed;
// }

// Keep in sync when the other page triggers a reverse
socket.on('scoreboard_reversed', function(data) {
    applyReversedState(data.is_reversed);
    refreshEditResultDisplay();
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
        return `<span class="events-td-player-number">${_gameEvent.player_number ?? ''}</span> ${_gameEvent.player_name ?? ''}`
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
    let newGameEventData = document.getElementById('new-game-event-data');
    let teamIdRaw = newGameEventData.dataset.teamId;
    let teamId = (teamIdRaw === 'null' || teamIdRaw === '') ? null : parseInt(teamIdRaw);
    const payload = {
        'game_event_id': _gameEventId,
        'new_event_type_id': _newEventTypeId,
        'new_team_id': teamId
    }
    showUiMonitorContent('get_event_squad', payload);
}

function showReplay(videoPath, replayStartTime, replayEndTime) {
    _replayCurrentSpeed = 0.9; // reset prędkości — nowa powtórka startuje z domyślną
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
    const colMap = {};
    for (let i = 0; i < FIELD_COLS; i++) {
        colMap[String.fromCharCode(65 + i)] = i;
    }

    const colLetter = cellId.charAt(0).toUpperCase();
    const rowNumber = parseInt(cellId.slice(1), 10);
    const lastColLetter = String.fromCharCode(65 + FIELD_COLS - 1);

    if (!(colLetter in colMap) || rowNumber < 1 || rowNumber > FIELD_ROWS) {
        throw new Error(`Nieprawidłowy identyfikator komórki. Użyj formatu A1-${lastColLetter}${FIELD_ROWS}.`);
    }

    const x = colMap[colLetter];
    const y = rowNumber - 1;

    return fieldSvgStr(MODULE_NAME, x, y, '#' + color);
}

var _showHiddenEvents = false;

function filterEvents(_element, _className) {
    let tableRowsToShow = document.querySelectorAll(`#game-events-table .${_className}`);
    let allTableRows = document.querySelectorAll(`#game-events-table .game-event-table-row`);
    let filterEventButtons = document.querySelectorAll('.filter-event-button');
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

function toggleHiddenEvents(_element) {
    _showHiddenEvents = !_showHiddenEvents;
    _element.style.backgroundColor = _showHiddenEvents ? '#FF8080' : 'white';
    showUiMonitorContent('events', { include_hidden: _showHiddenEvents });
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


function eventEditGameResultGenerator(_homeTeamGoals, _awayTeamGoals) {
    let html = `
    <div id="game-event-edit-result" class="reversible">
        <div id="game-event-edit-result-home-team-controllers" data-reverse-anchor>
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
            <div id="game-event-current-result" class="current-selection"
                data-home-goals="${_homeTeamGoals}"
                data-away-goals="${_awayTeamGoals}"
            >${_homeTeamGoals}:${_awayTeamGoals}</div>
            <div id="game-event-new-result" class="reversible new-selection">
                <span id="game-event-home-team-new-result" data-reverse-anchor>${_homeTeamGoals}</span><span class="result-separator">:</span><span id="game-event-away-team-new-result">${_awayTeamGoals}</span>
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

function refreshEditResultDisplay() {
    const el = document.getElementById('game-event-current-result');
    if (!el) return;
    const h = el.dataset.homeGoals;
    const a = el.dataset.awayGoals;
    el.textContent = appState.isReversed ? `${a}:${h}` : `${h}:${a}`;
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

function hideGameEvent(gameEventId) {
    socket.emit('hide_game_event', { 'game_event_id': gameEventId });
}

function restoreGameEvent(gameEventId) {
    socket.emit('restore_game_event', { 'game_event_id': gameEventId });
}

function selectEventTeam(button) {
    if (button.disabled) return;
    const container = document.getElementById('event-team-selector');
    container.querySelectorAll('button').forEach(btn => btn.classList.remove('new-selection'));
    if (!button.classList.contains('current-selection')) {
        button.classList.add('new-selection');
    }
    let newGameEventData = document.getElementById('new-game-event-data');
    let gameEventId = parseInt(newGameEventData.dataset.gameEventId);
    let eventTypeId = parseInt(newGameEventData.dataset.eventTypeId);
    let teamId = button.dataset.teamId === '' ? null : parseInt(button.dataset.teamId);
    showUiMonitorContent('get_event_squad', {
        'game_event_id': gameEventId,
        'new_event_type_id': eventTypeId,
        'new_team_id': teamId
    });
}

socket.on('game_event_hidden', function(data) {
    showUiMonitorContent('events', { include_hidden: _showHiddenEvents });
});

socket.on('game_event_restored', function(data) {
    showUiMonitorContent('events', { include_hidden: _showHiddenEvents });
});

function renderSubstitutionElement(element) {
    var div = document.createElement('div');
    div.className = 'substitution-element';
    div.setAttribute('ondblclick',
        "showUiMonitorContent('substitution-edit', {substitution_id: " + element.id + "})"
    );
    div.innerHTML =
        '<div class="player-in">' +
            '<span class="subst-player-number">' + (element.player_in_number  || '') + '</span>' +
            '<span class="subst-player-name">'   + (element.player_in_name    || '') + '</span>' +
        '</div>' +
        '<div class="player-out">' +
            '<span class="subst-player-number">' + (element.player_out_number || '') + '</span>' +
            '<span class="subst-player-name">'   + (element.player_out_name   || '') + '</span>' +
        '</div>';
    return div.outerHTML;
}

function showSubstitution(periodId, teamId, substitutionGroup) {
    socket.emit('show_substitution', {
        period_id:          periodId,
        team_id:            teamId,
        substitution_group: substitutionGroup,
    });
}

function _buildSubstGroupHtml(sGroup, groupHtml, periodId, teamId) {
    var svgIcon =
        '<svg height="13" viewBox="0 -960 481.49437 361.12079" width="11" fill="#ffffff" ' +
            'version="1.1" xmlns="http://www.w3.org/2000/svg">' +
            '<path d="m 90.28019,-689.1594 h 210.65379 v -45.1401 H 90.28019 Z m 255.79389,' +
            '0 h 45.14009 v -45.1401 H 346.07408 Z M 90.28019,-779.4396 h 45.1401 v -45.1401 ' +
            'h -45.1401 z m 90.2802,0 h 210.65378 v -45.1401 H 180.56039 Z M 45.1401,-598.87921 ' +
            'q -18.62029,0 -31.8802,-13.26617 Q 9.9999998e-7,-625.41156 9.9999998e-7,-644.04439 ' +
            'v -270.99104 q 0,-18.63283 13.25989900000002,-31.79869 13.25991,-13.16587 ' +
            '31.8802,-13.16587 h 391.21417 q 18.62029,0 31.88019,13.26618 13.25991,13.26617 ' +
            '13.25991,31.899 v 270.99105 q 0,18.63283 -13.25991,31.79869 -13.2599,13.16586 ' +
            '-31.88019,13.16586 z m 0,-45.1401 H 436.35427 V -914.85989 H 45.1401 Z m 0,0 ' +
            'v -270.84058 z" style="stroke-width:1"></path></svg>';

    var btn =
        '<button type="button" class="event-btn subst-overlay-btn" ' +
            'style="background-color:green;padding:1px 3.6px;" ' +
            'onclick="showSubstitution(' + periodId + ',' + teamId + ',' + sGroup + ')">' +
            svgIcon +
        '</button>';

    return '<div class="substitution-group" id="sg' + sGroup + '" ' +
        'style="position:relative;display:flex;align-items:center;gap:.3rem;">' +
        '<div style="flex:1;">' + groupHtml + '</div>' +
        '<div style="display:flex;align-items:center;align-self:stretch;">' + btn + '</div>' +
        '</div>';
}

function renderSubstitutions(substitutions, periodId, teamId) {
    if (!substitutions || substitutions.length === 0) {
        return '<div class="subst-empty">Brak zmian</div>';
    }

    var html      = '';
    var sGroup    = null;
    var groupHtml = '';

    substitutions.forEach(function (sub) {
        if (sub.substitution_group !== sGroup) {
            if (sGroup !== null) {
                html += _buildSubstGroupHtml(sGroup, groupHtml, periodId, teamId);
            }
            sGroup    = sub.substitution_group;
            groupHtml = renderSubstitutionElement(sub);
        } else {
            groupHtml += renderSubstitutionElement(sub);
        }
    });

    if (sGroup !== null) {
        html += _buildSubstGroupHtml(sGroup, groupHtml, periodId, teamId);
    }

    return html;
}



function _buildSubstitutionsView(data, uiMonitorContent) {
    uiMonitorContent.innerHTML = '';
    uiMonitorContent.dataset.isEventsUpdateBlocked = 'true';

    var homeTeamSubs = data.home_team_substitutions;
    var awayTeamSubs = data.away_team_substitutions;
    var reversed     = data.is_scoreboard_reversed;

    // Ciało — dwa panele drużyn
    var body = document.createElement('div');
    body.id = 'substitutions-container';
    addClassName(body, 'reversible');
    body.style.cssText = 'display:flex;flex:1;overflow:hidden;';

    var homeContainer = document.createElement('div');
    homeContainer.id = 'home-team-subst-container';
    homeContainer.dataset.reverseAnchor = '';
    homeContainer.style.cssText = 'flex:1;display:flex;flex-direction:column;border-right:1px solid #333;';

    var homeHeader = document.createElement('div');
    homeHeader.id = 'home-team-subst-container-header';
    homeHeader.className = 'subst-team-header';
    homeHeader.innerHTML =
        '<button type="button" class="subst-add-btn" ' +
            'onclick="showUiMonitorContent(\'addSubstitution\', {teamType: \'' +
            'home' + '\'})">' +
            (data.home_team_short_name || 'Gospodarz') + ' +' +
        '</button>';
    var homeBody = document.createElement('div');
    homeBody.id = 'home-team-subst-container-body';
    homeBody.className = 'subst-container-body';
    homeBody.innerHTML = renderSubstitutions(homeTeamSubs, data.period_id, data.home_team_id);


    homeContainer.appendChild(homeHeader);
    homeContainer.appendChild(homeBody);

    var awayContainer = document.createElement('div');
    awayContainer.id = 'away-team-subst-container';
    awayContainer.style.cssText = 'flex:1;display:flex;flex-direction:column;';

    var awayHeader = document.createElement('div');
    awayHeader.id = 'away-team-subst-container-header';
    awayHeader.className = 'subst-team-header';
    awayHeader.innerHTML =
        '<button type="button" class="subst-add-btn" ' +
            'onclick="showUiMonitorContent(\'addSubstitution\', {teamType: \'' +
            'away' + '\'})">' +
            (data.away_team_short_name || 'Gość') + ' +' +
        '</button>';

    var awayBody = document.createElement('div');
    awayBody.id = 'away-team-subst-container-body';
    awayBody.className = 'subst-container-body';
    awayBody.innerHTML = renderSubstitutions(awayTeamSubs, data.period_id, data.away_team_id);

    awayContainer.appendChild(awayHeader);
    awayContainer.appendChild(awayBody);

    body.appendChild(homeContainer);
    body.appendChild(awayContainer);
    uiMonitorContent.appendChild(body);
    applyReversedState(reversed);
}


// ── Blok `addSubstitution` — stan modułu ────────────────────────────────────

var _substState = {
    teamType:    null,
    teamId:      null,
    starters:    [],   // zawodnicy na boisku
    substitutes: [],   // zawodnicy na ławce
    midStarters: [],   // ze środka — wychodzący z boiska (max 5)
    midSubs:     [],   // ze środka — wchodzący z ławki (max 5)
};
var MAX_MID = 5;

function _buildAddSubstitutionView(data, uiMonitorContent) {
    uiMonitorContent.innerHTML = '';
    uiMonitorContent.dataset.isEventsUpdateBlocked = 'true';

    _substState.teamType      = data.team_type;
    _substState.teamShortName = data.team_short_name;
    _substState.teamId        = data.team_id;
    _substState.gameTimeS        = data.game_time_s;
    _substState.starters      = data.starters    || [];
    _substState.substitutes   = data.substitutes || [];
    _substState.midStarters   = [];
    _substState.midSubs       = [];

    _renderSubstEditor(uiMonitorContent);
}

function _renderSubstEditor(uiMonitorContent) {
    uiMonitorContent.innerHTML = '';

    // ── Nagłówek ─────────────────────────────────────────────────────────────
    var header = document.createElement('div');
    header.className = 'subst-editor-header';

    var titleEl = document.createElement('span');
    titleEl.className = 'subst-editor-title';
    titleEl.textContent = _substState.teamShortName;
    header.appendChild(titleEl);
    let _timeMm = Math.ceil(_substState.gameTimeS/60);
     var timerEl = document.createElement('span');
    timerEl.className = 'subst-editor-title';
    timerEl.innerHTML =
        '<label></label>' +
        '<input id="subst-time-input" type="text" placeholder="np. 45:00" ' +
            'class="subst-time-input" value="' + _timeMm + '">';
    header.appendChild(timerEl);

    var confirmBtn = document.createElement('button');
    confirmBtn.type = 'button';
    confirmBtn.className = 'subst-confirm-btn';
    confirmBtn.textContent = '✅ Zatwierdź';
    confirmBtn.onclick = _confirmSubstitution;
    header.appendChild(confirmBtn);

    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'subst-cancel-btn';
    cancelBtn.textContent = '✕ Anuluj';
    cancelBtn.onclick = function () { showUiMonitorContent('substitutions'); };
    header.appendChild(cancelBtn);

    uiMonitorContent.appendChild(header);

    // ── Trzy kolumny ─────────────────────────────────────────────────────────
    var cols = document.createElement('div');
    cols.className = 'subst-editor-cols';

    cols.appendChild(_buildSubstCol(
        'boisko',
        'BOISKO (' + _substState.starters.length + ')',
        _substState.starters,
        'starter',
        'mid-starters'
    ));
    cols.appendChild(_buildSubstMidCol());
    cols.appendChild(_buildSubstCol(
        'ławka',
        'ŁAWKA (' + _substState.substitutes.length + ')',
        _substState.substitutes,
        'substitute',
        'mid-subs'
    ));

    uiMonitorContent.appendChild(cols);
}

// Kolumna boisko / ławka
function _buildSubstCol(colKey, title, players, fromRole, targetMid) {
    var col = document.createElement('div');
    col.className = 'subst-col';
    col.dataset.col = colKey;
    col.ondragover = function (e) { e.preventDefault(); };
    col.ondrop     = function (e) { _onSubstDrop(e, fromRole); };

    var list = document.createElement('div');
    list.className = 'subst-col-body';

    players.forEach(function (p, idx) {
        list.appendChild(_buildSubstPlayerCard(p, fromRole, idx));
    });

    col.appendChild(list);
    return col;
}

// Środkowa kolumna — pary
function _buildSubstMidCol() {
    var col = document.createElement('div');
    col.className = 'subst-col subst-col--mid';
    col.ondragover = function (e) { e.preventDefault(); };
    col.ondrop     = _onSubstDropMid;

    var body = document.createElement('div');
    body.className = 'subst-col-body subst-mid-body';

    // Interleave: 1.boisko, 1.ławka, 2.boisko, 2.ławka ...
    var maxLen = Math.max(_substState.midStarters.length, _substState.midSubs.length);
    for (var i = 0; i < maxLen; i++) {
        var pairRow = document.createElement('div');
        pairRow.className = 'subst-pair-row';

        if (_substState.midStarters[i]) {
            pairRow.appendChild(_buildSubstMidCard(_substState.midStarters[i], 'midStarter', i));
        } else {
            pairRow.appendChild(_buildSubstMidPlaceholder('⬆ z boiska'));
        }
        if (_substState.midSubs[i]) {
            pairRow.appendChild(_buildSubstMidCard(_substState.midSubs[i], 'midSub', i));
        } else {
            pairRow.appendChild(_buildSubstMidPlaceholder('⬇ z ławki'));
        }

        body.appendChild(pairRow);
    }

    // Puste sloty (do MAX_MID) jako strefy drop
    for (var j = maxLen; j < MAX_MID; j++) {
        var emptyRow = document.createElement('div');
        emptyRow.className = 'subst-pair-row subst-pair-row--empty';
        emptyRow.innerHTML =
            '<div class="subst-mid-placeholder">⬆ z boiska</div>' +
            '<div class="subst-mid-placeholder">⬇ z ławki</div>';
        body.appendChild(emptyRow);
    }

    col.appendChild(body);
    return col;
}

function _buildSubstPlayerCard(player, role, idx) {
    var card = document.createElement('div');
    card.className = 'player-container subst-player-card';
    card.draggable = true;
    card.dataset.playerId  = player.player_id;
    card.dataset.playerRole = role;
    card.dataset.idx       = idx;
    card.ondragstart = function (e) { _onSubstDragStart(e, role, idx); };

    var num = player.number != null ? '#' + player.number : '';
    card.innerHTML =
        '<span style="color:#adb5bd;flex-shrink:0;">&#8291;</span>' +
        '<div style="flex:1;min-width:0;font-size:.68rem;">' +
            '<span style="font-weight:600;">' + (player.player_name || '') + '</span>' +
            (num ? '<span style="color:#6c757d;font-size:.68rem;"> ' + num + '</span>' : '') +
        '</div>' +
        '<span class="move-item-btn" style="color:#28a745;" ' +
            'onclick="_moveToMid(\'' + role + '\',' + idx + ')" title="Do środka">&#8594;</span>';
    return card;
}

function _buildSubstMidCard(player, midRole, idx) {
    var card = document.createElement('div');
    card.className = 'player-container subst-player-card subst-player-card--mid';
    card.draggable = true;
    card.ondragstart = function (e) { _onSubstDragStart(e, midRole, idx); };

    var isStarter = (midRole === 'midStarter');
    var num = player.number != null ? '#' + player.number : '';
    card.innerHTML =
        '<span style="color:#adb5bd;flex-shrink:0;">&#8291;</span>' +
        '<div style="flex:1;min-width:0;font-size:.68rem;">' +
            '<span style="font-weight:600;">' + (player.player_name || '') + '</span>' +
            (num ? '<span style="color:#6c757d;font-size:.68rem;"> ' + num + '</span>' : '') +
        '</div>' +
        '<span class="move-item-btn" style="color:#dc3545;" ' +
            'onclick="_moveFromMid(\'' + midRole + '\',' + idx + ')" title="Cofnij">&#8592;</span>';
    return card;
}

function _buildSubstMidPlaceholder(label) {
    var ph = document.createElement('div');
    ph.className = 'subst-mid-placeholder';
    ph.textContent = label;
    return ph;
}

// ── Logika przenoszenia ───────────────────────────────────────────────────────

var _substDragging = null;

function _onSubstDragStart(e, role, idx) {
    _substDragging = { role: role, idx: idx };
    e.dataTransfer.effectAllowed = 'move';
}

function _onSubstDrop(e, targetRole) {
    e.preventDefault();
    if (!_substDragging) return;
    var from = _substDragging;
    _substDragging = null;

    if (from.role === 'midStarter' && targetRole === 'starter') {
        _moveFromMid('midStarter', from.idx);
    } else if (from.role === 'midSub' && targetRole === 'substitute') {
        _moveFromMid('midSub', from.idx);
    } else if (from.role === 'starter' && targetRole === 'starter') {
        // drop na tę samą kolumnę — ignoruj
    } else if (from.role === 'substitute' && targetRole === 'substitute') {
        // drop na tę samą kolumnę — ignoruj
    } else if (from.role === 'starter') {
        _moveToMid('starter', from.idx);
    } else if (from.role === 'substitute') {
        _moveToMid('substitute', from.idx);
    }
    // midStarter→ławka i midSub→boisko — ignoruj (brak pasującego warunku)
}

function _onSubstDropMid(e) {
    e.preventDefault();
    if (!_substDragging) return;
    var from = _substDragging;
    _substDragging = null;

    if (from.role === 'starter') {
        _moveToMid('starter', from.idx);
    } else if (from.role === 'substitute') {
        _moveToMid('substitute', from.idx);
    }
    // midStarter/midSub dropped na mid — ignoruj
}

function _moveToMid(fromRole, idx) {
    if (fromRole === 'starter') {
        if (_substState.midStarters.length >= MAX_MID) return;
        var player = _substState.starters.splice(idx, 1)[0];
        _substState.midStarters.push(player);
    } else {
        if (_substState.midSubs.length >= MAX_MID) return;
        var player = _substState.substitutes.splice(idx, 1)[0];
        _substState.midSubs.push(player);
    }
    _renderSubstEditor(document.getElementById('ui-monitor-content'));
}

function _moveFromMid(midRole, idx) {
    if (midRole === 'midStarter') {
        var player = _substState.midStarters.splice(idx, 1)[0];
        _substState.starters.push(player);
    } else {
        var player = _substState.midSubs.splice(idx, 1)[0];
        _substState.substitutes.push(player);
    }
    _renderSubstEditor(document.getElementById('ui-monitor-content'));
}

// ── Czas zmiany ───────────────────────────────────────────────────────────────

function _substCurrentTimeStr() {
    // Spróbuj odczytać aktualny czas głównego timera z appState
    try {
        var ms = appState && appState.mainTimer && appState.mainTimer.elapsed_time
            ? appState.mainTimer.elapsed_time : 0;
        var totalSec = Math.floor(ms / 1000);
        var mm = Math.floor(totalSec / 60);
        var ss = totalSec % 60;
        return (mm < 10 ? '0' : '') + mm + ':' + (ss < 10 ? '0' : '') + ss;
    } catch (e) {
        return '00:00';
    }
}

function _parseTimeToMs(str) {
    var parts = (str || '').split(':');
    if (parts.length !== 2) return 0;
    var mm = parseInt(parts[0], 10) || 0;
    var ss = parseInt(parts[1], 10) || 0;
    return (mm * 60 + ss) * 1000;
}

// ── Zatwierdzenie ─────────────────────────────────────────────────────────────

function _confirmSubstitution() {
    // Zbuduj kompletne pary (min. długość obu tablic środkowych)
    var len = Math.min(_substState.midStarters.length, _substState.midSubs.length);
    if (len === 0) {
        alert('Brak kompletnych par do zmiany.');
        return;
    }

    var pairs = [];
    for (var i = 0; i < len; i++) {
        pairs.push({
            player_in_id:  _substState.midSubs[i].player_id,
            player_out_id: _substState.midStarters[i].player_id,
        });
    }

    // var timeStr      = (document.getElementById('subst-time-input') || {}).value || '00:00';
    var timeStr      = (document.getElementById('subst-time-input')).value;
    var game_time_ms = timeStr * 60000;

    socket.emit('request_ui_monitor_content', {
        type: 'confirmSubstitution',
        payload: {
            team_id:      _substState.teamId,
            game_time_ms: game_time_ms,
            pairs:        pairs,
        },
    });
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
          <button type="button" class="filter-event-button" data-is-clicked="false" onclick="filterEvents(this, 'var')">VARY</button>
          <button type="button" id="filter-hidden-button" style="background-color:${_showHiddenEvents ? '#FF8080' : 'white'};" onclick="toggleHiddenEvents(this)">UKRYTE</button>`
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
                    if (!gameEvent.is_visible) {
                        addClassName(gameEventTableRow, 'hidden-event');
                        gameEventTableRow.style.opacity = '0.4';
                        gameEventTableRow.style.textDecoration = 'line-through';
                    }
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
        <div id="current-game-event-data" class="current-selection"
            data-event-type-id="${gameEvent.event_id}"
            data-game-event-id="${gameEvent.id}"
            data-cell-id="${gameEvent.event_place}"
            data-team-id="${gameEvent.team_id}"
            data-home-team-goals="${gameEvent.home_team_goals}"
            data-away-team-goals="${gameEvent.away_team_goals}"
            data-selected-player-id="${gameEvent.player_id}">
            <span id="edit-event-current-event-type">${gameEvent.event_short_name}</span> 
            <span id="edit-event-current-team-short-name">(${gameEvent.team_short_name ?? ''})</span>
            <span id="edit-event-current-player">${gameEvent.player_number ?? ''} ${gameEvent.player_name ?? ''}</span>
        </div>
        <div id="new-game-event-data" class="new-selection"
            data-event-type-id="${gameEvent.event_id}"
            data-game-event-id="${gameEvent.id}"
            data-cell-id="${gameEvent.event_place}"
            data-team-id="${gameEvent.team_id}"
            data-home-team-goals="${gameEvent.home_team_goals}"
            data-away-team-goals="${gameEvent.away_team_goals}"
            data-selected-player-id="${gameEvent.player_id}">
            <span id="edit-event-new-event-type">${gameEvent.event_short_name ?? ''}</span>
            <span id="edit-event-new-team-short-name">(${gameEvent.team_short_name ?? ''})</span>
            <span id="edit-event-new-player">${gameEvent.player_number ?? ''} ${gameEvent.player_name ?? ''}</span>       
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
        let eventTeamSelector = document.createElement('div');
        eventTeamSelector.id = 'event-team-selector';
        eventTeamSelector.className = 'reversible';
        eventTeamSelector.style.display = 'flex';
        const _homeTeamId = data.home_team_id;
        const _awayTeamId = data.away_team_id;
        const _currentEventTeamId = gameEvent.team_id;
        const _noneDisabled = gameEvent.is_reported ? 'disabled' : '';
        eventTeamSelector.innerHTML = `
            <button type="button" style="flex: 1;" data-team-id="${_homeTeamId ?? ''}" data-reverse-anchor
                class="${_currentEventTeamId === _homeTeamId ? 'current-selection' : ''}"
                onclick="selectEventTeam(this)">${data.home_team_short_name ?? ''}</button>
            <button type="button" style="flex: 1;" data-team-id="" ${_noneDisabled}
                class="${_currentEventTeamId === null ? 'current-selection' : ''}"
                onclick="selectEventTeam(this)">BRAK</button>
            <button type="button" style="flex: 1;" data-team-id="${_awayTeamId ?? ''}"
                class="${_currentEventTeamId === _awayTeamId ? 'current-selection' : ''}"
                onclick="selectEventTeam(this)">${data.away_team_short_name ?? ''}</button>
        `;
        eventEditLeftColumn.appendChild(eventTeamSelector);
        const fieldEl = document.createElement('div');
        fieldEl.id = 'event-edit-game-field';
        fieldEl.className = 'game-field-selector';
        eventEditLeftColumn.appendChild(fieldEl);
        gameFieldGenerator(fieldEl, FIELD_COLS, FIELD_ROWS, gameEvent.event_place);
        eventEditLeftColumn.insertAdjacentHTML('beforeend', eventEditGameResultGenerator(gameEvent.home_team_goals, gameEvent.away_team_goals));
        const _visibilityBtn = gameEvent.is_visible
            ? `<button type="button" class="flex1" style="font-size:10px;font-weight:700;color:red;" ondblclick="hideGameEvent(${gameEvent.id})">UKRYJ</button>`
            : `<button type="button" class="flex1" style="font-size:10px;font-weight:700;" ondblclick="restoreGameEvent(${gameEvent.id})">WRÓĆ</button>`;
        eventEditLeftColumn.insertAdjacentHTML('beforeend', `
        <div style="display: flex;">
            ${_visibilityBtn}
            <button type="button" class="flex1" style="font-size:10px;font-weight:700;" onclick="updateGameEvent()">ZACHOWAJ</button>
            <button type="button" class="flex1" style="font-size:10px;font-weight:700;" onclick="updateGameEvent('events')">OK</button>
        </div>`);
        let eventEditRightColumn = document.createElement('div');
        eventEditRightColumn.id = 'event-edit-right-column';
        eventEditRightColumn.style.width = '260px';
        teamSelect = eventEditTeamsSquadSelectGenerator(gameEvent, teamSquad);
        uiMonitorContent.append(eventEditEventTypeRadios);
        uiMonitorContent.append(eventEditContainer);
        eventEditContainer.append(eventEditLeftColumn);
        eventEditContainer.append(eventEditRightColumn);
        eventEditRightColumn.append(teamSelect);
        applyReversedState(isScoreboardReversed);
        refreshEditResultDisplay();
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
        } else {
            newGameEventData.dataset.selectedPlayerId = 'null';
            document.getElementById('edit-event-new-player').innerHTML = '';
        }
        let eventTeamSelector = document.getElementById('event-team-selector');
        if (eventTeamSelector) {
            let noneButton = eventTeamSelector.querySelector('button[data-team-id=""]');
            if (noneButton) noneButton.disabled = !!gameEvent.is_reported;
        }
    } else if (data.content_type === 'substitutions') {
       _buildSubstitutionsView(data, uiMonitorContent);
    } else if (data.content_type === 'addSubstitution') {
       _buildAddSubstitutionView(data, uiMonitorContent);
    } else if (data.content_type === 'substitution-edit') {
       _buildSubstitutionEditView(data, uiMonitorContent);
    } else if (data.content_type === 'banners') {
        _buildBannersView(data, uiMonitorContent);
    } else if (data.content_type === 'backgrounds') {
        _buildBackgroundsView(data, uiMonitorContent);
    }
});

socket.on('substitution_error', function (data) {
       alert('Błąd zmiany: ' + data.message);
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

function _buildSubstitutionEditView(data, uiMonitorContent) {
    uiMonitorContent.innerHTML = '';
    uiMonitorContent.dataset.isEventsUpdateBlocked = 'true';
 
    var sub      = data.substitution;        // to_dict() pojedynczej zmiany
    var starters = data.starters;            // zawodnicy na boisku (ROLE_STARTER)
    var subs     = data.substitutes;         // zawodnicy na ławce (ROLE_SUBSTITUTE)
    // Dla list selectów dołączamy też aktualnych uczestników zmiany —
    // player_in był na ławce, player_out był na boisku — serwer zwraca ich
    // w osobnych listach (available_in, available_out) już z nimi włącznie.
    var availIn  = data.available_in;        // do selektu "kto wchodzi"
    var availOut = data.available_out;       // do selektu "kto wychodzi"
 
    // ── Nagłówek ──────────────────────────────────────────────────────────────
    var header = document.createElement('div');
    header.className = 'subst-editor-header';
 
    var title = document.createElement('span');
    title.className = 'subst-editor-title';
    title.textContent = 'Edycja zmiany #' + sub.id;
    header.appendChild(title);
 
    var saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'subst-confirm-btn';
    saveBtn.textContent = '💾 Zapisz';
    saveBtn.onclick = function () { _saveSubstitutionEdit(sub.id); };
    header.appendChild(saveBtn);
 
    var deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'subst-delete-btn';
    deleteBtn.textContent = '🗑 Usuń';
    deleteBtn.onclick = function () { _deleteSubstitution(sub.id); };
    header.appendChild(deleteBtn);
 
    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'subst-cancel-btn';
    cancelBtn.textContent = '✕ Anuluj';
    cancelBtn.onclick = function () { showUiMonitorContent('substitutions'); };
    header.appendChild(cancelBtn);
 
    uiMonitorContent.appendChild(header);
 
    // ── Czas zmiany ───────────────────────────────────────────────────────────
    var currentMs  = sub.game_time_ms || 0;
    var currentStr = _msToTimeStr(currentMs);
 
    var timerRow = document.createElement('div');
    timerRow.className = 'subst-timer-row';
    timerRow.innerHTML =
        '<label>Czas zmiany (mm:ss):</label>' +
        '<input id="subst-edit-time-input" type="text" ' +
            'class="subst-time-input" value="' + currentStr + '">' +
        '<span class="subst-edit-time-note">zmiana wpłynie na całą grupę (' +
            data.group_size + ' zmian)</span>';
    uiMonitorContent.appendChild(timerRow);
 
    // ── Formularz zawodników ──────────────────────────────────────────────────
    var form = document.createElement('div');
    form.className = 'subst-edit-form';
 
    // Kto wychodzi (player_out — był na boisku)
    form.appendChild(_buildSubstEditSelect(
        'subst-edit-out',
        '⬇ Schodzi z boiska',
        availOut,
        sub.player_out_id,
        'player_out_id',
        '#e57373'
    ));
 
    var arrow = document.createElement('div');
    arrow.className = 'subst-edit-arrow';
    arrow.textContent = '⇅';
    form.appendChild(arrow);
 
    // Kto wchodzi (player_in — był na ławce)
    form.appendChild(_buildSubstEditSelect(
        'subst-edit-in',
        '⬆ Wchodzi na boisko',
        availIn,
        sub.player_in_id,
        'player_in_id',
        '#4caf50'
    ));
 
    uiMonitorContent.appendChild(form);
}
 
function _buildSubstEditSelect(id, label, players, selectedPlayerId, fieldName, color) {
    var wrap = document.createElement('div');
    wrap.className = 'subst-edit-select-wrap';
 
    var lbl = document.createElement('div');
    lbl.className = 'subst-edit-select-label';
    lbl.style.color = color;
    lbl.textContent = label;
    wrap.appendChild(lbl);
 
    var select = document.createElement('select');
    select.id = id;
    select.className = 'subst-edit-select';
    select.dataset.field = fieldName;
 
    players.forEach(function (p) {
        var opt = document.createElement('option');
        opt.value = p.player_id;
        opt.textContent = (p.number != null ? '#' + p.number + ' ' : '') + (p.player_name || '');
        if (p.player_id === selectedPlayerId) opt.selected = true;
        select.appendChild(opt);
    });
 
    wrap.appendChild(select);
    return wrap;
}
 
function _msToTimeStr(ms) {
    var totalSec = Math.floor((ms || 0) / 1000);
    var mm = Math.floor(totalSec / 60);
    var ss = totalSec % 60;
    return (mm < 10 ? '0' : '') + mm + ':' + (ss < 10 ? '0' : '') + ss;
}
 
function _saveSubstitutionEdit(subId) {
    var timeStr      = (document.getElementById('subst-edit-time-input') || {}).value || '00:00';
    // var game_time_ms = _parseTimeToMs(timeStr);
    var outSel       = document.getElementById('subst-edit-out');
    var inSel        = document.getElementById('subst-edit-in');
    var player_out_id = outSel ? parseInt(outSel.value, 10) : null;
    var player_in_id  = inSel  ? parseInt(inSel.value,  10) : null;
 
    socket.emit('request_ui_monitor_content', {
        type: 'saveSubstitutionEdit',
        payload: {
            substitution_id: subId,
            game_time_ms:    game_time_ms,
            player_in_id:    player_in_id,
            player_out_id:   player_out_id,
        },
    });
}

function _saveSubstitutionEdit(subId) {
    var timeStr      = (document.getElementById('subst-edit-time-input') || {}).value || '00:00';
    // var game_time_ms = _parseTimeToMs(timeStr);
    var game_time_ms = timeStr * 1000;
    var outSel       = document.getElementById('subst-edit-out');
    var inSel        = document.getElementById('subst-edit-in');
    var player_out_id = outSel ? parseInt(outSel.value, 10) : null;
    var player_in_id  = inSel  ? parseInt(inSel.value,  10) : null;
 
    socket.emit('request_ui_monitor_content', {
        type: 'saveSubstitutionEdit',
        payload: {
            substitution_id: subId,
            game_time_ms:    game_time_ms,
            player_in_id:    player_in_id,
            player_out_id:   player_out_id,
        },
    });

}
function _saveSubstitutionEdit(subId) {
    var timeStr      = (document.getElementById('subst-edit-time-input') || {}).value || '00:00';
    // var game_time_ms = _parseTimeToMs(timeStr);
    var outSel       = document.getElementById('subst-edit-out');
    var inSel        = document.getElementById('subst-edit-in');
    var player_out_id = outSel ? parseInt(outSel.value, 10) : null;
    var player_in_id  = inSel  ? parseInt(inSel.value,  10) : null;
 
    socket.emit('request_ui_monitor_content', {
        type: 'saveSubstitutionEdit',
        payload: {
            substitution_id: subId,
            game_time_ms:    game_time_ms,
            player_in_id:    player_in_id,
            player_out_id:   player_out_id,
        },
    });
}
 
function _deleteSubstitution(subId) {
    if (!confirm('Usunąć tę zmianę? Role zawodników zostaną cofnięte.')) return;
    socket.emit('request_ui_monitor_content', {
        type: 'deleteSubstitution',
        payload: { substitution_id: subId },
    });
}


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


// =============================================================================
// ── ZAKŁADKA MECZE ───────────────────────────────────────────────────────────
// =============================================================================

// Stan zakładki MECZE — przechowywany między odświeżeniami w tej samej sesji
var _gamesTab = {
    leagueId:    null,
    maxGroupNr:  1,      // najwyższy group_nr meczów w wybranej lidze
    dateFrom:    null,
    dateTo:      null,
    activeTab:   'results',   // 'results' | 'table' | 'virtual'
    games:       [],          // lokalna kopia aktualnie wyświetlanych meczów
};

// ── Budowanie widoku MECZE ────────────────────────────────────────────────────

function _buildGamesView(data, container) {
    container.innerHTML = '';
    container.dataset.isEventsUpdateBlocked = 'true';

    // Zapamiętaj stan
    _gamesTab.leagueId = data.league_id;
    _gamesTab.dateFrom = data.date_from;
    _gamesTab.dateTo   = data.date_to;
    _gamesTab.games    = data.games ? data.games.slice() : [];

    // Zapamiętaj max_group_nr wybranej ligi
    var selectedLeague = (data.leagues || []).find(function(l) { return l.id === data.league_id; });
    _gamesTab.maxGroupNr = selectedLeague ? (selectedLeague.max_group_nr || 1) : 1;

    // ── Nagłówek: wybór ligi ──────────────────────────────────────────────
    var leagueBar = document.createElement('div');
    leagueBar.id = 'games-league-bar';
    leagueBar.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;padding:4px;background:#111;';

    data.leagues.forEach(function(league) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = league.name;
        btn.dataset.leagueId = league.id;
        btn.style.cssText = 'flex:1;min-width:80px;font-size:9px;cursor:pointer;';
        if (league.id === data.league_id) {
            btn.style.fontWeight = '700';
            btn.style.outline = '2px solid #fff';
        }
        btn.onclick = function() {
            showUiMonitorContent('games', {
                league_id: league.id,
                date_from: _gamesTab.dateFrom,
                date_to:   _gamesTab.dateTo,
            });
        };
        leagueBar.appendChild(btn);
    });
    container.appendChild(leagueBar);

    // ── Pasek filtra dat (floating, domyślnie ukryty) ────────────────────
    var dateToggleBtn = document.createElement('button');
    dateToggleBtn.id = 'games-date-toggle';
    dateToggleBtn.type = 'button';
    dateToggleBtn.textContent = '📅';
    dateToggleBtn.title = 'Filtruj daty';
    dateToggleBtn.style.cssText = 'font-size:10px;cursor:pointer;';
    dateToggleBtn.onclick = function() {
        var panel = document.getElementById('games-date-bar');
        panel.style.display = panel.style.display === 'none' ? 'flex' : 'none';
    };
    // Wstaw przycisk na końcu leagueBar
    leagueBar.appendChild(dateToggleBtn);

    var scrapeSuprescoreBtn = document.createElement('button');
    scrapeSuprescoreBtn.type = 'button';
    scrapeSuprescoreBtn.textContent = '⬇ Pobierz';
    scrapeSuprescoreBtn.title = 'Pobierz wyniki z superscore.live';
    scrapeSuprescoreBtn.style.cssText = 'font-size:10px;cursor:pointer;';
    scrapeSuprescoreBtn.onclick = function() {
        var leagueId = _gamesTab.leagueId || 1;
        scrapeSuprescoreBtn.disabled = true;
        scrapeSuprescoreBtn.textContent = '⏳';
        fetch('/leagues/' + leagueId + '/games/scrape-superscore')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.status === 'started') {
                    scrapeSuprescoreBtn.textContent = '✓';
                    setTimeout(function() {
                        scrapeSuprescoreBtn.disabled = false;
                        scrapeSuprescoreBtn.textContent = '⬇ Pobierz';
                    }, 3000);
                } else {
                    scrapeSuprescoreBtn.disabled = false;
                    scrapeSuprescoreBtn.textContent = '⬇ Pobierz';
                    alert(data.error || 'Błąd scrapowania');
                }
            })
            .catch(function(e) {
                scrapeSuprescoreBtn.disabled = false;
                scrapeSuprescoreBtn.textContent = '⬇ Pobierz';
                alert('Błąd: ' + e.message);
            });
    };
    leagueBar.appendChild(scrapeSuprescoreBtn);

    // Panel dat — floating, nie przesuwa elementów poniżej
    var dateBar = document.createElement('div');
    dateBar.id = 'games-date-bar';
    dateBar.style.cssText = [
        'display:none',
        'position:absolute',
        'top:' + (leagueBar.offsetHeight || 32) + 'px',
        'left:0',
        'right:0',
        'z-index:100',
        'align-items:center',
        'gap:6px',
        'padding:6px 8px',
        'background:#2a2a2a',
        'border-bottom:1px solid #444',
        'box-shadow:0 4px 12px rgba(0,0,0,.6)',
    ].join(';');
    dateBar.innerHTML =
        '<span style="color:#aaa;font-size:11px;white-space:nowrap;">Od:</span>' +
        '<input type="date" id="games-date-from" style="font-size:11px;padding:2px;flex:1;" value="' + (data.date_from || '') + '">' +
        '<span style="color:#aaa;font-size:11px;white-space:nowrap;">Do:</span>' +
        '<input type="date" id="games-date-to"   style="font-size:11px;padding:2px;flex:1;" value="' + (data.date_to   || '') + '">' +
        '<button type="button" id="games-date-today" style="font-size:11px;padding:2px 6px;white-space:nowrap;">Dziś</button>' +
        '<button type="button" id="games-date-apply" style="font-size:11px;padding:2px 6px;white-space:nowrap;">Filtruj</button>';

    // container musi mieć position:relative żeby absolute działał poprawnie
    container.style.position = 'relative';
    container.appendChild(dateBar);

    document.getElementById('games-date-apply').onclick = function() {
        var df = document.getElementById('games-date-from').value;
        var dt = document.getElementById('games-date-to').value || df;
        document.getElementById('games-date-bar').style.display = 'none';
        showUiMonitorContent('games', {
            league_id: _gamesTab.leagueId,
            date_from: df || null,
            date_to:   dt || null,
        });
    };
    document.getElementById('games-date-today').onclick = function() {
        var today = new Date().toISOString().slice(0, 10);
        document.getElementById('games-date-bar').style.display = 'none';
        showUiMonitorContent('games', {
            league_id: _gamesTab.leagueId,
            date_from: today,
            date_to:   today,
        });
    };

    // ── Podzakładki ───────────────────────────────────────────────────────
    var tabBar = document.createElement('div');
    tabBar.id = 'games-tab-bar';
    tabBar.style.cssText = 'display:flex;border-bottom:2px solid #444;';

    var tabs = [
        { id: 'results', label: 'Wyniki' },
        { id: 'table',   label: 'Tabela' },
        { id: 'virtual', label: 'Tabela wirtualna' },
    ];
    tabs.forEach(function(tab) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = tab.label;
        btn.dataset.tabId = tab.id;
        btn.style.cssText = 'flex:1;font-size:10px;border-top:none;border-right:none;border-left:none;border-image:initial;cursor:pointer;' +
            'background:' + (tab.id === _gamesTab.activeTab ? '#333' : '#1a1a1a') + ';' +
            'color:' + (tab.id === _gamesTab.activeTab ? '#fff' : '#aaa') + ';' +
            'border-bottom:' + (tab.id === _gamesTab.activeTab ? '2px solid #fff' : '2px solid transparent') + ';';
        btn.onclick = function() { _switchGamesTab(tab.id, data); };
        tabBar.appendChild(btn);
    });
    container.appendChild(tabBar);

    // ── Obszar treści podzakładki ─────────────────────────────────────────
    var tabContent = document.createElement('div');
    tabContent.id = 'games-tab-content';
    tabContent.style.cssText = 'overflow-y:auto;height:calc(100vh - 67px);';
    container.appendChild(tabContent);

    _switchGamesTab(_gamesTab.activeTab, data);
}

function _switchGamesTab(tabId, data) {
    _gamesTab.activeTab = tabId;

    // Podświetl aktywną zakładkę
    document.querySelectorAll('#games-tab-bar button').forEach(function(btn) {
        var active = btn.dataset.tabId === tabId;
        btn.style.background    = active ? '#333' : '#1a1a1a';
        btn.style.color         = active ? '#fff' : '#aaa';
        btn.style.borderTop     = 'none';
        btn.style.borderRight   = 'none';
        btn.style.borderLeft    = 'none';
        btn.style.borderImage   = 'initial';
        btn.style.borderBottom  = active ? '2px solid #fff' : '2px solid transparent';
    });

    var tabContent = document.getElementById('games-tab-content');
    if (!tabContent) return;
    tabContent.innerHTML = '';

    if (tabId === 'results') {
        var resultsData = Object.assign({}, data, { games: _gamesTab.games });
        _renderResultsTab(resultsData, tabContent);
    } else if (tabId === 'table' || tabId === 'virtual') {
        _renderStandingsTab(tabId, data, tabContent);
    }
}

// ── Podzakładka: Wyniki ───────────────────────────────────────────────────────

function _renderResultsTab(data, container) {
    if (!data.games || data.games.length === 0) {
        container.innerHTML = '<p style="color:#888;text-align:center;padding:1rem;">Brak meczów w wybranym dniu.</p>';
        return;
    }

    // Przycisk wysyłania do overlay
    var sendBtn = document.createElement('button');
    sendBtn.type = 'button';
    sendBtn.textContent = '▶ Wyślij do overlay';
    sendBtn.style.cssText = 'display:block;width:100%;padding:5px;font-size:12px;margin-bottom:4px;cursor:pointer;';
    sendBtn.onclick = function() { _sendResultsToOverlay(_gamesTab.games); };
    container.appendChild(sendBtn);

    var table = document.createElement('table');
    table.id = 'games-monitor-table';
    table.style.cssText = 'width:100%;border-collapse:collapse;font-size:12px;color:#ddd;';
    table.innerHTML =
        '<thead><tr style="background:#222;">' +
        '<th style="font-size:10px;">Data</th>' +
        '<th style="font-size:10px;">Mecz</th>' +
        '<th style="font-size:10px;">Wynik</th>' +
        '<th style="font-size:10px;">Status</th>' +
        '<th style="font-size:10px;"></th>' +
        '</tr></thead>';

    var tbody = document.createElement('tbody');
    tbody.id = 'games-monitor-tbody';
    data.games.forEach(function(g) { tbody.appendChild(_makeGameRow(g)); });
    table.appendChild(tbody);
    container.appendChild(table);

    // Modal zmiany statusu (osadzony w monitorze)
    container.appendChild(_buildStatusModal());
    container.appendChild(_buildScoreModal());
}

function _makeGameRow(g) {
    var tr = document.createElement('tr');
    tr.dataset.gameId = g.id;
    tr.style.borderBottom = '1px solid #333';

    var statusClass = g.status === 1 ? 'live' : g.status === 2 ? 'finished' : 'upcoming';
    var statusText  = g.status === 0 ? 'Nie rozp.' : g.status === 1 ? 'Trwa' : 'Zak.';
    var date = g.date ? g.date.replace('T', ' ').slice(0, 16) : '-';

    tr.innerHTML =
        '<td style="padding:1px 4px;color:#aaa;white-space:nowrap;">' + date + '</td>' +
        '<td style="padding:1px 4px;"><strong>' + (g.home_team_short_name || '?') + '</strong>' +
            ' – <strong>' + (g.away_team_short_name || '?') + '</strong></td>' +
        '<td style="padding:1px 4px;text-align:center;" id="games-score-' + g.id + '">' +
            (g.score_string || '-') + '</td>' +
        '<td style="padding:1px 4px;text-align:center;cursor:pointer;" ' +
            'ondblclick="_openMonitorStatusModal(' + g.id + ',' + g.status + ')">' +
            '<span class="game-status status-' + statusClass + '">' + statusText + '</span></td>' +
        '<td style="padding:1px 4px;text-align:center;">' +
            '<button type="button" style="font-size:10px;padding:1px 5px;" ' +
            'onclick="_openMonitorScoreModal(' + g.id + ',' +
                (g.home_team_goals !== null ? g.home_team_goals : 0) + ',' +
                (g.away_team_goals !== null ? g.away_team_goals : 0) + ')">✏</button>' +
        '</td>';
    return tr;
}

// ── Modal zmiany statusu (lekki, wbudowany w monitor) ────────────────────────

var _monitorCurrentGameId = null;

function _buildStatusModal() {
    var el = document.createElement('div');
    el.id = 'monitor-status-modal';
    el.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:2000;align-items:center;justify-content:center;';
    el.innerHTML =
        '<div style="background:#222;border-radius:6px;padding:1rem;min-width:220px;color:#ddd;">' +
        '<p style="margin:0 0 .75rem;font-weight:700;">Zmień status meczu</p>' +
        '<div style="display:flex;flex-direction:column;gap:.4rem;margin-bottom:.75rem;">' +
        '<label><input type="radio" name="mon-status-radio" value="0"> Nie rozpoczęty</label>' +
        '<label><input type="radio" name="mon-status-radio" value="1"> Trwa</label>' +
        '<label><input type="radio" name="mon-status-radio" value="2"> Zakończony</label>' +
        '</div>' +
        '<div style="display:flex;gap:.5rem;justify-content:flex-end;">' +
        '<button type="button" onclick="_closeMonitorStatusModal()">Anuluj</button>' +
        '<button type="button" onclick="_saveMonitorStatus()">Zapisz</button>' +
        '</div></div>';
    el.addEventListener('click', function(e) { if (e.target === el) _closeMonitorStatusModal(); });
    return el;
}

function _openMonitorStatusModal(gameId, currentStatus) {
    _monitorCurrentGameId = gameId;
    document.querySelectorAll('input[name="mon-status-radio"]').forEach(function(r) {
        r.checked = parseInt(r.value) === currentStatus;
    });
    document.getElementById('monitor-status-modal').style.display = 'flex';
}

function _closeMonitorStatusModal() {
    var m = document.getElementById('monitor-status-modal');
    if (m) m.style.display = 'none';
    _monitorCurrentGameId = null;
}

function _saveMonitorStatus() {
    var selected = document.querySelector('input[name="mon-status-radio"]:checked');
    if (!selected || _monitorCurrentGameId === null) return;

    fetch('/api/games/' + _monitorCurrentGameId + '/status', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: parseInt(selected.value) }),
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
        if (d.error) { alert('Błąd: ' + d.error); return; }
        var gameId = _monitorCurrentGameId || d.id;
        _closeMonitorStatusModal();
        _refreshMonitorGame(gameId);
    })
    .catch(function() { alert('Błąd połączenia'); });
}

// ── Modal edycji wyniku ───────────────────────────────────────────────────────

function _buildScoreModal() {
    var el = document.createElement('div');
    el.id = 'monitor-score-modal';
    el.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:2000;align-items:center;justify-content:center;';
    el.innerHTML =
        '<div style="background:#222;border-radius:6px;padding:1rem;min-width:200px;color:#ddd;">' +
        '<p style="margin:0 0 .75rem;font-weight:700;">Zmień wynik</p>' +
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:.75rem;">' +
        '<input type="number" id="mon-score-home" min="0" style="width:48px;font-size:1.2rem;text-align:center;">' +
        '<span style="font-size:1.2rem;">:</span>' +
        '<input type="number" id="mon-score-away" min="0" style="width:48px;font-size:1.2rem;text-align:center;">' +
        '</div>' +
        '<div style="display:flex;gap:.5rem;justify-content:flex-end;">' +
        '<button type="button" onclick="_closeMonitorScoreModal()">Anuluj</button>' +
        '<button type="button" onclick="_saveMonitorScore()">Zapisz</button>' +
        '</div></div>';
    el.addEventListener('click', function(e) { if (e.target === el) _closeMonitorScoreModal(); });
    return el;
}

function _openMonitorScoreModal(gameId, homeGoals, awayGoals) {
    _monitorCurrentGameId = gameId;
    document.getElementById('mon-score-home').value = homeGoals;
    document.getElementById('mon-score-away').value = awayGoals;
    document.getElementById('monitor-score-modal').style.display = 'flex';
}

function _closeMonitorScoreModal() {
    var m = document.getElementById('monitor-score-modal');
    if (m) m.style.display = 'none';
    _monitorCurrentGameId = null;
}

function _saveMonitorScore() {
    if (_monitorCurrentGameId === null) return;
    var home = parseInt(document.getElementById('mon-score-home').value);
    var away = parseInt(document.getElementById('mon-score-away').value);
    if (isNaN(home) || isNaN(away)) return;

    fetch('/api/games/' + _monitorCurrentGameId + '/score', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ home_team_goals: home, away_team_goals: away }),
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
        if (d.error) { alert('Błąd: ' + d.error); return; }
        var gameId = _monitorCurrentGameId;
        _closeMonitorScoreModal();
        _refreshMonitorGame(gameId);
    })
    .catch(function() { alert('Błąd połączenia'); });
}

function _refreshMonitorGame(gameId) {
    fetch('/api/games/' + gameId)
    .then(function(r) { return r.json(); })
    .then(function(g) {
        // Zaktualizuj lokalną kopię
        var idx = _gamesTab.games.findIndex(function(x) { return x.id === gameId; });
        if (idx !== -1) _gamesTab.games[idx] = g;

        // Zaktualizuj wiersz w tabeli
        var tr = document.querySelector('#games-monitor-tbody tr[data-game-id="' + gameId + '"]');
        if (tr) tr.replaceWith(_makeGameRow(g));
    });
}

// ── Podzakładki: Tabela / Tabela wirtualna ────────────────────────────────────

function _renderStandingsTab(tabId, data, container) {
    var virtual = (tabId === 'virtual');
    var leagueId = data.league_id;
    if (!leagueId) {
        container.innerHTML = '<p style="color:#888;padding:1rem;text-align:center;">Brak wybranej ligi.</p>';
        return;
    }

    container.innerHTML = '<p style="color:#888;padding:1rem;text-align:center;">Wczytuję tabelę...</p>';

    var groupNr = _gamesTab.maxGroupNr || 1;
    console.log('[standings] leagueId=' + leagueId + ' group_nr=' + groupNr + ' virtual=' + virtual);
    fetch('/api/leagues/' + leagueId + '/standings?group_nr=' + groupNr)
    .then(function(r) { return r.json(); })
    .then(function(d) {
        console.log('[standings] response:', d);
        container.innerHTML = '';

        // Przycisk wysyłania do overlay (obsługa w przyszłości)
        var sendBtn = document.createElement('button');
        sendBtn.type = 'button';
        sendBtn.textContent = '▶ Wyślij do overlay';
        sendBtn.style.cssText = 'display:block;width:100%;padding:5px;font-size:12px;margin-bottom:4px;cursor:pointer;';
        sendBtn.dataset.tabId = tabId;
        sendBtn.onclick = (function(capturedTabId, capturedD) {
            return function() { _sendStandingsToOverlay(capturedTabId, capturedD); };
        })(tabId, d);
        container.appendChild(sendBtn);

        var rows = virtual ? d.virtual : d.official;
        if (!rows || rows.length === 0) {
            var msg = virtual
                ? 'Brak meczów zakończonych lub trwających w tej lidze.'
                : 'Brak zakończonych meczów w tej lidze.';
            container.innerHTML += '<p style="color:#888;padding:1rem;text-align:center;">' + msg + '</p>';
            return;
        }

        var table = document.createElement('table');
        table.style.cssText = 'width:100%;border-collapse:collapse;font-size:11px;color:#ddd;';

        var thead = document.createElement('thead');
        thead.innerHTML =
            '<tr style="background:#222;text-align:center;">' +
            '<th style="padding:3px 2px;">#</th>' +
            '<th style="padding:3px 2px;text-align:left;">Drużyna</th>' +
            '<th title="Mecze" style="padding:3px 2px;">M</th>' +
            '<th title="Wygrane" style="padding:3px 2px;">W</th>' +
            '<th title="Remisy" style="padding:3px 2px;">R</th>' +
            '<th title="Porażki" style="padding:3px 2px;">P</th>' +
            '<th title="Bramki zdobyte" style="padding:3px 2px;">GZ</th>' +
            '<th title="Bramki stracone" style="padding:3px 2px;">GS</th>' +
            '<th title="Bilans bramek" style="padding:3px 2px;">BR</th>' +
            '<th title="Punkty" style="padding:3px 2px;">Pkt</th>' +
            '</tr>';
        table.appendChild(thead);

        var tbody = document.createElement('tbody');
        rows.forEach(function(row, idx) {
            var tr = document.createElement('tr');
            tr.style.borderBottom = '1px solid #2a2a2a';
            var br = row.goal_difference > 0 ? '+' + row.goal_difference : row.goal_difference;
            tr.innerHTML =
                '<td style="padding:3px 2px;text-align:center;color:#aaa;">' + (idx + 1) + '</td>' +
                '<td style="padding:3px 4px;">' + (row.team_short_name || row.team_name) + '</td>' +
                '<td style="padding:3px 2px;text-align:center;">' + row.games + '</td>' +
                '<td style="padding:3px 2px;text-align:center;">' + row.wins + '</td>' +
                '<td style="padding:3px 2px;text-align:center;">' + row.draws + '</td>' +
                '<td style="padding:3px 2px;text-align:center;">' + row.loses + '</td>' +
                '<td style="padding:3px 2px;text-align:center;">' + row.goals_scored + '</td>' +
                '<td style="padding:3px 2px;text-align:center;">' + row.goals_lost + '</td>' +
                '<td style="padding:3px 2px;text-align:center;">' + br + '</td>' +
                '<td style="padding:3px 2px;text-align:center;font-weight:700;">' + row.points + '</td>';
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        container.appendChild(table);

        if (virtual && d.has_live) {
            var note = document.createElement('p');
            note.style.cssText = 'color:#f0ad4e;font-size:10px;padding:4px 6px;margin:0;';
            note.textContent = '⚡ Tabela uwzględnia wyniki aktualnie trwających meczów.';
            container.appendChild(note);
        }
    })
    .catch(function() {
        container.innerHTML = '<p style="color:#e74c3c;padding:1rem;text-align:center;">Błąd pobierania tabeli.</p>';
    });
}

// ── BANERY ────────────────────────────────────────────────────────────────────

function _buildBannersView(data, uiMonitorContent) {
    uiMonitorContent.innerHTML = '';
    uiMonitorContent.dataset.isEventsUpdateBlocked = 'true';

    var previewContainer = document.createElement('div');
    previewContainer.id = 'banner-preview-container';
    previewContainer.style.cssText = 'width:100%; height:30vh; background:#111; overflow:hidden; display:flex; align-items:center; justify-content:center; border-bottom:1px solid #333;';
    previewContainer.innerHTML = '<span style="color:#555; font-size:11px;">PODGLĄD</span>';

    var listContainer = document.createElement('div');
    listContainer.id = 'banners-list-container';
    listContainer.style.cssText = 'height:62vh; overflow-y:auto;';

    var banners = data.banners || [];
    if (banners.length === 0) {
        listContainer.innerHTML = '<p style="color:#666; padding:1rem; text-align:center;">Brak banerów</p>';
    } else {
        banners.forEach(function(banner) {
            var row = document.createElement('div');
            row.style.cssText = 'display:flex; align-items:center; padding:4px 6px; border-bottom:1px solid #222; gap:4px;';

            var nameSpan = document.createElement('span');
            nameSpan.textContent = banner.name;
            nameSpan.style.cssText = 'flex:1; color:#ccc; font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;';

            var previewBtn = document.createElement('button');
            previewBtn.type = 'button';
            previewBtn.className = 'event-btn';
            previewBtn.textContent = 'P';
            previewBtn.style.cssText = 'background:#333; color:#ccc; font-size:10px;';
            previewBtn.addEventListener('click', (function(b) { return function() {
                var preview = document.getElementById('banner-preview-container');
                if (preview) { preview.innerHTML = b.source; }
            }; })(banner));

            var sendBtn = document.createElement('button');
            sendBtn.type = 'button';
            sendBtn.className = 'event-btn';
            sendBtn.textContent = 'W';
            sendBtn.style.cssText = 'background:green; color:white; font-size:10px;';
            sendBtn.addEventListener('click', (function(b) { return function() {
                socket.emit('send_banner_to_overlay', { banner_id: b.id });
            }; })(banner));

            var editBtn = document.createElement('button');
            editBtn.type = 'button';
            editBtn.className = 'event-btn';
            editBtn.textContent = '✏';
            editBtn.style.cssText = 'background:#555; color:#fff; font-size:10px;';
            editBtn.addEventListener('click', (function(b) { return function() {
                showUiMonitorContent('edit_banner', { banner_id: b.id });
            }; })(banner));

            row.appendChild(nameSpan);
            row.appendChild(previewBtn);
            row.appendChild(sendBtn);
            row.appendChild(editBtn);
            listContainer.appendChild(row);
        });
    }

    uiMonitorContent.appendChild(previewContainer);
    uiMonitorContent.appendChild(listContainer);
}

// ── TŁA ───────────────────────────────────────────────────────────────────────

function _buildBackgroundsView(data, uiMonitorContent) {
    uiMonitorContent.innerHTML = '';
    uiMonitorContent.dataset.isEventsUpdateBlocked = 'true';

    var PREVIEW_H = 80;
    var PREVIEW_W = Math.round(PREVIEW_H * 16 / 9);

    // Dwa okna podglądu (16:9, 80px high)
    var previews = document.createElement('div');
    previews.style.cssText = 'display:flex; gap:8px; padding:8px; background:#111; border-bottom:1px solid #333;';

    function makePreviewBox(label) {
        var wrap = document.createElement('div');
        wrap.style.cssText = 'display:flex; flex-direction:column; align-items:center; gap:3px;';
        var lbl = document.createElement('span');
        lbl.textContent = label;
        lbl.style.cssText = 'color:#666; font-size:9px; text-transform:uppercase;';
        var box = document.createElement('div');
        box.style.cssText = `width:${PREVIEW_W}px; height:${PREVIEW_H}px; background:#1a1a1a; border:1px solid #333; overflow:hidden; display:flex; align-items:center; justify-content:center;`;
        var img = document.createElement('img');
        img.style.cssText = 'width:100%; height:100%; object-fit:cover; display:none;';
        box.appendChild(img);
        wrap.appendChild(lbl);
        wrap.appendChild(box);
        return { wrap, img };
    }

    var left  = makePreviewBox('AKTUALNE');
    var right = makePreviewBox('WYBRANE');
    previews.appendChild(left.wrap);
    previews.appendChild(right.wrap);

    var active = data.active_background;
    if (active && active.static_url) {
        left.img.src = active.static_url;
        left.img.style.display = 'block';
    }

    // Lista
    var listContainer = document.createElement('div');
    listContainer.style.cssText = 'height:calc(100vh - ' + (PREVIEW_H + 60) + 'px); overflow-y:auto;';

    var backgrounds = (data.backgrounds || []).filter(function(b) { return b.is_visible; });
    if (backgrounds.length === 0) {
        listContainer.innerHTML = '<p style="color:#666; padding:1rem; text-align:center;">Brak teł</p>';
    } else {
        backgrounds.forEach(function(bg) {
            var row = document.createElement('div');
            row.style.cssText = 'display:flex; align-items:center; padding:4px 6px; border-bottom:1px solid #222; gap:6px; cursor:pointer;';
            if (active && bg.id === active.id) {
                row.style.background = '#1a2a1a';
            }

            var thumb = document.createElement('img');
            thumb.src = bg.static_url || '';
            thumb.style.cssText = `width:${Math.round(18 * 16 / 9)}px; height:18px; object-fit:cover; flex-shrink:0; border:1px solid #333;`;

            var nameSpan = document.createElement('span');
            nameSpan.textContent = bg.name;
            nameSpan.style.cssText = 'flex:1; color:#ccc; font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;';
            if (bg.description) {
                row.title = bg.description;
            }

            var sendBtn = document.createElement('button');
            sendBtn.type = 'button';
            sendBtn.className = 'event-btn';
            sendBtn.textContent = 'W';
            sendBtn.style.cssText = 'background:green; color:white; font-size:10px; flex-shrink:0;';
            sendBtn.addEventListener('click', (function(b) { return function(e) {
                e.stopPropagation();
                socket.emit('send_background_to_obs', { background_image_id: b.id });
                left.img.src = b.static_url;
                left.img.style.display = 'block';
            }; })(bg));

            row.addEventListener('click', (function(b) { return function() {
                right.img.src = b.static_url;
                right.img.style.display = 'block';
            }; })(bg));

            row.appendChild(thumb);
            row.appendChild(nameSpan);
            row.appendChild(sendBtn);
            listContainer.appendChild(row);
        });
    }

    uiMonitorContent.appendChild(previews);
    uiMonitorContent.appendChild(listContainer);
}

// ── Podłączenie do socket.on('show_ui_monitor_content') ──────────────────────
// Obsługa 'games' dodana przez rozszerzenie istniejącego handlera poniżej.
// Wywołanie _buildGamesView jest wstrzykiwane przez patch na końcu pliku:

var _origSocketHandler = null;
(function() {
    // Patch: jeśli handler już istnieje, dodajemy gałąź 'games' bez modyfikacji źródła
    // Obsługa przez globalny listener — patrz socket.on('show_ui_monitor_content') powyżej
    // Rozszerzona gałąź jest dołączana przez kolejny socket.on (socket.io akumuluje listenery)
})();

socket.on('show_ui_monitor_content', function(data) {
    if (data.content_type !== 'games') return;  // pozostałe typy obsługuje główny handler
    var uiMonitorContent = document.getElementById('ui-monitor-content');
    _buildGamesView(data, uiMonitorContent);
});

socket.on('scraping_completed', function() {
    var uiMonitorContent = document.getElementById('ui-monitor-content');
    if (!uiMonitorContent) return;
    // Odśwież widok MECZE jeśli jest aktualnie otwarty
    var leagueBar = document.getElementById('games-league-bar');
    if (!leagueBar) return;
    showUiMonitorContent('games', {
        league_id: _gamesTab.leagueId,
        date_from:  _gamesTab.dateFrom,
        date_to:    _gamesTab.dateTo,
    });
});

// =============================================================================
// ── STEROWANIE POWTÓRKĄ ──────────────────────────────────────────────────────
// =============================================================================
 
function replayControl(type, extra) {
    var data = Object.assign({ type: type }, extra || {});
    socket.emit('replay_control', data);
}

socket.on('replay_started', (data) => {
    console.log('replay_started');
    replayResumeElement.style.display = 'none';
    replayPauseElement.style.display = 'flex';
});

socket.on('replay_state_changed', function(data) {
    // Wysyłane przez ControllerManager przy każdej zmianie stanu lub prędkości.
    // status: 'idle' | 'playing' | 'paused'
    // speed:  float w zakresie [0.3, 0.9]
    if (!data) return;

    if (data.status === 'playing') {
        if (typeof replayResumeElement !== 'undefined' && replayResumeElement) {
            replayResumeElement.style.display = 'none';
        }
        if (typeof replayPauseElement !== 'undefined' && replayPauseElement) {
            replayPauseElement.style.display = 'flex';
        }
    } else if (data.status === 'paused') {
        if (typeof replayResumeElement !== 'undefined' && replayResumeElement) {
            replayResumeElement.style.display = 'flex';
        }
        if (typeof replayPauseElement !== 'undefined' && replayPauseElement) {
            replayPauseElement.style.display = 'none';
        }
    } else {
        // idle — powtórka skończona
        if (typeof replayResumeElement !== 'undefined' && replayResumeElement) {
            replayResumeElement.style.display = 'none';
        }
        if (typeof replayPauseElement !== 'undefined' && replayPauseElement) {
            replayPauseElement.style.display = 'none';
        }
    }

    // Synchronizacja wskaźnika/suwaka prędkości (jeśli istnieje w UI).
    // Nazwa elementu jest sugestią — dostosuj do faktycznej nazwy w uj-jinja.html.
    
    // var speedEl = document.getElementById('replay-speed');
    // if (speedEl && typeof data.speed === 'number') {
    //     if (speedEl.tagName === 'INPUT') {
    //         speedEl.value = data.speed;
    //     } else {
    //         speedEl.textContent = data.speed.toFixed(2);
    //     }
    // }
});

socket.on('replay_done', (data) => {
    console.log('replay_done');
    replayResumeElement.style.display = 'none';
    replayPauseElement.style.display = 'none';
});

function replayPause(){
    replayPauseElement.style.display = 'none';
    replayResumeElement.style.display = 'flex';
    replayControl('pause');
}

function replayResume(){
    replayResumeElement.style.display = 'none';
    replayPauseElement.style.display = 'flex';
    replayControl('resume');
}
function replayStop(){ replayControl('stop'); }
function replayFrameFwd(){ replayControl('frame_fwd'); }
function replayFrameBack(){ replayControl('frame_back'); }
function replayCancelTimer(){ replayControl('cancel_timer'); }
function replayEnd(){
    replayControl('end');
}
function replaySpeed(speed){ replayControl('speed', { speed: parseFloat(speed) }); }
 
// =============================================================================

function _sendToOverlay(type, payloadObj) {
    socket.emit('send_to_overlay', { type: type, payload: payloadObj });
}

function _sendResultsToOverlay(games) {
    // Wysyła wszystkie mecze — filtrowanie niekompletnych wyników następuje w overlay
    var mapped = games.map(function(g) {
        return {
            home_team_name14: g.home_team_name_14 || g.home_team_name || '',
            home_team_goals:  g.home_team_goals,
            away_team_goals:  g.away_team_goals,
            away_team_name14: g.away_team_name_14 || g.away_team_name || '',
            status:           g.status,
        };
    });
    _sendToOverlay('results', { games: mapped });
}

function _mapStandingsRow(row) {
    return {
        team_name14:     row.team_name_14 || row.team_name || '',
        team_name:       row.team_name       || '',
        team_short_name: row.team_short_name || '',
        points:          row.points,
        goal_difference: row.goal_difference,
        games:           row.games,
        wins:            row.wins,
        draws:           row.draws,
        loses:           row.loses,
        goals_scored:    row.goals_scored,
        goals_lost:      row.goals_lost,
    };
}

function _sendStandingsToOverlay(tabId, d) {
    if (tabId === 'table') {
        var rows = (d.official || []).map(_mapStandingsRow);
        _sendToOverlay('table', { rows: rows });
    } else if (tabId === 'virtual') {
        var official = (d.official || []).map(_mapStandingsRow);
        var virtual  = (d.virtual  || []).map(_mapStandingsRow);
        _sendToOverlay('virtual_table', { official: official, virtual: virtual });
    }
}
