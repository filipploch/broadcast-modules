function showOverlay(containerID){
    socket.emit('show_overlay_container', data={'container_id': containerID});
}

function showGameScene(){
    socket.emit('trigger_sequence', { sequence: 'show_game_scene', context: {}});
}

function showBreakScene(){
    socket.emit('trigger_sequence', { sequence: 'show_break_scene', context: {}});
}