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