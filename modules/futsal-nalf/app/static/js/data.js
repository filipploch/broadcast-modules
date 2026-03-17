var appState = {
    home_team_goals: null,
    away_team_goals: null,
    home_team_fouls: 0,
    away_team_fouls: 0,
    // fouls: { home: 0, away: 0 },
    home_penalties: [],
    away_penalties: [],
    teams: { home: [null], away: null },
    mainTimer: null,
    isReversed: false,
    isReordering: false,
};

console.log('appState: ', appState);

var cellID;
var clickTimer;



// var isReordering = false; // Flaga blokująca równoczesne wykonania
// var isReversed = false;