// Zakończona część nie może mieć aktywnych przycisków zegara (START / PAUZA / WZNÓW) ani oznaczenia biegu.
// Logika jest osobno od index.js (bez gniazd i bez DOM-u strony), żeby miała test w Node (tests/modules/js/period_lock_test.js).
(function (global) {
    'use strict';
    var ZAKONCZONY = 2;

    function zablokuj(doc, period) {
        if (!period || period.status !== ZAKONCZONY) return false;
        doc.querySelectorAll('.timer-main-controller').forEach(function (b) {
            b.disabled = true;
            b.setAttribute('disabled', 'disabled');
            b.removeAttribute('onclick');
            b.onclick = null;
            b.classList.add('nodisplayed');
            b.classList.add('period-finished');
        });
        doc.querySelectorAll('[data-state-for]').forEach(function (h) {
            ['timer-state-running', 'timer-state-idle', 'timer-state-limit_reached'].forEach(function (k) { h.classList.remove(k); });
            h.classList.add('timer-state-paused');
            h.classList.add('timer-state-finished');
        });
        return true;
    }

    global.PeriodLock = {
        zablokuj: zablokuj,
        zastosuj: function () { return typeof document !== 'undefined' ? zablokuj(document, global.period) : false; }
    };
    if (typeof document !== 'undefined') {
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { setTimeout(global.PeriodLock.zastosuj, 0); });
        else setTimeout(global.PeriodLock.zastosuj, 0);
    }
})(typeof window !== 'undefined' ? window : globalThis);
