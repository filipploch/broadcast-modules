// ============================================================================
// Motyw "garbarnia" — wygląd i zachowanie kontenerów specyficznych dla
// garbarni (game/squad/start/break/results/table/virtual-table). Każda
// funkcja window.override_<containerId>_open/_close rejestruje się jako
// nadpisanie mechanizmu podstawowego (patrz overlay.js: resolveContainerOverride,
// showContainer/closeContainer) dla DANEGO kontenera. Treść poniżej to
// dzisiejszy kod przeniesiony z overlay.js — logika nie została zmieniona,
// tylko przeniesiona pod tę konwencję.
//
// Garbarnia (w odróżnieniu od futsal-nalf) ma własne dekoracyjne tło
// (addContentBackground/hideContentBackground — ukośne panele + biały pas)
// używane przez squad/start/break/results/table/virtual-table, oraz własną,
// bogatszą choreografię 'game' (openGameContainer/closeGameContainer) — stąd
// ten plik jest znacznie większy niż odpowiednik dla "nalf".
//
// Funkcje bazowe, których ten plik NIE przenosi (współdzielone z innymi,
// niemigrowanymi funkcjami w tym samym module — mini-widget
// #results-table-container, scoreboard itd.) i na które poniższy kod się
// powołuje: prepareToOpenContainer, openContainer, activateElementsAfterTime,
// makePolygonTilt, rootApp, addClassName, getCurrentDate, setLeagueLogo,
// currentAddedTime, addedTimeCounterActive.
// ============================================================================

// ── Tło dekoracyjne (ukośne panele + biały pas) ──────────────────────────
// Używane przez squad/start/break/results/table/virtual-table.

function garbarniaAddContentBackground(_containerId) {
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

function garbarniaHideContentBackground(container) {
    const contentContainer = container.querySelector('#content-container');
    if (!contentContainer) return;
    const leftSide    = contentContainer.querySelector('#background-left-side');
    const rightSide   = contentContainer.querySelector('#background-right-side');
    const whiteStripe = contentContainer.querySelector('#white-stripe');
    garbarniaRestartAnimation(rightSide,       'rightSideSlide 500ms ease-out 250ms reverse both');
    garbarniaRestartAnimation(leftSide,        'leftSideSlide 500ms ease-out 250ms reverse both');
    garbarniaRestartAnimation(whiteStripe,     'whiteStripeSlide 500ms ease-out 250ms reverse both');
    garbarniaRestartAnimation(contentContainer,'contentContainerFade 500ms ease-out 750ms reverse both');
}

function garbarniaRestartAnimation(element, animationValue) {
    if (!element) return;
    element.style.animation = 'none';
    void element.offsetWidth;
    element.style.animation = animationValue;
}

function garbarniaSetBreakElementClosedState(element, properties) {
    if (!element) return;
    Object.entries(properties).forEach(([property, value]) => {
        element.style[property] = value;
    });
}

// ── GAME (scoreboard) ─────────────────────────────────────────────────────

function garbarniaOpenGameContainer(container) {
    openContainer(container);
    document.querySelectorAll('.both-side-tilted').forEach(element => {
        element.style.clipPath = makePolygonTilt(element.offsetHeight, element.offsetWidth, 'both');
    });

    const addedTimeDisplay = document.getElementById('added-time-display');
    const addedTimeLabel = document.getElementById('added-time-label');
    addedTimeLabel.innerText = currentAddedTime > 0 ? `+${currentAddedTime}'` : '';
    addedTimeDisplay.style.animation = 'none';
    addedTimeDisplay.offsetHeight;
    addedTimeDisplay.style.transform = addedTimeCounterActive ? 'translateX(170px)' : 'translateX(-15px)';
    let scoreboardContainer = document.getElementById('scoreboard-container');
    scoreboardContainer.style.animation = null;
    scoreboardContainer.style.animation = 'scoreboardSlideIn 500ms ease-in-out 300ms both';
}

function garbarniaCloseGameContainer(container) {
    const scoreboardContainer = container.querySelector('#scoreboard-container');
    if (scoreboardContainer) {
        garbarniaRestartAnimation(scoreboardContainer, 'scoreboardSlideIn 500ms ease-in-out 300ms reverse both');
    }
}

window['override_game-container_open'] = function (containerId, data, targetContainer) {
    if (typeof data.added_time !== 'undefined') currentAddedTime = data.added_time;
    prepareToOpenContainer(garbarniaOpenGameContainer, targetContainer);
};
window['override_game-container_close'] = garbarniaCloseGameContainer;

// ── SQUAD ────────────────────────────────────────────────────────────────
// UWAGA: w odróżnieniu od innych funkcji w tym pliku, ta NIE ma prefiksu
// "garbarnia" — zostaje nazwana dosłownie createTeamSquad, bo
// js/specific.js (ładowany jako baseline, nie część tego motywu) robi
// window.addEventListener('load', ...) monkey-patch TEJ GLOBALNEJ NAZWY,
// żeby dodać sekcje podstawowi/rezerwa/trener (pole `role`). Zmiana nazwy
// tutaj odłączyłaby ten monkey-patch i squad straciłby sekcję trenera.

function createTeamSquad(_arr, _logo, _coach) {
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

function garbarniaExpandSquadContainer(_containerId, _teamName, _teamShortName, _arr, _logo, _coach) {
    let squadContainer = document.getElementById(_containerId);
    squadContainer.innerHTML = '';
    garbarniaAddContentBackground(_containerId);
    let infoBody = document.createElement('div');
    addClassName(infoBody, 'info-body');
    addClassName(infoBody, 'animated-element');
    infoBody.dataset.animationOrder = '2';
    infoBody.style.position = 'relative';
    infoBody.style.zIndex = '1';
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
    infoBody.appendChild(teamSquadContent);
    infoBody.appendChild(teamLogo);
    squadContainer.appendChild(infoBody);
}

function garbarniaCloseSquadContainer(container) {
    garbarniaHideContentBackground(container);
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

window['override_home-team-squad-container_open'] = function (containerId, data, targetContainer) {
    let teamCoach = (data.coach !== 'undefined') ? data.coach : null;
    garbarniaExpandSquadContainer(containerId, data.team_name, data.team_short_name, data.team_squad, data.logo, teamCoach);
    let addedDelayTime = prepareToOpenContainer(openContainer, targetContainer);
    activateElementsAfterTime('squad-content', 2000 + addedDelayTime);
};
window['override_away-team-squad-container_open'] = window['override_home-team-squad-container_open'];
window['override_home-team-squad-container_close'] = garbarniaCloseSquadContainer;
window['override_away-team-squad-container_close'] = garbarniaCloseSquadContainer;

// ── START ────────────────────────────────────────────────────────────────
// Garbarnia renderuje start i break DWIEMA różnymi funkcjami (w odróżnieniu
// od nalf, który reużywa jednej z flagą) — zachowane 1:1.

function garbarniaExpandStartBottomSpecificContainer(_headerText, _arr) {
    let html = '';
    if (_arr.length === 0) {
        return html;
    } else {
        let header = `
                <div class="start-bottom-header specific-colors">${_headerText}</div>
            `;
        html += header;
        let _body = '';
        _arr.forEach(el => {
            let _bodyElement = `<div class="start-bottom-body">${el.name}</div>`;
            _body += _bodyElement;
        });
        html += _body;
        return html;
    }
}

function garbarniaExpandStartBottomInfoContainer(_gameData) {
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
    refereesContainer.innerHTML = garbarniaExpandStartBottomSpecificContainer(redereesContainerHeadText, referees);
    commentatorsContainer.innerHTML = garbarniaExpandStartBottomSpecificContainer('Komentarz', commentators);
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

function garbarniaExpandStartContainer(_gameData, _break = false) {
    let data = _gameData;
    const targetId = _break ? 'break-container' : 'start-container';
    let _startContainer = document.getElementById(targetId);
    _startContainer.innerHTML = '';
    garbarniaAddContentBackground(targetId);
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
        let homeTeamScorersWrapper = garbarniaGenerateScorersList(homeTeamScorers);
        homeTeamScorersContainer.appendChild(homeTeamScorersWrapper);

        let awayTeamScorersContainer = document.createElement('div');
        awayTeamScorersContainer.id = 'away-team-scorers-container';
        addClassName(awayTeamScorersContainer, 'team-scorers-container');
        let awayTeamScorers = _gameData.away_team_scorers.scorers;
        let awayTeamScorersWrapper = garbarniaGenerateScorersList(awayTeamScorers);
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
        let bottomInfoContainer = garbarniaExpandStartBottomInfoContainer(_gameData);
        startBottom.appendChild(bottomInfoContainer);
        startBody.appendChild(startBottom);

    }

    startContainer.appendChild(startBody);
    _startContainer.appendChild(startContainer);
}

function garbarniaCloseStartContainer(container) {
    garbarniaHideContentBackground(container);
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

window['override_start-container_open'] = function (containerId, data, targetContainer) {
    garbarniaExpandStartContainer(data, false);
    prepareToOpenContainer(openContainer, targetContainer);
    activateElementsAfterTime('start-content', 2500, 'flex');
};
window['override_start-container_close'] = garbarniaCloseStartContainer;

// ── PRZERWA (BREAK) ───────────────────────────────────────────────────────
// Garbarnia ma odrębną, bogatszą implementację przerwy (expandBreakContainer)
// niż start — nie reużywa garbarniaExpandStartContainer(..., true) tak jak
// robi to nalf. closeBreakContainer odwraca animacje wejścia konkretnych
// elementów (logo/nazwy/wynik), nie generyczny collapseHeight.

function garbarniaGenerateScorersList(_scorers, _side) {
    const isAway = (_side === 'away');

    const wrapper = document.createElement('div');
    Object.assign(wrapper.style, {
        width: '600px',
        padding: '0 20px'
    });

    _scorers.forEach((scorer, index) => {
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
            clipPath: isAway
                ? 'polygon(100% 0%, 97.75% 100%, 0% 100%, 0% 0%)'
                : 'polygon(100% 0%, 100% 100%, 0% 100%, 2.25% 0%)',
            animation: `rotateShowElement 250ms ease ${250 + 0 * 250}ms 1 reverse both`,
            visibility: 'visible'
        });
        row.dataset.scorerIndex = index;

        row.classList.add(
            'specific-colors',
            'rotate-show-element'
        );

        const firstName = document.createElement('span');
        Object.assign(firstName.style, {
            marginLeft: '30px'
        });
        firstName.textContent = scorer.player_first_name ?? '';

        const lastName = document.createElement('span');
        Object.assign(lastName.style, {
            paddingLeft: '10px',
            fontWeight: '700'
        });
        lastName.textContent = scorer.player_last_name ?? '';

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

function garbarniaExpandBreakContainer(_data) {
    const container = document.getElementById('break-container');
    if (!container) return;
    container.innerHTML = '';

    // ── #break-scorers-container ──────────────────────────────────────────
    const breakScorersContainer = document.createElement('div');
    breakScorersContainer.id = 'break-scorers-container';
    Object.assign(breakScorersContainer.style, {
        position: 'absolute',
        width: '1330px',
        height: '550px',
        left: '250px',
        bottom: '200px',
        display: 'none',
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

    const homeScorersCol = document.createElement('div');
    homeScorersCol.id = 'home-team-scorers-container';
    Object.assign(homeScorersCol.style, {
        width: '50%',
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'left'
    });
    const homeScorers = (_data.home_team_scorers && _data.home_team_scorers.scorers) || [];
    homeScorersCol.appendChild(garbarniaGenerateScorersList(homeScorers, 'home'));

    const awayScorersCol = document.createElement('div');
    awayScorersCol.id = 'away-team-scorers-container';
    Object.assign(awayScorersCol.style, {
        width: '50%',
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'right'
    });
    const awayScorers = (_data.away_team_scorers && _data.away_team_scorers.scorers) || [];
    awayScorersCol.appendChild(garbarniaGenerateScorersList(awayScorers, 'away'));

    scorersInner.appendChild(homeScorersCol);
    scorersInner.appendChild(awayScorersCol);
    breakScorersContainer.appendChild(scorersInner);

    // ── #result-container ─────────────────────────────────────────────────
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

    const xContainer = document.createElement('div');
    xContainer.id = 'x-container';
    Object.assign(xContainer.style, {
        position: 'absolute',
        top: '0',
        display: 'flex',
        height: '100%',
        width: '100%'
    });

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

    container.appendChild(breakScorersContainer);
    container.appendChild(resultContainer);
}

function garbarniaCloseBreakContainer(container) {
    garbarniaHideContentBackground(container);
    const players = container.querySelectorAll('.rotate-show-element');
    const homeTeamLogoContainer = container.querySelector('#home-team-logo-container');
    const awayTeamLogoContainer = container.querySelector('#away-team-logo-container');
    const homeTeamNameElement = container.querySelector('#home-team-name-element');
    const awayTeamNameElement = container.querySelector('#away-team-name-element');
    const resultElement = container.querySelector('#result-element');

    players.forEach(player => {
        garbarniaRestartAnimation(player, 'rotateHideElement 250ms ease 0ms 1 reverse forwards');
    });

    garbarniaRestartAnimation(
        homeTeamLogoContainer,
        'moveHomeTeamLogo 200ms ease-in-out 300ms 1 reverse forwards'
    );

    garbarniaRestartAnimation(
        awayTeamLogoContainer,
        'moveAwayTeamLogo 200ms ease-in-out 300ms 1 reverse forwards'
    );

    garbarniaRestartAnimation(
        homeTeamNameElement,
        'moveHomeTeamNameElement 300ms ease-in-out 500ms 1 reverse forwards'
    );

    garbarniaRestartAnimation(
        awayTeamNameElement,
        'moveAwayTeamNameElement 300ms ease-in-out 500ms 1 reverse forwards'
    );

    garbarniaRestartAnimation(
        resultElement,
        'resultFadeIn 300ms ease 700ms 1 reverse forwards'
    );

    setTimeout(() => {
        garbarniaSetBreakElementClosedState(homeTeamLogoContainer, {
            left: '130px',
            visibility: 'hidden'
        });

        garbarniaSetBreakElementClosedState(awayTeamLogoContainer, {
            right: '130px',
            visibility: 'hidden'
        });

        garbarniaSetBreakElementClosedState(homeTeamNameElement, {
            left: '500px',
            visibility: 'hidden'
        });

        garbarniaSetBreakElementClosedState(awayTeamNameElement, {
            right: '500px',
            visibility: 'hidden'
        });

        garbarniaSetBreakElementClosedState(resultElement, {
            opacity: 0
        });
    }, 850);
}

window['override_break-container_open'] = function (containerId, data, targetContainer) {
    garbarniaExpandBreakContainer(data);
    prepareToOpenContainer(openContainer, targetContainer);
    activateElementsAfterTime('break-content', 2500, 'flex');
};
window['override_break-container_close'] = garbarniaCloseBreakContainer;

// ── WYNIKI ───────────────────────────────────────────────────────────────
// buildResultsContent tutaj NIE jest współdzielony z mini-widgetem
// #results-table-container (ten używa innej funkcji, buildResultsContentGame,
// która zostaje w overlay.js) — można więc przenieść całość bez entanglementu.

function garbarniaBuildResultsContent(resultsEl, games) {
    resultsEl.innerHTML = '';
    resultsEl.classList.add('full-table');

    let header = document.createElement('div');
    header.id = 'results-header';
    header.className = 'results-row rotate-show-element0';
    header.textContent = 'WYNIKI';
    resultsEl.appendChild(header);

    games.forEach((game, index) => {
        let row = document.createElement('div');
        const statusClass = game.status === 2 ? 'finished' : 'pending';
        row.className = `results-row specific-colors rotate-show-element${index + 1} ${statusClass}`;

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

    resultsEl.style.position   = 'absolute';
    resultsEl.style.visibility = 'hidden';
    resultsEl.style.width      = document.body.offsetWidth + 'px';
    document.body.appendChild(resultsEl);

    const firstDataRow = resultsEl.querySelector('.results-row:not(:first-child)');
    if (firstDataRow) {
        const _h = firstDataRow.offsetHeight;
        const _w = firstDataRow.offsetWidth;
        if (_h > 0 && _w > 0) {
            const _polygon = makePolygonTilt(_h, _w, 'both');
            resultsEl.querySelectorAll('.results-row').forEach(row => {
                row.style.clipPath = _polygon;
            });
        }
    }

    resultsEl.style.top       = '50%';
    resultsEl.style.left      = '50%';
    resultsEl.style.transform = 'translate(-50%, -50%)';

    document.body.removeChild(resultsEl);
    resultsEl.style.visibility = '';
    resultsEl.style.width      = '';
}

function garbarniaExpandResultsContainer(_data) {
    const containerId = _data.container_id;
    const container = document.getElementById(containerId);
    container.innerHTML = '';
    garbarniaAddContentBackground(containerId);
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
    garbarniaBuildResultsContent(resultsEl, (_data && _data.games) || []);
    resultsEl.style.display = 'none';
    infoBody.appendChild(resultsEl);
    container.appendChild(infoBody);
}

function garbarniaCloseResultsBase(container) {
    garbarniaHideContentBackground(container);
    container.querySelectorAll('.results-row').forEach(row => {
        row.style.animation = 'rotateHideElement 250ms ease 0ms 1 reverse both';
    });
    const body = container.querySelector('.results');
    if (body) {
        body.style.setProperty('animation', 'collapseHeightCentered', 'important');
        body.style.animationDuration = '750ms';
        body.style.animationDelay = '250ms';
        body.style.animationFillMode = 'both';
    }
}

window['override_results-container_open'] = function (containerId, data, targetContainer) {
    garbarniaExpandResultsContainer(data);
    prepareToOpenContainer(openContainer, targetContainer);
};
window['override_results-container_close'] = garbarniaCloseResultsBase;

// ── TABELA / TABELA WIRTUALNA ─────────────────────────────────────────────
// Garbarnia renderuje pełną tabelę (z kolumnami M/Z/R/P/G+/G-/+/-/Pkt) przez
// buildFullTableContent — inna, bogatsza struktura niż nalf (buildTableContent).

let _garbarniaVirtualTableTimer = null;

function garbarniaBuildFullTableContent(resultsEl, rows) {
    resultsEl.innerHTML = '';
    resultsEl.style.flexDirection = 'column';
    resultsEl.classList.add('full-table');

    const headerLabels = ['', '', 'M', 'Z', 'R', 'P', 'G+', 'G-', '+/-', 'Pkt', ''];
    const headerRow = document.createElement('div');
    headerRow.className = 'results-table-row specific-colors-reversed rotate-show-element0';
    headerLabels.forEach((label, i) => {
        const cell = document.createElement('div');
        cell.className = i === 1
            ? 'results-table-cell results-table-name results-table-name-header'
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
            { text: index + 1,          specificClassName: 'results-table-standing' },
            { text: row.team_name14,    specificClassName: 'results-table-name' },
            { text: row.games    ?? '', specificClassName: null },
            { text: row.wins     ?? '', specificClassName: null },
            { text: row.draws    ?? '', specificClassName: null },
            { text: row.loses    ?? '', specificClassName: null },
            { text: row.goals_scored ?? '', specificClassName: null },
            { text: row.goals_lost   ?? '', specificClassName: null },
            { text: gd,                specificClassName: null },
            { text: row.points,        specificClassName: null },
        ].forEach(({ text, specificClassName }) => {
            const cell = document.createElement('div');
            cell.className = 'results-table-cell';
            if (specificClassName) {
                cell.classList.add(specificClassName);
            }
            cell.textContent = text;
            el.appendChild(cell);
        });

        const indicator = document.createElement('div');
        indicator.className = 'results-table-cell results-table-indicator';
        el.appendChild(indicator);

        resultsEl.appendChild(el);
    });

    resultsEl.style.position   = 'absolute';
    resultsEl.style.visibility = 'hidden';
    resultsEl.style.width      = document.body.offsetWidth + 'px';
    document.body.appendChild(resultsEl);

    const nameCells = Array.from(resultsEl.querySelectorAll('.results-table-name'));
    nameCells.forEach(cell => { cell.style.flex = 'none'; cell.style.width = 'max-content'; });
    let maxNameW = 0;
    nameCells.forEach(cell => { maxNameW = Math.max(maxNameW, cell.offsetWidth); });
    nameCells.forEach(cell => { cell.style.width = maxNameW + 'px'; cell.style.flexShrink = '0'; });

    const nonNameCells = Array.from(
        resultsEl.querySelectorAll('.results-table-cell:not(.results-table-name)')
    );
    let maxCellW = 0;
    nonNameCells.forEach(cell => { maxCellW = Math.max(maxCellW, cell.offsetWidth); });
    nonNameCells.forEach(cell => { cell.style.width = maxCellW + 'px'; });

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

    resultsEl.style.top       = '50%';
    resultsEl.style.left      = '50%';
    resultsEl.style.transform = 'translate(-50%, -50%)';

    document.body.removeChild(resultsEl);
    resultsEl.style.visibility = '';
    resultsEl.style.width      = '';
}

function garbarniaAnimateFullTableSwap(container, officialRows, virtualRows) {
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

function garbarniaExpandFullTableContainer(containerId, rows, virtual, withVirtualSwap) {
    const container = document.getElementById(containerId);
    container.innerHTML = '';
    garbarniaAddContentBackground(containerId);
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
    garbarniaBuildFullTableContent(resultsEl, rows);
    resultsEl.style.display = 'none';
    infoBody.appendChild(resultsEl);
    container.appendChild(infoBody);
    if (withVirtualSwap) {
        if (_garbarniaVirtualTableTimer !== null) { clearTimeout(_garbarniaVirtualTableTimer); _garbarniaVirtualTableTimer = null; }
        _garbarniaVirtualTableTimer = setTimeout(() => {
            _garbarniaVirtualTableTimer = null;
            garbarniaAnimateFullTableSwap(resultsEl, rows, virtual);
        }, 8000);
    }
}

function garbarniaCloseTableContainer(container) {
    garbarniaHideContentBackground(container);
    container.querySelectorAll('.results-table-row').forEach(row => {
        row.style.animation = 'rotateHideElement 250ms ease 0ms 1 reverse both';
    });
    const body = container.querySelector('.results');
    if (body) {
        body.style.setProperty('animation', 'collapseHeightCentered', 'important');
        body.style.animationDuration = '750ms';
        body.style.animationDelay = '250ms';
        body.style.animationFillMode = 'both';
    }
}

function garbarniaCloseVirtualTableContainer(container) {
    if (_garbarniaVirtualTableTimer !== null) { clearTimeout(_garbarniaVirtualTableTimer); _garbarniaVirtualTableTimer = null; }
    garbarniaCloseTableContainer(container);
}

window['override_table-container_open'] = function (containerId, data, targetContainer) {
    garbarniaExpandFullTableContainer(data.container_id, (data && data.rows) || [], [], false);
    prepareToOpenContainer(openContainer, targetContainer);
};
window['override_table-container_close'] = garbarniaCloseTableContainer;
window['override_virtual-table-container_open'] = function (containerId, data, targetContainer) {
    garbarniaExpandFullTableContainer(data.container_id, (data && data.official) || [], (data && data.virtual) || [], true);
    prepareToOpenContainer(openContainer, targetContainer);
};
window['override_virtual-table-container_close'] = garbarniaCloseVirtualTableContainer;
