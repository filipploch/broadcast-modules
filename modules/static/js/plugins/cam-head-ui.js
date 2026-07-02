// cam-head-ui.js — dynamiczny builder UI kalibracji głowic pan/tilt

var _positionsData     = {}; // position.id → position object (z to_dict)
var _availableCamHeads = [];
var _availableCameras  = [];
var _activePositionId  = null;

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
        const [posResp, headsResp, camsResp] = await Promise.all([
            fetch(`/api/stadium-camera-positions?stadium_id=${stadiumId}`),
            fetch('/api/cam-heads'),
            fetch('/api/cameras'),
        ]);
        const positions = await posResp.json();
        _availableCamHeads = await headsResp.json();
        _availableCameras  = await camsResp.json();

        _positionsData = {};
        positions.forEach(p => { _positionsData[p.id] = p; });

        const ui = buildFieldGridCalibrationUI(positions);
        targetEl.innerHTML = '';
        targetEl.appendChild(ui);

        const camField = document.getElementById('cam-head-game-field');
        if (camField) gameFieldGenerator(camField);
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


function _camBtn(position) {
    const btn = document.createElement('div');
    btn.className = 'cam-position-btn editable-cam-position-btn';
    btn.dataset.positionId   = position.id;
    btn.dataset.positionCode = position.code;
    btn.title = position.name;
    btn.addEventListener('click',    _onCamPositionBtnClick);
    btn.addEventListener('dblclick', _onCamPositionBtnDblClick);

    const code = document.createElement('span');
    code.className = 'cam-position-code';
    code.textContent = position.code;

    btn.appendChild(code);
    return btn;
}

function closeCamPositionEdit() {
    document.querySelectorAll('.cam-position-btn').forEach(el => el.classList.remove('on-edit'));
    _activePositionId = null;
    _renderPositionInfo(null);
    _clearCalibratedCells();
    if (typeof destroyServoJoystick === 'function') destroyServoJoystick();
    const servoCtrl = document.getElementById('servo-controller');
    if (servoCtrl) servoCtrl.style.display = 'none';
}

function _onCamPositionBtnClick(e) {
    document.querySelectorAll('.cam-position-btn').forEach(el => el.classList.remove('on-edit'));
    e.currentTarget.classList.add('on-edit');

    const posId = parseInt(e.currentTarget.dataset.positionId);
    _activePositionId = posId;
    const pos = _positionsData[posId] || null;
    _renderPositionInfo(pos);
    _clearCalibratedCells();
    if (pos && pos.default_camera_id) {
        _loadCalibrationZones(pos.id, pos.default_camera_id);
    }

    const servoCtrl = document.getElementById('servo-controller');
    if (servoCtrl) {
        servoCtrl.style.display = '';
        requestAnimationFrame(function () {
            if (typeof initServoJoystick === 'function') initServoJoystick();
        });
    }
}

function _renderPositionInfo(pos) {
    const nameEl  = document.getElementById('cam-calib-position-name');
    const headSel = document.getElementById('cam-calib-head-select');
    const camSel  = document.getElementById('cam-calib-camera-select');
    const calibEl = document.getElementById('cam-calib-has-calib');
    if (!nameEl) return;

    if (!pos) {
        nameEl.textContent = '—';
        _resetSelect(headSel);
        _resetSelect(camSel);
        if (calibEl) calibEl.textContent = '—';
        return;
    }

    nameEl.textContent = pos.code ? pos.name + ' (' + pos.code + ')' : pos.name;

    // kamera
    if (camSel) {
        _fillSelect(camSel, _availableCameras,
            c => c.id,
            c => c.name + ' (' + c.brand + ' ' + c.model + ')',
            pos.default_camera_id);
        camSel.disabled = false;
        camSel.onchange = function () { _onCameraSelectChange(pos.id, this); };
    }

    // głowica — odzwierciedla cam_head sparowaną z wybraną kamerą
    if (headSel) {
        _fillSelect(headSel, _availableCamHeads,
            h => h.id,
            h => (h.name || h.head_id) + ' (' + h.head_id + ')',
            pos.cam_head_id);
        headSel.disabled = !pos.default_camera_id;
        headSel.onchange = function () { _onCamHeadSelectChange(pos.id, this); };
    }

    if (calibEl) calibEl.textContent = pos.has_calibration ? '✅ Zdefiniowana' : '❌ Brak';
}

function _fillSelect(sel, items, valFn, labelFn, selectedVal) {
    sel.innerHTML = '<option value="">— brak —</option>';
    items.forEach(item => {
        const opt = document.createElement('option');
        opt.value = valFn(item);
        opt.textContent = labelFn(item);
        if (valFn(item) === selectedVal) opt.selected = true;
        sel.appendChild(opt);
    });
}

function _resetSelect(sel) {
    if (!sel) return;
    sel.innerHTML = '<option value="">— brak —</option>';
    sel.disabled = true;
    sel.onchange = null;
}

async function _onCameraSelectChange(positionId, sel) {
    const cameraId = sel.value ? parseInt(sel.value) : null;
    try {
        const resp = await fetch(`/api/stadium-camera-positions/${positionId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ default_camera_id: cameraId }),
        });
        const updated = await resp.json();
        _positionsData[positionId] = updated;

        const headSel = document.getElementById('cam-calib-head-select');
        const calibEl = document.getElementById('cam-calib-has-calib');
        if (headSel) {
            _fillSelect(headSel, _availableCamHeads,
                h => h.id,
                h => (h.name || h.head_id) + ' (' + h.head_id + ')',
                updated.cam_head_id);
            headSel.disabled = !cameraId;
            headSel.onchange = function () { _onCamHeadSelectChange(positionId, this); };
        }
        if (calibEl) calibEl.textContent = updated.has_calibration ? '✅ Zdefiniowana' : '❌ Brak';

        _clearCalibratedCells();
        if (cameraId) _loadCalibrationZones(positionId, cameraId);
    } catch (err) {
        console.error('[cam-head-ui] Błąd zapisu kamery dla pozycji:', err);
    }
}

async function _onCamHeadSelectChange(positionId, sel) {
    const pos = _positionsData[positionId];
    if (!pos || !pos.default_camera_id) return;
    const camHeadId = sel.value ? parseInt(sel.value) : null;
    try {
        const resp = await fetch(`/api/cameras/${pos.default_camera_id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cam_head_id: camHeadId }),
        });
        const updatedCam = await resp.json();
        const cam = _availableCameras.find(c => c.id === updatedCam.id);
        if (cam) cam.cam_head_id = updatedCam.cam_head_id;
        pos.cam_head_id = updatedCam.cam_head_id;
        const head = _availableCamHeads.find(h => h.id === updatedCam.cam_head_id);
        pos.cam_head_name = head ? (head.name || head.head_id) : null;
    } catch (err) {
        console.error('[cam-head-ui] Błąd zapisu głowicy dla kamery:', err);
    }
}

function _onCamPositionBtnDblClick(e) {
    if (e.currentTarget.classList.contains('on-edit')) {
        closeCamPositionEdit();
    }
}

// ── kalibracja stref boiska ───────────────────────────────────────────────────

async function _loadCalibrationZones(positionId, cameraId) {
    try {
        const resp = await fetch(
            `/api/camera-position-calibrations?position_id=${positionId}&camera_id=${cameraId}`
        );
        const calibrations = await resp.json();
        _markCalibratedCells(calibrations);
    } catch (err) {
        console.error('[cam-head-ui] Błąd ładowania kalibracji stref:', err);
    }
}

function _markCalibratedCells(calibrations) {
    const camField = document.getElementById('cam-head-game-field');
    if (!camField) return;
    calibrations.forEach(cal => {
        const cell = camField.querySelector(`[data-cell-id="${cal.zone_code}"]`);
        if (cell) cell.classList.add('calibrated-zone');
    });
}

function _clearCalibratedCells() {
    document.querySelectorAll('#cam-head-game-field .calibrated-zone')
        .forEach(el => el.classList.remove('calibrated-zone'));
}

async function _onCalibrationCellDblClick(cell) {
    const pos = _activePositionId ? _positionsData[_activePositionId] : null;
    if (!pos || !pos.default_camera_id) return;

    const zoneCode = cell.dataset.cellId;
    const pan  = typeof _servoPan  !== 'undefined' ? _servoPan  : 90;
    const tilt = typeof _servoTilt !== 'undefined' ? _servoTilt : 45;

    try {
        await fetch('/api/camera-position-calibrations', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                position_id: pos.id,
                camera_id:   pos.default_camera_id,
                zone_code:   zoneCode,
                pan:         pan,
                tilt:        tilt,
            }),
        });
        cell.classList.add('calibrated-zone');
        pos.has_calibration = true;
        const calibEl = document.getElementById('cam-calib-has-calib');
        if (calibEl) calibEl.textContent = '✅ Zdefiniowana';
    } catch (err) {
        console.error('[cam-head-ui] Błąd zapisu kalibracji strefy:', err);
    }
}
