// W8b: tabela ligowa z WP na żądanie dla zakładki MECZE (podzakładki „Tabela” = oficjalna i „Tabela wirtualna” = live) i wysyłania na nakładkę.
// Dane: GET /api/wp-tabela?league_id=<liga modułu>&mode=final|live (moduł pyta WP; nic nie jest buforowane ani odświeżane w tle).
// Logika (dane, opis ostrzeżeń i błędów) jest osobno od DOM i ma test w Node (tests/modules/js/wp_tabela_test.js).
(function (global) {
    'use strict';

    // Jedno żądanie; nigdy nie odrzuca obietnicy: błąd sieci to wynik {ok:false, error:...}, żeby panel mógł pokazać wyraźny komunikat.
    function pobierz(leagueId, tryb) {
        return fetch('/api/wp-tabela?league_id=' + encodeURIComponent(leagueId) + '&mode=' + tryb)
            .then(function (r) { return r.json().then(function (j) { j.http = r.status; return j; }); })
            .catch(function () { return { ok: false, kind: 'modul', error: 'Moduł nie odpowiada: nie udało się pobrać tabeli.' }; });
    }

    // Dane w kształcie używanym dotąd przez widok: official (final), virtual (live), has_live; błąd oficjalnej albo wirtualnej tabeli zatrzymuje cały widok.
    function dane(leagueId, wirtualna) {
        var zadania = [pobierz(leagueId, 'final')];
        if (wirtualna) zadania.push(pobierz(leagueId, 'live'));
        return Promise.all(zadania).then(function (w) {
            var bledna = w.filter(function (x) { return !x.ok; })[0];
            if (bledna) return { blad: bledna.error || 'Tabela niedostępna.', kind: bledna.kind || '' };
            var oficjalna = w[0], wirt = w[1];
            var ostrzezenia = (wirt ? wirt.warnings : oficjalna.warnings) || [];
            return {
                official: oficjalna.rows, virtual: wirt ? wirt.rows : [], has_live: !!(wirt && wirt.live_matches > 0),
                live_matches: wirt ? wirt.live_matches : 0, warnings: ostrzezenia, computed_at: (wirt || oficjalna).computed_at || '',
                engine: (wirt || oficjalna).engine || '', zrodlo: 'wp',
                needs_draw: !!(wirt ? wirt.needs_draw : oficjalna.needs_draw), interpretacja: (wirt || oficjalna).interpretacja || {},
            };
        });
    }

    function opisOstrzezen(lista) {
        return (lista || []).map(function (w) {
            return (w.mecz ? w.mecz + ': ' : '') + w.opis + (w.wplyw ? ' [' + w.wplyw + ']' : '');
        });
    }

    function godzina(iso) {
        var m = /T(\d\d:\d\d:\d\d)/.exec(iso || '');
        return m ? m[1] + ' UTC' : '';
    }

    global.WpTabela = { pobierz: pobierz, dane: dane, opisOstrzezen: opisOstrzezen, godzina: godzina };
})(typeof window !== 'undefined' ? window : globalThis);
