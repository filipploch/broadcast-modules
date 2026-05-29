// WebSocket z rejestracją jako overlay + subskrypcja timer
const overlayId = 'stream-overlay';
const ws = new WebSocket(`ws://${window.location.hostname}:${window.location.port}/ws`);

const rootApp = 'http://localhost:8081/';

const display = document.getElementById('main-timer-display');

let registered = false;
let currentAddedTime = 0;

var homeTeamScoreElement = document.getElementById('home-team-score');
var awayTeamScoreElement = document.getElementById('away-team-score');
var homeTeamRedCardsElement = document.getElementById('home-team-red-cards');
var awayTeamRedCardsElement = document.getElementById('away-team-red-cards');

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
        expandBreakContainer(_data);
        prepareToOpenContainer(openContainer, targetContainer);
        activateElementsAfterTime('break-content', 2500, 'flex');
    } else if (containerType === 'game') {
        if (typeof _data.added_time !== 'undefined') currentAddedTime = _data.added_time;
        prepareToOpenContainer(openGameContainer, targetContainer);
    } else if (containerType === 'shootout') {
        fillShootoutContainer(_data);
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
            console.log('cont:', cont.id);
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

function openGameContainer(container) {
    openContainer(container);
    document.querySelectorAll('.both-side-tilted').forEach(element => {
        element.style.clipPath = makePolygonTilt(element.offsetHeight, element.offsetWidth, 'both');
    });

    const addedTimeDisplay = document.getElementById('added-time-display');
    const addedTimeLabel = document.getElementById('added-time-label');
    addedTimeLabel.innerText = `+${currentAddedTime}'`;
    addedTimeDisplay.style.animation = 'none';
    addedTimeDisplay.offsetHeight;
    addedTimeDisplay.style.transform = currentAddedTime > 0 ? 'translateX(0)' : 'translateX(-80px)';

    let scoreboardContainer = document.getElementById('scoreboard-container');
    scoreboardContainer.style.animation = null;
    scoreboardContainer.style.animation = 'scoreboardSlideIn 500ms ease-in-out 300ms both';
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
        case 'game':
            closeGameContainer(container);
            console.log('closeGameContainer()');
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

function buildResultsContent(resultsEl, games) {
    resultsEl.innerHTML = '';

    let header = document.createElement('div');
    header.id = 'results-header';
    header.className = 'results-row rotate-show-element0';
    header.textContent = 'WYNIKI';
    resultsEl.appendChild(header);

    games.forEach((game, index) => {
        let row = document.createElement('div');
        const statusClass = game.status === 2 ? 'finished' : 'pending';
        row.className = `results-row rotate-show-element${index + 1} ${statusClass}`;

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

function buildTableContent(resultsEl, rows, headerText) {
    resultsEl.innerHTML = '';

    let header = document.createElement('div');
    header.id = 'table-header';
    header.className = 'results-row rotate-show-element0';
    header.textContent = headerText;
    resultsEl.appendChild(header);

    rows.forEach((row, index) => {
        let el = document.createElement('div');
        el.className = `results-row rotate-show-element${index + 1}`;
        el.dataset.teamName14 = row.team_name14;

        let diff = document.createElement('div');
        diff.className = 'results-difference';
        // Wypełnianie ▲/▼ następuje przy animacji zamiany
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
        row.className = `results-row specific-colors rotate-show-element${index + 1} ${statusClass}`;

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

    grid.style.position   = 'absolute';
    grid.style.visibility = 'hidden';
    document.body.appendChild(grid);
    const _firstRow = grid.querySelector('.results-row');
    if (_firstRow) {
        const _h = _firstRow.offsetHeight;
        if (_h > 0 && colWidth > 0) {
            const _polygon = makePolygonTilt(_h, colWidth, 'both');
            grid.querySelectorAll('.results-row').forEach(row => {
                row.style.clipPath = _polygon;
            });
        }
    }
    document.body.removeChild(grid);
    grid.style.position   = '';
    grid.style.visibility = '';

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
    const rowEls = Array.from(container.querySelectorAll('.results-row:not(:first-child)'));
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
    hideContentBackground(container);
    let logo = container.querySelector('img');
    let players = container.querySelectorAll('.squad-player-row');
    let infoBody = container.querySelector('.info-body');
    logo.style.animation = `fadeOut 250ms ease both`;
    players.forEach(player => {
        player.style.animation = `rotateHideElement 250ms ease 0ms 1 reverse both`;
    });
    infoBody.style.setProperty('animation', 'fadeOut', 'important');
    infoBody.style.animationDuration = '750ms';
    infoBody.style.animationDelay = '250ms';
    infoBody.style.animationFillMode = 'both';
}

function closeStartContainer(container) {
    hideContentBackground(container);
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
}

function restartAnimation(element, animationValue) {
    if (!element) return;

    element.style.animation = 'none';
    // Wymusza reflow, żeby przeglądarka faktycznie zresetowała poprzednią animację
    // przed ustawieniem kolejnej animacji na tym samym elemencie.
    void element.offsetWidth;
    element.style.animation = animationValue;
}

function setBreakElementClosedState(element, properties) {
    if (!element) return;

    Object.entries(properties).forEach(([property, value]) => {
        element.style[property] = value;
    });
}

function _closeResultsBase(container) {
    hideContentBackground(container);
    container.querySelectorAll('.results-row').forEach(row => {
        row.style.animation = 'rotateHideElement 250ms ease 0ms 1 reverse both';
    });
    const body = container.querySelector('.results');
    if (body) {
        body.style.setProperty('animation', 'collapseHeight', 'important');
        body.style.animationDuration = '750ms';
        body.style.animationDelay = '250ms';
        body.style.animationFillMode = 'both';
    }
}

function closeResultsContainer(container) {
    _closeResultsBase(container);
}

function closeTableContainer(container) {
    hideContentBackground(container);
    const body = container.querySelector('.results');
    if (body) {
        body.style.setProperty('animation', 'fadeOut 500ms ease both', 'important');
    }
}

function closeVirtualTableContainer(container) {
    if (_resultsTimer2 !== null) { clearTimeout(_resultsTimer2); _resultsTimer2 = null; }
    closeTableContainer(container);
}

function closeGameContainer(container) {
    const scoreboardContainer = container.querySelector('#scoreboard-container');
    if (scoreboardContainer) {
        restartAnimation(scoreboardContainer, 'scoreboardSlideIn 500ms ease-in-out 300ms reverse both');
    }
}

function closeBreakContainer(container) {
    hideContentBackground(container);
    const players = container.querySelectorAll('.rotate-show-element');
    const homeTeamLogoContainer = container.querySelector('#home-team-logo-container');
    const awayTeamLogoContainer = container.querySelector('#away-team-logo-container');
    const homeTeamNameElement = container.querySelector('#home-team-name-element');
    const awayTeamNameElement = container.querySelector('#away-team-name-element');
    const resultElement = container.querySelector('#result-element');

    players.forEach(player => {
        restartAnimation(player, 'rotateHideElement 250ms ease 0ms 1 reverse forwards');
    });

    restartAnimation(
        homeTeamLogoContainer,
        'moveHomeTeamLogo 200ms ease-in-out 300ms 1 reverse forwards'
    );

    restartAnimation(
        awayTeamLogoContainer,
        'moveAwayTeamLogo 200ms ease-in-out 300ms 1 reverse forwards'
    );

    restartAnimation(
        homeTeamNameElement,
        'moveHomeTeamNameElement 300ms ease-in-out 500ms 1 reverse forwards'
    );

    restartAnimation(
        awayTeamNameElement,
        'moveAwayTeamNameElement 300ms ease-in-out 500ms 1 reverse forwards'
    );

    restartAnimation(
        resultElement,
        'resultFadeIn 300ms ease 700ms 1 reverse forwards'
    );

    // Zabezpieczenie przed „odbiciem” elementów do stylu bazowego po animationend.
    // Wartości odpowiadają klatce 0% Twoich animacji wejścia.
    setTimeout(() => {
        setBreakElementClosedState(homeTeamLogoContainer, {
            left: '130px',
            visibility: 'hidden'
        });

        setBreakElementClosedState(awayTeamLogoContainer, {
            right: '130px',
            visibility: 'hidden'
        });

        setBreakElementClosedState(homeTeamNameElement, {
            left: '500px',
            visibility: 'hidden'
        });

        setBreakElementClosedState(awayTeamNameElement, {
            right: '500px',
            visibility: 'hidden'
        });

        setBreakElementClosedState(resultElement, {
            opacity: 0
        });
    }, 850);
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

function addContentBackground(_containerId) {
    const activeContainer = document.getElementById(_containerId);
    if (!activeContainer) return;
    const canvasW = document.body.offsetWidth;
    const canvasH = document.body.offsetHeight;
    const margin = Math.round(canvasW * 50 / 1920);
    const contentContainer = document.createElement('div');
    contentContainer.style.cssText = `
        display: flex;
        position: absolute;
        overflow: hidden;
        background-color: rgba(34, 34, 34, 0);
        // width: ${canvasW - margin * 2}px;
        // height: ${canvasH - margin * 2}px;
        // top: ${margin}px;
        // left: ${margin}px;
        width: 100%;
        height: 100%;
        top: 0;
        left: 0;
        z-index: 0;
    `;
    activeContainer.appendChild(contentContainer);
    contentContainer.id = 'content-container';
    const contentContainerWidth = canvasW - margin * 2;
    const contentContainerHeight = canvasH - margin * 2;
    const _widthFactor = contentContainerWidth / 1820;
    const xShift = contentContainerHeight * 19 / 38;
    const whiteStripeRelativeWidth = 25;
    const whiteStripeTotalWidth = (xShift + whiteStripeRelativeWidth);
    const xShiftPercent = (whiteStripeTotalWidth - whiteStripeRelativeWidth) / whiteStripeTotalWidth * 100;
    const whiteStripeLeftPos = 700;

    const whiteStripe = document.createElement('div');
    whiteStripe.id = 'white-stripe';
    whiteStripe.classList.add('white-stripe');
    whiteStripe.style.cssText = `
        position: absolute;
        display: flex;
        width: ${whiteStripeTotalWidth * _widthFactor}px;
        height: 100%;
        background-color: white;
        top: -100%;
        left: ${(whiteStripeLeftPos + xShift) * _widthFactor}px;
    `;
    whiteStripe.style.clipPath = `polygon(${xShiftPercent}% 0%, 100% 0%, ${100 - xShiftPercent}% 100%, 0% 100%)`;

    const leftSide = document.createElement('div');
    leftSide.id = 'background-left-side';
    leftSide.classList.add('left-side');
    leftSide.style.cssText = `
        position: absolute;
        display: flex;
        width: 100%;
        height: 100%;
        background-image:
          linear-gradient(rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0.1)),
          url('img/lew1820x980.png');
        background-size: cover;
        background-position: center;
        left: -110%;
    `;
    leftSide.style.clipPath = `polygon(0% 0%, ${(whiteStripeLeftPos + xShift) * _widthFactor / contentContainerWidth * 100}% 0%, ${whiteStripeLeftPos * _widthFactor / contentContainerWidth * 100}% 100%, 0% 100%)`;

    const rightSide = document.createElement('div');
    rightSide.id = 'background-right-side';
    rightSide.classList.add('right-side');
    rightSide.style.cssText = `
        position: absolute;
        display: flex;
        width: 100%;
        height: 100%;
        background-image:
          linear-gradient(
            110deg,
            rgba(50, 50, 50, 0.8) 0%,
            rgba(50, 50, 50, 0.8) 48%,
            rgba(150, 150, 150, 0.7) 50%,
            rgba(255, 255, 255, 0.5) 52%,
            rgba(255, 255, 255, 0.4) 100%
          ),
          url('img/lew1820x980.png');
        background-size: cover;
        background-position: center;
        right: -120%;
    `;
    rightSide.style.clipPath = `polygon(${(whiteStripeLeftPos + xShift) * _widthFactor / contentContainerWidth * 100}% 0%, 100% 0%, 100% 100%, ${whiteStripeLeftPos * _widthFactor / contentContainerWidth * 100}% 100%)`;

    contentContainer.innerHTML = '';
    contentContainer.appendChild(leftSide);
    contentContainer.appendChild(rightSide);
    contentContainer.appendChild(whiteStripe);

    const _style = document.createElement('style');
    document.head.appendChild(_style);

    _style.sheet.insertRule(`
        @keyframes whiteStripeSlide {
            0%   { top: -100%; left: ${(whiteStripeLeftPos + xShift) * _widthFactor}px }
            100% { top: 0;     left: ${whiteStripeLeftPos * _widthFactor}px }
        }
    `, 0);
    _style.sheet.insertRule(`
        @keyframes leftSideSlide {
            0%   { left: -120% }
            100% { left: 0 }
        }
    `, 0);
    _style.sheet.insertRule(`
        @keyframes rightSideSlide {
            0%   { right: -130% }
            100% { right: 0 }
        }
    `, 0);
    _style.sheet.insertRule(`
        @keyframes contentContainerFade {
            0%   { background-color: rgba(34, 34, 34, 0); }
            100% { background-color: rgba(34, 34, 34, 0.7); }
        }
    `, 0);

    contentContainer.style.animation = 'none';
    whiteStripe.style.animation       = 'none';
    leftSide.style.animation          = 'none';
    rightSide.style.animation         = 'none';

    contentContainer.style.animation = 'contentContainerFade 500ms ease-out 1 forwards';
    whiteStripe.style.animation       = 'whiteStripeSlide 500ms ease-out 500ms 1 forwards';
    leftSide.style.animation          = 'leftSideSlide 500ms ease-out 500ms 1 forwards';
    rightSide.style.animation         = 'rightSideSlide 500ms ease-out 500ms 1 forwards';
    return activeContainer;
}

function hideContentBackground(container) {
    const contentContainer = container.querySelector('#content-container');
    if (!contentContainer) return;
    const leftSide    = contentContainer.querySelector('#background-left-side');
    const rightSide   = contentContainer.querySelector('#background-right-side');
    const whiteStripe = contentContainer.querySelector('#white-stripe');
    restartAnimation(rightSide,       'rightSideSlide 500ms ease-out 250ms reverse both');
    restartAnimation(leftSide,        'leftSideSlide 500ms ease-out 250ms reverse both');
    restartAnimation(whiteStripe,     'whiteStripeSlide 500ms ease-out 250ms reverse both');
    restartAnimation(contentContainer,'contentContainerFade 500ms ease-out 750ms reverse both');
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

function generateScorersList(_scorers, _side) {
    const isAway = (_side === 'away');

    // .break-scorers-wrapper
    const wrapper = document.createElement('div');
    Object.assign(wrapper.style, {
        width: '600px',
        padding: '0 20px'
    });

    _scorers.forEach((scorer, index) => {
        // .break-scorer-element  +  home|away-team-scorer-break-element
        const row = document.createElement('div');
        Object.assign(row.style, {
            width: '100%',
            textAlign: 'left',
            padding: '2px 0px',
            fontSize: '28px',
            display: 'flex',
            filter: 'drop-shadow(3px 3px 3px black)',
            margin: '2px 0',
            color: '#d9d9d9',
            // skos tła zależy od strony
            clipPath: isAway
                ? 'polygon(100% 0%, 97.75% 100%, 0% 100%, 0% 0%)'
                : 'polygon(100% 0%, 100% 100%, 0% 100%, 2.25% 0%)',
            // animacja wejścia — każdy wiersz z rosnącym opóźnieniem
            animation: `rotateShowElement 250ms ease ${250 + 0 * 250}ms 1 reverse both`,
            visibility: 'visible'
        });
        // zachowaj dane potrzebne closeBreakContainer do obliczenia reverse delay
        row.dataset.scorerIndex = index;

        row.classList.add(
            'specific-colors',
            'rotate-show-element'
        );

        // .break-scorer-first-name
        const firstName = document.createElement('span');
        Object.assign(firstName.style, {
            marginLeft: '30px'
        });
        firstName.textContent = scorer.player_first_name ?? '';

        // .break-scorer-last-name
        const lastName = document.createElement('span');
        Object.assign(lastName.style, {
            paddingLeft: '10px',
            fontWeight: '700'
        });
        lastName.textContent = scorer.player_last_name ?? '';

        // .break-goal-time
        const goalTime = document.createElement('span');
        Object.assign(goalTime.style, {
            marginRight: '30px',
            textAlign: 'right',
            width: 'inherit'
        });
        goalTime.textContent = '';
        scorer.goals.forEach(goal => {
            let min = goal.minute;
            if (goal.added_time > 0) min += `+${goal.added_time}`;
            goalTime.textContent += goal.is_own_goal ? `(s)${min}' ` : `${min}' `;
        });

        row.appendChild(firstName);
        row.appendChild(lastName);
        row.appendChild(goalTime);
        wrapper.appendChild(row);
    });

    return wrapper;
}

function expandBreakContainer(_data) {
    const container = document.getElementById('break-container');
    if (!container) return;
    container.innerHTML = '';
    // addContentBackground('break-container');

    // Timingі wejścia — spójne z CSS keyframes w overlay
    // Strzelcy:  rotateShowElement reverse, delay rośnie o 250ms na wiersz, start po 2500ms
    // Nazwy:     moveHome/AwayTeamNameElement 500ms ease-in-out delay 1000ms
    // Wynik:     resultFadeIn 300ms ease-in-out delay 1000ms
    // Herby:     moveHome/AwayTeamLogo 500ms ease-in-out delay 1500ms

    // ── #break-scorers-container ──────────────────────────────────────────
    // Pozycja absolutna, 1330×550px, bottom:300px, left:295px
    const breakScorersContainer = document.createElement('div');
    breakScorersContainer.id = 'break-scorers-container';
    Object.assign(breakScorersContainer.style, {
        position: 'absolute',
        width: '1330px',
        height: '550px',
        left: '250px',
        bottom: '200px',
        display: 'none',   // activateElementsAfterTime('break-content') pokaże po 2500ms
        zIndex: '1'
    });
    addClassName(breakScorersContainer, 'break-content');

    const scorersInner = document.createElement('div');
    scorersInner.id = 'scorers-container';
    Object.assign(scorersInner.style, {
        display: 'flex',
        width: '100%',
        height: '100%',
        alignItems: 'flex-end'
    });

    // Home scorers column
    const homeScorersCol = document.createElement('div');
    homeScorersCol.id = 'home-team-scorers-container';
    Object.assign(homeScorersCol.style, {
        width: '50%',
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'left'
    });
    const homeScorers = (_data.home_team_scorers && _data.home_team_scorers.scorers) || [];
    homeScorersCol.appendChild(generateScorersList(homeScorers, 'home'));

    // Away scorers column
    const awayScorersCol = document.createElement('div');
    awayScorersCol.id = 'away-team-scorers-container';
    Object.assign(awayScorersCol.style, {
        width: '50%',
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'right'
    });
    const awayScorers = (_data.away_team_scorers && _data.away_team_scorers.scorers) || [];
    awayScorersCol.appendChild(generateScorersList(awayScorers, 'away'));

    scorersInner.appendChild(homeScorersCol);
    scorersInner.appendChild(awayScorersCol);
    breakScorersContainer.appendChild(scorersInner);

    // ── #result-container ─────────────────────────────────────────────────
    // Pozycja absolutna, 1330×170px, bottom:100px, left:295px
    const resultContainer = document.createElement('div');
    resultContainer.id = 'result-container';
    Object.assign(resultContainer.style, {
        position: 'absolute',
        width: '1330px',
        height: '170px',
        left: '250px',
        bottom: '10px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: '1'
    });

    // ── #logo-container ───────────────────────────────────────────────────
    const logoContainer = document.createElement('div');
    logoContainer.id = 'logo-container';
    Object.assign(logoContainer.style, {
        display: 'flex',
        position: 'absolute',
        top: '0',
        height: '100%',
        width: '100%',
        zIndex: '1'
    });

    // Home logo wrap — animacja moveHomeTeamLogo 500ms 1500ms
    const homeLogoWrap = document.createElement('div');
    homeLogoWrap.id = 'home-team-logo-container';
    Object.assign(homeLogoWrap.style, {
        visibility: 'visible',
        position: 'absolute',
        left: '0px',
        animation: 'moveHomeTeamLogo 500ms ease-in-out 1500ms both'
    });

    const homeLogoEl = document.createElement('div');
    homeLogoEl.id = 'home-team-logo-element';
    Object.assign(homeLogoEl.style, {
        display: 'flex',
        width: '168px',
        backgroundImage: "url('..../../img/home-team-logo-background-image.png')",
        backgroundRepeat: 'no-repeat',
        height: '100%',
        aspectRatio: '1',
        flex: '1',
        justifyContent: 'center',
        alignItems: 'center',
        filter: 'drop-shadow(10px 10px 20px black)'
    });
    const homeLogoImg = document.createElement('img');
    Object.assign(homeLogoImg.style, {
        width: '40%',
        aspectRatio: '1',
        objectFit: 'cover'
    });
    homeLogoImg.src = rootApp + (_data.home_team_logo || '');
    homeLogoEl.appendChild(homeLogoImg);
    homeLogoWrap.appendChild(homeLogoEl);

    // Away logo wrap — animacja moveAwayTeamLogo 500ms 1500ms
    const awayLogoWrap = document.createElement('div');
    awayLogoWrap.id = 'away-team-logo-container';
    Object.assign(awayLogoWrap.style, {
        visibility: 'visible',
        position: 'absolute',
        right: '0px',
        animation: 'moveAwayTeamLogo 500ms ease-in-out 1500ms both'
    });

    const awayLogoEl = document.createElement('div');
    awayLogoEl.id = 'away-team-logo-element';
    Object.assign(awayLogoEl.style, {
        display: 'flex',
        width: '168px',
        backgroundImage: "url('..../../img/away-team-logo-background-image.png')",
        backgroundRepeat: 'no-repeat',
        height: '100%',
        aspectRatio: '1',
        flex: '1',
        justifyContent: 'center',
        alignItems: 'center',
        filter: 'drop-shadow(10px 10px 20px black)'
    });
    const awayLogoImg = document.createElement('img');
    Object.assign(awayLogoImg.style, {
        width: '40%',
        aspectRatio: '1',
        objectFit: 'cover'
    });
    awayLogoImg.src = rootApp + (_data.away_team_logo || '');
    awayLogoEl.appendChild(awayLogoImg);
    awayLogoWrap.appendChild(awayLogoEl);

    logoContainer.appendChild(homeLogoWrap);
    logoContainer.appendChild(awayLogoWrap);

    // ── #x-container ──────────────────────────────────────────────────────
    const xContainer = document.createElement('div');
    xContainer.id = 'x-container';
    Object.assign(xContainer.style, {
        position: 'absolute',
        top: '0',
        display: 'flex',
        height: '100%',
        width: '100%'
    });

    // Home team name wrap — animacja moveHomeTeamNameElement 500ms 1000ms
    const homeNameWrap = document.createElement('div');
    Object.assign(homeNameWrap.style, {
        display: 'flex',
        width: '500px',
        height: '100%',
        overflow: 'hidden',
        zIndex: '9',
        filter: 'drop-shadow(10px 10px 20px black)'
    });
    const homeNameEl = document.createElement('div');
    homeNameEl.id = 'home-team-name-element';
    Object.assign(homeNameEl.style, {
        visibility: 'visible',
        position: 'relative',
        left: '120px',
        backgroundImage: "url('..../../img/home-team-name-background-image.png')",
        backgroundRepeat: 'no-repeat',
        width: '100%',
        paddingRight: '70px',
        fontSize: '35px',
        color: '#c9c9c9',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        fontWeight: '700',
        animation: 'moveHomeTeamNameElement 500ms ease-in-out 1000ms both'
    });
    homeNameEl.textContent = (_data.home_team_name_14 || '').toUpperCase();
    homeNameWrap.appendChild(homeNameEl);

    // Result element — animacja resultFadeIn 300ms 1000ms
    const resultParts = ((_data.result || '0 : 0').toString()).split(':').map(s => s.trim());
    const resultEl = document.createElement('div');
    Object.assign(resultEl.style, {
        fontSize: '75px',
        color: 'white',
        fontWeight: '700',
        visibility: 'visible',
        display: 'flex',
        width: '324px',
        height: '100%',
        backgroundImage: "url('..../../img/result-element-background-image.png')",
        alignItems: 'center',
        animation: 'resultFadeIn 300ms ease-in-out 1000ms both',
        zIndex: '10',
        filter: 'drop-shadow(10px 10px 20px black)'
    });
    resultEl.id = 'result-element';

    const homeResultEl = document.createElement('div');
    homeResultEl.id = 'home-team-result-element';
    Object.assign(homeResultEl.style, { flex: '2', textAlign: 'center' });
    homeResultEl.textContent = resultParts[0] || '0';

    const leagueLogoEl = document.createElement('div');
    Object.assign(leagueLogoEl.style, {
        flex: '1',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center'
    });
    const leagueLogoImg = document.createElement('img');
    Object.assign(leagueLogoImg.style, {
        width: '100%',
        height: '100%',
        objectFit: 'cover',
        filter: 'drop-shadow(0px 5px 10px rgba(0,0,0,0.5))'
    });
    leagueLogoImg.src = rootApp + setLeagueLogo();
    leagueLogoEl.appendChild(leagueLogoImg);

    const awayResultEl = document.createElement('div');
    awayResultEl.id = 'away-team-result-element';
    Object.assign(awayResultEl.style, { flex: '2', textAlign: 'center' });
    awayResultEl.textContent = resultParts[1] || '0';

    resultEl.appendChild(homeResultEl);
    resultEl.appendChild(leagueLogoEl);
    resultEl.appendChild(awayResultEl);

    // Away team name wrap — animacja moveAwayTeamNameElement 500ms 1000ms
    const awayNameWrap = document.createElement('div');
    Object.assign(awayNameWrap.style, {
        display: 'flex',
        width: '500px',
        height: '100%',
        overflow: 'hidden',
        zIndex: '9',
        filter: 'drop-shadow(10px 10px 20px black)'
    });
    const awayNameEl = document.createElement('div');
    awayNameEl.id = 'away-team-name-element';
    Object.assign(awayNameEl.style, {
        visibility: 'visible',
        position: 'relative',
        right: '120px',
        backgroundImage: "url('..../../img/away-team-name-background-image.png')",
        backgroundRepeat: 'no-repeat',
        width: '100%',
        paddingLeft: '70px',
        fontSize: '35px',
        color: '#c9c9c9',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        fontWeight: '700',
        animation: 'moveAwayTeamNameElement 500ms ease-in-out 1000ms both'
    });
    awayNameEl.textContent = (_data.away_team_name_14 || '').toUpperCase();
    awayNameWrap.appendChild(awayNameEl);

    xContainer.appendChild(homeNameWrap);
    xContainer.appendChild(resultEl);
    xContainer.appendChild(awayNameWrap);

    resultContainer.appendChild(logoContainer);
    resultContainer.appendChild(xContainer);

    // ── Złóż całość ───────────────────────────────────────────────────────
    container.appendChild(breakScorersContainer);
    container.appendChild(resultContainer);
}

function expandStartContainer(_gameData, _break = false) {
    let data = _gameData;
    const targetId = _break ? 'break-container' : 'start-container';
    let _startContainer = document.getElementById(targetId);
    _startContainer.innerHTML = '';
    addContentBackground(targetId);
    let startContainer = document.createElement('div');
    startContainer.style.display = 'block';

    let startBody = document.createElement('div');
    addClassName(startBody, 'info-body');
    addClassName(startBody, 'start-body');
    addClassName(startBody, 'animated-element');
    startBody.style.display = 'flex';
    startBody.style.position = 'relative';
    startBody.style.zIndex = '1';

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
        homeTeamNameElement.innerText = data.home_team_name;
        let awayTeamNameElement = document.createElement('div');
        addClassName(awayTeamNameElement, 'start-team');
        addClassName(awayTeamNameElement, 'specific-colors');
        addClassName(awayTeamNameElement, 'rotate-show-element1');
        awayTeamNameElement.innerText = data.away_team_name;
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

function expandResultsContainer(_data) {
    const containerId = _data.container_id;
    const container = document.getElementById(containerId);
    container.innerHTML = '';
    addContentBackground(containerId);
    const infoBody = document.createElement('div');
    addClassName(infoBody, 'info-body');
    addClassName(infoBody, 'animated-element');
    infoBody.dataset.animationOrder = '2';
    infoBody.style.position = 'relative';
    infoBody.style.zIndex = '1';
    const resultsEl = document.createElement('div');
    addClassName(resultsEl, 'results');
    addClassName(resultsEl, 'results-content');
    addClassName(resultsEl, 'animated-element');
    resultsEl.dataset.animationOrder = '3';
    buildResultsContent(resultsEl, (_data && _data.games) || []);
    infoBody.appendChild(resultsEl);
    container.appendChild(infoBody);
}

function _expandFullTableContainer(containerId, rows, virtual, withVirtualSwap) {
    const container = document.getElementById(containerId);
    container.innerHTML = '';
    addContentBackground(containerId);
    const infoBody = document.createElement('div');
    addClassName(infoBody, 'info-body');
    addClassName(infoBody, 'animated-element');
    infoBody.dataset.animationOrder = '2';
    infoBody.style.position = 'absolute';
    infoBody.style.width = '100%';
    infoBody.style.height = '100%';
    infoBody.style.zIndex = '1';
    const resultsEl = document.createElement('div');
    addClassName(resultsEl, 'results');
    addClassName(resultsEl, 'results-content');
    addClassName(resultsEl, 'animated-element');
    resultsEl.dataset.animationOrder = '3';
    buildFullTableContent(resultsEl, rows);
    infoBody.appendChild(resultsEl);
    container.appendChild(infoBody);
    if (withVirtualSwap) {
        if (_resultsTimer2 !== null) { clearTimeout(_resultsTimer2); _resultsTimer2 = null; }
        _resultsTimer2 = setTimeout(() => {
            _resultsTimer2 = null;
            animateFullTableSwap(resultsEl, rows, virtual);
        }, 8000);
    }
}

function expandTableContainer(_data) {
    _expandFullTableContainer(
        _data.container_id,
        (_data && _data.rows) || [],
        [],
        false
    );
}

function expandVirtualTableContainer(_data) {
    _expandFullTableContainer(
        _data.container_id,
        (_data && _data.official) || [],
        (_data && _data.virtual)  || [],
        true
    );
}

function buildFullTableContent(resultsEl, rows) {
    resultsEl.innerHTML = '';
    resultsEl.style.flexDirection = 'column';

    const headerLabels = ['', '', 'M', 'Z', 'R', 'P', 'G+', 'G-', '+/-', 'Pkt', ''];
    const headerRow = document.createElement('div');
    headerRow.className = 'results-table-row specific-colors-reversed rotate-show-element0';
    headerLabels.forEach((label, i) => {
        const cell = document.createElement('div');
        cell.className = i === 1
            ? 'results-table-cell results-table-name'
            : 'results-table-cell';
        cell.textContent = label;
        headerRow.appendChild(cell);
    });
    resultsEl.appendChild(headerRow);

    rows.forEach((row, index) => {
        const el = document.createElement('div');
        el.className = `results-table-row specific-colors rotate-show-element${index + 1}`;
        el.dataset.teamName14 = row.team_name14;

        const gd = (row.goal_difference > 0 ? '+' : '') + row.goal_difference;
        [
            { text: index + 1,          name: false },
            { text: row.team_name14,    name: true  },
            { text: row.games    ?? '', name: false },
            { text: row.wins     ?? '', name: false },
            { text: row.draws    ?? '', name: false },
            { text: row.loses    ?? '', name: false },
            { text: row.goals_scored ?? '', name: false },
            { text: row.goals_lost   ?? '', name: false },
            { text: gd,                name: false },
            { text: row.points,        name: false },
        ].forEach(({ text, name }) => {
            const cell = document.createElement('div');
            cell.className = name
                ? 'results-table-cell results-table-name'
                : 'results-table-cell';
            cell.textContent = text;
            el.appendChild(cell);
        });

        const indicator = document.createElement('div');
        indicator.className = 'results-table-cell results-table-indicator';
        el.appendChild(indicator);

        resultsEl.appendChild(el);
    });

    // Measure, equalize, tilt, position — all inside temp body insertion
    resultsEl.style.position   = 'absolute';
    resultsEl.style.visibility = 'hidden';
    resultsEl.style.width      = document.body.offsetWidth + 'px';
    document.body.appendChild(resultsEl);

    // Equalize name cells — reset flex first to measure natural content width
    const nameCells = Array.from(resultsEl.querySelectorAll('.results-table-name'));
    nameCells.forEach(cell => { cell.style.flex = 'none'; cell.style.width = 'max-content'; });
    let maxNameW = 0;
    nameCells.forEach(cell => { maxNameW = Math.max(maxNameW, cell.offsetWidth); });
    nameCells.forEach(cell => { cell.style.width = maxNameW + 'px'; cell.style.flexShrink = '0'; });

    // Equalize non-name cell widths to the widest
    const nonNameCells = Array.from(
        resultsEl.querySelectorAll('.results-table-cell:not(.results-table-name)')
    );
    let maxCellW = 0;
    nonNameCells.forEach(cell => { maxCellW = Math.max(maxCellW, cell.offsetWidth); });
    nonNameCells.forEach(cell => { cell.style.width = maxCellW + 'px'; });

    // Apply tilt based on data row height and full row width
    const firstDataRow = resultsEl.querySelector('.results-table-row:not(:first-child)');
    if (firstDataRow) {
        const _h = firstDataRow.offsetHeight;
        const _w = firstDataRow.offsetWidth;
        if (_h > 0 && _w > 0) {
            const _polygon = makePolygonTilt(_h, _w, 'both');
            resultsEl.querySelectorAll('.results-table-row').forEach(row => {
                row.style.clipPath = _polygon;
            });
        }
    }

    // Golden ratio vertical positioning: top_margin / bottom_margin = 1/φ
    const tableH  = resultsEl.offsetHeight;
    const screenH = document.body.offsetHeight;
    const topPos  = Math.max(0, (screenH - tableH) / (1 + 1.618));
    resultsEl.style.top       = topPos + 'px';
    resultsEl.style.left      = '50%';
    resultsEl.style.transform = 'translateX(-50%)';

    document.body.removeChild(resultsEl);
    resultsEl.style.visibility = '';
    resultsEl.style.width      = '';
    // position stays 'absolute' — positioned relative to infoBody (100% w/h)
}

function animateFullTableSwap(container, officialRows, virtualRows) {
    const rowEls = Array.from(
        container.querySelectorAll('.results-table-row:not(:first-child)')
    );
    const indexMap = {};
    rowEls.forEach((el, i) => { indexMap[el.dataset.teamName14] = i; });

    virtualRows.forEach((itemB, indexB) => {
        const indexA = indexMap[itemB.team_name14];
        if (indexA === undefined) return;
        const el = rowEls[indexA];
        const cells = el.querySelectorAll('.results-table-cell');

        if (cells[0]) cells[0].textContent = indexB + 1;
        if (cells[9]) cells[9].textContent = itemB.points;

        const indicator = el.querySelector('.results-table-indicator');
        if (indicator) {
            indicator.classList.remove('promotion', 'degradation');
            if (indexB < indexA)      indicator.classList.add('promotion');
            else if (indexB > indexA) indicator.classList.add('degradation');
        }

        if (indexA !== indexB) {
            const translateY = (indexB - indexA) * el.offsetHeight;
            el.style.animation = 'none';
            el.style.transform = 'translateY(0px)';
            void el.offsetWidth;
            el.style.transform = `translateY(${translateY}px)`;
        }
    });
}

function expandSquadContainer(_containerId, _teamName, _teamShortName, _arr, _logo, _coach) {
    let squadContainer = document.getElementById(_containerId);
    squadContainer.innerHTML = '';
    addContentBackground(_containerId);
    let infoBody = document.createElement('div');
    addClassName(infoBody, 'info-body');
    addClassName(infoBody, 'animated-element');
    infoBody.dataset.animationOrder = '2';
    infoBody.style.position = 'relative';
    infoBody.style.zIndex = '1';
    // let infoBodyLeft = document.createElement('div');
    // addClassName(infoBodyLeft, 'info-body-left');
    // let infoBodyRight = document.createElement('div');
    // addClassName(infoBodyRight, 'info-body-right');
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
    // infoBodyLeft.appendChild(teamSquadContent);
    // infoBodyRight.appendChild(teamLogo);
    // infoBody.appendChild(infoBodyLeft);
    // infoBody.appendChild(infoBodyRight);
    infoBody.appendChild(teamSquadContent);
    infoBody.appendChild(teamLogo);
    squadContainer.appendChild(infoBody);
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

    // Tymczasowo wstaw squadContent do body — cały kontekst CSS zachowany
    squadContent.style.position   = 'absolute';
    squadContent.style.visibility = 'hidden';
    document.body.appendChild(squadContent);
    const _firstRow = squadContent.querySelector('.squad-player-row');
    if (_firstRow) {
        const _h = _firstRow.offsetHeight;
        const _w = _firstRow.offsetWidth;
        if (_h > 0 && _w > 0) {
            const _polygon = makePolygonTilt(_h, _w, 'both');
            squadContent.querySelectorAll('.squad-player-row').forEach(row => {
                row.style.clipPath = _polygon;
            });
        }
    }
    document.body.removeChild(squadContent);
    squadContent.style.position   = '';
    squadContent.style.visibility = '';
    return squadContent;
}

function updateRedCardsElement(_redCards, _element) {
    const wasVisible = _element.style.display === 'flex';
    const isVisible  = _redCards > 0;

    if (isVisible) {
        _element.textContent = _redCards > 1 ? String(_redCards) : '';
    }

    if (isVisible === wasVisible) return;

    if (_element._rcHandler) {
        _element.removeEventListener('animationend', _element._rcHandler);
        _element._rcHandler = null;
    }
    _element.style.animation = '';

    if (isVisible) {
        _element.style.top = '0px';
        _element.style.display = 'flex';
        void _element.offsetWidth;
        _element.style.animation = 'redCardSlideIn 400ms ease forwards';
    } else {
        _element.textContent = '';
        _element._rcHandler = function () {
            _element.removeEventListener('animationend', _element._rcHandler);
            _element._rcHandler = null;
            _element.style.display = 'none';
            _element.style.animation = '';
        };
        _element.addEventListener('animationend', _element._rcHandler);
        _element.style.animation = 'redCardSlideOut 400ms ease forwards';
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
        updateRedCardsElement(data.home_team_value2, homeTeamRedCardsElement);
    }
    if (typeof data.away_team_value2 != "undefined") {
        updateRedCardsElement(data.away_team_value2, awayTeamRedCardsElement);
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

        if (data.elapsed_time === undefined) {
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

    if (msg.type === 'banner_show') {
        const data = msg.payload || msg.data;
        const bannerContainer = document.getElementById('banner-container');
        bannerContainer.innerHTML = data.source || '';
        bannerContainer.style.display = 'block';
        if (data.activation_function && typeof window[data.activation_function] === 'function') {
            window[data.activation_function]();
        }
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

        if (typeof data.home_team_red_cards != "undefined") {
            updateRedCardsElement(data.home_team_red_cards, homeTeamRedCardsElement);
        }

        if (typeof data.away_team_red_cards != "undefined") {
            updateRedCardsElement(data.away_team_red_cards, awayTeamRedCardsElement);
        }

        if (typeof data.home_team_uniform != "undefined") {
            updateUniformElements(data.home_team_uniform, 'home-team-uniform');
        }

        if (typeof data.away_team_uniform != "undefined") {
            updateUniformElements(data.away_team_uniform, 'away-team-uniform');
        }

        if (typeof data.periods !== 'undefined') {
            const activePeriod = data.periods.find(p => p.status === 1);
            if (activePeriod) {
                showAddedTime(activePeriod.added_time ?? 0);
            }
        } else if (typeof data.added_time !== 'undefined') {
            showAddedTime(data.added_time);
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

    if (msg.type === 'added_time_updated') {
        const data = msg.payload || msg.data;
        showAddedTime(data.added_time);
    }
}

function showAddedTime(added_time) {
    const addedTimeDisplay = document.getElementById('added-time-display');
    const addedTimeLabel = document.getElementById('added-time-label');

    addedTimeLabel.innerText = added_time > 0 ? `+${added_time}'` : '';

    if (currentAddedTime === 0 && added_time > 0) {
        addedTimeDisplay.style.animation = 'none';
        addedTimeDisplay.offsetHeight;
        addedTimeDisplay.style.animation = 'addedTimeSlideIn 500ms ease-in-out both';
    } else if (currentAddedTime > 0 && added_time === 0) {
        addedTimeDisplay.style.animation = 'none';
        addedTimeDisplay.offsetHeight;
        addedTimeDisplay.style.animation = 'addedTimeSlideOut 500ms ease-in-out both';
    }

    currentAddedTime = added_time;
}