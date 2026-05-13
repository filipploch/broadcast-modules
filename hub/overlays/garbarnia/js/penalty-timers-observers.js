/**
 * penalty-timers-observers.js
 *
 * Obsługa wyświetlania timerów kar w overlay — architektura derived-variable.
 *
 * Źródło prawdy o karach: sygnał `penalty_state` z backendu (nie timer-plugin).
 * Czas pozostały kary obliczany lokalnie przy każdym ticku głównego timera.
 *
 * Publiczne API (window.PenaltyTimers):
 *   .syncState(penalties)          — zastąp stan kar danymi z backendu
 *   .tickMain(mainElapsedMs)       — przelicz i odśwież wszystkie kary
 *   .remove(id)                    — usuń konkretną karę (animacja)
 *   .clearAll()                    — usuń wszystkie kary
 */

(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // Stan
    // -------------------------------------------------------------------------

    /**
     * Mapa aktywnych kar.
     * key: id (GameTimer.id z backendu, string)
     * value: {
     *   id, team, player_id, limit_ms, start_offset_ms, adjustment_ms, state,
     *   element   — referencja do elementu DOM (null jeśli jeszcze nie utworzony)
     *   container — referencja do kontenera DOM
     * }
     */
    const penalties = new Map();

    // -------------------------------------------------------------------------
    // Helpers obliczeniowe
    // -------------------------------------------------------------------------

    /**
     * Oblicza pozostały czas kary w ms na podstawie elapsed głównego timera.
     * Odpowiednik penalty_remaining_ms() z modelu GameTimer w Pythonie.
     *
     * @param {Object} pen   — obiekt kary z penalties Map
     * @param {number} mainElapsedMs — aktualny elapsed_time głównego timera
     * @returns {number} pozostały czas w ms (min. 0)
     */
    function calcRemaining(pen, mainElapsedMs) {
        const elapsedInPenalty =
            mainElapsedMs - pen.start_offset_ms + (pen.adjustment_ms || 0);
        return Math.max(0, pen.limit_ms - elapsedInPenalty);
    }

    /**
     * Formatuje ms → "M:SS"
     * @param {number} ms
     * @returns {string}
     */
    function formatMs(ms) {
        const totalSeconds = Math.ceil(ms / 1000);
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        return `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }

    // -------------------------------------------------------------------------
    // DOM
    // -------------------------------------------------------------------------

    function getContainer(team) {
        const id = team === 'home'
            ? 'home-team-penalty-timer-container'
            : 'away-team-penalty-timer-container';
        return document.getElementById(id);
    }

    /**
     * Tworzy element DOM timera kary i dodaje go do kontenera.
     * @param {Object} pen
     * @returns {HTMLElement|null}
     */
    function createPenaltyElement(pen) {
        const container = getContainer(pen.team);
        if (!container) {
            console.error(`[PenaltyTimers] Brak kontenera dla drużyny: ${pen.team}`);
            return null;
        }

        const el = document.createElement('div');
        el.className = 'penalty-timer';
        el.setAttribute('data-penalty-id', pen.id);
        el.textContent = formatMs(pen.limit_ms);
        container.appendChild(el);

        // Animacja pojawienia się
        el.classList.add('show-penalty-timer');
        setTimeout(() => el.classList.remove('show-penalty-timer'), 300);

        console.log(`[PenaltyTimers] Utworzono element kary id=${pen.id} (${pen.team})`);
        return el;
    }

    /**
     * Usuwa element DOM kary z animacją.
     * @param {Object} pen
     */
    function removePenaltyElement(pen) {
        if (!pen.element) return;
        const { element, container } = pen;
        element.classList.add('hide-penalty-timer');
        setTimeout(() => {
            if (element.parentNode === container) {
                container.removeChild(element);
            }
        }, 300);
    }

    // -------------------------------------------------------------------------
    // Publiczne API
    // -------------------------------------------------------------------------

    /**
     * Synchronizuje lokalny stan kar z danymi z backendu.
     * Wywoływane przy sygnale `penalty_state`.
     *
     * @param {{ home: Object[], away: Object[] }} data — payload z to_dict() kar
     */
    function syncState(data) {
        const incomingIds = new Set();

        const allPenalties = [
            ...(data.home || []),
            ...(data.away || []),
        ];

        allPenalties.forEach(p => {
            const id = String(p.id);
            incomingIds.add(id);

            if (penalties.has(id)) {
                // Aktualizuj dane bez dotykania elementu DOM
                const existing = penalties.get(id);
                existing.start_offset_ms = p.start_offset_ms;
                existing.adjustment_ms   = p.adjustment_ms  || 0;
                existing.limit_ms        = p.limit_ms;
                existing.state           = p.state;
            } else {
                // Nowa kara — zarejestruj, element DOM powstanie przy pierwszym ticku
                penalties.set(id, {
                    id:              id,
                    team:            p.team,
                    player_id:       p.player_id,
                    limit_ms:        p.limit_ms,
                    start_offset_ms: p.start_offset_ms,
                    adjustment_ms:   p.adjustment_ms || 0,
                    state:           p.state,
                    element:         null,
                    container:       null,
                });
                console.log(`[PenaltyTimers] Zarejestrowano karę id=${id} (${p.team})`);
            }
        });

        // Usuń kary których już nie ma w danych backendu
        penalties.forEach((pen, id) => {
            if (!incomingIds.has(id)) {
                removePenaltyById(id);
            }
        });
    }

    /**
     * Przelicza i odświeża wyświetlanie wszystkich aktywnych kar.
     * Wywoływane przy każdym `timer_updated` głównego timera.
     *
     * @param {number} mainElapsedMs — elapsed_time głównego timera w ms
     */
    function tickMain(mainElapsedMs) {
        penalties.forEach(pen => {
            if (pen.state === 'removed') return;

            const remainingMs = calcRemaining(pen, mainElapsedMs);

            // Leniwe tworzenie elementu DOM przy pierwszym ticku
            if (!pen.element) {
                pen.element   = createPenaltyElement(pen);
                pen.container = pen.element ? pen.element.parentNode : null;
            }

            if (!pen.element) return;

            pen.element.textContent = formatMs(remainingMs);

            // Kara dobiegła końca — ukryj (backend wyśle penalty_state bez niej)
            if (remainingMs === 0) {
                pen.element.classList.add('penalty-timer--expired');
            }
        });
    }

    /**
     * Usuwa konkretną karę po id (np. po sygnale limit_reached z backendu).
     * @param {string|number} id
     */
    function removePenaltyById(id) {
        const pen = penalties.get(String(id));
        if (!pen) return;
        removePenaltyElement(pen);
        penalties.delete(String(id));
        console.log(`[PenaltyTimers] Usunięto karę id=${id}`);
    }

    /**
     * Usuwa wszystkie kary (np. przy przeładowaniu overlay).
     */
    function clearAll() {
        penalties.forEach((pen, id) => removePenaltyById(id));
    }

    // -------------------------------------------------------------------------
    // Eksport
    // -------------------------------------------------------------------------

    window.PenaltyTimers = {
        syncState,
        tickMain,
        remove:   removePenaltyById,
        clearAll,
        // Tylko do debugowania
        _state: () => penalties,
    };

    console.log('[PenaltyTimers] Zainicjalizowano (architektura derived-variable)');
})();
