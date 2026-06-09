// cam-head-ui.js — dynamiczny builder UI kalibracji głowic pan/tilt

// Kolejność kodów pozycji w każdym wierszu (lewa → prawa)
const CAM_POSITION_LAYOUT = {
    far:       ['LCF', 'LF', 'CF', 'RF', 'RCF'],
    leftGoal:  ['LG'],
    rightGoal: ['RG'],
    close:     ['LCC', 'LC', 'CC', 'RC', 'RCC'],
};

/**
 * Buduje cały blok kalibracji dla FIELD_GRID.
 * @param {Array} positions  — tablica obiektów {id, code, name, zone_scheme, ...}
 * @returns {HTMLElement}    — gotowy blok do wstawienia w DOM
 */
function buildFieldGridCalibrationUI(positions) {
    const byCode = {};
    positions.forEach(p => { byCode[p.code] = p; });

    // ── rząd dalszy ──────────────────────────────────────────────────
    const farRow = _row('far-cameras-positions-container');
    CAM_POSITION_LAYOUT.far.forEach(code => {
        if (byCode[code]) farRow.appendChild(_camBtn(byCode[code]));
    });

    // ── bramka lewa ──────────────────────────────────────────────────
    const leftGoal = _goalCol('left-goal-cameras-positions-container');
    CAM_POSITION_LAYOUT.leftGoal.forEach(code => {
        if (byCode[code]) leftGoal.appendChild(_camBtn(byCode[code]));
    });

    // ── siatka boiska ─────────────────────────────────────────────────
    const field = document.createElement('div');
    field.id = 'cam-head-game-field';
    field.className = 'game-field-selector';

    // ── bramka prawa ─────────────────────────────────────────────────
    const rightGoal = _goalCol('right-goal-cameras-positions-container');
    CAM_POSITION_LAYOUT.rightGoal.forEach(code => {
        if (byCode[code]) rightGoal.appendChild(_camBtn(byCode[code]));
    });

    // ── środkowy rząd (bramka + boisko + bramka) ─────────────────────
    const midRow = document.createElement('div');
    midRow.id = 'game-field-and-goals-cameras-position-container';
    midRow.style.cssText = 'display:flex; flex-direction:row; align-items: center;';
    midRow.appendChild(leftGoal);
    midRow.appendChild(field);
    midRow.appendChild(rightGoal);

    // ── rząd bliższy ─────────────────────────────────────────────────
    const closeRow = _row('close-cameras-positions-container');
    CAM_POSITION_LAYOUT.close.forEach(code => {
        if (byCode[code]) closeRow.appendChild(_camBtn(byCode[code]));
    });

    // ── główny kontener ───────────────────────────────────────────────
    const root = document.createElement('div');
    root.id = 'cam-head-calibration-grid';
    root.style.cssText = 'display:flex; flex-direction:column;';
    root.appendChild(farRow);
    root.appendChild(midRow);
    root.appendChild(closeRow);

    return root;
}

/**
 * Pobiera pozycje z API i renderuje UI kalibracji w podanym elemencie.
 * Wywołuje gameFieldGenerator() jeśli jest dostępna (wypełnia siatkę boiska).
 * @param {number}      stadiumId  — ID stadionu
 * @param {HTMLElement} targetEl   — element, w którym pojawi się blok
 */
async function loadCamHeadCalibrationUI(stadiumId, targetEl) {
    try {
        const resp = await fetch(`/api/stadium-camera-positions?stadium_id=${stadiumId}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const positions = await resp.json();

        const ui = buildFieldGridCalibrationUI(positions);
        targetEl.innerHTML = '';
        targetEl.appendChild(ui);

        // Wypełnij siatkę boiska komórkami (tło + komórki jak #game-field)
        const camField = document.getElementById('cam-head-game-field');
        if (camField) _fillCalibrationField(camField);
    } catch (err) {
        console.error('[cam-head-ui] Nie udało się załadować pozycji kamer:', err);
    }
}

// ── helpers ───────────────────────────────────────────────────────────────────

function _row(id) {
    const el = document.createElement('div');
    el.id = id;
    el.style.cssText = 'display:flex; flex-direction:row; align-items:center; justify-content:space-between; width:100%;';
    return el;
}

function _goalCol(id) {
    const el = document.createElement('div');
    el.id = id;
    el.className = 'goal-cameras-positions-container';
    el.style.cssText = 'display:flex; flex-direction:column; align-items:center;';
    return el;
}

function _fillCalibrationField(containerEl, cols = 15, rows = 9) {
    if (typeof fieldSvgStr === 'function') {
        const svg = fieldSvgStr(MODULE_NAME, null, null, null);
        containerEl.style.backgroundImage = `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
    }

    containerEl.innerHTML = '';

    for (let row = 1; row <= rows; row++) {
        const rowEl = document.createElement('div');
        rowEl.className = 'game-field-row';
        rowEl.style.display = 'flex';

        for (let col = 0; col < cols; col++) {
            const cell = document.createElement('div');
            cell.className = 'game-field-cell';
            rowEl.appendChild(cell);
        }
        containerEl.appendChild(rowEl);
    }
}

/**
 * Tworzy przycisk pozycji kamery.
 * data-position-id i data-position-code są dostępne dla innych skryptów.
 */
function _camBtn(position) {
    const btn = document.createElement('div');
    btn.className = 'cam-position-btn';
    btn.dataset.positionId   = position.id;
    btn.dataset.positionCode = position.code;
    btn.title = position.name;

    const code = document.createElement('span');
    code.className = 'cam-position-code';
    code.textContent = position.code;

    btn.appendChild(code);
    return btn;
}
