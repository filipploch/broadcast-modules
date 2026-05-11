
function setCameraPosition(element) {
    // Anuluj poprzedni timer
    clearTimeout(clickTimer);
    
    // Ustaw nowy timer
    clickTimer = setTimeout(() => {
        cellID = element.id;
        console.log('click -> cellID:', cellID);
    }, 100); // 250ms opóźnienia
}