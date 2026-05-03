// WebSocket z rejestracją jako overlay + subskrypcja timer
        const overlayId = 'stream-overlay';
        const ws = new WebSocket(`ws://${window.location.hostname}:${window.location.port}/ws`);

        const rootApp = 'http://localhost:8081/';
                
        let registered = false;
          
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
        
        if (msg.type === 'game_data') {
            const data = msg.payload || msg.data;
            console.log('game_data', data);
            let homeTeamNameElement = document.querySelector('#home_team_name');
            let homeTeamLogoElement = document.querySelector('#home_team_logo');
            let homeTeamShortNameElement = document.querySelector('#home_team_short_name');
            let awayTeamNameElement = document.querySelector('#away_team_name');
            let awayTeamLogoElement = document.querySelector('#away_team_logo');
            let awayTeamShortNameElement = document.querySelector('#away_team_short_name');
            let divisionElement = document.querySelector('#division');
            let dateElement = document.querySelector('#date');
            let logosElement = document.querySelector('#logos-img');
            let nalfLogoElement = document.querySelector('#nalf-logo');
            
            if (typeof data.home_team_name != "undefined") {
                homeTeamNameElement.textContent = data.home_team_name;
            }
            
            if (typeof data.away_team_name != "undefined") {
                awayTeamNameElement.textContent = data.away_team_name;
            }

            homeTeamShortNameElement.textContent = data.home_team_short_name;
            awayTeamShortNameElement.textContent = data.away_team_short_name;
            divisionElement.textContent = data.league_name;
            homeTeamLogoElement.src = rootApp+`${data.home_team_logo}`;
            awayTeamLogoElement.src = rootApp+`${data.away_team_logo}`;
            let separator = 'T';
            let _date = data.date.split(separator);
            dateElement.textContent = `${_date[0]} ${_date[1].slice(0, -3)}`
            logosElement.src = rootApp+'/static/images/nalf/druzyny-logo-belka.png';
            nalfLogoElement.src = rootApp+'/static/images/nalf/NALFlogoTekst.png';
        }
            
    }