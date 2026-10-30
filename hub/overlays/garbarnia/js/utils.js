// W7f-null: wartość do wyświetlenia na ekranie. null, undefined, NaN oraz teksty dokładnie "null", "undefined", "NaN" i "None" (cały tekst pola, wielkość liter
// jak podano, bez przycinania fragmentów dłuższych tekstów) dają "". Wszystko inne (w tym 0 i false) przechodzi bez zmian. Identyczna w obu nakładkach.
function displayText(value) {
    if (value === null || value === undefined) { return ""; }
    if (typeof value === "number" && isNaN(value)) { return ""; }
    if (value === "null" || value === "undefined" || value === "NaN" || value === "None") { return ""; }
    return value;
}

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

// Minuta zdarzenia (reguła właściciela: docs/regula-minuty.md; przypadki: tests/modules/js/minuta_przypadki.json). Czasy w sekundach zegara meczu.
//   t <= S (pierwsza chwila okresu albo czas sprzed jego początku): S/60 + 1   (0:00 -> 1', początek 2. połowy 45:00 -> 46', NALF 20:00 -> 21')
//   S < t <= E:                                                     ceil(t/60) (dokładny koniec okresu zostaje w okresie: 45:00 -> 45')
//   t > E (doliczony czas, tylko Garbarnia):                        E/60 + k', k = ceil((t - E)/60)   (45:05 -> 45+1', 46:01 -> 45+2')
// periodStartS jest opcjonalny: gdy go brak w danych (stary ładunek), zachowanie jak dotąd (bez wyjątku pierwszej chwili okresu).
function formatGameTimeDisplay(gameTimeS, periodEndS, periodStartS) {
    if (typeof gameTimeS !== "number" || !isFinite(gameTimeS)) { return ""; }      // W7f-null: brak czasu to pusty tekst, nie "NaN'"
    var maStart = typeof periodStartS === "number" && isFinite(periodStartS) && periodStartS >= 0;
    if (maStart && gameTimeS <= periodStartS) {
        return (Math.floor(periodStartS / 60) + 1) + "'";
    }
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