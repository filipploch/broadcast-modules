// replay-utils.js
// replayPauseElement i replayResumeElement zdefiniowane w ui-jinja.js

var _replayCurrentSpeed = 0.9; // synchronizuj z config.json default_speed
var _replayIsPaused = false;
var _replayLastFrameStepAt = 0;
var _replayFrameStepThrottleMs = 120;

function replayRequestFrameStep(deltaY) {
    var now = Date.now();
    if (now - _replayLastFrameStepAt < _replayFrameStepThrottleMs) return;
    _replayLastFrameStepAt = now;

    if (deltaY < 0) replayFrameFwd();
    else            replayFrameBack();
}

if (replayPauseElement && replayResumeElement) {
    var _replayClickTimer = null;
    var _replayLastClickAt = 0;
    var _replayLastEndAt = 0;
    var _replayDoubleClickMs = 280;

    function replayEndOnce(event) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        if (_replayClickTimer) {
            clearTimeout(_replayClickTimer);
            _replayClickTimer = null;
        }

        var now = Date.now();
        if (now - _replayLastEndAt < 500) return;
        _replayLastEndAt = now;
        replayEnd();
    }

    function bindReplayClick(element, singleClickAction) {
        element.addEventListener('click', function(event) {
            event.preventDefault();
            event.stopPropagation();

            var now = Date.now();
            if (now - _replayLastClickAt <= _replayDoubleClickMs) {
                _replayLastClickAt = 0;
                replayEndOnce(event);
                return;
            }
            _replayLastClickAt = now;

            if (_replayClickTimer) clearTimeout(_replayClickTimer);
            _replayClickTimer = setTimeout(function() {
                _replayClickTimer = null;
                singleClickAction();
            }, _replayDoubleClickMs);
        });

        // Zostawiamy natywny dblclick jako backup dla urządzeń/przeglądarek,
        // które wygenerują go mimo zmiany widoczności przycisków.
        element.addEventListener('dblclick', replayEndOnce);
    }

    // Kliknięcie PAUSE / RESUME. Pojedynczy klik jest celowo opóźniony
    // o _replayDoubleClickMs, żeby drugi klik mógł zakończyć replay zamiast
    // przełączać widoczność elementu i psuć dwuklik.
    bindReplayClick(replayPauseElement, function() {
        replayPause();
        _replayIsPaused = true;
    });

    bindReplayClick(replayResumeElement, function() {
        replayResume();
        _replayIsPaused = false;
    });

    // Scroll na PAUSE → zmiana prędkości (szybciej/wolniej)
    replayPauseElement.addEventListener('wheel', function(event) {
        event.preventDefault();

        var delta = event.deltaY < 0 ? 0.1 : -0.1;
        _replayCurrentSpeed = Math.round((_replayCurrentSpeed + delta) * 10) / 10;
        _replayCurrentSpeed = Math.max(0.1, Math.min(4.0, _replayCurrentSpeed));

        replaySpeed(_replayCurrentSpeed);
    }, { passive: false });

    // Scroll na RESUME → krok klatkowy
    // Automatycznie pauzuje jeśli mpv gra
    replayResumeElement.addEventListener('wheel', function(event) {
        event.preventDefault();

        if (!_replayIsPaused) {
            replayPause();
            _replayIsPaused = true;
            // Krótkie opóźnienie — mpv musi przetworzyć pause przed frame-step
            var deltaY = event.deltaY;
            setTimeout(function() {
                replayRequestFrameStep(deltaY);
            }, _replayFrameStepThrottleMs);
            return;
        }

        replayRequestFrameStep(event.deltaY);
    }, { passive: false });
}
