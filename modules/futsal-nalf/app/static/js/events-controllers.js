// ── Konfiguracja siatki boiska ────────────────────────────────────────────────
const _FIELD_COLS = 15;  // kolumny: A–O
const _FIELD_ROWS = 9;   // wiersze: 1–9

// ── Stan ──────────────────────────────────────────────────────────────────────
var selectedCellID = null;
var allGameFieldCells = null;  // inicjowane po wygenerowaniu DOM
var hiddedEventsControllersContainer = document.getElementById('hidded-events-controllers-container');

// ── Generowanie siatki #game-field ───────────────────────────────────────────

/**
 * Generuje komórki siatki boiska w kontenerze #game-field.
 * Każda komórka: onclick=setCameraPosition, ondblclick=selectGameFieldCell.
 * @param {number} cols - liczba kolumn
 * @param {number} rows - liczba wierszy
 */
function gameFieldGenerator(cols = _FIELD_COLS, rows = _FIELD_ROWS) {
    const container = document.getElementById('game-field');
    if (!container) return;

    container.innerHTML = '';

    for (let row = 1; row <= rows; row++) {
        const rowEl = document.createElement('div');
        rowEl.className = 'game-field-row';
        rowEl.style.display = 'flex';

        for (let col = 0; col < cols; col++) {
            const letter = String.fromCharCode(65 + col);  // A, B, C, …, O
            const cellId = letter + row;

            const cell = document.createElement('div');
            cell.id = cellId;
            cell.className = 'game-field-cell';
            cell.ondblclick = function () { selectGameFieldCell(this); };
            cell.onclick    = function () { setCameraPosition(this); };

            rowEl.appendChild(cell);
        }
        container.appendChild(rowEl);
    }

    // Odśwież referencje po wygenerowaniu komórek
    allGameFieldCells = document.querySelectorAll('.game-field-cell');
    attachGameFieldHoverListeners();
}

// ── Hover ─────────────────────────────────────────────────────────────────────
function attachGameFieldHoverListeners() {
    allGameFieldCells.forEach(cell => {
        cell.addEventListener('mouseover', () => {
            cell.style.backgroundColor = 'rgba(0, 0, 0, 0.1)';
        });
        cell.addEventListener('mouseout', () => {
            cell.style.backgroundColor = 'rgba(0, 0, 0, 0)';
        });
    });
}

// ── Zaznaczanie komórek ───────────────────────────────────────────────────────
function showEventsControllers() {
    removeClassName(hiddedEventsControllersContainer, 'hidden');
}

function hideEventsControllers() {
    addClassName(hiddedEventsControllersContainer, 'hidden');
}

function unselectAllGameFieldCells() {
    allGameFieldCells.forEach(cell => {
        removeClassName(cell, 'selected-game-field-cell');
    });
    selectedCellID = null;
    hideEventsControllers();
}

function selectGameFieldCell(selectedCell) {
    clearTimeout(clickTimer);
    unselectAllGameFieldCells();
    addClassName(selectedCell, 'selected-game-field-cell');
    selectedCellID = selectedCell.id;
    showEventsControllers();
}

// ── Dodawanie zdarzeń ─────────────────────────────────────────────────────────

/**
 * Domyślne pozycje bramek przy braku zaznaczonej komórki.
 * Bramka lewa  = kolumna A, środkowy wiersz (rząd ~5 dla 9 wierszy)
 * Bramka prawa = kolumna O (ostatnia), środkowy wiersz
 */
function getDefaultGoalCellID(isHome, isGoal, isReversed) {
    const midRow   = Math.ceil(_FIELD_ROWS / 2);           // środkowy rząd (5)
    const lastCol  = String.fromCharCode(65 + _FIELD_COLS - 1);  // 'O'
    const nearGoal = isReversed ? `${lastCol}${midRow}` : `A${midRow}`;
    const farGoal  = isReversed ? `A${midRow}`          : `${lastCol}${midRow}`;
    return (isGoal === isHome) ? farGoal : nearGoal;
}

function showUiMonitorEvents() {
    const uiMonitorContentElement = document.querySelector('#ui-monitor-content');
    const isUpdateBlockedData = uiMonitorContentElement.dataset.isEventsUpdateBlocked;
    if (isUpdateBlockedData === 'false') {
        showUiMonitorContent('events');
    }
}

function addTeamEvent(_team, _event) {
    if (_event === 'Bramka') {
        changeGameValue('score', _team, 1);
        socket.emit('broadcast_goal', { 'team_type': _team });
    }
    if (selectedCellID === null) {
        selectedCellID = getDefaultGoalCellID(
            _team === 'home',
            _event === 'Bramka',
            appState.isReversed
        );
    }
    socket.emit('add_game_event_to_db', {
        'team_type':       _team,
        'event_type':      _event,
        'selected_cell_id': selectedCellID
    });
    unselectAllGameFieldCells();
    setTimeout(showUiMonitorEvents, 200);
}

function addFieldEvent(_event) {
    socket.emit('add_game_event_to_db', {
        'team_type':       null,
        'event_type':      _event,
        'selected_cell_id': selectedCellID
    });
    unselectAllGameFieldCells();
    setTimeout(showUiMonitorEvents, 100);
}

function addNoReplayEvent(_event) {
    socket.emit('add_game_event_to_db', {
        'team_type':       null,
        'event_type':      _event,
        'selected_cell_id': null
    });
    unselectAllGameFieldCells();
}

// ── Init ──────────────────────────────────────────────────────────────────────
gameFieldGenerator();

