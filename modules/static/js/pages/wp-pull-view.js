// Podsumowanie podglądu i pobrania pary z WP (W7a): czysta funkcja stanu (testowana w Node) i rysowanie na karcie „Rozgrywki WP”.
// Zależy od wpPluralMatches z wp-competitions.js (w przeglądarce wczytywanego wcześniej).

const WP_PULL_SECTIONS = [
    ['pominiete', 'Pominięte (mecz trwa lub rozpoczęty w module)', 'warning'],
    ['korekty', 'Korekty zakończonych meczów z WP', 'info'],
    ['kilka_aktualnych', 'Zawodnicy z kilkoma aktualnymi drużynami w parze (przypisano jedną, do sprawdzenia)', 'warning'],
    ['tylko_dawne', 'Tylko dawne drużyny w tej parze (poza pulą tej ligi)', 'info'],
    ['zwolnieni', 'Zwolnieni z drużyny (WP nie wymienia jej już jako aktualnej)', 'warning'],
    ['numery_z_modulu', 'Numery wpisane w module (WP nie ma numeru, numer zostaje)', 'info'],
    ['rozbieznosci', 'Rozbieżności', 'warning'],
    ['brak_logo', 'Brak pliku logo (użyto default.png)', 'warning'],
    ['skroty_wyliczone', 'Skróty wyliczone z nazwy, do sprawdzenia', 'info'],
    ['dolaczono', 'Dołączono istniejące rekordy modułu', 'info'],
    ['nieobecne', 'Nieobecne w WP (zostają w module)', 'warning'],
    ['zablokowane', 'Wynik zablokowany w WP', 'info'],
];

function wpMatchesText(n) {
    if (n === 1) return '1 mecz';
    const last = n % 10, tens = n % 100;
    if (last >= 2 && last <= 4 && !(tens >= 12 && tens <= 14)) return n + ' mecze';
    return n + ' meczów';
}

function wpPullViewModel(st, now) {
    const vm = {busy: false, canPull: false, hasResult: false, title: '', error: '', table: [], sections: [], waiting: '', membership: '', staleWarning: '', changes: []};
    if (!st || !st.enabled) return vm;
    vm.busy = !!st.pulling;
    vm.canPull = st.connected !== false && !st.pulling && (st.items || []).length > 0;
    const last = st.last_apply_at ? Date.parse(st.last_apply_at) : NaN;
    const nowMs = now === undefined ? Date.now() : now;
    if (isNaN(last)) {
        vm.staleWarning = 'Z WP nie pobrano jeszcze danych do tego modułu.';
    } else if (nowMs - last > 24 * 3600 * 1000) {
        vm.staleWarning = `Ostatnie pobranie z WP: ${st.last_apply_at.replace('T', ' ')} (ponad 24 godziny temu). Pobierz ponownie przed transmisją.`;
    }
    const p = st.pull;
    if (!p) return vm;
    vm.hasResult = true;
    const when = (p.at || '').replace('T', ' ');
    vm.title = `${p.apply ? 'Pobranie' : 'Podgląd zmian'}: ${p.label || p.key} (${when})`;
    if (!p.ok) {
        vm.error = p.blad || 'Nie udało się pobrać danych z WP.';
        return vm;
    }
    const r = p.raport || {};
    const names = {druzyny: 'Drużyny', zawodnicy: 'Zawodnicy', mecze: 'Mecze'};
    vm.table = Object.keys(names).map(k => {
        const c = (r.liczniki || {})[k] || {};
        return {label: names[k], added: c.dodano || 0, updated: c.zaktualizowano || 0, same: c.bez_zmian || 0, skipped: c.pominieto || 0};
    });
    vm.sections = WP_PULL_SECTIONS.map(([key, title, level]) => ({key, title, level, items: r[key] || []})).filter(s => s.items.length > 0);
    if (r.do_ustalenia_liczba > 0) {
        vm.waiting = `Czekają na ustalenie par: ${wpMatchesText(r.do_ustalenia_liczba)} (nie wczytano).`;
    }
    const pr = r.przynaleznosc;
    if (pr) {
        vm.membership = `Przynależność zawodników: ${pr.jedna || 0} z jedną aktualną drużyną, ${pr.kilka || 0} z kilkoma aktualnymi, `
            + `${pr.tylko_dawne || 0} tylko z dawnymi drużynami w tej parze` + (pr.bez_rozroznienia ? `, ${pr.bez_rozroznienia} ze źródła bez rozróżnienia aktualnych i dawnych` : '') + '.';
    }
    vm.changes = p.apply ? [] : (r.zmiany || []);
    if (p.apply && !p.zapisano) vm.title += ': brak zmian do zapisania';
    return vm;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {wpPullViewModel, wpMatchesText};
}

if (typeof document !== 'undefined') {
    (function () {
        const $ = id => document.getElementById(id);

        function addList(box, title, level, items) {
            const det = document.createElement('details');
            det.className = 'wp-note wp-note-' + level;
            det.open = level === 'warning' || items.length <= 5;
            const sum = document.createElement('summary');
            sum.textContent = `${title} (${items.length})`;
            det.appendChild(sum);
            const ul = document.createElement('ul');
            items.forEach(t => { const li = document.createElement('li'); li.textContent = t; ul.appendChild(li); });
            det.appendChild(ul);
            box.appendChild(det);
        }

        function renderPull(st) {
            const vm = wpPullViewModel(st);
            $('wp-preview').disabled = !vm.canPull;
            $('wp-pull').disabled = !vm.canPull;
            $('wp-pull-busy').textContent = vm.busy ? 'Trwa pobieranie z WP…' : '';
            const warn = $('wp-pull-stale');
            warn.textContent = vm.staleWarning;
            warn.style.display = vm.staleWarning ? '' : 'none';
            const box = $('wp-pull-result');
            box.innerHTML = '';
            if (!vm.hasResult) return;
            const h = document.createElement('div');
            h.className = 'wp-note ' + (vm.error ? 'wp-note-error' : 'wp-note-info');
            h.textContent = vm.title + (vm.error ? ': ' + vm.error : '');
            box.appendChild(h);
            if (vm.error) return;
            const table = document.createElement('table');
            table.className = 'wp-pull-table';
            table.innerHTML = '<tr><th></th><th>dodano</th><th>zaktualizowano</th><th>bez zmian</th><th>pominięto</th></tr>';
            vm.table.forEach(r => {
                const tr = document.createElement('tr');
                [r.label, r.added, r.updated, r.same, r.skipped].forEach((v, i) => {
                    const td = document.createElement(i === 0 ? 'th' : 'td');
                    td.textContent = v;
                    tr.appendChild(td);
                });
                table.appendChild(tr);
            });
            box.appendChild(table);
            if (vm.membership) {
                const mb = document.createElement('div');
                mb.className = 'wp-note wp-note-info';
                mb.textContent = vm.membership;
                box.appendChild(mb);
            }
            if (vm.waiting) {
                const w = document.createElement('div');
                w.className = 'wp-note wp-note-info';
                w.textContent = vm.waiting;
                box.appendChild(w);
            }
            if (vm.changes.length) addList(box, 'Co się zmieni po pobraniu', 'info', vm.changes);
            vm.sections.forEach(s => addList(box, s.title, s.level, s.items));
        }

        function pull(apply) {
            const row = (window._wpRows || []).find(r => r.key === window._wpSelected);
            const body = row ? {apply, league_id: row.leagueId, season_id: row.seasonId} : {apply};
            $('wp-pull-busy').textContent = 'Trwa pobieranie z WP…';
            $('wp-preview').disabled = true;
            $('wp-pull').disabled = true;
            fetch('/api/wp/pull', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
                .then(r => r.json())
                .then(() => socket.emit('get_wp_state'))
                .catch(() => { $('wp-pull-busy').textContent = 'Nie udało się połączyć z modułem.'; });
        }

        document.addEventListener('DOMContentLoaded', () => {
            socket.on('wp_state', renderPull);
            $('wp-preview').addEventListener('click', () => pull(false));
            $('wp-pull').addEventListener('click', () => pull(true));
        });
    })();
}
