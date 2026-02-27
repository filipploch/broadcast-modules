socket.on('plugins_states', data => {
    const timerStateElement = document.getElementById('timer-state');
    const recorderStateElement = document.getElementById('recorder-state');
    const obsWsStateElement = document.getElementById('obs-ws-state');

    const _plugins = data;
    console.log(_plugins);
    
    for (const [key, value] of Object.entries(_plugins)) {
     console.log(`${key} is ${value}`);
     console.log(document.querySelector(`[data-plugin-for=${key}]`));
     
     if(document.querySelector(`[data-plugin-for=${key}]`)){
         _pluginElement = document.querySelector(`[data-plugin-for=${key}]`);
         _icon = _pluginElement.querySelector('img');
         if(value.is_active === true){
             addClassName(_pluginElement, 'status-plugin-active');
             addClassName(_icon, 'filter-green');
            } else {
                removeClassName(_pluginElement, 'status-plugin-active');
                removeClassName(_icon, 'filter-green');
            };
            if(value.is_healthy === true){
                addClassName(_pluginElement, 'status-plugin-healthy');
            } else {
                removeClassName(_pluginElement, 'status-plugin-healthy');
            };
        };
    }
});