// penalty-timers-observer.js
const penaltyTimers = new Map(); // key: timer_id, value: { element, container }
(function() {
    'use strict';

    // Przechowujemy referencje do istniejących timerów

    // Funkcja tworząca element timera karnego
    function createPenaltyTimerElement(timerId, initialTime) {
        // Sprawdź czy timer już istnieje
        if (penaltyTimers.has(timerId)) {
            console.log(`Timer ${timerId} already exists, updating time...`);
            const existing = penaltyTimers.get(timerId);
            existing.element.textContent = initialTime;
            return existing.element;
        }

        // Określ kontener docelowy na podstawie timer_id
        let containerId;
        if (timerId.startsWith('penalty_home')) {
            containerId = 'home-team-penalty-timer-container';
        } else if (timerId.startsWith('penalty_away')) {
            containerId = 'away-team-penalty-timer-container';
        } else {
            console.error(`Unknown timer type: ${timerId}`);
            return null;
        }

        const container = document.getElementById(containerId);
        if (!container) {
            console.error(`Container ${containerId} not found`);
            return null;
        }

        // Usuń istniejący timer w kontenerze (jeśli istnieje)
        // const existingTimer = container.querySelector('.penalty-timer');
        // if (existingTimer) {
        //     container.removeChild(existingTimer);
        // }

        // Utwórz nowy element timera
        const timerElement = document.createElement('div');
        timerElement.className = 'penalty-timer';
        timerElement.setAttribute('data-timer-id', timerId);
        timerElement.textContent = initialTime;

        // Dodaj do kontenera
        container.appendChild(timerElement);

        // Zapisz referencję
        penaltyTimers.set(timerId, {
            element: timerElement,
            container: container
        });

        // Wywołaj animację pojawienia się
        timerElement.classList.add('show-penalty-timer');
        
        // Usuń klasę animacji po jej zakończeniu (opcjonalnie)
        setTimeout(() => {
            timerElement.classList.remove('show-penalty-timer');
        }, 300);

        console.log(`✅ Created penalty timer: ${timerId} with time ${initialTime}`);
        return timerElement;
    }

    // Funkcja aktualizująca istniejący timer
    function updatePenaltyTimer(timerId, newTime) {
        if (penaltyTimers.has(timerId)) {
            const { element } = penaltyTimers.get(timerId);
            element.textContent = newTime;
        } else {
            console.warn(`Cannot update ${timerId} - timer doesn't exist`);
        }
    }

    // Funkcja usuwająca timer
    function removePenaltyTimer(timerId) {
        if (penaltyTimers.has(timerId)) {
            const { element, container } = penaltyTimers.get(timerId);
            
            // Dodaj animację zniknięcia
            element.classList.add('hide-penalty-timer');
            
            // Usuń po zakończeniu animacji
            setTimeout(() => {
                if (element.parentNode === container) {
                    container.removeChild(element);
                }
                penaltyTimers.delete(timerId);
                console.log(`❌ Removed penalty timer: ${timerId}`);
            }, 300);
        }
    }

    // Funkcja czyszcząca wszystkie timery
    function clearAllPenaltyTimers() {
        penaltyTimers.forEach((_, timerId) => {
            removePenaltyTimer(timerId);
        });
    }

    // Eksponuj funkcje do globalnego zasięgu (dla dostępu z WebSocket)
    window.PenaltyTimers = {
        create: createPenaltyTimerElement,
        update: updatePenaltyTimer,
        remove: removePenaltyTimer,
        clearAll: clearAllPenaltyTimers
    };

    console.log('✅ Penalty Timers Observer initialized');
})();