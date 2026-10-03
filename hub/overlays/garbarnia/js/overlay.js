// WebSocket z rejestracją jako overlay + subskrypcja timer
const overlayId = 'stream-overlay';
const ws = new WebSocket(`ws://${window.location.hostname}:${window.location.port}/ws`);

const rootApp = 'http://localhost:8081/';

const display = document.getElementById('main-timer-display');

let registered = false;
let currentAddedTime = 0;
let addedTimeCounterActive = false;

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
    if (classList.contains('interview-container')) return 'interview';
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

// ── Mechanizm podstawowy: hook override + generyczny fallback ───────────
// Dodanie NOWEGO kontenera (nowy div w overlay.html) nie wymaga ŻADNEJ
// zmiany w tym pliku: showContainer/closeContainer najpierw sprawdzają, czy
// motyw (style-override.js) zdefiniował window.override_<containerId>_open
// / _close — jeśli tak, ten kontener jest w całości pod jego kontrolą.
// Jeśli nie, a containerType nie jest jednym ze znanych typów (squad/start/
// break/results/table/virtual-table/shootout/game), treść renderowana jest
// generycznie (renderGenericContent — tabela dla tablicy, lista
// klucz:wartość dla obiektu) i pokazywana/chowana prostym fade
// (prepareToOpenContainer/closeDefaultContainer, już generyczne). Wywiad
// (interview) ma własny, odrębny mechanizm (generateInfoContainer) i nie
// przechodzi przez ten hook.
function resolveContainerOverride(containerId, phase) {
    const fn = window[`override_${containerId}_${phase}`];
    return typeof fn === 'function' ? fn : null;
}

function renderGenericContent(container, data) {
    container.innerHTML = '';
    if (data === undefined || data === null) return;
    const wrapper = document.createElement('div');
    addClassName(wrapper, 'generic-container-content');
    if (Array.isArray(data)) {
        wrapper.appendChild(renderGenericTable(data));
    } else if (typeof data === 'object') {
        wrapper.appendChild(renderGenericRecord(data));
    } else {
        wrapper.textContent = String(data);
    }
    container.appendChild(wrapper);
}

function renderGenericTable(rows) {
    const table = document.createElement('table');
    addClassName(table, 'generic-container-table');
    if (rows.length && typeof rows[0] === 'object' && rows[0] !== null) {
        const keys = Object.keys(rows[0]);
        const headRow = document.createElement('tr');
        keys.forEach(k => {
            const th = document.createElement('th');
            th.textContent = k;
            headRow.appendChild(th);
        });
        table.appendChild(headRow);
        rows.forEach(row => {
            const tr = document.createElement('tr');
            keys.forEach(k => {
                const td = document.createElement('td');
                const v = row[k];
                td.textContent = (v === null || v === undefined) ? '' : String(v);
                tr.appendChild(td);
            });
            table.appendChild(tr);
        });
    } else {
        rows.forEach(item => {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.textContent = String(item);
            tr.appendChild(td);
            table.appendChild(tr);
        });
    }
    return table;
}

function renderGenericRecord(obj) {
    const dl = document.createElement('dl');
    addClassName(dl, 'generic-container-record');
    Object.entries(obj).forEach(([k, v]) => {
        const dt = document.createElement('dt');
        dt.textContent = k;
        const dd = document.createElement('dd');
        dd.textContent = (v === null || v === undefined) ? '' : (typeof v === 'object' ? JSON.stringify(v) : String(v));
        dl.appendChild(dt);
        dl.appendChild(dd);
    });
    return dl;
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

    if (containerType !== 'interview') {
        const overrideOpen = resolveContainerOverride(containerId, 'open');
        if (overrideOpen) {
            overrideOpen(containerId, _data, targetContainer);
            return;
        }
    }

    if (containerType === 'none') {
        prepareToOpenContainer();
    } else if (containerType === 'interview') {
        // Karta (.interview-content) startuje i zostaje display:none — nie
        // odkrywamy jej tu automatycznie (w odróżnieniu od innych typów).
        // Widoczność steruje wyłącznie show_interview/hide_interview, żeby
        // operator mógł otworzyć ten kontener raz i pokazywać/chować kartę
        // wielokrotnie w trakcie jednego wywiadu.
        generateInfoContainer('interview-content', 'match-notification');
        if (_data) updateInterviewData(_data);
        prepareToOpenContainer(openContainer, targetContainer);
    } else if (containerType === 'shootout') {
        // Dogrywka NIE jest (jeszcze) częścią motywu "garbarnia" — działa
        // tak jak dotąd, niezależnie od aktywnego stylingClass.
        fillShootoutContainer(_data);
        prepareToOpenContainer(openContainer, targetContainer);
    } else if (containerType === 'game') {
        // #game-container ma TREŚĆ STATYCZNĄ (scoreboard już w overlay.html),
        // nie generowaną z danych — renderGenericContent by ją wymazał.
        // Bez override (motyw "garbarnia") po prostu pokazujemy kontener
        // takim, jaki jest.
        prepareToOpenContainer(openContainer, targetContainer);
    } else {
        // squad/start/break/results/table/virtual-table: dziś zawsze
        // obsługiwane przez motyw "garbarnia" (patrz override hook powyżej)
        // — ta gałąź to czysty fallback na wypadek wyczyszczenia
        // stylingClass (mechanizm podstawowy, generyczny render + fade).
        renderGenericContent(targetContainer, _data);
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
    notifyActiveContainerChanged(container.id);
}

// Informuje backend (przez hub, adresowanie 'main-module' — jak
// request_game_data) o aktualnie widocznym głównym kontenerze, żeby admin
// UI mógł podświetlić odpowiedni .overlay-switcher na zielono.
// containerId=null oznacza "nic nie jest pokazywane" (po zamknięciu, przed
// ewentualnym otwarciem kolejnego — patrz openContainer/closeContainer).
function notifyActiveContainerChanged(containerId) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({
        from: overlayId,
        to: 'main-module',
        type: 'active_container_changed',
        payload: { container_id: containerId },
    }));
}

// openGameContainer przeniesiona (jako garbarniaOpenGameContainer) do
// style/garbarnia/js/style.js — zarejestrowana jako override_game-container_open.

function closeContainer(_container) {
    let container = _container;
    let containerType = getContainerType(container);
    let animationDuration = 1000;

    if (containerType !== 'interview') {
        const overrideClose = resolveContainerOverride(container.id, 'close');
        if (overrideClose) {
            // Override może opcjonalnie zwrócić własny czas trwania (ms) —
            // jeśli nie, używamy domyślnego 1000ms jak reszta mechanizmu.
            const customDuration = overrideClose(container);
            const duration = (typeof customDuration === 'number') ? customDuration : animationDuration;
            setTimeout(() => {
                clearAnimations(container);
                container.style.display = 'none';
                notifyActiveContainerChanged(null);
            }, duration);
            return;
        }
    }

    // squad/start/break/game/results/table/virtual-table mają dziś zawsze
    // override_<id>_close (motyw "garbarnia", patrz hook powyżej) —
    // trafienie tutaj dla nich (i dla shootout, który override'u nie ma)
    // oznacza brak aktywnego motywu, więc generyczny fade jest poprawnym
    // mechanizmem podstawowym.
    console.log(`containerType: ${containerType}`);
    closeDefaultContainer(container);

    // Wyczyść animacje po ich zakończeniu
    setTimeout(() => {
        // Usuń tymczasowe animacje
        clearAnimations(container);
        container.style.display = 'none';
        notifyActiveContainerChanged(null);
    }, animationDuration);
}

// ── WYNIKI / TABELA ──────────────────────────────────────────────────────

var _resultsTimer = null;   // guard przed wielokrotnym wywołaniem
var _resultsTimer2 = null;  // timer animacji zamiany (virtual_table)

// ── Budowanie DOM ─────────────────────────────────────────────────────────

// buildResultsContent przeniesiona (jako garbarniaBuildResultsContent) do
// style/garbarnia/js/style.js — jedyny wołający (expandResultsContainer)
// przeniósł się tam razem z nią.

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

// closeSquadContainer/closeStartContainer/restartAnimation/
// setBreakElementClosedState/_closeResultsBase/closeResultsContainer/
// closeTableContainer/closeVirtualTableContainer/closeGameContainer/
// closeBreakContainer przeniesione do style/garbarnia/js/style.js (motyw
// "garbarnia") — zarejestrowane tam jako override_<containerId>_close.
// Brak override (styling_class wyczyszczony) spada na closeDefaultContainer
// poniżej.

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

// addContentBackground/hideContentBackground/expandStartBottomSpecificContainer/
// expandStartBottomInfoContainer/generateScorersList przeniesione do
// style/garbarnia/js/style.js (motyw "garbarnia") — zarejestrowane tam
// jako override_<containerId>_open (poprzez garbarniaExpand*).

// expandBreakContainer/expandStartContainer przeniesione do
// style/garbarnia/js/style.js (motyw "garbarnia") — zarejestrowane tam
// jako override_break-container_open / override_start-container_open.

// ── Generyczny generator "paska powiadomień" ────────────────────────────
// #action_info_container (belka eventów meczowych, patrz handler 'show_info'
// niżej) i .interview-content (karta wywiadu) mają tę samą rolę: ikona +
// blok tekstu, pokazywane na chwilę z animacją wejścia/wyjścia. Zamiast
// dwóch niezależnych implementacji, oba generowane są przez jedno wejście —
// generateInfoContainer(containerName, stylingClass) — które samo
// dobiera właściwy "budowniczy treści" wg nazwy kontenera. Klasa
// stylizująca (2. argument) nie zmienia TEGO builder-a: decyduje tylko o
// tym, jakie klasy enter/exit (patrz showNotificationContainer/
// hideNotificationContainer niżej) zostaną użyte przy pokazywaniu/chowaniu —
// więc przygotowanie nowego kompletu klas CSS (np. "inna-animacja-icon-enter/
// exit", "inna-animacja-text-enter/exit") i podanie jej nazwy w obu
// wywołaniach generatora od razu zmienia wygląd/zachowanie OBU kontenerów
// naraz, bez dotykania JS.
function generateInfoContainer(containerName, stylingClass) {
    if (containerName === 'action_info_container') {
        return buildActionInfoContainerContent(stylingClass);
    }
    if (containerName === 'interview-content') {
        return buildInterviewContainerContent(stylingClass);
    }
    console.error(`generateInfoContainer: nieznany containerName "${containerName}"`);
    return null;
}

// Buduje wnętrze #action_info_container od zera (ikona w kwadracie, blok
// tekstu z minutą/zawodnikiem/drużyną, kwadrat-wypełniacz na symetrię) —
// identyczna struktura co dotąd statyczny HTML w overlay.html, tylko teraz
// generowana przy każdym 'show_info'. Elementy, które handler 'show_info'
// musi później wypełnić danymi, zachowują swoje stałe id.
function buildActionInfoContainerContent(stylingClass) {
    let container = document.getElementById('action_info_container');
    if (!container) return null;
    container.innerHTML = '';
    container.dataset.stylingClass = stylingClass;
    addClassName(container, `${stylingClass}-container`);

    let iconSquare = document.createElement('div');
    addClassName(iconSquare, 'action_square');
    iconSquare.id = 'action_icon';
    let iconImg = document.createElement('img');
    iconImg.id = 'action_icon_img';
    addClassName(iconImg, 'info-container-icon');
    iconSquare.appendChild(iconImg);

    let infoText = document.createElement('div');
    infoText.id = 'action_info_text';
    addClassName(infoText, 'info-container-text');

    let minuteEl = document.createElement('div');
    addClassName(minuteEl, 'action_minute');
    let timeSpan = document.createElement('span');
    timeSpan.id = 'action_time';
    minuteEl.appendChild(timeSpan);

    let playerEl = document.createElement('div');
    playerEl.id = 'action_player';
    let playerNameSpan = document.createElement('span');
    playerNameSpan.id = 'action_player_name';
    let playerTeamSpan = document.createElement('span');
    playerTeamSpan.id = 'action_player_team_short_name';
    playerEl.appendChild(playerNameSpan);
    playerEl.appendChild(playerTeamSpan);

    let minuteInvisible = document.createElement('div');
    addClassName(minuteInvisible, 'action_minute');
    addClassName(minuteInvisible, 'invisible_text');

    let cleaner = document.createElement('div');
    addClassName(cleaner, 'cleaner');

    let teamNameEl = document.createElement('div');
    teamNameEl.id = 'action_team_name';

    infoText.appendChild(minuteEl);
    infoText.appendChild(playerEl);
    infoText.appendChild(minuteInvisible);
    infoText.appendChild(cleaner);
    infoText.appendChild(teamNameEl);

    let spacerSquare = document.createElement('div');
    addClassName(spacerSquare, 'action_square');
    spacerSquare.appendChild(document.createElement('p'));

    container.appendChild(iconSquare);
    container.appendChild(infoText);
    container.appendChild(spacerSquare);

    return container;
}

// Buduje szkielet karty wywiadu (zdjęcie, imię i nazwisko, opis) w
// #interview-container, tą samą "powłoką" co pasek akcji (kwadrat z ikoną +
// kwadrat-wypełniacz, patrz .action_square) — stąd wspólne klasy
// .info-container-icon/.info-container-text (czytane przez
// showNotificationContainer/hideNotificationContainer). Karta
// (.interview-content) zostaje display:none — jej widoczność i treść są
// sterowane osobnymi sygnałami hub (show_interview/hide_interview/
// update_interview, patrz ws.onmessage), nie tym wywołaniem — to tylko
// przygotowuje puste miejsce pod te dane.
function buildInterviewContainerContent(stylingClass) {
    let container = document.getElementById('interview-container');
    if (!container) return null;
    container.innerHTML = '';

    let content = document.createElement('div');
    addClassName(content, 'interview-content');
    content.dataset.stylingClass = stylingClass;
    addClassName(content, `${stylingClass}-container`);

    let iconSquare = document.createElement('div');
    addClassName(iconSquare, 'action_square');
    let iconImg = document.createElement('img');
    addClassName(iconImg, 'interview-image');
    addClassName(iconImg, 'info-container-icon');
    iconSquare.appendChild(iconImg);

    let infoText = document.createElement('div');
    addClassName(infoText, 'interview-text');
    addClassName(infoText, 'info-container-text');
    let name = document.createElement('div');
    addClassName(name, 'interview-name');
    let description = document.createElement('div');
    addClassName(description, 'interview-description');
    infoText.appendChild(name);
    infoText.appendChild(description);

    let spacerSquare = document.createElement('div');
    addClassName(spacerSquare, 'action_square');
    spacerSquare.appendChild(document.createElement('p'));

    content.appendChild(iconSquare);
    content.appendChild(infoText);
    content.appendChild(spacerSquare);
    container.appendChild(content);

    return content;
}

// Podmienia zdjęcie/imię-nazwisko/opis w już zbudowanej karcie wywiadu, bez
// zmiany jej widoczności. Każde pole jest aktualizowane tylko jeśli zostało
// przekazane — dzięki temu sygnał może podmienić np. samo zdjęcie.
function updateInterviewData(_data) {
    let container = document.getElementById('interview-container');
    if (!container) return;
    let image = container.querySelector('.interview-image');
    let name = container.querySelector('.interview-name');
    let description = container.querySelector('.interview-description');

    if (image && _data.image !== undefined) {
        // rootApp: ścieżki obrazków (domyślne ikony typu, herb drużyny) są
        // względne, tak jak home_team_logo w expandStartContainer — stąd ten
        // sam prefiks.
        image.src = _data.image ? `${rootApp}${_data.image}` : '';
    }
    if (name && _data.name !== undefined) {
        name.innerText = _data.name || '';
    }
    if (description && _data.description !== undefined) {
        description.innerText = _data.description || '';
    }
}

// ── Pokazywanie/chowanie z animacją — wspólne dla obu kontenerów ────────
// stylingClass musi być tą samą nazwą podaną przy generateInfoContainer —
// to ona wskazuje, których klas enter/exit (zdefiniowanych w action.css)
// użyć. Timer auto-chowania przechowywany jest na samym elemencie
// (contentEl._notifAutoHideTimer), nie w zmiennej modułowej, żeby ta sama
// funkcja mogła bezpiecznie obsługiwać kilka różnych kontenerów naraz.
const NOTIFICATION_EXIT_ANIM_MS = 400; // zgodne z match-notification-*-exit w action.css

// identity (opcjonalny): {kind: 'action_info'|'interview', id: <game_event_id|participant_id>}
// — potrzebny tylko po to, żeby przy AUTOMATYCZNYM zamknięciu (upłynięcie
// autoHideMs, bez ingerencji operatora) overlay mógł odesłać sygnał
// overlay->hub->backend->UI z informacją "to id właśnie przestało się
// wyświetlać" (patrz notifyNotificationAutoHidden). Manualne zamknięcie
// (hide_info/hide_interview z admina) NIE przechodzi przez ten mechanizm —
// backend już wie o zmianie stanu, bo to on ją zainicjował.
function showNotificationContainer(contentEl, stylingClass, displayValue, autoHideMs, identity) {
    if (!contentEl) return;
    clearTimeout(contentEl._notifAutoHideTimer);
    let icon = contentEl.querySelector('.info-container-icon');
    let text = contentEl.querySelector('.info-container-text');

    contentEl.style.display = displayValue;

    // Restart animacji wejścia nawet jeśli element już miał klasę exit
    // (np. szybkie ponowne show po hide) — bez resetu animation+reflow
    // przeglądarka czasem nie odtworzy animacji od nowa.
    if (icon) { removeClassName(icon, `${stylingClass}-icon-exit`); icon.style.animation = 'none'; }
    if (text) { removeClassName(text, `${stylingClass}-text-exit`); text.style.animation = 'none'; }
    void contentEl.offsetHeight; // reflow
    if (icon) { icon.style.animation = ''; addClassName(icon, `${stylingClass}-icon-enter`); }
    if (text) { text.style.animation = ''; addClassName(text, `${stylingClass}-text-enter`); }

    if (autoHideMs) {
        contentEl._notifAutoHideTimer = setTimeout(() => {
            hideNotificationContainer(contentEl, stylingClass);
            notifyNotificationAutoHidden(identity);
        }, autoHideMs);
    }
}

// Odsyła do backendu (przez hub, adresowanie 'main-module' — tak samo jak
// request_game_data) informację, że dana notyfikacja sama się zamknęła, bo
// operator nie zrobił tego ręcznie. Backend na tej podstawie przestawia
// stan w adminie (zielony->szary) bez czekania na kolejną interakcję.
function notifyNotificationAutoHidden(identity) {
    if (!identity || identity.id === undefined || identity.id === null) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({
        from: overlayId,
        to: 'main-module',
        type: 'notification_auto_hidden',
        payload: identity,
    }));
}

function hideNotificationContainer(contentEl, stylingClass) {
    if (!contentEl) return;
    clearTimeout(contentEl._notifAutoHideTimer);
    contentEl._notifAutoHideTimer = null;
    if (contentEl.style.display === 'none') return;
    let icon = contentEl.querySelector('.info-container-icon');
    let text = contentEl.querySelector('.info-container-text');

    // Ten sam reset animation+reflow co w showNotificationContainer: klasa
    // exit używa tego samego @keyframes co enter (tylko reverse), więc samo
    // podmienienie klas bez restartu bywa przez przeglądarkę zignorowane —
    // element po prostu zamiera w ostatnim stanie, a po timeoucie "ucina"
    // się do display:none bez animacji.
    if (icon) { removeClassName(icon, `${stylingClass}-icon-enter`); icon.style.animation = 'none'; }
    if (text) { removeClassName(text, `${stylingClass}-text-enter`); text.style.animation = 'none'; }
    void contentEl.offsetHeight; // reflow
    if (icon) { icon.style.animation = ''; addClassName(icon, `${stylingClass}-icon-exit`); }
    if (text) { text.style.animation = ''; addClassName(text, `${stylingClass}-text-exit`); }

    setTimeout(() => {
        contentEl.style.display = 'none';
    }, NOTIFICATION_EXIT_ANIM_MS);
}

// Auto-chowanie karty wywiadu, jeśli operator sam nie wywoła hide_interview
// (tak samo jak pasek akcji w handlerze 'show_info' niżej — tam również
// 11.1s). Tutaj timer restartowany przy każdym show_interview, bo wywiad
// może zostać odsłonięty wielokrotnie.
const INTERVIEW_AUTO_HIDE_MS = 11100;

function showInterviewContent(_data) {
    let content = document.querySelector('#interview-container .interview-content');
    let identity = { kind: 'interview', id: _data && _data.participant_id };
    showNotificationContainer(content, 'match-notification', 'flex', INTERVIEW_AUTO_HIDE_MS, identity);
}

function hideInterviewContent() {
    let content = document.querySelector('#interview-container .interview-content');
    hideNotificationContainer(content, 'match-notification');
}

// expandResultsContainer/_expandFullTableContainer/expandTableContainer/
// expandVirtualTableContainer/buildFullTableContent/animateFullTableSwap/
// expandSquadContainer/createTeamSquad przeniesione do
// style/garbarnia/js/style.js (motyw "garbarnia") — zarejestrowane tam jako
// override_<containerId>_open. buildResultsContent (powyżej, ~l.339) NIE
// jest przenoszona — to inna funkcja niż buildResultsContentGame (mini-
// widget), ale żeby jej nie zgubić: patrz garbarniaBuildResultsContent w
// motywie, osobna kopia.

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

        // Świeży load overlayu — wszystkie kontenery startują display:none
        // w HTML, więc "aktywny" jest none. Jeśli admin UI akurat czeka na
        // odświeżenie, od razu dostaje poprawny (zgaszony) stan.
        notifyActiveContainerChanged(null);

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
            // remove_timer (koniec/zmiana części) wysyła "timer_updated" bez elapsed_time —
            // to sygnał, że stary main timer przestał istnieć, więc doliczony czas
            // poprzedniej części trzeba schować od razu, a nie dopiero po pierwszym
            // ticku nowej części (inaczej wisi na ekranie do startu odliczania).
            // Kary (timer_id zaczynające się od "penalty_") są tu pomijane — ich
            // usunięcie nie powinno wpływać na wyświetlanie doliczonego czasu gry.
            if (!(data.timer_id && data.timer_id.startsWith('penalty_'))) {
                updateAddedTimeCounter(null);
            }
        } else {
            // limit dotyczy elapsed_time tej części (bez initial_time — patrz plugin.go)
            const limit = data.limit;
            const isOvertime = typeof limit === 'number' && limit > 0 && data.elapsed_time >= limit;

            if (isOvertime) {
                // Główny zegar zamraża się na wartości limitu, doliczony czas idzie od 00:00
                display.textContent = FutsalFormatters.formatElapsedTime(limit, data.initial_time);
                updateAddedTimeCounter(data.elapsed_time - limit);
            } else {
                // Aktualizuj wyświetlanie głównego zegara
                display.textContent = FutsalFormatters.formatElapsedTime(
                    data.elapsed_time, data.initial_time
                );
                updateAddedTimeCounter(null);
            }

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

    // Wywiad: podmiana treści (zdjęcie/imię-nazwisko/opis) i pokazywanie/
    // chowanie karty niezależnie od otwierania/zamykania samego kontenera
    // (patrz generateInfoContainer/buildInterviewContainerContent oraz
    // showContainer 'interview').
    if (msg.type === 'update_interview') {
        const data = msg.payload || msg.data;
        updateInterviewData(data);
    }

    if (msg.type === 'show_interview') {
        showInterviewContent(msg.payload || msg.data);
    }

    if (msg.type === 'hide_interview') {
        hideInterviewContent();
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
        let actionInfoContainer = generateInfoContainer('action_info_container', 'match-notification');
        if (actionInfoContainer) {
            let actionImgElement = actionInfoContainer.querySelector('#action_icon_img');
            let actionTimeElement = actionInfoContainer.querySelector('#action_time');
            let actionPlayerInfoElement = actionInfoContainer.querySelector('#action_player_name');
            let actionPlayerTeamShortNameElement = actionInfoContainer.querySelector('#action_player_team_short_name');
            let actionTeamNameElement = actionInfoContainer.querySelector('#action_team_name');

            actionImgElement.src = `${rootApp}${data.event_image_path}`;
            actionTimeElement.textContent = (data.period_limit_s !== undefined)
                ? formatGameTimeDisplay(data.game_time, data.period_limit_s)
                : FutsalFormatters.formatElapsedTime(data.game_time, 0, { 'format': 'min', 'unit': 's' });
            actionPlayerInfoElement.textContent = `${data.player_number ?? ''} ${data.player_name ?? ''}`.trim();
            actionPlayerTeamShortNameElement.textContent =
                actionPlayerTeamShortNameElementGenerator(data.player_team_short_name ?? '', data.event_type_id);
            actionTeamNameElement.textContent = data.team_name ?? '';

            showNotificationContainer(actionInfoContainer, 'match-notification', 'block', 11100,
                { kind: 'action_info', id: data.game_event_id });
        }
    }

    if (msg.type === 'hide_info') {
        let actionInfoContainer = document.getElementById('action_info_container');
        hideNotificationContainer(actionInfoContainer, 'match-notification');
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
    // Sam label tylko aktualizuje treść — pokazanie/schowanie #added-time-display
    // steruje teraz updateAddedTimeCounter() w momencie startu/końca doliczonego czasu.
    const addedTimeLabel = document.getElementById('added-time-label');
    addedTimeLabel.innerText = added_time > 0 ? `+${added_time}'` : '';
    currentAddedTime = added_time;
}

function updateAddedTimeCounter(overtimeMs) {
    const addedTimeDisplay = document.getElementById('added-time-display');
    const addedTimeCounter = document.getElementById('added-time-counter');

    if (overtimeMs === null) {
        addedTimeCounter.innerText = FutsalFormatters.formatElapsedTime(0, 0, { format: 'mm:ss' });
        if (addedTimeCounterActive) {
            addedTimeCounterActive = false;
            addedTimeDisplay.style.animation = 'none';
            addedTimeDisplay.offsetHeight;
            addedTimeDisplay.style.animation = 'addedTimeSlideOut 500ms ease-in-out both';
        }
        return;
    }

    addedTimeCounter.innerText = FutsalFormatters.formatElapsedTime(overtimeMs, 0, { format: 'mm:ss' });

    if (!addedTimeCounterActive) {
        addedTimeCounterActive = true;
        addedTimeDisplay.style.animation = 'none';
        addedTimeDisplay.offsetHeight;
        addedTimeDisplay.style.animation = 'addedTimeSlideIn 500ms ease-in-out both';
    }
}