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

// function animateWord(elementId, word, duration) {

//     // Walidacja parametrów
//     // if (typeof elementId !== 'string' || typeof word !== 'string' || typeof duration !== 'number' || typeof hexColor1 !== 'string' || typeof hexColor2 !== 'string') {
//     //     console.error('Nieprawidłowe typy parametrów');
//     //     return;
//     // }
//     const container = document.getElementById(elementId);
//     if (!container) {
//         console.error(`Element o id "${elementId}" nie istnieje.`);
//         return;
//     }
//     if (duration <= 0) {
//         console.warn('Czas trwania (duration) powinien być dodatni. Ustawiono wartość domyślną 300 ms.');
//         duration = 300;
//     }

//     // Usunięcie poprzedniej animacji, jeśli istnieje
//     if (window._currentAnimationTimeout) {
//         clearTimeout(window._currentAnimationTimeout);
//     }
//     if (window._currentAnimationInterval) {
//         clearInterval(window._currentAnimationInterval);
//     }

//     // Wyczyść zawartość kontenera
//     container.innerHTML = '';

//     // Stwórz główny kontener dla znaków
//     const wordContainer = document.createElement('div');
//     wordContainer.className = 'word-animation-container';
//     wordContainer.style.display = 'flex';
//     wordContainer.style.flexWrap = 'wrap';
//     wordContainer.style.justifyContent = 'end';
//     wordContainer.style.transition = 'opacity 0.5s ease'; // dla efektu znikania

//     // Przechowuj referencje do elementów (spanów z tekstem)
//     const charSpans = [];

//     // Dla każdego znaku stwórz ramkę i umieść w niej znak
//     for (let i = 0; i < word.length; i++) {
//         const char = word[i];

//         // Ramka dla pojedynczego znaku
//         const charBox = document.createElement('div');
//         charBox.className = 'char-box';
//         addClassName(charBox, 'char-box-0');
//         charBox.style.width = '140px';
//         charBox.style.height = '140px';
//         charBox.style.display = 'flex';
//         charBox.style.justifyContent = 'center';
//         charBox.style.alignItems = 'center';
//         charBox.style.fontSize = '110px'; // połowa wysokości ramki
//         charBox.style.transition = 'background-color 0.2s, color 0.2s';

//         // Wewnętrzny span, który będzie skalowany
//         const charSpan = document.createElement('span');
//         charSpan.textContent = char;
//         charSpan.style.display = 'inline-block';
//         charSpan.style.transition = 'transform 0.2s ease';
//         charSpan.style.transform = 'scale(1)';

//         charBox.appendChild(charSpan);
//         wordContainer.appendChild(charBox);
//         charSpans.push(charSpan);
//     }

//     container.appendChild(wordContainer);

//     // Jeśli słowo jest puste – nie ma co animować
//     if (word.length === 0) return;

//     // Zmienne pomocnicze
//     let currentIndex = 0;
//     let enlargeTimeout = null;

//     // Funkcja resetująca powiększenie dla danego znaku
//     function resetEnlargement(index) {
//         if (index >= 0 && index < charSpans.length) {
//             charSpans[index].style.transform = 'scale(1)';
//         }
//     }

//     // Funkcja powiększająca znak
//     function enlargeCharacter(index) {
//         if (index >= 0 && index < charSpans.length) {
//             charSpans[index].style.transform = 'scale(1.5)'; // powiększenie o 50%
//         }
//     }

//     // Sekwencja powiększania
//     function startEnlargementSequence() {
//         if (currentIndex >= word.length) {
//             // Zakończono powiększanie – najpierw przywróć ostatnią literę do skali 1
//             resetEnlargement(word.length - 1);
//             // Przejdź do zamiany kolorów
//             startColorSwapSequence();
//             return;
//         }

//         // Przywróć poprzedni znak
//         if (currentIndex > 0) {
//             resetEnlargement(currentIndex - 1);
//         }
//         // Powiększ bieżący
//         enlargeCharacter(currentIndex);

//         currentIndex++;
//         enlargeTimeout = setTimeout(startEnlargementSequence, duration);
//     }

//     // Sekwencja zamiany kolorów
//     let swapStep = 0;
//     let swapTimeout = null;

//     function swapColors() {
//         // Dla każdego elementu zamień background-color z color
//         const boxes = document.querySelectorAll(`#${elementId} .char-box`);
//         boxes.forEach(box => {
//           if(box.classList.contains('char-box-0')){
//             removeClassName(box, 'char-box-0');
//             addClassName(box, 'char-box-1');
//           }else{
//             removeClassName(box, 'char-box-1');
//             addClassName(box, 'char-box-0');
//           }
//         });
//     }

//     function startColorSwapSequence() {
//         if (swapStep >= 6) {
//             // Po zakończeniu 6 zamian kolorów uruchom efekt zniknięcia
//             if (swapTimeout) clearTimeout(swapTimeout);
//             if (enlargeTimeout) clearTimeout(enlargeTimeout);

//             // Efekt fade-out: ustaw przezroczystość na 0, po zakończeniu usuń kontener
//             wordContainer.style.opacity = '0';
//             const removeContainer = () => {
//                 if (wordContainer.parentNode) {
//                     wordContainer.remove();
//                 }
//                 // Wyczyść zapisy timeoutów
//                 window._currentAnimationTimeout = null;
//                 window._currentAnimationTimeoutSwap = null;
//             };
//             // Poczekaj na zakończenie przejścia (0.5s)
//             wordContainer.addEventListener('transitionend', removeContainer, { once: true });
//             // Opcjonalnie awaryjnie usuń po 0.6s, gdyby transitionend nie zadziałało
//             setTimeout(removeContainer, 600);
//             return;
//         }

//         swapColors();
//         swapStep++;
//         swapTimeout = setTimeout(startColorSwapSequence, duration);
//     }

//     // Rozpocznij od pierwszego znaku
//     currentIndex = 0;
//     startEnlargementSequence();

//     // Zapisz identyfikatory timeoutów do ewentualnego przerwania
//     window._currentAnimationTimeout = enlargeTimeout;
//     window._currentAnimationTimeoutSwap = swapTimeout;
// }

function animateWord(elementId, word, duration, elementToHideId) {

    // Walidacja parametrów
    // if (typeof elementId !== 'string' || typeof word !== 'string' || typeof duration !== 'number' || typeof hexColor1 !== 'string' || typeof hexColor2 !== 'string') {
    //     console.error('Nieprawidłowe typy parametrów');
    //     return;
    // }
    const container = document.getElementById(elementId);
    if (!container) {
        console.error(`Element o id "${elementId}" nie istnieje.`);
        return;
    }
    if (duration <= 0) {
        console.warn('Czas trwania (duration) powinien być dodatni. Ustawiono wartość domyślną 300 ms.');
        duration = 300;
    }

    // Ukryj element jeśli został podany
    let elementToHide = null;
    if (elementToHideId) {
        elementToHide = document.getElementById(elementToHideId);
        if (elementToHide) {
            elementToHide.style.visibility = 'hidden';
        } else {
            console.warn(`Element o id "${elementToHideId}" nie istnieje.`);
        }
    }

    // Usunięcie poprzedniej animacji, jeśli istnieje
    if (window._currentAnimationTimeout) {
        clearTimeout(window._currentAnimationTimeout);
    }
    if (window._currentAnimationInterval) {
        clearInterval(window._currentAnimationInterval);
    }

    // Wyczyść zawartość kontenera
    container.innerHTML = '';

    // Stwórz główny kontener dla znaków
    const wordContainer = document.createElement('div');
    wordContainer.className = 'word-animation-container';
    wordContainer.style.display = 'flex';
    wordContainer.style.flexWrap = 'wrap';
    wordContainer.style.justifyContent = 'end';
    wordContainer.style.transition = 'opacity 0.5s ease'; // dla efektu znikania

    // Przechowuj referencje do elementów (spanów z tekstem)
    const charSpans = [];

    // Dla każdego znaku stwórz ramkę i umieść w niej znak
    for (let i = 0; i < word.length; i++) {
        const char = word[i];

        // Ramka dla pojedynczego znaku
        const charBox = document.createElement('div');
        charBox.className = 'char-box';
        addClassName(charBox, 'char-box-0');
        charBox.style.width = '55px';
        charBox.style.height = '55px';
        charBox.style.display = 'flex';
        charBox.style.justifyContent = 'center';
        charBox.style.alignItems = 'center';
        charBox.style.fontSize = '40px'; // połowa wysokości ramki
        charBox.style.transition = 'background-color 0.2s, color 0.2s';

        // Wewnętrzny span, który będzie skalowany
        const charSpan = document.createElement('span');
        charSpan.textContent = char;
        charSpan.style.display = 'inline-block';
        charSpan.style.transition = 'transform 0.2s ease';
        charSpan.style.transform = 'scale(1)';

        charBox.appendChild(charSpan);
        wordContainer.appendChild(charBox);
        charSpans.push(charSpan);
    }

    container.appendChild(wordContainer);

    // Jeśli słowo jest puste – nie ma co animować
    if (word.length === 0) {
        // Przywróć widoczność elementu jeśli był ukryty
        if (elementToHide) {
            elementToHide.style.visibility = '';
        }
        return;
    }

    // Zmienne pomocnicze
    let currentIndex = 0;
    let enlargeTimeout = null;

    // Funkcja resetująca powiększenie dla danego znaku
    function resetEnlargement(index) {
        if (index >= 0 && index < charSpans.length) {
            charSpans[index].style.transform = 'scale(1)';
        }
    }

    // Funkcja powiększająca znak
    function enlargeCharacter(index) {
        if (index >= 0 && index < charSpans.length) {
            charSpans[index].style.transform = 'scale(1.5)'; // powiększenie o 50%
        }
    }

    // Sekwencja powiększania
    function startEnlargementSequence() {
        if (currentIndex >= word.length) {
            // Zakończono powiększanie – najpierw przywróć ostatnią literę do skali 1
            resetEnlargement(word.length - 1);
            // Przejdź do zamiany kolorów
            startColorSwapSequence();
            return;
        }

        // Przywróć poprzedni znak
        if (currentIndex > 0) {
            resetEnlargement(currentIndex - 1);
        }
        // Powiększ bieżący
        enlargeCharacter(currentIndex);

        currentIndex++;
        enlargeTimeout = setTimeout(startEnlargementSequence, duration);
    }

    // Sekwencja zamiany kolorów
    let swapStep = 0;
    let swapTimeout = null;

    function swapColors() {
        // Dla każdego elementu zamień background-color z color
        const boxes = document.querySelectorAll(`#${elementId} .char-box`);
        boxes.forEach(box => {
          if(box.classList.contains('char-box-0')){
            removeClassName(box, 'char-box-0');
            addClassName(box, 'char-box-1');
          }else{
            removeClassName(box, 'char-box-1');
            addClassName(box, 'char-box-0');
          }
        });
    }

    function startColorSwapSequence() {
        if (swapStep >= 6) {
            // Po zakończeniu 6 zamian kolorów uruchom efekt zniknięcia
            if (swapTimeout) clearTimeout(swapTimeout);
            if (enlargeTimeout) clearTimeout(enlargeTimeout);

            // Efekt fade-out: ustaw przezroczystość na 0, po zakończeniu usuń kontener
            wordContainer.style.opacity = '0';
            const removeContainer = () => {
                if (wordContainer.parentNode) {
                    wordContainer.remove();
                }
                // Przywróć widoczność ukrytego elementu
                if (elementToHide) {
                    elementToHide.style.visibility = '';
                }
                // Wyczyść zapisy timeoutów
                window._currentAnimationTimeout = null;
                window._currentAnimationTimeoutSwap = null;
            };
            // Poczekaj na zakończenie przejścia (0.5s)
            wordContainer.addEventListener('transitionend', removeContainer, { once: true });
            // Opcjonalnie awaryjnie usuń po 0.6s, gdyby transitionend nie zadziałało
            setTimeout(removeContainer, 600);
            return;
        }

        swapColors();
        swapStep++;
        swapTimeout = setTimeout(startColorSwapSequence, duration);
    }

    // Rozpocznij od pierwszego znaku
    currentIndex = 0;
    startEnlargementSequence();

    // Zapisz identyfikatory timeoutów do ewentualnego przerwania
    window._currentAnimationTimeout = enlargeTimeout;
    window._currentAnimationTimeoutSwap = swapTimeout;
}