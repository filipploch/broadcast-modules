// ---------------------------------------------------------------------------
// Game scraping
// ---------------------------------------------------------------------------
function startGameScraping(leagueId) {
    fetch('/leagues/' + leagueId + '/games/scrape')
    .then(function(r) {
        if (r.status === 202) {
            showScrapeBar('Scrapowanie w toku...');
            pollScrapeStatus();
        } else {
            return r.json().then(function(d) { alert('Błąd: ' + (d.error || 'nieznany')); });
        }
    })
    .catch(function() { alert('Błąd połączenia'); });
}

function pollScrapeStatus() {
    if (_scrapeIntervalId) clearInterval(_scrapeIntervalId);

    _scrapeIntervalId = setInterval(function() {
        // Safety check — stop polling if user left the page
        if (!document.getElementById('games-table')) {
            clearInterval(_scrapeIntervalId);
            _scrapeIntervalId = null;
            return;
        }

        fetch('/api/games/scrape/status')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!document.getElementById('games-table')) {
                // Navigated away while fetch was in flight
                clearInterval(_scrapeIntervalId);
                _scrapeIntervalId = null;
                return;
            }

            if (data.status === 'in_progress') {
                var msg = 'Scrapowanie w toku';
                if (data.total_scraped !== undefined) msg += ' — pobrano: ' + data.total_scraped;
                showScrapeBar(msg);
            } else {
                // finished or idle
                clearInterval(_scrapeIntervalId);
                _scrapeIntervalId = null;
                hideScrapeBar();
                refreshGamesTable();
            }
        })
        .catch(function(e) { console.warn('pollScrapeStatus error:', e); });
    }, 2000);
}

function showScrapeBar(msg) {
    var bar = document.getElementById('scrape-status-bar');
    if (!bar) return;
    document.getElementById('scrape-status-text').textContent = msg;
    bar.style.display = 'block';
}

function hideScrapeBar() {
    var bar = document.getElementById('scrape-status-bar');
    if (bar) bar.style.display = 'none';
}