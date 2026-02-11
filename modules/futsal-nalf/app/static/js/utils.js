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

function enableElementToEdit(element) {
    element.removeAttribute("readonly");
    element.style.background = "#fff";
    element.style.cursor = "text";
    element.focus();
    element.select();
    element.onblur = function() {
        this.setAttribute("readonly", "readonly");
        this.style.background = "#f8f9fa";
        this.style.cursor = "pointer";
    };
}