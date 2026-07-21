function clearSocketMonitor(){
    const statusClasses = new Array('bg_red', 'bg_blue', 'bg_green');
    let textElements = document.querySelectorAll('.sm-text');
    let monitor = document.getElementById('socket-monitor');
    statusClasses.forEach(className => {
        removeClassName(monitor, className);
    });
    textElements.forEach(element => {
        element.textContent = '';
    });
}

var socket = (typeof socket !== 'undefined') ? socket : io();

socket.on('connect', () => {
    console.log('✅ WebSocket connected');
});

socket.on('disconnect', () => {
    console.log('❌ WebSocket disconnected');
});

socket.on('scraping_started', (data) => {
    clearSocketMonitor();
    let headerText = 'Rozpoczęto scrapowanie: ';
    let monitor = document.getElementById('socket-monitor');
    addClassName(monitor, 'bg_blue');
    document.getElementById('header-text').textContent = headerText;
    document.getElementById('header-name').textContent = data.name;
    removeClassName(monitor, 'hidden');
});

socket.on('scraping_completed', (data) => {
    clearSocketMonitor();
    let headerText = 'Zakończono scrapowanie: ';
    let monitor = document.getElementById('socket-monitor');
    addClassName(monitor, 'bg_green');
    document.getElementById('header-text').textContent = headerText;
    document.getElementById('header-name').textContent = data.name;
    removeClassName(monitor, 'hidden');  
});

socket.on('scraping_error', (data) => {
    clearSocketMonitor();
    let headerText = 'Błąd scrapowania: ';
    let monitor = document.getElementById('socket-monitor');
    addClassName(monitor, 'bg_green');
    document.getElementById('header-text').textContent = headerText;
    document.getElementById('header-name').textContent = data.name;
    removeClassName(monitor, 'hidden');  
});

function closeSocketMonitor() {
    let monitor = document.getElementById('socket-monitor');
    addClassName(monitor, 'hidden');
}

function startPlayerScraping(teamID) {
    fetch(`/teams/${teamID}/scrape-players`)
        .catch(err => console.error('Player scraping request failed:', err));
}

function copyTeamUrlToClipboard(btn, url) {
    navigator.clipboard.writeText(url).then(function() {
        const original = btn.textContent;
        btn.textContent = '✓ skopiowano';
        setTimeout(function() { btn.textContent = original; }, 2000);
    });
}