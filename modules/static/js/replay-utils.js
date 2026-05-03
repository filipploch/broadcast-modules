// replay-utils.js
// replayPauseElement i replayResumeElement zdefiniowane w ui-jinja.js

var _replayCurrentSpeed = 0.9; // synchronizuj z config.json default_speed
var _replayIsPaused = false;

// Kliknięcie PAUSE
replayPauseElement.addEventListener('click', function() {
    replayPause();
    _replayIsPaused = true;
});

// Kliknięcie RESUME
replayResumeElement.addEventListener('click', function() {
    replayResume();
    _replayIsPaused = false;
});

// Dwuklik PAUSE lub RESUME → end_replay
replayPauseElement.addEventListener('dblclick', function() { replayEnd(); });
replayResumeElement.addEventListener('dblclick', function() { replayEnd(); });

// Scroll na PAUSE → zmiana prędkości (szybciej/wolniej)
replayPauseElement.addEventListener('wheel', function(event) {
    event.preventDefault();
    replayCancelTimer();

    var delta = event.deltaY < 0 ? 0.1 : -0.1;
    _replayCurrentSpeed = Math.round((_replayCurrentSpeed + delta) * 10) / 10;
    _replayCurrentSpeed = Math.max(0.1, Math.min(4.0, _replayCurrentSpeed));

    replaySpeed(_replayCurrentSpeed);
}, { passive: false });

// Scroll na RESUME → krok klatkowy
// Automatycznie pauzuje jeśli mpv gra
replayResumeElement.addEventListener('wheel', function(event) {
    event.preventDefault();
    replayCancelTimer();

    if (!_replayIsPaused) {
        replayPause();
        _replayIsPaused = true;
        // Krótkie opóźnienie — mpv musi przetworzyć pause przed frame-step
        setTimeout(function() {
            if (event.deltaY < 0) replayFrameFwd();
            else                  replayFrameBack();
        }, 80);
        return;
    }

    if (event.deltaY < 0) replayFrameFwd();
    else                  replayFrameBack();
}, { passive: false });