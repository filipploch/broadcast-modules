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
        if(containerType === 'none') {
            prepareToOpenContainer();
        }else if(containerType === 'squad') {
            let teamName = _data.team_name;
            let teamShortName = _data.team_short_name;
            let teamSquad = _data.team_squad;
            let teamLogo = _data.logo;
			let teamCoach;
			if(_data.coach !== 'undefined') {teamCoach = _data.coach;} else {teamCoach = null;}
            expandSquadContainer(containerId, teamName, teamShortName, teamSquad, teamLogo, teamCoach);
            let addedDelayTime = prepareToOpenContainer(openContainer, targetContainer);
            delayTime += addedDelayTime;
            activateElementsAfterTime('squad-content', delayTime);
        }else if (containerType === 'start'){
            expandStartContainer(_data);
            prepareToOpenContainer(openContainer, targetContainer);
            activateElementsAfterTime('start-content', 2500, 'flex');
        }else if (containerType === 'break'){
            expandStartContainer(_data, true);
            prepareToOpenContainer(openContainer, targetContainer);
            activateElementsAfterTime('break-content', 2500, 'flex');
        }else if (containerType === 'shootout'){
            fillShootoutContainer(_data);
            prepareToOpenContainer(openContainer, targetContainer);
            // activateElementsAfterTime('break-content', 2500, 'flex');
        }else{
            prepareToOpenContainer(openContainer, targetContainer);
        }
        
    }
    
    function prepareToOpenContainer(callback, param) {
        let delayTime = 0;
        let overlayContainers = document.querySelectorAll('.overlay-container');
        overlayContainers.forEach(cont => {
            if(cont.style.display !== 'none') {
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
        switch(containerType) {
            case 'squad':
                closeSquadContainer(container);
                console.log('closeSquadContainer()')
                break;
            default:
                closeDefaultContainer(container);
                console.log('closeDefaultContainer()')
                break;
        }
        
        // Wyczyść animacje po ich zakończeniu
        setTimeout(() => {
            // Usuń tymczasowe animacje
            clearAnimations(container);
            container.style.display = 'none';
        }, animationDuration);
    }

    function closeSquadContainer(container) {
        let logo = container.querySelector('img');
        let players = container.querySelectorAll('.squad-player-row');
        let squadBody = container.querySelector('.squad-body');
        let infoHead = container.querySelector('.info-head');
        logo.style.animation = `fadeOut 250ms ease both`;
        players.forEach(player => {
            player.style.animation = `rotateHideElement 250ms ease 0ms 1 reverse both`;
        });
        squadBody.style.setProperty('animation','collapseHeight', 'important');
        squadBody.style.animationDuration = '750ms';
        squadBody.style.animationDelay = '250ms';
        squadBody.style.animationFillMode = 'both';
        infoHead.style.animation = 'rotateHideElement 250ms ease 750ms 1 reverse both';
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
        if(referees.length > 1) redereesContainerHeadText = 'Sędziowie';
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
        _scorers.forEach((scorer, index)=> {
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
            firstName.innerText = scorer.player_first_name;
            lastName.innerText = scorer.player_last_name;
            goalTimeContainer.innerText = '';
            let goals = scorer.goals;
            goals.forEach(goal => {
				let displayedMinute = goal.minute;
				if(goal.added_time>0) displayedMinute += `+${goal.added_time}`
                if(goal.is_own_goal === true){
                    goalTimeContainer.innerText += `(s)${displayedMinute}' `;
                }else{
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

    function expandStartContainer(_gameData, _break=false) {
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
        roundTitleElement.innerText = `${data.round_name}`;
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
        homeTeamLogoImg.src = rootApp+`${data.home_team_logo}`;
        addClassName(homeTeamLogoImg, 'drop-shadow');
        homeTeamLogoContainer.appendChild(homeTeamLogoImg);
        let leagueLogoContainer = document.createElement('div');
        leagueLogoContainer.id = 'start-league-logo';
        leagueLogoContainer.style.display = 'flex';
        let leagueLogoImg = document.createElement('img');
        leagueLogoImg.src = rootApp+setLeagueLogo();
        addClassName(leagueLogoImg, 'drop-shadow');
        leagueLogoContainer.appendChild(leagueLogoImg);
        let awayTeamLogoContainer = document.createElement('div');
        awayTeamLogoContainer.style.display = 'flex';
        awayTeamLogoContainer.id = 'start-away-team-logo';
        addClassName(awayTeamLogoContainer, 'start-logo');
        let awayTeamLogoImg = document.createElement('img');
        awayTeamLogoImg.src = rootApp+`${data.away_team_logo}`;
        addClassName(awayTeamLogoImg, 'drop-shadow');
        awayTeamLogoContainer.appendChild(awayTeamLogoImg);

        startBodyLogosContainer.appendChild(homeTeamLogoContainer);
        startBodyLogosContainer.appendChild(leagueLogoContainer);
        startBodyLogosContainer.appendChild(awayTeamLogoContainer);

        startBody.appendChild(startBodyLogosContainer);

        if(_break === true){
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
        }else{

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
        addClassName(spanTeamName, 'squad-team-name');
        let spanTeamShortName = document.createElement('span');
        spanTeamShortName.innerHTML = ` (${_teamShortName})`;
        addClassName(spanTeamShortName, 'squad-team-short-name');
        infoHead.appendChild(spanTeamName);
        infoHead.appendChild(spanTeamShortName);
        squadContainer.appendChild(infoHead);
        let squadBody = document.createElement('div');
        addClassName(squadBody, 'squad-body');
        addClassName(squadBody, 'animated-element');
        squadBody.dataset.animationOrder = '2';
        let squadBodyLeft = document.createElement('div');
        addClassName(squadBodyLeft, 'squad-body-left');
        let squadBodyRight = document.createElement('div');
        addClassName(squadBodyRight, 'squad-body-right');
        let teamSquadContent = createTeamSquad(_arr, _logo, _coach);
        teamSquadContent.style.display = 'none';
        addClassName(teamSquadContent,'squad-content');
        let teamLogo = document.createElement('img');
        addClassName(teamLogo,'squad-content');
        addClassName(teamLogo,'squad-team-logo');
        addClassName(teamLogo,'drop-shadow');
        addClassName(teamLogo, 'animated-element');
        teamLogo.dataset.animationOrder = '3';
        teamLogo.src = rootApp + _logo;
        teamLogo.style.display = 'none';
        squadBodyLeft.appendChild(teamSquadContent);
        squadBodyRight.appendChild(teamLogo);
        squadBody.appendChild(squadBodyLeft);
        squadBody.appendChild(squadBodyRight);
        squadContainer.appendChild(squadBody);
    }
    
    function createTeamSquad(_arr, _logo) {
        var squadContent = document.createElement('div');
        addClassName(squadContent,'team-squad-content');
        addClassName(squadContent,'squad-content');
        squadContent.innerHTML = '';
        
        _arr.forEach(function(element, index) {
            var goalkeeper = '';
            var captain = '';
            if (element.is_goalkeeper === true){
                goalkeeper = ' (B) '
            }
            if (element.is_captain === true){
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
        if(_fouls === '' || _fouls === null){
            _foulsElement.textContent = '';
        }else if(parseInt(_fouls) !== 'undefined' && _fouls >= 0 && _fouls < 6) {
            _foulsElement.textContent = '●'.repeat(_fouls);
            _foulsElement.style.color = 'yellow';
            if(_fouls > 4){
                _foulsElement.style.color = 'red';
            }else if(_fouls < 4){
                _foulsElement.style.color = 'white';
            }else{
                
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
            if(data.home_team_goals === '' || data.home_team_goals === null){
                homeTeamScoreElement.textContent = '';
            }else if(parseInt(data.home_team_goals) !== 'undefined'){
                homeTeamScoreElement.textContent = data.home_team_goals;
            }else{
                
            }
        }
        if (typeof data.away_team_goals != "undefined") {
            if(data.away_team_goals === '' || data.away_team_goals === null){
                awayTeamScoreElement.textContent = '';
            }else if(parseInt(data.home_team_goals) !== 'undefined'){
                awayTeamScoreElement.textContent = data.away_team_goals;
            }else{
                
            }
        }
        if (typeof data.home_team_fouls != "undefined") {
            updateFoulsElement(data.home_team_fouls, homeTeamFoulsElement);
                        }
                        if (typeof data.away_team_fouls != "undefined") {
                            updateFoulsElement(data.away_team_fouls, awayTeamFoulsElement);
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
        if(_eventTypeId === 2) {
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
            msg.type === 'timer_paused'  ||
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
        
        if(msg.type === 'scoreboard_data') {
            const data = msg.payload || msg.data;
            updateScoreboard(data);
        }

        if(msg.type === 'goal') {
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
                    element.textContent = data.home_team_short_name;
                })
            }
            
            if (typeof data.away_team_short_name != "undefined") {
                awayTeamShortNameElements.forEach(element => {
                    element.textContent = data.away_team_short_name;
                })
            }
            
            if (typeof data.home_team_goals != "undefined") {
                homeTeamScoreElements.forEach(element => {
                    element.textContent = data.home_team_goals;
                })
            }
            
            if (typeof data.away_team_goals != "undefined") {
                awayTeamScoreElements.forEach(element => {
                    element.textContent = data.away_team_goals;
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
            : FutsalFormatters.formatElapsedTime(data.game_time, 0, {'format': 'min', 'unit': 's'});
            actionPlayerInfoElement.textContent = '';
            actionPlayerInfoElement.textContent = `${data.player_number} ${data.player_name}`;
            actionPlayerTeamShortNameElement.textContent = ''; 
            actionPlayerTeamShortNameElement.textContent = 
                actionPlayerTeamShortNameElementGenerator(data.player_team_short_name, data.event_type_id);
            actionTeamNameElement.textContent = '';
            actionTeamNameElement.textContent = data.team_name;

            actionInfoContainer.style.display = 'block';
            setTimeout(() => {
                actionInfoContainer.style.display = 'none';
            }, 11100);
        }
    }