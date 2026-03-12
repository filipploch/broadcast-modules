function showOverlay(containerID){
    socket.emit('show_overlay_container', data={'container_id': containerID});
}