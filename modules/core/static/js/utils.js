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

function updateObsRecordingIndicator(responseData) {
    const _obsRecordingIndicator = document.getElementById('obs-recording-indicator');
    const _obsRecordingIndicatorIcon = _obsRecordingIndicator.querySelector('img');
    if(responseData.outputActive === true) {
        removeClassName(_obsRecordingIndicatorIcon, 'filter-yellow');
        addClassName(_obsRecordingIndicatorIcon, 'filter-green');
    }else{
        removeClassName(_obsRecordingIndicatorIcon, 'filter-green');
        removeClassName(_obsRecordingIndicatorIcon, 'filter-yellow');
    }
}

function updateRecordingIndicators(cameras) {
  for (let cameraKey in cameras) {
    const camera = cameras[cameraKey];
    const element = document.querySelector(`.recording-indicator[data-camera-id="${cameraKey}"]`);

  if (!element) continue;

  const elementImg = element.querySelector('img');

  if (camera.is_recording === true) {
    removeClassName(element, 'important_bg_orange');
    addClassName(element, 'important_bg_black');
    addClassName(elementImg, 'filter-red');
  } else {
    removeClassName(element, 'important_bg_orange');
    removeClassName(element, 'important_bg_black');
    removeClassName(elementImg, 'filter-red');
  }
}}

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

function setMultiColorBackground(elementId, colors) {
  const el = document.getElementById(elementId);
  if (!el || !Array.isArray(colors) || colors.length === 0) return;

  const n = colors.length;
  const step = 100 / n;

  const stops = colors.map((color, i) => {
    const start = i * step;
    const end = (i + 1) * step;
    return `${color} ${start}%, ${color} ${end}%`;
  });

  el.style.background = `linear-gradient(to right, ${stops.join(", ")})`;
}

function applyReversedState(isReversed) {
    document.querySelectorAll('.reversible').forEach(function(el) {
        var children = Array.from(el.children);
        if (children.length < 2) return;

        var anchor = children.find(function(c) {
            return c.hasAttribute('data-reverse-anchor');
        });
        if (!anchor) return;

        var anchorIsFirst = children[0] === anchor;
        var shouldFlip = (isReversed && anchorIsFirst) || (!isReversed && !anchorIsFirst);

        if (shouldFlip) {
            children.reverse().forEach(function(c) {
                el.appendChild(c);
            });
        }
    });

    appState.isReversed = isReversed;
}

function changeGameValue(valueType, teamType, value) {
   socket.emit('change_game_value', {value_type: valueType, team_type: teamType, value: value});
}

