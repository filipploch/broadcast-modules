function formatTime(_elapsed, _format='mm:ss', _isDescending=false, _limit=0, _pauseAtLimit=false) {
    var timer = new Object();
    timer['elapsedTime'] = _elapsed;
    timer['timerLimit'] = _limit;
    timer['pauseAtLimit'] = _pauseAtLimit;
    timer['timerFormat'] = _format;
    timer['isDescending'] = _isDescending;
    
    if(timer['timerLimit'] === 0){
        timer['isDescending'] = false;
    }

    if(timer['isDescending']){
        timer['pauseAtLimit'] = true;
    }

    if(!timer['pauseAtLimit']){
        timer['isDescending'] = false;
    }


    switch(timer['timerFormat']){
        default:
            _formatTimeMmSs(timer);
    }
}

function _formatTimeMmSs(_timer) {
    // Zabezpieczenie przed brakującymi polami
    let elapsedTime = _timer['elapsedTime'] || 0;
    let timerLimit = _timer['timerLimit'] || 0;
    
    const _formatTime = (ms) => {
        const totalSeconds = Math.floor(ms / 1000);
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        return {
            minutes: minutes.toString().padStart(2, '0'),
            seconds: seconds.toString().padStart(2, '0')
        };
    };
    
    const regulationTime = _formatTime(Math.min(elapsedTime, timerLimit));
    
    if (timerLimit >= elapsedTime) {
        console.log('regulationTime: ', regulationTime);
        return { regulationTime };
    }
    
    const addedTime = _formatTime(elapsedTime - timerLimit);
    console.log('regulationTime, addedTime: ', regulationTime, addedTime);
    return { regulationTime, addedTime };
}