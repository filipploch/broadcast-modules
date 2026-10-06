// ============================================================================
// Motyw "nalf" — wygląd i zachowanie kontenerów specyficznych dla futsal-nalf
// (squad/start/break/results/table/virtual-table/shootout). Każda funkcja
// window.override_<containerId>_open/_close rejestruje się jako nadpisanie
// mechanizmu podstawowego (patrz overlay.js: resolveContainerOverride,
// showContainer/closeContainer) dla DANEGO kontenera. Treść poniżej to
// dzisiejszy kod przeniesiony z overlay.js — logika nie została zmieniona,
// tylko przeniesiona pod tę konwencję (plus 2 poprawki błędów w shootout,
// opisane przy odpowiednich funkcjach).
//
// Funkcje bazowe, których ten plik NIE przenosi (bo są współdzielone z
// innymi, niemigrowanymi jeszcze funkcjami w tym samym module — np. mini-
// widget #results-table-container) i na które poniższy kod się powołuje:
// prepareToOpenContainer, openContainer, activateElementsAfterTime,
// buildResultsContent, buildTableContent, rootApp, addClassName,
// getCurrentDate, setLeagueName, setLeagueLogo.
// ============================================================================

// ── SQUAD ────────────────────────────────────────────────────────────────

function nalfExpandSquadContainer(_containerId, _teamName, _teamShortName, _arr, _logo, _coach) {
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
    let teamSquadContent = nalfCreateTeamSquad(_arr, _logo, _coach);
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

function nalfCreateTeamSquad(_arr, _logo) {
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

function nalfCloseSquadContainer(container) {
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

window['override_home-team-squad-container_open'] = function (containerId, data, targetContainer) {
    let teamCoach = (data.coach !== 'undefined') ? data.coach : null;
    nalfExpandSquadContainer(containerId, data.team_name, data.team_short_name, data.team_squad, data.logo, teamCoach);
    let addedDelayTime = prepareToOpenContainer(openContainer, targetContainer);
    activateElementsAfterTime('squad-content', 2000 + addedDelayTime);
};
window['override_away-team-squad-container_open'] = window['override_home-team-squad-container_open'];
window['override_home-team-squad-container_close'] = nalfCloseSquadContainer;
window['override_away-team-squad-container_close'] = nalfCloseSquadContainer;

// ── START / PRZERWA ──────────────────────────────────────────────────────
// futsal-nalf renderuje oba tą samą funkcją (flaga _break), tak jak dotąd.

function nalfExpandStartBottomSpecificContainer(_headerText, _arr) {
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

function nalfExpandStartBottomInfoContainer(_gameData) {
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
    refereesContainer.innerHTML = nalfExpandStartBottomSpecificContainer(redereesContainerHeadText, referees);
    commentatorsContainer.innerHTML = nalfExpandStartBottomSpecificContainer('Komentarz', commentators);
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

function nalfGenerateScorersList(_scorers) {
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

function nalfExpandStartContainer(_gameData, _break = false) {
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
        let homeTeamScorersWrapper = nalfGenerateScorersList(homeTeamScorers);
        homeTeamScorersContainer.appendChild(homeTeamScorersWrapper);

        let awayTeamScorersContainer = document.createElement('div');
        awayTeamScorersContainer.id = 'away-team-scorers-container';
        addClassName(awayTeamScorersContainer, 'team-scorers-container');
        let awayTeamScorers = _gameData.away_team_scorers.scorers;
        let awayTeamScorersWrapper = nalfGenerateScorersList(awayTeamScorers);
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
        let bottomInfoContainer = nalfExpandStartBottomInfoContainer(_gameData);
        startBottom.appendChild(bottomInfoContainer);
        startBody.appendChild(startBottom);

    }

    startContainer.appendChild(startBody);
    _startContainer.appendChild(startContainer);
}

function nalfCloseStartContainer(container) {
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

function nalfCloseBreakContainer(container) {
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

window['override_start-container_open'] = function (containerId, data, targetContainer) {
    nalfExpandStartContainer(data, false);
    prepareToOpenContainer(openContainer, targetContainer);
    activateElementsAfterTime('start-content', 2500, 'flex');
};
window['override_start-container_close'] = nalfCloseStartContainer;
window['override_break-container_open'] = function (containerId, data, targetContainer) {
    nalfExpandStartContainer(data, true);
    prepareToOpenContainer(openContainer, targetContainer);
    activateElementsAfterTime('break-content', 2500, 'flex');
};
window['override_break-container_close'] = nalfCloseBreakContainer;

// ── WYNIKI / TABELA / TABELA WIRTUALNA ───────────────────────────────────
// buildResultsContent/buildTableContent zostają w overlay.js (baseline) —
// są też używane przez niezależny mini-widget #results-table-container.

function nalfExpandResultsContainer(_data) {
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

function nalfCloseResultsContainer(container) {
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

function nalfExpandTableContainer(_data) {
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

function nalfCloseTableContainer(container) {
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

let _nalfVirtualTableTimer = null;

function nalfAnimateTableSwap(container, officialRows, virtualRows) {
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

function nalfExpandVirtualTableContainer(_data) {
    if (_nalfVirtualTableTimer !== null) { clearTimeout(_nalfVirtualTableTimer); _nalfVirtualTableTimer = null; }

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
    const virtual = _data.virtual || [];
    buildTableContent(tableContent, official, 'TABELA', true);
    infoBody.appendChild(tableContent);
    tableContainer.appendChild(infoBody);

    if (virtual.length > 0) {
        _nalfVirtualTableTimer = setTimeout(() => {
            _nalfVirtualTableTimer = null;
            nalfAnimateTableSwap(tableContent, official, virtual);
        }, 8000);
    }
}

function nalfCloseVirtualTableContainer(container) {
    if (_nalfVirtualTableTimer !== null) { clearTimeout(_nalfVirtualTableTimer); _nalfVirtualTableTimer = null; }

    const rowEls = Array.from(container.querySelectorAll('[data-team-name14]'));

    if (rowEls.length > 0) {
        const parent = rowEls[0].parentNode;
        const withPos = rowEls.map(el => {
            const m = (el.style.transform || '').match(/translateY\(([-\d.]+)px\)/);
            const ty = m ? parseFloat(m[1]) : 0;
            return { el, visualTop: el.offsetTop + ty };
        });
        withPos.sort((a, b) => a.visualTop - b.visualTop);
        withPos.forEach(({ el }) => {
            el.style.transform = '';
            el.classList.remove('promotion', 'degradation');
            parent.appendChild(el);
        });
    }

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

window['override_results-container_open'] = function (containerId, data, targetContainer) {
    nalfExpandResultsContainer(data);
    prepareToOpenContainer(openContainer, targetContainer);
};
window['override_results-container_close'] = nalfCloseResultsContainer;
window['override_table-container_open'] = function (containerId, data, targetContainer) {
    nalfExpandTableContainer(data);
    prepareToOpenContainer(openContainer, targetContainer);
};
window['override_table-container_close'] = nalfCloseTableContainer;
window['override_virtual-table-container_open'] = function (containerId, data, targetContainer) {
    nalfExpandVirtualTableContainer(data);
    prepareToOpenContainer(openContainer, targetContainer);
};
window['override_virtual-table-container_close'] = nalfCloseVirtualTableContainer;

// ── DOGRYWKA (SHOOTOUT) ───────────────────────────────────────────────────
// Przeniesione z js/shootout.js. Przy tej okazji dwie poprawki błędów:
// 1) showContainer (overlay.js) wołał nieistniejącą expandShootoutContainer —
//    teraz poprawnie wpięte pod override_shootout-container_open.
// 2) homeTeamResult wskazywał błędnie na #shootout-away-team-result (ten
//    sam element co awayTeamResult) — wynik gospodarzy nigdy się nie
//    aktualizował. Poprawione na #shootout-home-team-result.
// Brak override_..._close — dogrywka nigdy nie miała własnej animacji
// zamykania, zawsze spadała na closeDefaultContainer (generyczny fade).

function nalfMakeShootoutContainer() {
    let shootoutContainer = document.querySelector('#shootout-container');
    let shootoutContent = `
    <div id="shootout-logo-container" style="z-index: 3; position: absolute; bottom: 70px; width: 100%; height: 65px; background-color: rgba(0,0,0,0); display: flex; filter: drop-shadow(0px 3px 3px black);">
        <div id="shootout-home-team-logo" class="shootout-team-logo"><img src="ukr.png"></div>
        <div class="shootout-break"></div>
        <div id="shootout-away-team-logo" class="shootout-team-logo"><img src="opp.png"></div>
    </div>
    <div id="shootout-content" style="z-index: 1; position: absolute; bottom: 0; width: 100%; height: 85px; background-color: rgba(0,0,0,0.8); display: block;">
        <div id="shootout-content2" style="z-index: 2; position: absolute; bottom: 85px; width: 100%; height: 70px; background-color: rgba(255,255,255,1); display: block; filter: drop-shadow(0px 5px 5px black);">
            <div id="shootout-content3">
                <div id="shootout-home-team-name" style="text-align: right;	" class="shootout-team-name">UKRAINIAN LEGION</div>
                <div style="width: 20%; display: flex; justify-content: center; align-items: center;">
                    <div id="shootout-result-container">
                        <div id="shootout-home-team-result" style="justify-content: right;" class="shootout-result-element">0</div>
                        <div style="justify-content: center;" class="shootout-result-element">:</div>
                        <div id="shootout-away-team-result" style="justify-content: left;" class="shootout-result-element">0</div>
                    </div>
                </div>
                <div id="shootout-away-team-name" class="shootout-team-name">ODDZIAŁ PREWENCJI POLICJI</div>
            </div>
        </div>
    </div>
    <div id="shootout-content" style="z-index: 3; position: absolute; bottom: 1vw; width: 100%; height: 2.5vw; display: flex; filter: drop-shadow(0px 3px 3px black);">
        <div style="justify-content: right;" class="shootout-points-container">
            <div data-round-nr="13" class="shootout-point shootout-home-team-point shootout-point-hidden">13</div>
            <div data-round-nr="12" class="shootout-point shootout-home-team-point shootout-point-hidden">12</div>
            <div data-round-nr="11" class="shootout-point shootout-home-team-point shootout-point-hidden">11</div>
            <div data-round-nr="10" class="shootout-point shootout-home-team-point shootout-point-hidden">10</div>
            <div data-round-nr="9" class="shootout-point shootout-home-team-point shootout-point-hidden">9</div>
            <div data-round-nr="8" class="shootout-point shootout-home-team-point shootout-point-hidden">8</div>
            <div data-round-nr="7" class="shootout-point shootout-home-team-point shootout-point-hidden">7</div>
            <div data-round-nr="6" class="shootout-point shootout-home-team-point shootout-point-hidden">6</div>
            <div data-round-nr="5" class="shootout-point shootout-home-team-point shootout-point-hidden">5</div>
            <div data-round-nr="4" class="shootout-point shootout-home-team-point shootout-point-hidden">4</div>
            <div data-round-nr="3" class="shootout-point shootout-home-team-point shootout-point-null">3</div>
            <div data-round-nr="2" class="shootout-point shootout-home-team-point shootout-point-null">2</div>
            <div data-round-nr="1" class="shootout-point shootout-home-team-point shootout-point-null">1</div>
        </div>
        <div style="width: 12%; display: flex; justify-content: center; align-items: center;"></div>
        <div style="justify-content: left;" class="shootout-points-container">
            <div data-round-nr="1" class="shootout-point shootout-away-team-point shootout-point-null">1</div>
            <div data-round-nr="2" class="shootout-point shootout-away-team-point shootout-point-null">2</div>
            <div data-round-nr="3" class="shootout-point shootout-away-team-point shootout-point-null">3</div>
            <div data-round-nr="4" class="shootout-point shootout-away-team-point shootout-point-hidden">4</div>
            <div data-round-nr="5" class="shootout-point shootout-away-team-point shootout-point-hidden">5</div>
            <div data-round-nr="6" class="shootout-point shootout-away-team-point shootout-point-hidden">6</div>
            <div data-round-nr="7" class="shootout-point shootout-away-team-point shootout-point-hidden">7</div>
            <div data-round-nr="8" class="shootout-point shootout-away-team-point shootout-point-hidden">8</div>
            <div data-round-nr="9" class="shootout-point shootout-away-team-point shootout-point-hidden">9</div>
            <div data-round-nr="10" class="shootout-point shootout-away-team-point shootout-point-hidden">10</div>
            <div data-round-nr="11" class="shootout-point shootout-away-team-point shootout-point-hidden">11</div>
            <div data-round-nr="12" class="shootout-point shootout-away-team-point shootout-point-hidden">12</div>
            <div data-round-nr="13" class="shootout-point shootout-away-team-point shootout-point-hidden">13</div>
        </div>
    </div>`;
    shootoutContainer.innerHTML = shootoutContent;
}

function nalfFillShootoutContainer(data) {
    let homeTeamLogoImg = document.querySelector('#shootout-home-team-logo img');
    let awayTeamLogoImg = document.querySelector('#shootout-away-team-logo img');
    let homeTeamNameElement = document.querySelector('#shootout-home-team-name');
    let awayTeamNameElement = document.querySelector('#shootout-away-team-name');
    let homeTeamResult = document.querySelector('#shootout-home-team-result');
    let awayTeamResult = document.querySelector('#shootout-away-team-result');

    homeTeamNameElement.innerText = data.home_team_name;
    awayTeamNameElement.innerText = data.away_team_name;
    homeTeamResult.innerText = data.home_team_shootouts;
    awayTeamResult.innerText = data.away_team_shootouts;
    homeTeamLogoImg.src = rootApp + `${data.home_team_logo}`;
    awayTeamLogoImg.src = rootApp + `${data.away_team_logo}`;
}

window['override_shootout-container_open'] = function (containerId, data, targetContainer) {
    nalfMakeShootoutContainer();
    nalfFillShootoutContainer(data);
    prepareToOpenContainer(openContainer, targetContainer);
};
