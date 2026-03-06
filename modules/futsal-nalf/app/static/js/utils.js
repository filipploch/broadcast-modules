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

function convertToClassName(str) {
    const polishMap = {
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
        'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
        'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N',
        'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z'
    };
    
    return str
        .split('')
        .map(char => polishMap[char] || char)
        .join('')
        .replace(/[^\w\s-]/g, '')
        .replace(/\s+/g, '-')
        .toLowerCase();
}

function updateCamerasIndicators(camerasDict) {
    for (let cameraId in camerasDict) {
        if (camerasDict.hasOwnProperty(cameraId)) {
            const cameraInfo = camerasDict[cameraId];
            const element = document.querySelector(`.recording-indicator[data-camera-id="${cameraId}"]`);
            const elementImg = element.querySelector('img');
            console.log(cameraInfo['succes']);
            console.log(elementImg);
            
            if (element) {
              if (cameraInfo['succes'] === true ){
                if(cameraInfo['is_recording'] === true){
                  removeClassName(element, 'important_bg_orange');
                  addClassName(element, 'important_bg_black');
                  addClassName(elementImg, 'filter-red');
                }else{
                  removeClassName(element, 'important_bg_orange');
                  removeClassName(element, 'important_bg_black');
                  removeClassName(elementImg, 'filter-red');
                }      
              } else {
                removeClassName(element, 'important_bg_black');
                removeClassName(elementImg, 'filter-red');
                addClassName(element, 'important_bg_orange');
              }
            }
        }
    }
}