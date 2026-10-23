// Rozgrywki z WordPressa (WP-2): lista par (liga, sezon) z instancji WP modułu, wybór i zapis rozgrywek domyślnych.
// Cała logika treści jest w wpViewModel (czysta funkcja, testowana w Node); reszta to rysowanie i Socket.IO.

function wpPluralMatches(n) {
    if (n === 1) return '1 mecz';
    const last = n % 10, tens = n % 100;
    if (last >= 2 && last <= 4 && !(tens >= 12 && tens <= 14)) return n + ' mecze';
    return n + ' meczów';
}

function wpFormatDate(iso) {
    // 2026-01-02 -> 02.01.2026
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
    return m ? `${m[3]}.${m[2]}.${m[1]}` : '';
}

function wpItemDetail(item) {
    const parts = [wpPluralMatches(item.events)];
    const a = wpFormatDate(item.first_date), b = wpFormatDate(item.last_date);
    if (a && b) parts.push(a === b ? a : `${a} – ${b}`);
    return parts.join(' · ');
}

function wpViewModel(st) {
    const vm = {status: '', statusClass: 'wp-unknown', notes: [], rows: [], selectedKey: null, canSave: false, hint: ''};
    if (!st || !st.enabled) {
        vm.status = 'Ten moduł nie ma własnej instancji WP (brak bloku „wp” w module.json).';
        if (st && st.problem) vm.notes.push({level: 'error', text: st.problem});
        return vm;
    }
    const name = st.title ? `${st.title}, ${st.url}` : st.url;
    if (st.connected === true) {
        vm.status = `WP: połączony (${name})`;
        vm.statusClass = 'wp-ok';
    } else if (st.connected === false) {
        vm.status = `WP: brak połączenia (${name}): ${st.error}`;
        vm.statusClass = 'wp-bad';
        if (st.from_cache && st.fetched_at) {
            vm.notes.push({level: 'warning', text: `Lista z ostatniego pobrania (${st.fetched_at.replace('T', ' ')}); może być nieaktualna.`});
        }
    } else {
        vm.status = 'WP: sprawdzam połączenie…';
    }
    if (st.problem) vm.notes.push({level: 'error', text: st.problem});
    if (st.connected !== false && !st.has_auth) {
        vm.notes.push({level: 'info', text: 'Brak danych logowania do WP (wp-local\\dane-api-<id modułu>.json): lista obejmuje tylko opublikowane mecze.'});
    }
    const defKey = st.default ? st.default.key : null;
    vm.rows = (st.items || []).map(i => ({
        key: i.key, leagueId: i.league_id, seasonId: i.season_id,
        label: `${i.league_name} — ${i.season_name}`, detail: wpItemDetail(i), isDefault: i.key === defKey,
    }));
    vm.selectedKey = defKey && vm.rows.some(r => r.key === defKey) ? defKey : null;
    vm.canSave = vm.rows.length > 0;
    if (st.no_competitions) {
        vm.notes.push({level: 'warning', text: 'W WP nie ma meczów z przypisaną ligą i sezonem. Dodaj je w panelu WP (Mecze, Edycja zbiorcza).'});
    }
    if (st.default_missing && st.default) {
        vm.notes.push({level: 'warning', text: `Zapisanych rozgrywek (${st.default.league_name} — ${st.default.season_name}) nie ma już w WP. Wybierz ponownie.`});
    } else if (st.needs_choice) {
        vm.notes.push({level: 'info', text: 'Wybierz rozgrywki domyślne modułu.'});
    } else if (st.default && st.default.auto) {
        vm.notes.push({level: 'info', text: 'Przypisano automatycznie (to jedyne rozgrywki w WP).'});
    }
    if (st.unassigned > 0) {
        vm.notes.push({level: 'info', text: `${wpPluralMatches(st.unassigned)} bez ligi lub sezonu nie ${st.unassigned === 1 ? 'jest' : 'są'} na liście.`});
    }
    if (st.default && !st.default_missing) {
        vm.hint = `Domyślne rozgrywki modułu: ${st.default.league_name} — ${st.default.season_name}`;
    } else {
        vm.hint = 'Domyślne rozgrywki modułu: nie wybrano';
    }
    return vm;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {wpPluralMatches, wpFormatDate, wpItemDetail, wpViewModel};
}

if (typeof document !== 'undefined') {
    (function () {
        let selected = null;
        const $ = id => document.getElementById(id);

        function render(st) {
            const vm = wpViewModel(st);
            const status = $('wp-status');
            status.textContent = vm.status;
            status.className = 'wp-status ' + vm.statusClass;
            const list = $('wp-list');
            list.innerHTML = '';
            if (selected && !vm.rows.some(r => r.key === selected)) selected = null;
            if (selected === null) selected = vm.selectedKey;
            vm.rows.forEach(r => {
                const label = document.createElement('label');
                label.className = 'wp-row' + (r.isDefault ? ' wp-default' : '');
                const radio = document.createElement('input');
                radio.type = 'radio';
                radio.name = 'wp-competition';
                radio.value = r.key;
                radio.checked = r.key === selected;
                radio.addEventListener('change', () => { selected = r.key; });
                const title = document.createElement('span');
                title.className = 'wp-title';
                title.textContent = r.label + (r.isDefault ? ' (domyślne)' : '');
                const detail = document.createElement('span');
                detail.className = 'wp-detail';
                detail.textContent = r.detail;
                label.append(radio, title, detail);
                list.appendChild(label);
            });
            $('wp-hint').textContent = vm.hint;
            $('wp-save').disabled = !vm.canSave;
            const notes = $('wp-notes');
            notes.innerHTML = '';
            vm.notes.forEach(n => {
                const div = document.createElement('div');
                div.className = 'wp-note wp-note-' + n.level;
                div.textContent = n.text;
                notes.appendChild(div);
            });
            window._wpRows = vm.rows;
        }

        document.addEventListener('DOMContentLoaded', () => {
            socket.on('wp_state', render);
            socket.on('wp_result', res => {
                const msg = $('wp-result');
                msg.textContent = res.ok ? 'Zapisano rozgrywki domyślne.' : `Nie zapisano: ${res.error}`;
                msg.className = 'wp-note ' + (res.ok ? 'wp-note-info' : 'wp-note-error');
            });
            $('wp-refresh').addEventListener('click', () => socket.emit('wp_refresh'));
            $('wp-save').addEventListener('click', () => {
                const row = (window._wpRows || []).find(r => r.key === selected);
                if (!row) {
                    const msg = $('wp-result');
                    msg.textContent = 'Najpierw zaznacz rozgrywki na liście.';
                    msg.className = 'wp-note wp-note-warning';
                    return;
                }
                socket.emit('wp_set_default', {league_id: row.leagueId, season_id: row.seasonId});
            });
            socket.emit('get_wp_state');
        });
    })();
}
