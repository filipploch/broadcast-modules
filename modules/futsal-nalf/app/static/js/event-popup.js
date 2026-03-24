// Globalne zmienne
let activePopup = null;
let activeRow = null;
let activeScrollHandler = null;

// Funkcja zamykająca popup
window.closeReplaysPopup = function() {
    if (activePopup) {
        if (activeScrollHandler && activePopup._scrollContainer) {
            activePopup._scrollContainer.removeEventListener('scroll', activeScrollHandler);
        }
        activePopup.remove();
        activePopup = null;
        activeRow = null;
        activeScrollHandler = null;
    }
};

// Funkcja aktualizująca pozycję popupu
function updateReplaysPopupPosition(popup, row) {
    if (!popup || !row) return;
    
    const rowRect = row.getBoundingClientRect();
    const popupHeight = popup.offsetHeight;
    const popupWidth = popup.offsetWidth;
    
    // Znajdź przycisk w kolumnie events-td-open-replays-popup
    const td = row.querySelector('.events-td-open-replays-popup');
    const button = td ? td.querySelector('button') : null;
    
    // Oblicz pozycję - nad przyciskiem/wierszem
    let top = rowRect.top; // 5px odstępu
    
    // Jeśli brak miejsca nad, pokaż pod spodem
    if (top < 0) {
        top = rowRect.bottom + 5;
    }
    
    // Pozycja pozioma - domyślnie nad przyciskiem
    let left;
    if (button) {
        const buttonRect = button.getBoundingClientRect();
        left = buttonRect.left;
        
        // Zapobiegaj wychodzeniu poza prawą krawędź
        if (left + popupWidth > window.innerWidth) {
            left = window.innerWidth - popupWidth - 10;
        }
    } else {
        left = rowRect.left;
    }
    
    // Zapobiegaj wychodzeniu poza lewą krawędź
    if (left < 10) {
        left = 10;
    }
    
    popup.style.top = top + 'px';
    popup.style.left = left + 'px';
}

// Funkcja pokazująca popup z replayami
window.showReplaysPopup = function(gameEvent, row, buttonElement) {
    // Jeśli już jest otwarty popup dla tego samego wiersza - zamknij
    console.log('window.showReplaysPopup');
    if (activeRow === row && activePopup) {
        closeReplaysPopup();
        return;
    }
    
    // Zamknij istniejący popup
    closeReplaysPopup();
    
    // Pobierz kontener z przewijaniem
    const gameEventsContainer = document.getElementById('game-events-container');
    if (!gameEventsContainer) return;
    
    // Utwórz popup
    const popup = document.createElement('div');
    popup.id = 'replays-popup';
    popup.className = 'replays-popup';
    popup.style.cssText = `
        position: fixed;
        background: white;
        border: 1px solid #333;
        padding: 1px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10000; 
        display: block;
    `;
    let popupContent = replaysPopupGenerator(gameEvent); 
    popup.innerHTML = popupContent; 
    
    document.body.appendChild(popup);
    
    // Zapisz referencje
    activePopup = popup;
    activeRow = row;
    
    // Ustaw pozycję
    updateReplaysPopupPosition(popup, row);
    
    // Dodaj nasłuchiwanie przewijania
    const updatePosition = () => updateReplaysPopupPosition(popup, row);
    gameEventsContainer.addEventListener('scroll', updatePosition);
    activeScrollHandler = updatePosition;
    popup._scrollContainer = gameEventsContainer;
};

// Funkcja obsługująca wybór opcji replay
window.handleReplayOption = function(gameEventId, option) {
    console.log(`Wybrano opcję ${option} dla wydarzenia ${gameEventId}`);
    
    // Wyślij przez socket
    if (window.socket) {
        window.socket.emit('replay_option', { 
            event_id: gameEventId, 
            option: option 
        });
    }
    
    // Opcjonalnie: pokaż komunikat
    console.log(`Odtwarzanie ${option} dla wydarzenia ${gameEventId}`);
    
    // Zamknij popup
    closeReplaysPopup();
};