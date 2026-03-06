function showEventsControllers(_element){
    clearTimeout(clickTimer);
    cellID = _element.id;
    _container = document.getElementById('hidded-events-controllers-container');
    removeClassName(_container, 'hidden');
    console.log('dblclick -> cellID:', cellID);
}

function addTeamEvent(_team, _event){
    console.log('teamEvent:',_team, _event);
}

function addFieldEvent(_event){
    console.log('field event:', _event);
    _container = document.getElementById('hidded-events-controllers-container');
    addClassName(_container, 'hidden');
}