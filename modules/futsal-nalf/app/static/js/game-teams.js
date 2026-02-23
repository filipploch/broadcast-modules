// Funkcje dla przycisków
function changeGameValue(valueType, teamType, value) {
   socket.emit('change_game_value', {value_type: valueType, team_type: teamType, value: value});
}

// Funkcja odwracająca układ
// function reverseScoreboard() {
//     const container = document.getElementById('game-teams-content');
    
//     if (container.classList.contains('before-layout')) {
//         container.classList.remove('before-layout');
//         container.classList.add('after-layout');
//     } else {
//         container.classList.remove('after-layout');
//         container.classList.add('before-layout');
//     }
// }

socket.on('initial_data', (data) => {
    // data powinno zawierać: { scores: {home, away}, fouls: {home, away}, penalties: {home: [...], away: [...]}, teamNames: {home, away}, isReversed, gameTimerRunning }
    appState.scores = data.scores;
    appState.fouls = data.fouls;
    appState.penalties = data.penalties;
    appState.teams = data.teams;
    appState.mainTimer = data.main_timer;
    appState.isReversed = data.is_reversed;
    appState.isReordering = false;

    let timer = appState.mainTimer;
    console.log('initial_data timer: ', timer);
    updateTimerDisplay(timer.timer_id, timer.elapsed_time, timer.limit);
    fillPenaltiesTimersContainer('home');
    fillPenaltiesTimersContainer('away');
    // appState.gameTimerRunning = data.gameTimerRunning; // potrzebne do ewentualnego wyświetlania
    // Ustawienie nextPenaltyId na podstawie max id z danych
    // appState.nextPenaltyId = Math.max(...Object.values(data.penalties).flat().map(p => p.id), 0) + 1;
    // renderMainGrid();
    // if (document.getElementById('add-penalty-modal').style.display === 'block') {
    //     renderPenaltyModal();
    // }
});

// var appState = {
//     'scores': { 'home': 0, 'away': 0 },
//     'fouls': { 'home': 0, 'away': 0 },
//     'penalties': { 'home': [], 'away': [] },
//     'teamNames': { 'home': 'Gospodarze', 'away': 'Goście' },
//     'layoutReversed': false,
//     'gameTimerRunning': false,
//     'nextPenaltyId': 1
// };

// Funkcje renderujące
// function renderMainGrid() {
//     const container = document.getElementById('game-teams-container');
//     const reversed = appState.layoutReversed;
//     const homeTeam = reversed ? 'away' : 'home';
//     const awayTeam = reversed ? 'home' : 'away';
//     const homeLabel = reversed ? 'Away' : 'Home';
//     const awayLabel = reversed ? 'Home' : 'Away';

//     container.innerHTML = `
//         <button class="grid-item" onclick="addScore('${homeTeam}')">addScore${homeLabel}</button>
//         <button class="grid-item" onclick="addScore('${awayTeam}')">addScore${awayLabel}</button>
//         <button class="grid-item" onclick="addFouls('${homeTeam}')">addFouls${homeLabel}</button>
//         <button class="grid-item" onclick="addFouls('${awayTeam}')">addFouls${awayLabel}</button>

//         <label class="grid-item">fouls${homeLabel}: <span id="foulsHomeDisplay">${appState.fouls[homeTeam]}</span></label>
//         <label class="grid-item">score${homeLabel}: <span id="scoreHomeDisplay">${appState.scores[homeTeam]}</span></label>
//         <label class="grid-item">score${awayLabel}: <span id="scoreAwayDisplay">${appState.scores[awayTeam]}</span></label>
//         <label class="grid-item">fouls${awayLabel}: <span id="foulsAwayDisplay">${appState.fouls[awayTeam]}</span></label>

//         <button class="grid-item" onclick="substractScore('${homeTeam}')">substractScore${homeLabel}</button>
//         <button class="grid-item" onclick="substractScore('${awayTeam}')">substractScore${awayLabel}</button>
//         <button class="grid-item" onclick="substractFouls('${homeTeam}')">substractFouls${homeLabel}</button>
//         <button class="grid-item" onclick="substractFouls('${awayTeam}')">substractFouls${awayLabel}</button>

//         <div class="grid-item data-item" colspan="2">dataTeam${homeLabel}</div>
//         <div class="grid-item data-item" colspan="2">dataTeam${awayLabel}</div>
//     `;
// }

// Funkcje modyfikacji (wysyłają do backendu przez socket, tu symulacja)
// function addScore(team) {
//     // Symulacja: wysyłamy do backendu, a po odpowiedzi aktualizujemy stan
//     // Tutaj bezpośrednio modyfikujemy stan dla demo
//     appState.scores[team]++;
//     renderMainGrid();
//     // Jeśli modal otwarty, odśwież go
//     if (!document.getElementById('penalty-modal').classList.contains('hidden')) {
//         renderPenaltyModal();
//     }
// }

// function addFouls(team) {
//     appState.fouls[team]++;
//     renderMainGrid();
// }

// function substractScore(team) {
//     if (appState.scores[team] > 0) {
//         appState.scores[team]--;
//         renderMainGrid();
//     }
// }

// function substractFouls(team) {
//     if (appState.fouls[team] > 0) {
//         appState.fouls[team]--;
//         renderMainGrid();
//     }
// }

// function countItems(items) {
//     let x = items ? items.length : 'BRAK';
//     console.log('items: ', x);
// }

// // Funkcje kar
// function addPenaltyTimer(team) {
//     countItems(appState.penalties[team]);
//     console.log('typeof: ', typeof(appState.penalties[team]));
//     if (appState.penalties[team].length >= 2) return;
//     const newTimer = {
//         id: appState.nextPenaltyId++,
//         time: 60 // sekundy
//     };
//     appState.penalties[team].push(newTimer);
//     if (!document.getElementById('penalty-modal').classList.contains('hidden')) {
//         renderPenaltyModal();
//     }
// }

// function removePenalty(team, penaltyId) {
//     appState.penalties[team] = appState.penalties[team].filter(p => p.id !== penaltyId);
//     if (!document.getElementById('penalty-modal').classList.contains('hidden')) {
//         renderPenaltyModal();
//     }
// }

// function adjustPenaltyTime(team, penaltyId, deltaSeconds) {
//     const penalty = appState.penalties[team].find(p => p.id === penaltyId);
//     if (penalty) {
//         penalty.time = Math.max(0, penalty.time + deltaSeconds);
//         if (!document.getElementById('penalty-modal').classList.contains('hidden')) {
//             renderPenaltyModal();
//         }
//     }
// }

// Funkcje modalu
// function openModal(modalID) {
//     const modal = document.getElementById(modalID);
//     removeClassName(modal, 'hidden');
//     // renderPenaltyModal();
// }

// function closeModal() {
//     const modal = document.getElementById('modal-penalties-timers');
//     addClassName(modal, 'hidden');
//     // document.getElementById('modal-penalties-timers').classList.add('hidden');
// }

// Renderowanie modalu kar
// function renderPenaltyModal() {
//     const modalBody = document.getElementById('penalty-modal-body');
//     const reversed = appState.layoutReversed;
//     const leftTeam = reversed ? 'away' : 'home';
//     const rightTeam = reversed ? 'home' : 'away';
//     const leftLabel = reversed ? 'Away' : 'Home';
//     const rightLabel = reversed ? 'Home' : 'Away';

//     function renderColumn(team, label) {
//         const penalties = appState.penalties[team];
//         // Maksymalnie 2 sloty
//         const slots = [];
//         // Najpierw wypełniamy istniejącymi karami
//         penalties.forEach(p => {
//             slots.push(`
//                 <div class="penalty-item">
//                     <div class="timer-display">${formatTime(p.time)}</div>
//                     <div class="timer-controls">
//                         <button onclick="adjustPenaltyTime('${team}', ${p.id}, -1)">-1s</button>
//                         <button onclick="adjustPenaltyTime('${team}', ${p.id}, 1)">+1s</button>
//                         <button class="remove-button" onclick="removePenalty('${team}', ${p.id})">✖</button>
//                     </div>
//                 </div>
//             `);
//         });
//         // Jeśli jest mniej niż 2 kary, dodajemy przycisk "Dodaj karę"
//         if (penalties.length < 2) {
//             slots.push(`
//                 <button class="penalty-item add-penalty-button" onclick="addPenaltyTimer('${team}')">
//                     Dodaj karę
//                 </button>
//             `);
//         }
//         // Jeśli jest tylko jedna kara, to slots ma długość 1 (kara) + przycisk = 2 elementy
//         // Jeśli zero kar, slots ma 1 element (przycisk)
//         // Jeśli dwie kary, slots ma 2 elementy (dwa timery)
//         return `
//             <div class="penalty-column">
//                 ${slots.join('')}
//             </div>
//         `;
//     }

//     modalBody.innerHTML = renderColumn(leftTeam, leftLabel) + renderColumn(rightTeam, rightLabel);
// }

// function formatTime(seconds) {
//     const mins = Math.floor(seconds / 60);
//     const secs = seconds % 60;
//     return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
// }

// Odwracanie układu
// function reverseLayout() {
//     appState.layoutReversed = !appState.layoutReversed;
//     renderMainGrid();
//     if (!document.getElementById('penalty-modal').classList.contains('hidden')) {
//         renderPenaltyModal();
//     }
// }

// Inicjalizacja
// renderMainGrid();

// Przykładowe dane
// appState.penalties.home.push({ id: appState.nextPenaltyId++, time: 120 });
// appState.penalties.home.push({ id: appState.nextPenaltyId++, time: 90 });
// appState.penalties.away.push({ id: appState.nextPenaltyId++, time: 60 });