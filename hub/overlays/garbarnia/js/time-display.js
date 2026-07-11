/**
 * time-display.js — wspólny algorytm wyświetlania czasu.
 *
 * KOPIA pliku kanonicznego: modules/static/js/core/time-display.js
 * (overlaye i UI operatora są serwowane przez dwa różne serwery bez
 * wspólnego build-stepu, więc synchronizacja jest ręczna — przy zmianie
 * logiki zaktualizuj WSZYSTKIE 3 kopie: tę, futsal-nalf i core/time-display.js).
 *
 * Dwa algorytmy, bo czas może płynąć w dwie strony:
 *   - formatCountUp   — zegar główny meczu (rośnie)
 *   - formatCountDown — kary (maleje, odliczanie do zera)
 *
 * Konwencja zaokrąglania (ustalona świadomie): floor. Kara z limitem 2:00
 * pokazuje 1:59 już po pierwszej upływającej milisekundzie, nie czeka na
 * pełną sekundę.
 */
(function (global) {
    'use strict';

    function clockString(totalSeconds) {
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        return `${minutes}:${String(seconds).padStart(2, '0')}`;
    }

    /**
     * Zegar rosnący (główny timer meczu).
     * @param {number} elapsedMs — czas, jaki upłynął (już z uwzględnieniem
     *   ewentualnego initial_time — doliczany PRZED wywołaniem tej funkcji).
     */
    function formatCountUp(elapsedMs) {
        const totalSeconds = Math.floor(Math.max(0, elapsedMs) / 1000);
        return clockString(totalSeconds);
    }

    /**
     * Zegar malejący (kary). Przyjmuje już wyliczony czas pozostały.
     * @param {number} remainingMs
     */
    function formatCountDown(remainingMs) {
        const totalSeconds = Math.floor(Math.max(0, remainingMs) / 1000);
        return clockString(totalSeconds);
    }

    /**
     * Wylicza czas pozostały kary na podstawie elapsed głównego timera —
     * ten sam wzór co GameTimer.penalty_remaining_ms() w Pythonie
     * (modules/{futsal_nalf,garbarnia}/app/models/game_timer.py) i logika
     * dependent timera w pluginie (plugins/timer-plugin/timer.go).
     *
     * @param {{start_offset_ms: number, limit_ms: number, adjustment_ms?: number}} pen
     * @param {number} mainElapsedMs — aktualny elapsed_time głównego timera
     * @returns {number} pozostały czas w ms, w przedziale [0, pen.limit_ms]
     */
    function derivePenaltyRemainingMs(pen, mainElapsedMs) {
        const elapsedInPenalty =
            mainElapsedMs - pen.start_offset_ms + (pen.adjustment_ms || 0);
        return Math.min(pen.limit_ms, Math.max(0, pen.limit_ms - elapsedInPenalty));
    }

    const TimeDisplay = {
        formatCountUp,
        formatCountDown,
        derivePenaltyRemainingMs,
    };

    global.TimeDisplay = TimeDisplay;
})(typeof window !== 'undefined' ? window : globalThis);
