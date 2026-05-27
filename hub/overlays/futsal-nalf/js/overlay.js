// WebSocket z rejestracją jako overlay + subskrypcja timer
const overlayId = 'stream-overlay';
const ws = new WebSocket(`ws://${window.location.hostname}:${window.location.port}/ws`);

const rootApp = 'http://localhost:8081/';

const display = document.getElementById('main-timer-display');

let registered = false;

var homeTeamScoreElement = document.getElementById('home-team-score');
var awayTeamScoreElement = document.getElementById('away-team-score');
var homeTeamFoulsElement = document.getElementById('home-team-fouls');
var awayTeamFoulsElement = document.getElementById('away-team-fouls');

function showTransition() {
    let gameContainer = document.querySelector('#game-container');
    let oldTransition = document.querySelector('#game-transition');

    // Usuń stary element całkowicie
    if (oldTransition) {
        oldTransition.remove();
    }

    // Stwórz nowy od zera
    let transitionElement = document.createElement('div');
    transitionElement.id = 'game-transition';
    addClassName(transitionElement, 'game-container-element');

    let image = document.createElement('img');
    // Dodaj timestamp, żeby uniknąć cache
    const baseUrl = 'http://localhost:8081/static/video/transitions/league_transition.gif';
    image.src = `${baseUrl}?t=${Date.now()}`;

    transitionElement.appendChild(image);
    gameContainer.appendChild(transitionElement);

    // Pokaż od razu
    transitionElement.style.display = 'block';

    setTimeout(() => {
        transitionElement.style.display = 'none';
    }, 1450);
}

function getContainerType(container) {
    // Określ typ kontenera na podstawie jego klas
    const classList = container.classList;

    if (classList.contains('start-container')) return 'start';
    if (classList.contains('squad-container')) return 'squad';
    if (classList.contains('break-container')) return 'break';
    if (classList.contains('game-container')) return 'game';
    if (classList.contains('shootout-container')) return 'shootout';
    if (classList.contains('results-container')) return 'results';
    if (classList.contains('virtual-table-container')) return 'virtual-table';
    if (classList.contains('table-container')) return 'table';

    // Domyślny typ
    return 'none';
}

function showContainer(_data) {
    let containerId = _data.container_id;

    // Pobierz wszystkie kontenery
    // const containers = document.querySelectorAll('.overlay-container');
    // let activeContainer = null;
    let targetContainer = document.getElementById(containerId);

    // Walidacja
    if (!targetContainer) {
        console.error(`Kontener o ID "${containerId}" nie istnieje`);
        return;
    }

    const containerType = getContainerType(targetContainer);

    let delayTime = 2000;
    if (containerType === 'none') {
        prepareToOpenContainer();
    } else if (containerType === 'squad') {
        let teamName = _data.team_name;
        let teamShortName = _data.team_short_name;
        let teamSquad = _data.team_squad;
        let teamLogo = _data.logo;
        let teamCoach;
        if (_data.coach !== 'undefined') { teamCoach = _data.coach; } else { teamCoach = null; }
        expandSquadContainer(containerId, teamName, teamShortName, teamSquad, teamLogo, teamCoach);
        let addedDelayTime = prepareToOpenContainer(openContainer, targetContainer);
        delayTime += addedDelayTime;
        activateElementsAfterTime('squad-content', delayTime);
    } else if (containerType === 'start') {
        expandStartContainer(_data);
        prepareToOpenContainer(openContainer, targetContainer);
        activateElementsAfterTime('start-content', 2500, 'flex');
    } else if (containerType === 'break') {
        expandStartContainer(_data, true);
        prepareToOpenContainer(openContainer, targetContainer);
        activateElementsAfterTime('break-content', 2500, 'flex');
    } else if (containerType === 'shootout') {
        expandShootoutContainer(_data);
        prepareToOpenContainer(openContainer, targetContainer);
        // activateElementsAfterTime('break-content', 2500, 'flex');
    } else if (containerType === 'results') {
        expandResultsContainer(_data);
        prepareToOpenContainer(openContainer, targetContainer);
    } else if (containerType === 'table') {
        expandTableContainer(_data);
        prepareToOpenContainer(openContainer, targetContainer);
    } else if (containerType === 'virtual-table') {
        expandVirtualTableContainer(_data);
        prepareToOpenContainer(openContainer, targetContainer);
    } else {
        prepareToOpenContainer(openContainer, targetContainer);
    }

}

function prepareToOpenContainer(callback, param) {
    let delayTime = 0;
    let overlayContainers = document.querySelectorAll('.overlay-container');
    overlayContainers.forEach(cont => {
        if (cont.style.display !== 'none') {
            closeContainer(cont);
            console.log('cont none');
            // cont.style.display = 'none';
            delayTime = 1000;
        }
    });
    setTimeout(() => {
        if (callback) callback(param);
    }, delayTime);
    return delayTime;
}

function openContainer(container) {
    container.style.display = 'flex';
}

function closeContainer(_container) {
    let container = _container;
    let containerType = getContainerType(container);
    let animationDuration = 1000;

    console.log(`containerType: ${containerType}`);
    switch (containerType) {
        case 'squad':
            closeSquadContainer(container);
            console.log('closeSquadContainer()');
            break;
        case 'start':
            closeStartContainer(container);
            console.log('closeStartContainer()');
            break;
        case 'break':
            closeBreakContainer(container);
            console.log('closeBreakContainer()');
            break;
        case 'results':
            closeResultsContainer(container);
            console.log('closeResultsContainer()');
            break;
        case 'table':
            closeTableContainer(container);
            console.log('closeTableContainer()');
            break;
        case 'virtual-table':
            if (_resultsTimer2 !== null) { clearTimeout(_resultsTimer2); _resultsTimer2 = null; }
            closeVirtualTableContainer(container);
            console.log('closeVirtualTableContainer()');
            break;
        default:
            closeDefaultContainer(container);
            console.log('closeDefaultContainer()');
            break;
    }

    // Wyczyść animacje po ich zakończeniu
    setTimeout(() => {
        // Usuń tymczasowe animacje
        clearAnimations(container);
        container.style.display = 'none';
    }, animationDuration);
}

// ── WYNIKI / TABELA ──────────────────────────────────────────────────────

var _resultsTimer = null;   // guard przed wielokrotnym wywołaniem
var _resultsTimer2 = null;  // timer animacji zamiany (virtual_table)

// ── Budowanie DOM ─────────────────────────────────────────────────────────

function buildResultsContent(resultsEl, games, overlayContainer = false) {
    // Filtrowanie: tylko mecze z liczbowymi wynikami obu drużyn
    resultsEl.innerHTML = '';
    if (!overlayContainer) {
        let header = document.createElement('div');
        header.id = 'results-header';
        header.className = 'results-row rotate-show-element0';
        header.textContent = 'WYNIKI';
        resultsEl.appendChild(header);
    }
    games.forEach((game, index) => {
        let row = document.createElement('div');
        const statusClass = game.status === 2 ? 'finished' : 'pending';
        row.className = `results-row rotate-show-element${index + 1} ${statusClass}`;
        if (overlayContainer) {
            addClassName(row, 'overlay-container-element');
            row.style.animationDelay = `${index * 250 + 2000}ms`;
        }
        let homeName = document.createElement('div');
        homeName.className = 'results-home-team-name14 results-team-name14';
        homeName.textContent = game.home_team_name14;

        let homeResult = document.createElement('div');
        homeResult.className = 'results-home-team-result results-team-result';
        homeResult.textContent = game.home_team_goals;

        let separator = document.createElement('div');
        separator.className = 'results-separator';
        separator.textContent = ':';

        let awayResult = document.createElement('div');
        awayResult.className = 'results-away-team-result results-team-result';
        awayResult.textContent = game.away_team_goals;

        let awayName = document.createElement('div');
        awayName.className = 'results-away-team-name14 results-team-name14';
        awayName.textContent = game.away_team_name14;

        row.appendChild(homeName);
        row.appendChild(homeResult);
        row.appendChild(separator);
        row.appendChild(awayResult);
        row.appendChild(awayName);
        resultsEl.appendChild(row);
    });
}

function buildTableContent(resultsEl, rows, headerText, overlayContainer = false) {
    resultsEl.innerHTML = '';
    if (!overlayContainer) {
        let header = document.createElement('div');
        header.id = 'table-header';
        header.className = 'results-row rotate-show-element0';
        header.textContent = headerText;
        resultsEl.appendChild(header);
    } else {
        // Sub-header z etykietami kolumn (tylko w trybie pełnoekranowym)
        let subHeader = document.createElement('div');
        subHeader.className = 'results-row results-row--subheader rotate-show-element0';
        subHeader.style.animationDelay = '1750ms';
        subHeader.style.fontSize = '30px';
        subHeader.innerHTML =
            '<div class="results-standing"></div>' +
            '<div class="results-name14 results-name14--wide"></div>' +
            '<div class="results-stat">M</div>' +
            '<div class="results-stat">W</div>' +
            '<div class="results-stat">R</div>' +
            '<div class="results-stat">P</div>' +
            '<div class="results-stat">GZ</div>' +
            '<div class="results-stat">GS</div>' +
            '<div class="results-stat">BR</div>' +
            '<div class="results-points">Pkt</div>';
        resultsEl.appendChild(subHeader);
    }

    rows.forEach((row, index) => {
        let el = document.createElement('div');
        el.className = `results-row rotate-show-element${index + 2}`;
        if (overlayContainer) {
            addClassName(el, 'overlay-container-element');
            el.style.animationDelay = `${index * 250 + 2000}ms`;
        }
        el.dataset.teamName14 = row.team_name14;

        if (overlayContainer) {
            const gd = row.goal_difference > 0 ? '+' + row.goal_difference : row.goal_difference;
            el.innerHTML =
                `<div class="results-standing">${index + 1}</div>` +
                `<div class="results-name14 results-name14--wide">${row.team_name14}</div>` +
                `<div class="results-stat">${row.games  ?? ''}</div>` +
                `<div class="results-stat">${row.wins   ?? ''}</div>` +
                `<div class="results-stat">${row.draws  ?? ''}</div>` +
                `<div class="results-stat">${row.loses  ?? ''}</div>` +
                `<div class="results-stat">${row.goals_scored ?? ''}</div>` +
                `<div class="results-stat">${row.goals_lost  ?? ''}</div>` +
                `<div class="results-stat">${gd ?? ''}</div>` +
                `<div class="results-points">${row.points}</div>`;
        } else {
            let diff = document.createElement('div');
            diff.className = 'results-difference';
            diff.textContent = '';

            let standing = document.createElement('div');
            standing.className = 'results-standing';
            standing.textContent = index + 1;

            let name = document.createElement('div');
            name.className = 'results-name14';
            name.textContent = row.team_name14;

            let pts = document.createElement('div');
            pts.className = 'results-points';
            pts.textContent = row.points;

            el.appendChild(diff);
            el.appendChild(standing);
            el.appendChild(name);
            el.appendChild(pts);
        }
        resultsEl.appendChild(el);
    });
}

// ── Zamknięcie kontenera ─────────────────────────────────────────────────

function closeResultsTableContainer(container, onDone, { skipRowAnimation = false } = {}) {
    let rows = container.querySelectorAll('.results-row');
    if (!skipRowAnimation) {
        rows.forEach(row => {
            row.style.animation = 'rotateHideElement 250ms ease 0ms 1 reverse both';
        });
    }
    let body = container.querySelector('.results');
    if (body) {
        body.style.setProperty('animation', 'collapseHeight', 'important');
        body.style.animationDuration = '750ms';
        body.style.animationDelay = skipRowAnimation ? '0ms' : '250ms';
        body.style.animationFillMode = 'both';
    }
    const cleanupDelay = skipRowAnimation ? 750 : 1000;
    setTimeout(() => {
        container.style.display = 'none';
        rows.forEach(r => { r.style.animation = ''; r.style.transform = ''; });
        if (body) {
            body.style.animation = '';
            body.style.animationDuration = '';
            body.style.animationDelay = '';
            body.style.animationFillMode = '';
        }
        if (onDone) onDone();
    }, cleanupDelay);
}

// ── Tryb gry (inside game-container) ─────────────────────────────────────

function buildResultsContentGame(resultsEl, games) {
    resultsEl.innerHTML = '';
    resultsEl.classList.add('results--horizontal');

    const count = games.length;
    const cols = count <= 3 ? 1 : count <= 8 ? 2 : 3;
    const hGap = 20;
    const margin = 40;
    const colWidth = Math.floor((document.body.offsetWidth - 2 * margin) / 3);

    let header = document.createElement('div');
    header.id = 'results-header';
    header.className = 'results-header--horizontal rotate-show-element0';
    header.textContent = 'WYNIKI';
    resultsEl.appendChild(header);

    const rowCount = Math.ceil(count / cols);
    let grid = document.createElement('div');
    grid.className = 'results-grid';
    grid.style.gridAutoFlow = 'column';
    grid.style.gridTemplateRows = `repeat(${rowCount}, auto)`;
    grid.style.columnGap = `${hGap}px`;

    games.forEach((game, index) => {
        let row = document.createElement('div');
        const statusClass = game.status === 2 ? 'finished' : 'pending';
        row.className = `results-row rotate-show-element${index + 1} ${statusClass}`;

        let homeName = document.createElement('div');
        homeName.className = 'results-home-team-name14 results-team-name14';
        homeName.textContent = game.home_team_name14;

        let homeResult = document.createElement('div');
        homeResult.className = 'results-home-team-result results-team-result';
        homeResult.textContent = game.home_team_goals ?? '-';

        let separator = document.createElement('div');
        separator.className = 'results-separator';
        separator.textContent = ':';

        let awayResult = document.createElement('div');
        awayResult.className = 'results-away-team-result results-team-result';
        awayResult.textContent = game.away_team_goals ?? '-';

        let awayName = document.createElement('div');
        awayName.className = 'results-away-team-name14 results-team-name14';
        awayName.textContent = game.away_team_name14;

        row.appendChild(homeName);
        row.appendChild(homeResult);
        row.appendChild(separator);
        row.appendChild(awayResult);
        row.appendChild(awayName);
        grid.appendChild(row);
    });

    resultsEl.appendChild(grid);
}

function buildTableContentHorizontal(resultsEl, rows, headerText) {
    resultsEl.innerHTML = '';
    resultsEl.classList.add('results--horizontal');

    let header = document.createElement('div');
    header.id = 'table-header';
    header.className = 'results-header--horizontal rotate-show-element0';
    header.textContent = headerText;
    resultsEl.appendChild(header);

    let cellsRow = document.createElement('div');
    cellsRow.className = 'results-cells-row';

    rows.forEach((row, index) => {
        let cell = document.createElement('div');
        cell.className = `results-cell rotate-show-element${index + 1}`;
        cell.dataset.teamName14 = row.team_name14;

        let standing = document.createElement('div');
        standing.className = 'results-cell-standing';
        standing.textContent = index + 1;

        let name = document.createElement('div');
        name.className = 'results-cell-name';
        name.textContent = row.team_short_name || row.team_name14;

        let pts = document.createElement('div');
        pts.className = 'results-cell-points';
        pts.textContent = row.points;

        cell.appendChild(standing);
        cell.appendChild(name);
        cell.appendChild(pts);
        cellsRow.appendChild(cell);
    });

    resultsEl.appendChild(cellsRow);
}

function animateTableSwapHorizontal(container, officialRows, virtualRows) {
    const cellEls = Array.from(container.querySelectorAll('.results-cell'));
    const indexMap = {};
    cellEls.forEach((el, i) => { indexMap[el.dataset.teamName14] = i; });

    virtualRows.forEach((itemB, indexB) => {
        const indexA = indexMap[itemB.team_name14];
        if (indexA === undefined) return;
        const el = cellEls[indexA];

        const ptsEl = el.querySelector('.results-cell-points');
        if (ptsEl) ptsEl.textContent = itemB.points;
        const standingEl = el.querySelector('.results-cell-standing');
        if (standingEl) standingEl.textContent = indexB + 1;

        if (indexA !== indexB) {
            const translateX = (indexB - indexA) * el.offsetWidth;
            el.style.animation = 'none';
            el.style.transform = 'translateX(0px)';
            void el.offsetWidth;
            el.style.transform = `translateX(${translateX}px)`;
            el.classList.remove('promotion', 'degradation');
            if (indexB < indexA) el.classList.add('promotion');
            else el.classList.add('degradation');
        }
    });
}

// ── Animacja zamiany pozycji (virtual_table) ──────────────────────────────

function animateTableSwap(container, officialRows, virtualRows) {
    const rowEls = Array.from(container.querySelectorAll('[data-team-name14]'));
    const indexMap = {};
    rowEls.forEach((el, i) => { indexMap[el.dataset.teamName14] = i; });

    virtualRows.forEach((itemB, indexB) => {
        const indexA = indexMap[itemB.team_name14];
        if (indexA === undefined) return;
        const el = rowEls[indexA];

        const ptsEl = el.querySelector('.results-points');
        if (ptsEl) ptsEl.textContent = itemB.points;
        const standingEl = el.querySelector('.results-standing');
        if (standingEl) standingEl.textContent = indexB + 1;

        if (indexA !== indexB) {
            const translateY = (indexB - indexA) * el.offsetHeight;
            el.style.animation = 'none';
            el.style.transform = 'translateY(0px)';
            void el.offsetWidth;
            el.style.transform = `translateY(${translateY}px)`;
            el.classList.remove('promotion', 'degradation');
            if (indexB < indexA) el.classList.add('promotion');
            else el.classList.add('degradation');
        }
    });
}

// ── Główna funkcja wyświetlania ───────────────────────────────────────────

function showInResultsTableContainer(type, payload) {
    const container = document.getElementById('results-table-container');
    if (!container) {
        console.warn('[overlay] Brak #results-table-container w DOM');
        return;
    }

    // Anuluj ewentualne poprzednie timery
    if (_resultsTimer !== null) { clearTimeout(_resultsTimer); _resultsTimer = null; }
    if (_resultsTimer2 !== null) { clearTimeout(_resultsTimer2); _resultsTimer2 = null; }
    container.style.display = 'none';

    const headerText = (type === 'results') ? 'WYNIKI' : 'TABELA';

    if (type === 'results') {
        const games = (payload && payload.games) || [];
        container.querySelectorAll('.results').forEach(el => {
            buildResultsContentGame(el, games);
        });
        container.style.display = 'flex';
        _resultsTimer = setTimeout(() => {
            _resultsTimer = null;
            closeResultsTableContainer(container, null);
        }, 20000);

    } else if (type === 'table') {
        const rows = (payload && payload.rows) || [];
        container.querySelectorAll('.results').forEach(el => {
            buildTableContentHorizontal(el, rows, headerText);
        });
        container.style.display = 'flex';
        _resultsTimer = setTimeout(() => {
            _resultsTimer = null;
            closeResultsTableContainer(container, null);
        }, 20000);

    } else if (type === 'virtual_table') {
        const official = (payload && payload.official) || [];
        const virtual = (payload && payload.virtual) || [];

        // t=0: pokaż tabelę finished
        container.querySelectorAll('.results').forEach(el => {
            buildTableContentHorizontal(el, official, headerText);
        });
        container.style.display = 'flex';

        // t=8000ms: animacja zamiany na virtual
        _resultsTimer2 = setTimeout(() => {
            _resultsTimer2 = null;
            container.querySelectorAll('.results').forEach(el => {
                animateTableSwapHorizontal(el, official, virtual);
            });
        }, 8000);

        // t=20000ms: zamknięcie — scaleY bez animacji per wiersz
        _resultsTimer = setTimeout(() => {
            _resultsTimer = null;
            closeResultsTableContainer(container, null, { skipRowAnimation: true });
        }, 20000);
    }
}

// ── KONIEC WYNIKI / TABELA ────────────────────────────────────────────────

function closeSquadContainer(container) {
    let logo = container.querySelector('img');
    let players = container.querySelectorAll('.squad-player-row');
    let infoBody = container.querySelector('.info-body');
    let infoHead = container.querySelector('.info-head');
    logo.style.animation = `fadeOut 250ms ease both`;
    players.forEach(player => {
        player.style.animation = `rotateHideElement 250ms ease 0ms 1 reverse both`;
    });
    infoBody.style.setProperty('animation', 'fadeOut', 'important');
    infoBody.style.animationDuration = '750ms';
    infoBody.style.animationDelay = '250ms';
    infoBody.style.animationFillMode = 'both';
    infoHead.style.animation = 'rotateHideElement 250ms ease 750ms 1 reverse both';
}

function closeStartContainer(container) {
    // Trzy grafiki: herby drużyn i logo ligi → fadeOut
    let logos = container.querySelectorAll('#start-home-team-logo img, #start-league-logo img, #start-away-team-logo img');
    logos.forEach(logo => {
        logo.style.animation = `fadeOut 250ms ease both`;
    });
    // Elementy rotate (nazwy drużyn) → rotateHideElement reverse
    let rotateElements = container.querySelectorAll('.rotate-show-element1');
    rotateElements.forEach(el => {
        el.style.animation = `rotateHideElement 250ms ease 0ms 1 reverse both`;
    });
    // Body → collapseHeight
    let startBody = container.querySelector('.start-body');
    if (startBody) {
        startBody.style.setProperty('animation', 'collapseHeight', 'important');
        startBody.style.animationDuration = '750ms';
        startBody.style.animationDelay = '250ms';
        startBody.style.animationFillMode = 'both';
    }
    // Head → rotateHideElement reverse
    let infoHead = container.querySelector('.info-head');
    if (infoHead) {
        infoHead.style.animation = 'rotateHideElement 250ms ease 750ms 1 reverse both';
    }
}

function closeBreakContainer(container) {
    // Dwa herby drużyn + wynik (zastąpił logo ligi) → fadeOut
    let logos = container.querySelectorAll('#start-home-team-logo img, #start-away-team-logo img');
    logos.forEach(logo => {
        logo.style.animation = `fadeOut 250ms ease both`;
    });
    let result = container.querySelector('#start-league-logo');
    if (result) {
        result.style.animation = `fadeOut 250ms ease both`;
    }
    // Wiersze strzelców → rotateHideElement reverse
    let scorerRows = container.querySelectorAll('.break-scorer-element');
    scorerRows.forEach(row => {
        row.style.animation = `rotateHideElement 250ms ease 0ms 1 reverse both`;
    });
    // Body → collapseHeight
    let startBody = container.querySelector('.start-body');
    if (startBody) {
        startBody.style.setProperty('animation', 'collapseHeight', 'important');
        startBody.style.animationDuration = '750ms';
        startBody.style.animationDelay = '250ms';
        startBody.style.animationFillMode = 'both';
    }
    // Head → rotateHideElement reverse
    let infoHead = container.querySelector('.info-head');
    if (infoHead) {
        infoHead.style.animation = 'rotateHideElement 250ms ease 750ms 1 reverse both';
    }
}

function closeResultsContainer(container) {
    let rows = container.querySelectorAll('.results-row');
    rows.forEach(row => {
        row.style.animation = 'rotateHideElement 250ms ease 0ms 1 reverse both';
    });
    let body = container.querySelector('.info-body');
    if (body) {
        body.style.setProperty('animation', 'collapseHeight', 'important');
        body.style.animationDuration = '750ms';
        body.style.animationDelay = '250ms';
        body.style.animationFillMode = 'both';
    }
    let infoHead = container.querySelector('.info-head');
    if (infoHead) {
        infoHead.style.animation = 'rotateHideElement 250ms ease 750ms 1 reverse both';
    }
}

function closeTableContainer(container) {
    let rows = container.querySelectorAll('.results-row');
    rows.forEach(row => {
        row.style.animation = 'rotateHideElement 250ms ease 0ms 1 reverse both';
    });
    let body = container.querySelector('.info-body');
    if (body) {
        body.style.setProperty('animation', 'collapseHeight', 'important');
        body.style.animationDuration = '750ms';
        body.style.animationDelay = '250ms';
        body.style.animationFillMode = 'both';
    }
    let infoHead = container.querySelector('.info-head');
    if (infoHead) {
        infoHead.style.animation = 'rotateHideElement 250ms ease 750ms 1 reverse both';
    }
}

function closeVirtualTableContainer(container) {
    const rowEls = Array.from(container.querySelectorAll('[data-team-name14]'));

    if (rowEls.length > 0) {
        const parent = rowEls[0].parentNode;

        // Oblicz aktualne pozycje wizualne (naturalny offsetTop + translateY z animateTableSwap)
        const withPos = rowEls.map(el => {
            const m = (el.style.transform || '').match(/translateY\(([-\d.]+)px\)/);
            const ty = m ? parseFloat(m[1]) : 0;
            return { el, visualTop: el.offsetTop + ty };
        });
        withPos.sort((a, b) => a.visualTop - b.visualTop);

        // Przearanżuj DOM do porządku wirtualnego i wyzeruj transform —
        // rzędy wizualnie stoją w tym samym miejscu, ale już bez translateY
        withPos.forEach(({ el }) => {
            el.style.transform = '';
            el.classList.remove('promotion', 'degradation');
            parent.appendChild(el);
        });
    }

    // Identyczna animacja jak closeTableContainer()
    container.querySelectorAll('.results-row').forEach(row => {
        row.style.animation = 'rotateHideElement 250ms ease 0ms 1 reverse both';
    });
    const body = container.querySelector('.info-body');
    if (body) {
        body.style.setProperty('animation', 'collapseHeight', 'important');
        body.style.animationDuration = '750ms';
        body.style.animationDelay = '250ms';
        body.style.animationFillMode = 'both';
    }
    const infoHead = container.querySelector('.info-head');
    if (infoHead) {
        infoHead.style.animation = 'rotateHideElement 250ms ease 750ms 1 reverse both';
    }
}

function closeDefaultContainer(container) {
    container.style.animation = `fadeOut 500ms ease forwards`;
}

function clearAnimations(container) {
    // Usuń animacje z głównego kontenera
    container.style.animation = '';

    // Usuń animacje ze wszystkich dzieci
    const allElements = container.querySelectorAll('*');
    allElements.forEach(element => {
        element.style.animation = '';
        element.style.animationDelay = '';
    });
}

function expandStartBottomSpecificContainer(_headerText, _arr) {
    let html = '';
    if (_arr.length === 0) {
        return html;
    } else {
        let header = `
                <div class="start-bottom-header specific-colors">${_headerText}</div>
            `;
        html += header;
        _body = '';
        _arr.forEach(el => {
            let _bodyElement = `<div class="start-bottom-body">${el.name}</div>`;
            _body += _bodyElement;
        });
        html += _body;
        return html;
    }
}

function expandStartBottomInfoContainer(_gameData) {
    let wrapper = document.createElement('div');
    wrapper.id = 'start-bottom-info-container';
    let currentDate = getCurrentDate();
    let stadium = _gameData.stadium;
    let commentators = _gameData.commentators;
    let referees = _gameData.referees;
    let dateAndStadiumContainer = document.createElement('div');
    addClassName(dateAndStadiumContainer, 'start-bottom-info-element');
    dateAndStadiumContainer.style.animationDelay = '2000ms';
    let refereesContainer = document.createElement('div');
    addClassName(refereesContainer, 'start-bottom-info-element');
    refereesContainer.style.animationDelay = '9000ms';
    let commentatorsContainer = document.createElement('div');
    addClassName(commentatorsContainer, 'start-bottom-info-element');
    commentatorsContainer.style.animationDelay = '16000ms';
    let redereesContainerHeadText = 'Arbiter';
    if (referees.length > 1) redereesContainerHeadText = 'Sędziowie';
    refereesContainer.innerHTML = expandStartBottomSpecificContainer(redereesContainerHeadText, referees);
    commentatorsContainer.innerHTML = expandStartBottomSpecificContainer('Komentarz', commentators);
    let address1Element = document.createElement('div');
    addClassName(address1Element, 'start-bottom-header');
    addClassName(address1Element, 'specific-colors');
    address1Element.innerText = stadium.name;
    let address2Element = document.createElement('div');
    addClassName(address2Element, 'start-bottom-header');
    addClassName(address2Element, 'specific-colors');
    address2Element.innerText = stadium.address;
    let currentDateElement = document.createElement('div');
    addClassName(currentDateElement, 'start-bottom-body');
    currentDateElement.innerText = currentDate;
    dateAndStadiumContainer.appendChild(address1Element);
    dateAndStadiumContainer.appendChild(address2Element);
    dateAndStadiumContainer.appendChild(currentDateElement);

    wrapper.appendChild(dateAndStadiumContainer);
    wrapper.appendChild(refereesContainer);
    wrapper.appendChild(commentatorsContainer);
    return wrapper;
}

function generateScorersList(_scorers) {
    let wrapper = document.createElement('div');
    addClassName(wrapper, 'break-scorers-wrapper');
    _scorers.forEach((scorer, index) => {
        let _row = document.createElement('div');
        addClassName(_row, 'break-scorer-element');
        addClassName(_row, 'specific-colors');
        addClassName(_row, `rotate-show-element${index}`);
        let firstName = document.createElement('span');
        addClassName(firstName, 'break-scorer-first-name');
        let lastName = document.createElement('span');
        addClassName(lastName, 'break-scorer-last-name');
        let goalTimeContainer = document.createElement('span');
        addClassName(goalTimeContainer, 'break-goal-time');
        firstName.innerText = scorer.player_first_name ?? '';
        lastName.innerText = scorer.player_last_name ?? '';
        goalTimeContainer.innerText = '';
        let goals = scorer.goals;
        goals.forEach(goal => {
            let displayedMinute = goal.minute;
            if (goal.added_time > 0) displayedMinute += `+${goal.added_time}`
            if (goal.is_own_goal === true) {
                goalTimeContainer.innerText += `(s)${displayedMinute}' `;
            } else {
                goalTimeContainer.innerText += `${displayedMinute}' `;
            }
        });
        _row.appendChild(firstName);
        _row.appendChild(lastName);
        _row.appendChild(goalTimeContainer);
        wrapper.appendChild(_row);
    });
    return wrapper;
}

function expandStartContainer(_gameData, _break = false) {
    let data = _gameData;
    const targetId = _break ? 'break-container' : 'start-container';
    let _startContainer = document.getElementById(targetId);
    _startContainer.innerHTML = '';
    let startContainer = document.createElement('div');
    startContainer.style.display = 'block';
    let infoHead = document.createElement('div');
    addClassName(infoHead, 'rotate-show-element0');
    addClassName(infoHead, 'animated-element');
    addClassName(infoHead, 'info-head');
    addClassName(infoHead, 'specific-colors');
    let leagueTitleElement = document.createElement('div');
    addClassName(leagueTitleElement, 'start-container-league-title');
    leagueTitleElement.innerText = setLeagueName();
    let roundTitleElement = document.createElement('div');
    addClassName(roundTitleElement, 'start-container-round-title');
    roundTitleElement.innerText = data.round_name ?? '';
    infoHead.appendChild(leagueTitleElement);
    infoHead.appendChild(roundTitleElement);
    startContainer.appendChild(infoHead);

    let startBody = document.createElement('div');
    addClassName(startBody, 'info-body');
    addClassName(startBody, 'start-body');
    addClassName(startBody, 'animated-element');
    startBody.style.display = 'flex';

    let startBodyLogosContainer = document.createElement('div');
    startBodyLogosContainer.style.display = 'none';
    addClassName(startBodyLogosContainer, 'start-content');
    addClassName(startBodyLogosContainer, 'break-content');

    let homeTeamLogoContainer = document.createElement('div');
    homeTeamLogoContainer.style.display = 'flex';
    homeTeamLogoContainer.id = 'start-home-team-logo';
    addClassName(homeTeamLogoContainer, 'start-logo');
    let homeTeamLogoImg = document.createElement('img');
    homeTeamLogoImg.src = rootApp + `${data.home_team_logo}`;
    addClassName(homeTeamLogoImg, 'drop-shadow');
    homeTeamLogoContainer.appendChild(homeTeamLogoImg);
    let leagueLogoContainer = document.createElement('div');
    leagueLogoContainer.id = 'start-league-logo';
    leagueLogoContainer.style.display = 'flex';
    let leagueLogoImg = document.createElement('img');
    leagueLogoImg.src = rootApp + setLeagueLogo();
    addClassName(leagueLogoImg, 'drop-shadow');
    leagueLogoContainer.appendChild(leagueLogoImg);
    let awayTeamLogoContainer = document.createElement('div');
    awayTeamLogoContainer.style.display = 'flex';
    awayTeamLogoContainer.id = 'start-away-team-logo';
    addClassName(awayTeamLogoContainer, 'start-logo');
    let awayTeamLogoImg = document.createElement('img');
    awayTeamLogoImg.src = rootApp + `${data.away_team_logo}`;
    addClassName(awayTeamLogoImg, 'drop-shadow');
    awayTeamLogoContainer.appendChild(awayTeamLogoImg);

    startBodyLogosContainer.appendChild(homeTeamLogoContainer);
    startBodyLogosContainer.appendChild(leagueLogoContainer);
    startBodyLogosContainer.appendChild(awayTeamLogoContainer);

    startBody.appendChild(startBodyLogosContainer);

    if (_break === true) {
        startBodyLogosContainer.style.height = '200px';
        startBodyLogosContainer.style.paddingTop = '20px';
        leagueLogoImg.remove();
        leagueLogoContainer.innerText = _gameData.result;
        let scorersContainer = document.createElement('div');
        scorersContainer.id = 'scorers-container';
        scorersContainer.style.display = 'none';
        addClassName(scorersContainer, 'break-content');

        let homeTeamScorersContainer = document.createElement('div');
        homeTeamScorersContainer.id = 'home-team-scorers-container';
        addClassName(homeTeamScorersContainer, 'team-scorers-container');
        let homeTeamScorers = _gameData.home_team_scorers.scorers;
        let homeTeamScorersWrapper = generateScorersList(homeTeamScorers);
        homeTeamScorersContainer.appendChild(homeTeamScorersWrapper);

        let awayTeamScorersContainer = document.createElement('div');
        awayTeamScorersContainer.id = 'away-team-scorers-container';
        addClassName(awayTeamScorersContainer, 'team-scorers-container');
        let awayTeamScorers = _gameData.away_team_scorers.scorers;
        let awayTeamScorersWrapper = generateScorersList(awayTeamScorers);
        awayTeamScorersContainer.appendChild(awayTeamScorersWrapper);

        scorersContainer.appendChild(homeTeamScorersContainer);
        scorersContainer.appendChild(awayTeamScorersContainer);

        startBody.appendChild(scorersContainer);
    } else {

        let startBodyTeamsContainer = document.createElement('div');
        startBodyTeamsContainer.style.display = 'none';
        addClassName(startBodyTeamsContainer, 'start-content');
        startBodyTeamsContainer.id = 'start-teams-container';
        let startBodyTeamsInternalElement = document.createElement('div');
        startBodyTeamsInternalElement.style.width = '950px';
        startBodyTeamsInternalElement.style.textAlign = 'center';

        let homeTeamNameElement = document.createElement('div');
        addClassName(homeTeamNameElement, 'start-team');
        addClassName(homeTeamNameElement, 'specific-colors');
        addClassName(homeTeamNameElement, 'rotate-show-element1');
        homeTeamNameElement.innerText = data.home_team_name ?? '';
        let awayTeamNameElement = document.createElement('div');
        addClassName(awayTeamNameElement, 'start-team');
        addClassName(awayTeamNameElement, 'specific-colors');
        addClassName(awayTeamNameElement, 'rotate-show-element1');
        awayTeamNameElement.innerText = data.away_team_name ?? '';
        startBodyTeamsInternalElement.appendChild(homeTeamNameElement);
        startBodyTeamsInternalElement.appendChild(awayTeamNameElement);
        startBodyTeamsContainer.appendChild(startBodyTeamsInternalElement);
        startBody.appendChild(startBodyTeamsContainer);

        let startBottom = document.createElement('div');
        startBottom.id = 'start-bottom-container';
        let bottomInfoContainer = expandStartBottomInfoContainer(_gameData);
        startBottom.appendChild(bottomInfoContainer);
        startBody.appendChild(startBottom);

    }

    startContainer.appendChild(startBody);
    _startContainer.appendChild(startContainer);
}

function expandSquadContainer(_containerId, _teamName, _teamShortName, _arr, _logo, _coach) {
    let squadContainer = document.getElementById(_containerId);
    squadContainer.innerHTML = '';
    let infoHead = document.createElement('div');
    addClassName(infoHead, 'rotate-show-element0');
    addClassName(infoHead, 'animated-element');
    addClassName(infoHead, 'info-head');
    addClassName(infoHead, 'specific-colors');
    infoHead.dataset.animationOrder = '1';
    let spanTeamName = document.createElement('span');
    spanTeamName.innerHTML = _teamName;
    addClassName(spanTeamName, 'main-head-text');
    let spanTeamShortName = document.createElement('span');
    spanTeamShortName.innerHTML = ` (${_teamShortName})`;
    addClassName(spanTeamShortName, 'squad-team-short-name');
    infoHead.appendChild(spanTeamName);
    infoHead.appendChild(spanTeamShortName);
    squadContainer.appendChild(infoHead);
    let infoBody = document.createElement('div');
    addClassName(infoBody, 'info-body');
    addClassName(infoBody, 'animated-element');
    infoBody.dataset.animationOrder = '2';
    let infoBodyLeft = document.createElement('div');
    addClassName(infoBodyLeft, 'info-body-left');
    let infoBodyRight = document.createElement('div');
    addClassName(infoBodyRight, 'info-body-right');
    let teamSquadContent = createTeamSquad(_arr, _logo, _coach);
    teamSquadContent.style.display = 'none';
    addClassName(teamSquadContent, 'squad-content');
    let teamLogo = document.createElement('img');
    addClassName(teamLogo, 'squad-content');
    addClassName(teamLogo, 'squad-team-logo');
    addClassName(teamLogo, 'drop-shadow');
    addClassName(teamLogo, 'animated-element');
    teamLogo.dataset.animationOrder = '3';
    teamLogo.src = rootApp + _logo;
    teamLogo.style.display = 'none';
    infoBodyLeft.appendChild(teamSquadContent);
    infoBodyRight.appendChild(teamLogo);
    infoBody.appendChild(infoBodyLeft);
    infoBody.appendChild(infoBodyRight);
    squadContainer.appendChild(infoBody);
}

function expandResultsContainer(_data) {
    let resultsContainer = document.getElementById('results-container');
    resultsContainer.innerHTML = '';
    let infoHead = document.createElement('div');
    addClassName(infoHead, 'rotate-show-element0');
    addClassName(infoHead, 'animated-element');
    addClassName(infoHead, 'info-head');
    addClassName(infoHead, 'specific-colors');
    let spanHeadText = document.createElement('span');
    spanHeadText.innerHTML = 'WYNIKI';
    addClassName(spanHeadText, 'main-head-text');
    infoHead.appendChild(spanHeadText);
    resultsContainer.appendChild(infoHead);
    let infoBody = document.createElement('div');
    addClassName(infoBody, 'info-body');
    let resultsContent = document.createElement('div');
    addClassName(resultsContent, 'results-content');
    addClassName(resultsContent, 'animated-element');
    resultsContent.dataset.animationOrder = '1';
    buildResultsContent(resultsContent, _data.games, true);
    infoBody.appendChild(resultsContent);
    resultsContainer.appendChild(infoBody);
}

function expandTableContainer(_data) {
    let tableContainer = document.getElementById('table-container');
    tableContainer.innerHTML = '';
    let infoHead = document.createElement('div');
    addClassName(infoHead, 'rotate-show-element0');
    addClassName(infoHead, 'animated-element');
    addClassName(infoHead, 'info-head');
    addClassName(infoHead, 'specific-colors');
    let spanHeadText = document.createElement('span');
    spanHeadText.innerHTML = 'TABELA';
    addClassName(spanHeadText, 'main-head-text');
    infoHead.appendChild(spanHeadText);
    tableContainer.appendChild(infoHead);
    let infoBody = document.createElement('div');
    addClassName(infoBody, 'info-body');
    let tableContent = document.createElement('div');
    addClassName(tableContent, 'results-content');
    addClassName(tableContent, 'animated-element');
    tableContent.dataset.animationOrder = '1';
    buildTableContent(tableContent, _data.rows || [], 'TABELA', true);
    infoBody.appendChild(tableContent);
    tableContainer.appendChild(infoBody);
}


function expandVirtualTableContainer(_data) {
    if (_resultsTimer2 !== null) { clearTimeout(_resultsTimer2); _resultsTimer2 = null; }

    let tableContainer = document.getElementById('virtual-table-container');
    tableContainer.innerHTML = '';

    let infoHead = document.createElement('div');
    addClassName(infoHead, 'rotate-show-element0');
    addClassName(infoHead, 'animated-element');
    addClassName(infoHead, 'info-head');
    addClassName(infoHead, 'specific-colors');
    let spanHeadText = document.createElement('span');
    spanHeadText.innerHTML = 'TABELA WIRTUALNA';
    addClassName(spanHeadText, 'main-head-text');
    infoHead.appendChild(spanHeadText);
    tableContainer.appendChild(infoHead);

    let infoBody = document.createElement('div');
    addClassName(infoBody, 'info-body');
    let tableContent = document.createElement('div');
    addClassName(tableContent, 'results-content');
    addClassName(tableContent, 'animated-element');
    tableContent.dataset.animationOrder = '1';
    const official = _data.official || [];
    const virtual  = _data.virtual  || [];
    buildTableContent(tableContent, official, 'TABELA', true);
    infoBody.appendChild(tableContent);
    tableContainer.appendChild(infoBody);

    if (virtual.length > 0) {
        _resultsTimer2 = setTimeout(() => {
            _resultsTimer2 = null;
            animateTableSwap(tableContent, official, virtual);
        }, 8000);
    }
}

function createTeamSquad(_arr, _logo) {
    var squadContent = document.createElement('div');
    addClassName(squadContent, 'team-squad-content');
    addClassName(squadContent, 'squad-content');
    squadContent.innerHTML = '';

    _arr.forEach(function (element, index) {
        var goalkeeper = '';
        var captain = '';
        if (element.is_goalkeeper === true) {
            goalkeeper = ' (B) '
        }
        if (element.is_captain === true) {
            captain = ' (C) '
        }
        var squadPlayerRow = document.createElement('div');
        addClassName(squadPlayerRow, 'squad-player-row');
        addClassName(squadPlayerRow, 'specific-colors');
        addClassName(squadPlayerRow, 'rotate-show-element');
        addClassName(squadPlayerRow, `rotate-show-element${index}`);
        addClassName(squadPlayerRow, 'animated-element');
        squadPlayerRow.dataset.animationOrder = '3';
        squadPlayerRow.innerHTML = `<span class="squad-player-number">${element.number}</span><span class="squad-player-name">${element.player_name}</span><span class="squad-player-func">${goalkeeper}${captain}</span>`;
        squadContent.appendChild(squadPlayerRow);
    });
    return squadContent;
}

function updateFoulsElement(_fouls, _foulsElement) {
    if (_fouls === '' || _fouls === null) {
        _foulsElement.textContent = '';
    } else if (parseInt(_fouls) !== 'undefined' && _fouls >= 0 && _fouls < 6) {
        _foulsElement.textContent = '●'.repeat(_fouls);
        _foulsElement.style.color = 'yellow';
        if (_fouls > 4) {
            _foulsElement.style.color = 'red';
        } else if (_fouls < 4) {
            _foulsElement.style.color = 'white';
        } else {

        }
    }
}

function updateUniformElements(_uniform, _uniformEelements) {
    let uniform = JSON.parse(_uniform);
    let uniformElements = document.querySelectorAll(`.${_uniformEelements}`);
    uniformElements.forEach(element => {
        element.innerHTML = '';
        uniform.forEach(color => {
            let colorElement = document.createElement('div');
            addClassName(colorElement, 'team-uniform-element');
            colorElement.style.backgroundColor = color;
            colorElement.innerHTML = '.';
            element.appendChild(colorElement);
        });
    });
}

function updateScoreboard(data) {
    if (typeof data.home_team_goals != "undefined") {
        homeTeamScoreElement.textContent = (data.home_team_goals === null || data.home_team_goals === '') ? 0 : data.home_team_goals;
    }
    if (typeof data.away_team_goals != "undefined") {
        awayTeamScoreElement.textContent = (data.away_team_goals === null || data.away_team_goals === '') ? 0 : data.away_team_goals;
    }
    if (typeof data.home_team_value2 != "undefined") {
        updateFoulsElement(data.home_team_value2, homeTeamFoulsElement);
    }
    if (typeof data.away_team_value2 != "undefined") {
        updateFoulsElement(data.away_team_value2, awayTeamFoulsElement);
    }
}

ws.onopen = () => {
    console.log('✅ Connected to HUB');

    ws.send(JSON.stringify({
        type: 'register',
        from: overlayId,
        to: 'hub',
        payload: {
            id: overlayId,
            component_type: 'overlay',
            type: 'overlay'
        }
    }));
};

// function actionPlayerInfoGenerator(_playerNumber, _playerName) {

// }

function actionPlayerTeamShortNameElementGenerator(_playerTeamShortName, _eventTypeId) {
    if (_eventTypeId === 2) {
        return `(${_playerTeamShortName})`;
    }
    return '';
}

ws.onclose = () => {
    console.log('❌ Disconnected from HUB');
    setTimeout(() => location.reload(), 3000);
};

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    console.log('📨 Received:', msg.type, msg);

    // Po rejestracji → subskrybuj timer
    if (msg.type === 'registered' && !registered) {
        registered = true;
        console.log('✅ Registered! Now subscribing to timer...');

        ws.send(JSON.stringify({
            type: 'subscribe',
            from: overlayId,
            to: 'hub',
            payload: {
                class: ['timer', 'overlay', 'timer_update_receiver', 'timer_state_receiver', 'game_data_receiver']
            }
        }));

        ws.send(JSON.stringify({
            type: 'request_game_data',
            from: overlayId,
            to: 'main-module'
        }));

        setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'heartbeat',
                    from: overlayId,
                    to: 'hub',
                    payload: { plugin_id: overlayId, timestamp: Date.now() }
                }));
            }
        }, 5000);
    }

    // Po subskrypcji
    if (msg.type === 'subscribed') {
        console.log('✅ Subscribed to classes!');

    }

    if (msg.type === 'show_transition') {
        showTransition();
    }

    // ── GŁÓWNY TIMER ─────────────────────────────────────────────────────────
    // timer_updated: tick z timer-plugin (tylko główny timer, ~100ms)
    // timer_paused / timer_reset: zmiany stanu
    if (msg.type === 'timer_updated' ||
        msg.type === 'timer_paused' ||
        msg.type === 'timer_reset') {

        const data = msg.payload || msg.data;

        if (data.timer_id && data.timer_id.startsWith('penalty_')) {
            // skip — penalty timers handled by PenaltyTimers module via penalty_state
        } else if (data.elapsed_time === undefined) {
            display.textContent = '';
        } else {
            // Aktualizuj wyświetlanie głównego zegara
            display.textContent = FutsalFormatters.formatElapsedTime(
                data.elapsed_time, data.initial_time
            );

            // Cache ostatniego elapsed — potrzebny przy rehydratacji po reload
            window._lastMainElapsed = data.elapsed_time;

            // Prześlij tick do modułu kar — przelicza remaining każdej kary
            window.PenaltyTimers.tickMain(data.elapsed_time);

            // Przy starcie zegara: wynik null/pusty → 0
            [homeTeamScoreElement, awayTeamScoreElement].forEach(el => {
                if (el && (el.textContent === '' || el.textContent === 'null' || el.textContent === 'None')) {
                    el.textContent = '0';
                }
            });
            document.querySelectorAll('.home-team-score, .away-team-score').forEach(el => {
                if (el.textContent === '' || el.textContent === 'null' || el.textContent === 'None') {
                    el.textContent = '0';
                }
            });
        }
    }

    // ── STAN KAR ──────────────────────────────────────────────────────────
    // Wysyłany przez backend przy każdej zmianie stanu kar oraz przy
    // request_game_data (reload overlay). Zastępuje indywidualne
    // timer_updated per-kara.
    if (msg.type === 'penalty_state') {
        const data = msg.payload || msg.data;
        window.PenaltyTimers.syncState(data);

        // Jednorazowy tick żeby wyrenderować kary natychmiast po reloadzie,
        // nawet jeśli główny timer jest aktualnie zapauzowany.
        const cachedElapsed = window._lastMainElapsed;
        if (cachedElapsed !== undefined) {
            window.PenaltyTimers.tickMain(cachedElapsed);
        }
    }

    if (msg.type === 'limit_reached' || msg.type === 'timer_removed') {
        const data = msg.payload || msg.data;
        if (data.timer_id && data.timer_id.startsWith('penalty_')) {
            window.PenaltyTimers.remove(data.timer_id);  // animacja chowania jest już w remove()
        }
    }

    if (msg.type === 'show_overlay_container') {
        const data = msg.payload || msg.data;
        showContainer(data);
    }

    if (msg.type === 'scoreboard_data') {
        const data = msg.payload || msg.data;
        updateScoreboard(data);
    }

    if (msg.type === 'goal') {
        const data = msg.payload || msg.data;
        animateWord(
            'animationArea',
            'GOOOOL',
            350,
            'scoreboard-container',
            'class1',
            'class2',
            data.name_14,
            60);
    }

    if (msg.type === 'reload') {
        console.log('🔄 Reload requested by server — reloading overlay');
        location.reload();
        return;
    }

    if (msg.type === 'game_data') {
        const data = msg.payload || msg.data;
        console.log('game_data', data);
        let homeTeamShortNameElements = document.querySelectorAll('.home-team-shortname');
        let awayTeamShortNameElements = document.querySelectorAll('.away-team-shortname');
        let homeTeamScoreElements = document.querySelectorAll('.home-team-score');
        let awayTeamScoreElements = document.querySelectorAll('.away-team-score');

        if (typeof data.home_team_short_name != "undefined") {
            homeTeamShortNameElements.forEach(element => {
                element.textContent = data.home_team_short_name ?? '';
            })
        }

        if (typeof data.away_team_short_name != "undefined") {
            awayTeamShortNameElements.forEach(element => {
                element.textContent = data.away_team_short_name ?? '';
            })
        }

        if (typeof data.home_team_goals != "undefined") {
            homeTeamScoreElements.forEach(element => {
                element.textContent = data.home_team_goals ?? 0;
            })
        }

        if (typeof data.away_team_goals != "undefined") {
            awayTeamScoreElements.forEach(element => {
                element.textContent = data.away_team_goals ?? 0;
            })
        }

        if (typeof data.home_team_fouls != "undefined") {
            updateFoulsElement(data.home_team_fouls, homeTeamFoulsElement);
        }

        if (typeof data.away_team_fouls != "undefined") {
            updateFoulsElement(data.away_team_fouls, awayTeamFoulsElement);
        }

        if (typeof data.home_team_uniform != "undefined") {
            updateUniformElements(data.home_team_uniform, 'home-team-uniform');
        }

        if (typeof data.away_team_uniform != "undefined") {
            updateUniformElements(data.away_team_uniform, 'away-team-uniform');
        }



    }

    if (msg.type === 'show_substitution') {
        showSubstitutionOverlay(msg.payload);
    }

    if (msg.type === 'show_info') {
        let data = msg.payload;
        let actionInfoContainer = document.querySelector('#action_info_container');
        let actionInfoElements = document.querySelectorAll('.action_square');
        let actionImgElement = document.querySelector('#action_icon_img');
        let actionInfoTextElement = document.querySelector('#action_info_text');
        let actionTimeElements = document.querySelectorAll('.action_minute');
        let actionTimeElement = document.querySelector('#action_time');
        let actionPlayerInfoElement = document.querySelector('#action_player_name');
        let actionPlayerTeamShortNameElement = document.querySelector('#action_player_team_short_name');
        let actionTeamNameElement = document.querySelector('#action_team_name');

        actionImgElement.src = '';
        actionImgElement.src = `${rootApp}${data.event_image_path}`;
        actionTimeElement.textContent = '';
        actionTimeElement.textContent = (data.period_limit_s !== undefined)
            ? formatGameTimeDisplay(data.game_time, data.period_limit_s)
            : FutsalFormatters.formatElapsedTime(data.game_time, 0, { 'format': 'min', 'unit': 's' });
        actionPlayerInfoElement.textContent = '';
        actionPlayerInfoElement.textContent = `${data.player_number ?? ''} ${data.player_name ?? ''}`.trim();
        actionPlayerTeamShortNameElement.textContent = '';
        actionPlayerTeamShortNameElement.textContent =
            actionPlayerTeamShortNameElementGenerator(data.player_team_short_name ?? '', data.event_type_id);
        actionTeamNameElement.textContent = '';
        actionTeamNameElement.textContent = data.team_name ?? '';

        actionInfoContainer.style.display = 'block';
        setTimeout(() => {
            actionInfoContainer.style.display = 'none';
        }, 11100);
    }

    if (msg.type === 'results' || msg.type === 'table' || msg.type === 'virtual_table') {
        const gameContainer = document.getElementById('game-container');
        const gameVisible = gameContainer && gameContainer.style.display !== 'none';

        if (gameVisible) {
            showInResultsTableContainer(msg.type, msg.payload);
        } else {
            var containerId = `${msg.type.replace('_', '-')}-container`;
            var _data = msg.payload;
            _data.container_id = containerId;
            showContainer(_data);
        }
    }
}