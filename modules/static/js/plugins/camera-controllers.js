// #camera-controllers-container (.field-games) — centralny przełącznik kamer.
// Dokładnie jedno z 5 źródeł OBS w scenie "CAMERAS" jest aktywne naraz:
//   M       -> Camera1 (fizyczna kamera OBS, zawsze używalny)
//   m/C/L/R -> sCamera1..sCamera4 (strumienie SRT z recorder-plugin na Debianie),
//              używalne tylko gdy dana kamera aktualnie nagrywa — streaming do
//              Windows startuje/stopuje automatycznie razem z nagrywaniem
//              (patrz recorder.go StartRecord/StopRecord), więc "nagrywa" ==
//              "strumień dostępny". Ten sam sygnał (recording_started/
//              recording_stopped) steruje już kolorem #camera1-icon..
//              #camera4-icon w index.js.

var CAMERA_CONTROLLER_SCENE = 'CAMERAS';

var CAMERA_SOURCE_MAP = {
    M: { sourceName: 'Camera1',  cameraId: null },
    m: { sourceName: 'sCamera1', cameraId: 'camera1' },
    C: { sourceName: 'sCamera2', cameraId: 'camera2' },
    L: { sourceName: 'sCamera3', cameraId: 'camera3' },
    R: { sourceName: 'sCamera4', cameraId: 'camera4' },
};

function switchCameraSource(btnKey) {
    console.log('switchCameraSource', btnKey);
    var btn = document.querySelector('.field-camera-btn[data-camera-btn="' + btnKey + '"]');
    if (!btn || btn.disabled) return;

    var entry = CAMERA_SOURCE_MAP[btnKey];
    if (!entry) return;

    socket.emit('switch_camera_source', {
        scene_name: CAMERA_CONTROLLER_SCENE,
        source_name: entry.sourceName,
    });
}

socket.on('camera_source_switched', function (data) {
    if (!data || data.scene_name !== CAMERA_CONTROLLER_SCENE) return;

    document.querySelectorAll('.field-camera-btn').forEach(function (btn) {
        var entry = CAMERA_SOURCE_MAP[btn.getAttribute('data-camera-btn')];
        btn.classList.toggle('is-active', !!entry && entry.sourceName === data.source_name);
    });
});

function _setCameraButtonRecording(cameraId, isRecording) {
    document.querySelectorAll('.field-camera-btn').forEach(function (btn) {
        var entry = CAMERA_SOURCE_MAP[btn.getAttribute('data-camera-btn')];
        if (entry && entry.cameraId === cameraId) {
            btn.disabled = !isRecording;
        }
    });
}

socket.on('recording_status_response', function (data) {
    var cameras = (data && data.cameras) || {};
    Object.keys(cameras).forEach(function (cameraId) {
        _setCameraButtonRecording(cameraId, !!cameras[cameraId]);
    });
});

// Two bugs, same shape, same fix: this file only ever *reacts* to future
// events (recording_started/stopped for the disabled state, a manual
// switch_camera_source for is-active) — it never asks for the state that
// already exists when the panel loads. So:
//   - m/L/C/R start `disabled` (hard-coded in ui-jinja.html) and only wake
//     up on that camera's NEXT start/stop, staying stuck if it was already
//     recording when the panel opened;
//   - M starts `is-active` (also hard-coded) regardless of which of the 5
//     CAMERA_CONTROLLER_SOURCES is actually live in OBS right now, and only
//     corrects itself on the NEXT manual switch.
// ui-jinja.html only loads ui-jinja.js, not index.js — ui-jinja.js's own
// `connect` handler doesn't ask for either of these — so nothing on this
// page has ever requested either piece of current state; this is the one
// place that does, for both.
(function () {
    function requestCurrentCameraState() {
        socket.emit('get_camera_recording_status'); // → recording_status_response (handled above)
        socket.emit('get_camera_source_status');     // → camera_source_switched (handled above)
    }
    if (socket.connected) {
        requestCurrentCameraState();
    } else {
        socket.on('connect', requestCurrentCameraState);
    }
})();

socket.on('recording_started', function (data) {
    if (data && data.camera_id) _setCameraButtonRecording(data.camera_id, true);
});

socket.on('recording_stopped', function (data) {
    if (data && data.camera_id) _setCameraButtonRecording(data.camera_id, false);
});
