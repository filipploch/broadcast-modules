var appState = {
    scores: { home: null, away: null },
    fouls: { home: 0, away: 0 },
    penalties: { home: [], away: [] },
    teams: { home: [null], away: null },
    mainTimer: null,
    isReversed: false,
    isReordering: false,
};

console.log('appState: ', appState);



// var isReordering = false; // Flaga blokująca równoczesne wykonania
// var isReversed = false;