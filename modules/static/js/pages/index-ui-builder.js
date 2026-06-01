function _buildStartButton(timerId) {
    const periodStatus = window.period ? window.period.status : null;
    const canStart = (typeof PERIOD_CAN_START !== 'undefined') && PERIOD_CAN_START;

    if (periodStatus === 0) {
        // NOT_STARTED: aktywny lub zablokowany w zależności od kolejności periodów
        if (canStart) {
            return `<button class="timer-main-controller"
                    data-timer-id="${timerId}"
                    data-timer-state="idle"
                    onclick="onStartPeriodClick('${timerId}');">START</button>`;
        } else {
            return `<button class="timer-main-controller"
                    data-timer-id="${timerId}"
                    data-timer-state="idle"
                    disabled>START</button>`;
        }
    }
    // PENDING / FINISHED / brak periodu — standardowy startTimer
    return `<button class="timer-main-controller"
                    data-timer-id="${timerId}"
                    data-timer-state="idle"
                    onclick="startTimer('${timerId}');">START</button>`;
}

function _buildTopBar() {
    return `
<div class="top-bar">
    <button id="nav-to-game-settings" class="top-bar-element wingdings"
            onclick="toggleLeftFrame()">Û</button>
</div>`;
}

function _buildTimersContainer(timerId, { withPenalties, withAddedTime } = {}) {
    const penaltiesHtml = withPenalties ? `
            <button class="thin-wide-button bg_red"
                onclick="openModal('modal-penalties-timers')">KARY</button>
            <div id="modal-penalties-timers" class="hidden">
                <div id="modal-penalties-header">
                    <button class="top-bar-element bg_red"
                        onclick="closeModal('modal-penalties-timers');">X</button>
                </div>
                <div id="penalties-timers" class="modal-content reversible">
                    <div id="home-team-penalties-timers-container" data-reverse-anchor
                        class="penalties-timers-container flex1"></div>
                    <div id="away-team-penalties-timers-container"
                        class="penalties-timers-container flex1"></div>
                </div>
            </div>` : '';

    const addedTimeHtml = withAddedTime ? `
            <div id="added-time" style="display: flex; font-size: 10px; color: white">
                <span style="width: 55%; text-align:right; padding-right: 5px;">Doliczony czas: </span>
                <input id="added-time-input" type="number" min="0" style="width: 25%">
                <input type="button" style="width: 20%" value="OK" onclick="onAddedTimeOkClick()">
            </div>` : '';

    return `
<div id="timers-container" class="module-frame">
    <div id="${timerId}-header" class="main-timer-header"
        data-state-for="${timerId}">${timerId}</div>
    <div class="timer-content">
        <div class="main-timer-display-container">
            <button onclick="adjustTimer('${timerId}', -60000);" class="timer-button"
                data-timer-id="${timerId}"></button>
            <button onclick="adjustTimer('${timerId}', -1000);" class="timer-button"
                data-timer-id="${timerId}"></button>
            <button onclick="adjustTimer('${timerId}', -100);"
                class="timer-button ds-element ds-${timerId}-element"
                data-timer-id="${timerId}"></button>
            <div id="${timerId}-min-display" class="timer-display"
                data-display-for="${timerId}-min-display">00</div>
            <div id="${timerId}-sec-display" class="timer-display"
                data-display-for="${timerId}-sec-display">00</div>
            <div id="${timerId}-ds-display"
                class="timer-display ds-element ds-${timerId}-element"
                data-display-for="${timerId}-ds-display">0</div>
            <button onclick="adjustTimer('${timerId}', 60000);" class="timer-button"
                data-timer-id="${timerId}"></button>
            <button onclick="adjustTimer('${timerId}', 1000);" class="timer-button"
                data-timer-id="${timerId}"></button>
            <button onclick="adjustTimer('${timerId}', 100);"
                class="timer-button ds-element ds-${timerId}-element"
                data-timer-id="${timerId}"></button>
        </div>
        <div class="timer-controllers-container">
            <div class="timer-small-controllers">
                <button id="btn-reset-period"
                    ondblclick="onResetPeriodDblClick('${timerId}');">0</button>
                <button></button>
                <button id="btn-finish-period"
                    ondblclick="onFinishPeriodDblClick();">X</button>
            </div>
            <div class="timer-main-controllers">
                ${_buildStartButton(timerId)}
                <button class="timer-main-controller nodisplayed"
                    data-timer-id="${timerId}"
                    data-timer-state="running"
                    onclick="pauseTimer('${timerId}');">PAUZA</button>
                <button class="timer-main-controller nodisplayed"
                    data-timer-id="${timerId}"
                    data-timer-state="paused"
                    onclick="resumeTimer('${timerId}');">WZNÓW</button>
            </div>
        </div>
    </div>${penaltiesHtml}${addedTimeHtml}
</div>`;
}

function _buildGameTeamsContainer() {
    const value2Home = (window.period && window.period.home_team_value2) || 0;
    const value2Away = (window.period && window.period.away_team_value2) || 0;
    const goalsHome  = (window.game   && window.game.home_team_goals)   || 0;
    const goalsAway  = (window.game   && window.game.away_team_goals)   || 0;
    const nameHome   = window.teamHomeShortName || '';
    const nameAway   = window.teamAwayShortName || '';

    return `
<div id="game-teams-container" class="module-frame">
    <div id="game-teams-content">
        <div class="reversible scoreboard">
            <button class="flex-item flex1" id="addValue2Home"
                onclick="changeGameValue('value2', 'home', 1)" data-reverse-anchor>+</button>
            <button class="flex-item flex1" id="addScoreHome"
                onclick="changeGameValue('score', 'home', 1)">+</button>
            <button class="flex-item flex1" id="addScoreAway"
                onclick="changeGameValue('score', 'away', 1)">+</button>
            <button class="flex-item flex1" id="addValue2Away"
                onclick="changeGameValue('value2', 'away', 1)">+</button>
        </div>
        <div class="reversible scoreboard">
            <label class="flex-item flex1 fouls-label" id="labelValue2Home" data-reverse-anchor>
                <span id="value2Home">${value2Home}</span>
            </label>
            <label class="flex-item flex1 goals-label" id="labelScoreHome">
                <span id="scoreHome">${goalsHome}</span>
            </label>
            <label class="flex-item flex1 goals-label" id="labelScoreAway">
                <span id="scoreAway">${goalsAway}</span>
            </label>
            <label class="flex-item flex1 fouls-label" id="labelValue2Away">
                <span id="value2Away">${value2Away}</span>
            </label>
        </div>
        <div class="reversible scoreboard">
            <button class="flex-item flex1" id="substractValue2Home"
                onclick="changeGameValue('value2', 'home', -1)" data-reverse-anchor>-</button>
            <button class="flex-item flex1" id="substractScoreHome"
                onclick="changeGameValue('score', 'home', -1)">-</button>
            <button class="flex-item flex1" id="substractScoreAway"
                onclick="changeGameValue('score', 'away', -1)">-</button>
            <button class="flex-item flex1" id="substractValue2Away"
                onclick="changeGameValue('value2', 'away', -1)">-</button>
        </div>
        <div class="reversible">
            <div class="flex-item flex3 data-item data-home"
                id="teamHomeName" data-reverse-anchor>${nameHome}</div>
            <div class="flex-item flex2">
                <button id="reverse-scoreboard-button"
                    onclick="onReverseButtonClick()"><=></button>
            </div>
            <div class="flex-item flex3 data-item data-away"
                id="teamAwayName">${nameAway}</div>
        </div>
        <div class="reversible cards-container">
            <div class="cards flex3" data-reverse-anchor data-reverse-anchor>
                <button class="flex-item flex1 card yellowCard" id="yellowCardHome"
                    onclick="addTeamEvent('home', 'Żółta Kartka');"> </button>
                <button class="flex-item flex1 card redCard" id="redCardHome"
                    onclick="addTeamEvent('home', 'Czerwona Kartka');"> </button>
            </div>
            <div class="flex-item flex2 cards-middle-element"></div>
            <div class="cards flex3">
                <button class="flex-item flex1 card yellowCard" id="yellowCardAway"
                    onclick="addTeamEvent('away', 'Żółta Kartka');"> </button>
                <button class="flex-item flex1 card redCard" id="redCardAway"
                    onclick="addTeamEvent('away', 'Czerwona Kartka');"> </button>
            </div>
        </div>
    </div>
</div>`;
}

function _buildStreamControllers() {
    return `
<div id="stream-controllers">
    <div style="display:flex; width:100%;">
        <div id="stream-icon" style="width:20%;" ondblclick="onStreamIconDblClick()"></div>
        <div id="record-icon" style="width:20%;" ondblclick="onRecordIconDblClick()"></div>
        <div id="cameras-icons" style="width:20%; display:flex; flex-wrap:wrap;">
            <div id="camera1-icon" style="width:50%;"></div>
            <div id="camera2-icon" style="width:50%;"></div>
            <div id="camera3-icon" style="width:50%;"></div>
            <div id="camera4-icon" style="width:50%;"></div>
        </div>
        <div id="microphone-icon" style="width:20%;" ondblclick="onMicrophoneIconDblClick()"></div>
        <div id="stream-overlay-plugin-icon" style="width:20%;" ondblclick="onStreamOverlayIconDblClick()"></div>
    </div>
    <div style="display:flex; width:100%;">
        <div id="timer-plugin-icon" style="width:12.5%;"></div>
        <div id="recorder-plugin-icon" style="width:12.5%;"></div>
        <div id="obs-ws-plugin-icon" style="width:12.5%;"></div>
        <div id="replay-plugin-icon" style="width:12.5%;"></div>
        <div id="controller-plugin-icon" style="width:12.5%;"></div>
    </div>
</div>`;
}

function renderIndexUI(moduleName) {
    const columnControls = document.getElementById('column-controls');
    const timerId = (window.main_timer && window.main_timer.timer_id) || 'main-timer';

    let html = _buildTopBar();

    switch (moduleName) {
        case 'futsal_nalf':
            html += _buildTimersContainer(timerId, { withPenalties: true });
            html += _buildGameTeamsContainer();
            break;
        case 'garbarnia':
            html += _buildTimersContainer(timerId, { withAddedTime: true });
            html += _buildGameTeamsContainer();
            break;
        default:
            html += _buildTimersContainer(timerId, { withPenalties: false });
            html += _buildGameTeamsContainer();
    }

    html += _buildStreamControllers();
    columnControls.innerHTML = html;

    const addedTimeInput = document.getElementById('added-time-input');
    if (addedTimeInput) {
        addedTimeInput.value = (window.period && window.period.added_time) || 0;
    }
}

function onAddedTimeOkClick() {
    if (!window.period || !window.period.id) return;
    const input = document.getElementById('added-time-input');
    const value = parseInt(input.value, 10);
    if (isNaN(value) || value < 0) return;

    fetch(`/api/periods/${window.period.id}/added-time`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ added_time: value }),
    }).then(r => r.json()).then(data => {
        if (data.ok) {
            window.period.added_time = value;
        }
    });
}
