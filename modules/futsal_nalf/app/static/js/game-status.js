// ---------------------------------------------------------------------------
// Status modal
// ---------------------------------------------------------------------------
function openStatusModal(gameId, currentStatus) {
    _currentGameId = gameId;
    var radios = document.querySelectorAll('input[name="game-status-radio"]');
    radios.forEach(function(r) {
        r.checked = parseInt(r.value) === currentStatus;
    });
    var overlay = document.getElementById('status-modal-overlay');
    overlay.style.display = 'flex';
}

function closeStatusModal() {
    document.getElementById('status-modal-overlay').style.display = 'none';
    _currentGameId = null;
}

function saveGameStatus() {
    var selected = document.querySelector('input[name="game-status-radio"]:checked');
    if (!selected || _currentGameId === null) return;

    fetch('/api/games/' + _currentGameId + '/status', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: parseInt(selected.value) }),
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.error) { alert('Błąd: ' + data.error); return; }
        closeStatusModal();
        refreshGamesTable();
    })
    .catch(function() { alert('Błąd połączenia'); });
}

// Close modal on overlay click
document.getElementById('status-modal-overlay').addEventListener('click', function(e) {
    if (e.target === this) closeStatusModal();
});

// ---------------------------------------------------------------------------
// Table refresh — reusable, safe to call from anywhere
// ---------------------------------------------------------------------------
function refreshGamesTable() {
    var table = document.getElementById('games-table');
    if (!table) return;   // user navigated away — abort silently

    var url = '/api/games';
    if (_leagueId !== null) url += '?league_id=' + _leagueId;

    fetch(url)
    .then(function(r) { return r.json(); })
    .then(function(data) {
        var table = document.getElementById('games-table');
        if (!table) return;   // navigated away while fetch was in flight

        var tbody = document.getElementById('games-tbody');
        if (!tbody) return;

        tbody.innerHTML = data.games.map(function(g) {
            var statusClass = g.status === 1 ? 'live' : g.status === 2 ? 'finished' : 'upcoming';
            var statusText  = g.status === 0 ? 'Nie rozpoczęty' : g.status === 1 ? 'Trwa' : 'Zakończony';
            var date = g.date ? g.date.replace('T', ' ').slice(0, 16) : '-';
            var home = g.home_team_short_name || '?';
            var away = g.away_team_short_name || '?';
            var score = g.score_string || '-';
            return '<tr data-game-id="' + g.id + '">'
                + '<td>' + date + '</td>'
                + '<td><strong>' + home + '</strong> vs <strong>' + away + '</strong></td>'
                + '<td class="game-score">' + score + '</td>'
                + '<td ondblclick="openStatusModal(' + g.id + ',' + g.status + ')">'
                +   '<span class="game-status status-' + statusClass + '">' + statusText + '</span>'
                + '</td>'
                + '<td><div class="actions">'
                +   '<a href="/games/' + g.id + '" class="btn btn-primary btn-small">Widok</a> '
                +   '<a href="/games/' + g.id + '/edit" class="btn btn-secondary btn-small">Edytuj</a>'
                + '</div></td>'
                + '</tr>';
        }).join('');
    })
    .catch(function(e) { console.warn('refreshGamesTable failed:', e); });
}