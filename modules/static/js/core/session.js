// Pasek stanu sesji transmisji (E1): pokazuje, czy sesja jest otwarta i w jakim stanie, oraz ręczne akcje.
// Źródło prawdy: /api/session; odświeżany po zdarzeniu socket 'session_state' i po każdej akcji.
(function () {
    const bar = document.getElementById('session-bar');
    if (!bar) return;
    const LABELS = { preparation: 'przygotowanie', on_air: 'NA ANTENIE', finished: 'zakończona' };

    function render(state) {
        if (!state || !state.open) {
            bar.className = 'session-bar session-none';
            bar.innerHTML = '<span>Brak otwartej sesji transmisji</span>';
            return;
        }
        const onAir = state.status === 'on_air';
        bar.className = 'session-bar ' + (onAir ? 'session-on-air' : 'session-preparation');
        let html = '<span>Sesja: <strong>' + (LABELS[state.status] || state.status) + '</strong></span>';
        if (!onAir) html += '<button type="button" data-session-action="go-on-air">Rozpocznij transmisję</button>';
        const queued = (state.queue || []).filter(q => q.status === 'queued').length;
        if (queued > 0) html += '<button type="button" data-session-action="next-game">Następny mecz (' + queued + ')</button>';
        html += '<button type="button" data-session-action="close">Zakończ sesję</button>';
        bar.innerHTML = html;
    }

    function load() {
        fetch('/api/session').then(r => r.json()).then(render).catch(() => {});
    }

    bar.addEventListener('click', function (ev) {
        const action = ev.target && ev.target.getAttribute('data-session-action');
        if (!action) return;
        if (action === 'close' && !confirm('Zakończyć sesję transmisji? Stream i nagrywanie w OBS nie zostaną zatrzymane.')) return;
        fetch('/api/session/' + action, { method: 'POST' }).then(r => r.json()).then(function (res) {
            if (!res.success) alert(res.error || 'Nie udało się wykonać akcji.');
            render(res.session);
        }).catch(() => {});
    });

    if (typeof socket !== 'undefined') socket.on('session_state', render);
    load();
})();
