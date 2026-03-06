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

    if(appState.isReversed===true){
        reorderReversible(onLoad=true);
    }
    let timer = appState.mainTimer;
    console.log('initial_data timer: ', timer);
    updateTimerDisplay(timer);
    fillPenaltiesTimersContainer('home');
    fillPenaltiesTimersContainer('away');
});