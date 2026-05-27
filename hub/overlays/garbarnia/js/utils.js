function addClassName(element, className) {
  try {
    if (element && element.classList && !element.classList.contains(className)) {
      element.classList.add(className);
      return true;
    }
    return false;
  } catch (error) {
    console.error('Błąd podczas dodawania klasy:', error);
    return false;
  }
}

// Wersja removeClassName z obsługą błędów
function removeClassName(element, className) {
  try {
    if (element && element.classList && element.classList.contains(className)) {
      element.classList.remove(className);
      return true;
    }
    return false;
  } catch (error) {
    console.error('Błąd podczas usuwania klasy:', error);
    return false;
  }
}

function hideAllOverlays() {
  const containers = document.querySelectorAll('.overlay-container');
  containers.forEach(container => {
    // Znajdź wszystkie elementy wewnątrz kontenera z atrybutem data-animation-class
    const animElements = container.querySelectorAll('[data-animation-class]');
    animElements.forEach(el => {
      const className = el.getAttribute('data-animation-class');
      if (className) {
        removeClassName(el, className); // usuń klasę animacji
      }
    });
    // Ukryj kontener
    addClassName(container, 'hidden');
  });
}

function showOverlay(overlayID) {
  hideAllOverlays(); // ukryj wszystkie nakładki

  const overlay = document.getElementById(overlayID);
  if (!overlay) return; // zabezpieczenie na wypadek braku elementu

  removeClassName(overlay, 'hidden'); // pokaż wybraną nakładkę

  // Dodaj klasy animacji do wewnętrznych elementów
  const animElements = overlay.querySelectorAll('[data-animation-class]');
  animElements.forEach(el => {
    const className = el.getAttribute('data-animation-class');
    if (className) {
      addClassName(el, className); // dodaj klasę animacji
    }
  });
}

function getCurrentDate() {
    const today = new Date();
    const day = String(today.getDate()).padStart(2, '0');
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const year = today.getFullYear();

    return `${day}-${month}-${year}`;
}

function formatGameTimeDisplay(gameTimeS, periodEndS) {
    if (periodEndS > 0 && gameTimeS > periodEndS) {
        var baseMin  = Math.floor(periodEndS / 60);
        var extraMin = Math.ceil((gameTimeS - periodEndS) / 60);
        return baseMin + "+" + extraMin + "'";
    }
    return Math.ceil(gameTimeS / 60) + "'";
}

function makePolygonTilt(elementHeight, elementWidth, side='both'){
  const tiltFactor = 19/38;
  const tiltShift = elementHeight * tiltFactor;
  if (side === 'left') {
    return `polygon(0 0, 100% 0, ${100 - tiltShift/elementWidth*100}% 100%, 0% 100%)`;
  } else if (side === 'right') {
    return `polygon(${tiltShift/elementWidth*100}% 0, 100% 0, 100% 100%, 0% 100%)`;
  } else {
    return `polygon(${tiltShift/elementWidth*100}% 0, 100% 0, ${100 - tiltShift/elementWidth*100}% 100%, 0% 100%)`;
  }
}