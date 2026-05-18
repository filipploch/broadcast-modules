socket.on('plugins_states', data => {
    const timerStateElement = document.getElementById('timer-state');
    const recorderStateElement = document.getElementById('recorder-state');
    const obsWsStateElement = document.getElementById('obs-ws-state');

    const _plugins = data;
    
    for (const [key, value] of Object.entries(_plugins)) {
     
     if(document.querySelector(`[data-plugin-for=${key}]`)){
         _pluginElement = document.querySelector(`[data-plugin-for=${key}]`);
         _icon = _pluginElement.querySelector('img');
         if(value.is_active === true){
             addClassName(_pluginElement, 'status-plugin-active');
             addClassName(_icon, 'filter-black');
            } else {
                removeClassName(_pluginElement, 'status-plugin-active');
                removeClassName(_icon, 'filter-black');
            };
            if(value.is_healthy === true){
                addClassName(_pluginElement, 'status-plugin-healthy');
            } else {
                removeClassName(_pluginElement, 'status-plugin-healthy');
            };
        };
    }
});

socket.on('obs_record_state', data => {
    const _obsRecordingIndicator = document.getElementById('obs-recording-indicator');
    if (!_obsRecordingIndicator) return;
    const _obsRecordingIndicatorIcon = _obsRecordingIndicator.querySelector('img');
    if(data.state === 'changing') {
        removeClassName(_obsRecordingIndicatorIcon, 'filter-green');
        addClassName(_obsRecordingIndicatorIcon, 'filter-yellow');
    }else if(data.state === 'active') {
        removeClassName(_obsRecordingIndicatorIcon, 'filter-yellow');
        addClassName(_obsRecordingIndicatorIcon, 'filter-green');
    }else{
        removeClassName(_obsRecordingIndicatorIcon, 'filter-green');
        removeClassName(_obsRecordingIndicatorIcon, 'filter-yellow');
    }
});

socket.on('obs_status', status => {
    _obsWsPluginStateIndicator = document.getElementById('obs-ws-state');
    if (!_obsWsPluginStateIndicator) return;
    _obsWsConnectionIndicator = _obsWsPluginStateIndicator.querySelector('img');
    if(status === 'connected'){
        removeClassName(_obsWsConnectionIndicator, 'filter-red');
        removeClassName(_obsWsConnectionIndicator, 'filter-yellow');
        addClassName(_obsWsConnectionIndicator, 'filter-green');
    }else if(status === 'disconnected'){
        removeClassName(_obsWsConnectionIndicator, 'filter-green');
        removeClassName(_obsWsConnectionIndicator, 'filter-yellow');
        addClassName(_obsWsConnectionIndicator, 'filter-red');
    }else if(status === 'reconnecting'){
        removeClassName(_obsWsConnectionIndicator, 'filter-red');
        removeClassName(_obsWsConnectionIndicator, 'filter-green');
        addClassName(_obsWsConnectionIndicator, 'filter-yellow');
    }else{
        removeClassName(_obsWsConnectionIndicator, 'filter-red');
        removeClassName(_obsWsConnectionIndicator, 'filter-green');
        removeClassName(_obsWsConnectionIndicator, 'filter-yellow');
    }
});