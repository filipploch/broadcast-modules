function activateElementsAfterTime(_elementsClassName, _time) {
  // Ustaw opóźnienie (np. 1 sekunda)
  setTimeout(function() {
    console.log('squad.js')
    // Wybierz wszystkie elementy z klasą "timeline-content"
    const elements = document.querySelectorAll(`.${_elementsClassName}`);
    elements.forEach(function(el) {
      // Przywróć domyślne wyświetlanie (lub ustaw odpowiednią wartość)
      // Dla tabel lepiej 'table', dla innych bloków 'block'
      if (el.tagName === 'TABLE') {
        el.style.display = 'table';
      } else {
        el.style.display = 'block';
      }
    });
  }, _time);
};