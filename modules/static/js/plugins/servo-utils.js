// servo-utils.js — wirtualny joystick pan/tilt dla głowic cam-head

// ── Stałe ─────────────────────────────────────────────────────────────────────

var SERVO_SPEED        = 0.6;   // stopni na tick przy max odchyleniu joysticka
var SERVO_TICK_MS      = 20;    // ms między kolejnymi komendami ruchu (= 50 Hz, sync z PWM serwa)
var SERVO_DEADZONE     = 5;     // % odchylenia joysticka ignorowane (dead zone)
var SERVO_PAN_MIN      = 0;
var SERVO_PAN_MAX      = 180;
var SERVO_TILT_MIN     = 0;
var SERVO_TILT_MAX     = 180;

// ── Stan ──────────────────────────────────────────────────────────────────────

var _servoHeadId       = null;   // aktywna głowica (pierwsza online)
var _servoPan          = 90;     // aktualna pozycja pan (stopnie)
var _servoTilt         = 90;     // aktualna pozycja tilt (stopnie)
var _joystick          = null;   // instancja JoyStick
var _joystickInterval  = null;   // setInterval → loop ruchu

// ── Socket.IO — śledzenie stanu głowicy ───────────────────────────────────────

socket.on('servo_head_online', function (data) {
    if (!_servoHeadId) _servoHeadId = data.head_id;
});

socket.on('servo_head_offline', function (data) {
    if (_servoHeadId === data.head_id) _servoHeadId = null;
});

// Prosi serwer o ponowne wysłanie listy głowic online.
// Potrzebne gdy skrypt ładuje się po nawiązaniu połączenia (race condition
// z handle_connect) lub po re-connect.
function _requestServoHeads() {
    socket.emit('get_servo_heads');
}
socket.on('connect', _requestServoHeads);
if (socket.connected) {
    _requestServoHeads();
}

socket.on('servo_status', function (data) {
    if (data.head_id === _servoHeadId) {
        _servoPan  = data.pan;
        _servoTilt = data.tilt;
    }
});

// ── Joystick ──────────────────────────────────────────────────────────────────

function initServoJoystick() {
    if (_joystick) return;

    var ctrl = document.getElementById('servo-controller');
    if (!ctrl) return;

    var w = ctrl.clientWidth;
    var h = ctrl.clientHeight;
    if (w === 0 || h === 0) {
        requestAnimationFrame(initServoJoystick);
        return;
    }

    var size = Math.min(w, h, 320);

    _joystick = new JoyStick('servo-controller', {
        title:               'servo-joystick',
        width:               size,
        height:              size,
        internalFillColor:   'rgba(220,38,38,0.7)',
        internalStrokeColor: 'rgba(180,20,20,0.9)',
        externalStrokeColor: 'rgba(255,255,255,0.3)',
        autoReturnToCenter:  true,
    });

    _joystickInterval = setInterval(_servoTick, SERVO_TICK_MS);
}

function destroyServoJoystick() {
    if (_joystickInterval) {
        clearInterval(_joystickInterval);
        _joystickInterval = null;
    }
    _joystick = null;
    var ctrl = document.getElementById('servo-controller');
    if (ctrl) ctrl.innerHTML = '';
}

function _servoTick() {
    if (!_joystick || !_servoHeadId) return;

    var x = parseFloat(_joystick.GetX());  // -100..100, prawo=+
    var y = parseFloat(_joystick.GetY());  // -100..100, góra=+

    if (Math.abs(x) < SERVO_DEADZONE && Math.abs(y) < SERVO_DEADZONE) return;

    var newPan  = _servoPan  + (x / 100) * SERVO_SPEED;
    var newTilt = _servoTilt - (y / 100) * SERVO_SPEED;  // Y góra → tilt maleje

    newPan  = Math.round(Math.max(SERVO_PAN_MIN,  Math.min(SERVO_PAN_MAX,  newPan)));
    newTilt = Math.round(Math.max(SERVO_TILT_MIN, Math.min(SERVO_TILT_MAX, newTilt)));

    if (newPan === _servoPan && newTilt === _servoTilt) return;

    _servoPan  = newPan;
    _servoTilt = newTilt;

    socket.emit('servo_set_pan_tilt', {
        head_id: _servoHeadId,
        pan:     _servoPan,
        tilt:    _servoTilt,
    });
}

// ── setCameraPosition — handler kliknięcia komórki boiska ────────────────────

var clickTimer = null;

function setCameraPosition(element) {
    clearTimeout(clickTimer);
    clickTimer = setTimeout(() => {
        var cellID = element.id;
        console.log('click -> cellID:', cellID);
    }, 100);
}
