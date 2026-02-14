// Przechowujemy mapę istniejących obserwatorów, aby uniknąć wielokrotnego obserwowania tego samego elementu
const elementObservers = new WeakMap();

// Funkcja dodająca obserwatora tekstu do pojedynczego elementu
function observeSingleElement(element) {
    // Sprawdź, czy element już nie jest obserwowany
    if (elementObservers.has(element)) {
        return;
    }

    // Konfiguracja obserwatora dla zmian tekstu
    const config = { characterData: true, subtree: true };
    
    const callback = function(mutationsList) {
        for (let mutation of mutationsList) {
            if (mutation.type === 'characterData') {
                const targetElement = mutation.target.parentElement;
                
                if (targetElement && targetElement.classList.contains('penalty-timer')) {
                    if (targetElement.textContent.trim() !== '') {
                        targetElement.classList.add('show-penalty-timer');
                        targetElement.classList.remove('hide-penalty-timer');
                    } else {
                        targetElement.classList.add('hide-penalty-timer');
                        targetElement.classList.remove('show-penalty-timer');
                    }
                }
            }
        }
    };
    
    // Utwórz i zapisz obserwatora
    const observer = new MutationObserver(callback);
    observer.observe(element, config);
    
    // Zapisz obserwatora w mapie
    elementObservers.set(element, observer);
    
    // Inicjalne sprawdzenie stanu elementu
    if (element.textContent.trim() !== '') {
        element.classList.add('show-penalty-timer');
    }
}

// Funkcja usuwająca obserwatora z elementu
function unobserveSingleElement(element) {
    if (elementObservers.has(element)) {
        const observer = elementObservers.get(element);
        observer.disconnect();
        elementObservers.delete(element);
    }
}

// Główny obserwator całego dokumentu
function observeDocument() {
    // Obserwuj cały dokument pod kątem nowych elementów
    const bodyObserver = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            // Obsługa DODANYCH węzłów
            mutation.addedNodes.forEach((node) => {
                // Sprawdź, czy dodany węzeł to element z klasą 'penalty-timer'
                if (node.nodeType === Node.ELEMENT_NODE) {
                    if (node.classList && node.classList.contains('penalty-timer')) {
                        observeSingleElement(node);
                    }
                    
                    // Sprawdź również dzieci dodanego elementu
                    const nestedElements = node.querySelectorAll('.penalty-timer');
                    nestedElements.forEach(observeSingleElement);
                }
            });
            
            // Obsługa USUNIĘTYCH węzłów
            mutation.removedNodes.forEach((node) => {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    if (node.classList && node.classList.contains('penalty-timer')) {
                        unobserveSingleElement(node);
                    }
                    
                    // Sprawdź również dzieci usuwanego elementu
                    const nestedElements = node.querySelectorAll('.penalty-timer');
                    nestedElements.forEach(unobserveSingleElement);
                }
            });
        });
    });
    
    // Rozpocznij obserwację całego dokumentu
    bodyObserver.observe(document.body, {
        childList: true,      // obserwuj dodawanie/usuwanie dzieci
        subtree: true         // obserwuj całe drzewo DOM
    });
    
    // Znajdź i obserwuj istniejące elementy
    const existingElements = document.querySelectorAll('.penalty-timer');
    existingElements.forEach(observeSingleElement);
    
    return bodyObserver; // zwróć obserwatora na wypadek, gdyby trzeba go było zatrzymać
}

// Uruchom cały mechanizm po załadowaniu strony
document.addEventListener('DOMContentLoaded', () => {
    const observer = observeDocument();
    
    // Opcjonalnie: jeśli chcesz móc zatrzymać obserwację w przyszłości
    window.stopObserving = () => observer.disconnect();
});