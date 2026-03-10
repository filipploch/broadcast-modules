var selectedCellID = null;
var allGameFieldCells = document.querySelectorAll('.game-field-cell');
var hiddedEventsControllersContainer = document.getElementById('hidded-events-controllers-container');

function showEventsControllers(){
    removeClassName(hiddedEventsControllersContainer, 'hidden');
}

function hideEventsControllers(){
    addClassName(hiddedEventsControllersContainer, 'hidden');
}

function unselectAllGameFieldCells() {
    allGameFieldCells.forEach(cell => {
        removeClassName(cell, 'selected-game-field-cell');
    });
    selectedCellID = null;
}

function selectGameFieldCell(selectedCell) {
    clearTimeout(clickTimer);
    let selectedGameFieldCell = selectedCell;
    selectedCellID = selectedGameFieldCell.id;
    unselectAllGameFieldCells();
    addClassName(selectedGameFieldCell, 'selected-game-field-cell');
    showEventsControllers();
}

function addTeamEvent(_team, _event) {
    if (selectedCellID === null) {
        const reversed = appState.isReversed;
        const isGoal = _event === 'Bramka';
        const isHome = _team === 'home';
        const nearGoal  = reversed ? 'H3' : 'A3';
        const farGoal   = reversed ? 'A3' : 'H3';
        selectedCellID = (isGoal === isHome) ? farGoal : nearGoal;
    }
    socket.emit('add_game_event_to_db', {
        'team_type': _team,
        'event_type': _event,
        'selected_cell_id': selectedCellID
    });
    unselectAllGameFieldCells();
    hideEventsControllers();
}

function addFieldEvent(_event){

    unselectAllGameFieldCells();
    hideEventsControllers();
}
