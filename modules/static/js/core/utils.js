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

function loadSvgIntoContainer(containerId, url, onLoad) {
    fetch(url)
        .then(r => r.text())
        .then(svgText => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(svgText, 'image/svg+xml');
            const svg = doc.querySelector('svg');
            if (!svg) return;
            svg.setAttribute('width', '100%');
            svg.removeAttribute('height');
            svg.style.display = 'block';
            const container = document.getElementById(containerId);
            if (container) {
                container.appendChild(svg);
                if (typeof onLoad === 'function') onLoad();
            }
        })
        .catch(err => console.warn(`SVG load failed for #${containerId}:`, err));
}

function parseColor(input) {
    if (!input) return 'transparent';
    const s = String(input).trim();
    if (/^rgba?\s*\(/i.test(s)) return s;
    const hexMatch = s.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (hexMatch) {
        let h = hexMatch[1];
        if (h.length === 3) h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
        const r = parseInt(h.slice(0, 2), 16);
        const g = parseInt(h.slice(2, 4), 16);
        const b = parseInt(h.slice(4, 6), 16);
        return `rgb(${r}, ${g}, ${b})`;
    }
    const tmp = document.createElement('div');
    tmp.style.color = s;
    document.body.appendChild(tmp);
    const resolved = getComputedStyle(tmp).color;
    document.body.removeChild(tmp);
    return resolved || s;
}

function colorizeSvgBody(_svgContainerId, color) {
    const svg = document.querySelector(`#${_svgContainerId} svg`);
    if (!svg) return;
    const el = svg.querySelector('#svg-body');
    if (!el) return;
    el.style.fill = parseColor(color);
}

function colorizeSvgBackground(_svgContainerId, color) {
    const svg = document.querySelector(`#${_svgContainerId} svg`);
    if (!svg) { console.warn(`[colorizeSvgBackground] no svg in #${_svgContainerId}`); return; }
    const el = svg.querySelector('#svg-background');
    if (!el) { console.warn(`[colorizeSvgBackground] no #svg-background in #${_svgContainerId}`); return; }
    const parsed = parseColor(color);
    console.log(`[colorizeSvgBackground] #${_svgContainerId} fill → ${parsed}`);
    el.style.fill = parsed;
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

function scaleScreen(){
    if(SCALE_DOWN){
        SCALE_DOWN = false;
        socket.emit('enable_scene_filter', {
          'source_name': 'STREAM',
          'filter_name': 'OutputScaleDown',
          'filter_state': true,
        });
    } else {
      SCALE_DOWN = true;
        socket.emit('enable_scene_filter', {
          'source_name': 'STREAM',
          'filter_name': 'OutputScaleUp',
          'filter_state': true,
        });
    }
}