// W8a: pasek zapisu do WP (kolejka, błąd, wyłącznik, „Wyślij teraz”), trwały pasek „Mecz nie jest zakończony” i okno „Zakończyć mecz?”.
// Dane: GET /api/wp-zapis/status (odpytywane co kilka sekund; lokalnie, tanie), POST /api/wp-zapis/wlacznik|ponow, POST /api/games/<id>/finish.
// Logika decyzji (opisPaska, odrzuconeTeksty, czyOferowacOkno) jest osobno od DOM i ma test w Node (tests/modules/js/wp_zapis_ui_test.js).
(function (global) {
    'use strict';
    const ODSWIEZ_MS = 4000;
    const PROG_CZERWONY_S = 20;

    // ── logika (bez DOM) ────────────────────────────────────────────────
    function opisPaska(s) {
        // pasek jest ZAWSZE widoczny: także szary „NIEAKTYWNY” (baza próbna, brak danych logowania, brak odpowiedzi modułu), z powodem
        if (!s || s.brak_odpowiedzi) return { kolor: 'szary', tekst: 'Zapis do WP: brak odpowiedzi modułu', pokazPonow: false, pokazPrzelacznik: false };
        if (!s.skonfigurowany) return { kolor: 'szary', tekst: 'Zapis do WP: NIEAKTYWNY' + (s.powod ? ' (' + s.powod + ')' : ''), pokazPonow: false, pokazPrzelacznik: false };
        const n = s.w_kolejce || 0;
        const blad = s.ostatni_blad ? s.ostatni_blad.tekst : '';
        if (!s.wlaczony) return { kolor: 'szary', tekst: 'Zapis do WP: WYŁĄCZONY' + (n ? ` (niezapisane: ${n})` : ''), pokazPonow: false, pokazPrzelacznik: true };
        if (blad || (n > 0 && (s.najstarszy_s || 0) > PROG_CZERWONY_S)) {
            return { kolor: 'czerwony', tekst: `WP: niezapisane: ${n}` + (blad ? ` · błąd: ${blad}` : ''), pokazPonow: n > 0, pokazPrzelacznik: true };
        }
        if (n > 0) return { kolor: 'zolty', tekst: `WP: niezapisane: ${n}`, pokazPonow: true, pokazPrzelacznik: true };
        return { kolor: 'zielony', tekst: 'WP: zapisane', pokazPonow: false, pokazPrzelacznik: true };
    }

    function odrzuconeTeksty(s) {
        return ((s && s.odrzucone) || []).map(o => (o.nazwa ? o.nazwa + ': ' : '') + o.powod);
    }

    // Okno „Zakończyć mecz?” otwieramy raz na mecz w tej karcie przeglądarki (pasek zostaje, gdy operator wybierze „Nie teraz”).
    function czyOferowacOkno(s, oferowane) {
        const lista = (s && s.niezakonczone) || [];
        return lista.find(m => !oferowane.has(m.game_id)) || null;
    }

    // ── DOM ─────────────────────────────────────────────────────────────
    const KOLORY = { zielony: '#1e7e34', zolty: '#b8860b', czerwony: '#b02a37', szary: '#6c757d' };
    const oferowane = new Set();
    let ostatni = null;
    let zbudowane = false;
    let el = {};

    function stworz(tag, css, tekst) {
        const e = document.createElement(tag);
        e.style.cssText = css || '';
        if (tekst !== undefined) e.textContent = tekst;
        return e;
    }

    function zbuduj() {
        if (zbudowane) return;
        zbudowane = true;
        el.pasek = stworz('div', 'position:fixed;top:0;right:0;z-index:50;display:none;align-items:center;gap:.5rem;padding:.2rem .6rem;font:12px sans-serif;color:#fff;border-bottom-left-radius:6px;');
        el.pasek.id = 'wp-zapis-bar';
        el.tekst = stworz('span');
        el.ponow = stworz('button', 'font-size:11px;cursor:pointer;', 'Wyślij teraz');
        el.ponow.id = 'wp-zapis-ponow';
        el.przelacz = stworz('button', 'font-size:11px;cursor:pointer;', '');
        el.przelacz.id = 'wp-zapis-przelacz';
        el.pasek.append(el.tekst, el.ponow, el.przelacz);
        el.odrzucone = stworz('div', 'position:fixed;top:24px;right:0;z-index:50;display:none;max-width:420px;padding:.3rem .6rem;font:12px sans-serif;background:#b02a37;color:#fff;border-bottom-left-radius:6px;');
        el.odrzucone.id = 'wp-zapis-odrzucone';
        el.nz = stworz('div', 'position:fixed;top:0;left:50%;transform:translateX(-50%);z-index:60;display:none;align-items:center;gap:.7rem;padding:.35rem .9rem;font:14px sans-serif;background:#c2410c;color:#fff;border-radius:0 0 8px 8px;box-shadow:0 2px 8px rgba(0,0,0,.4);');
        el.nz.id = 'mecz-niezakonczony-bar';
        el.nzTekst = stworz('span');
        el.nzPrzycisk = stworz('button', 'font-size:14px;padding:.2rem .7rem;cursor:pointer;', 'Zakończ mecz');
        el.nzPrzycisk.id = 'mecz-niezakonczony-zakoncz';
        el.nz.append(el.nzTekst, el.nzPrzycisk);
        el.okno = stworz('div', 'position:fixed;inset:0;z-index:100;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.55);');
        el.okno.id = 'zakoncz-mecz-okno';
        const karta = stworz('div', 'background:#fff;color:#222;border-radius:10px;padding:1.2rem 1.6rem;min-width:320px;max-width:520px;font:16px sans-serif;box-shadow:0 8px 32px rgba(0,0,0,.4);');
        karta.append(stworz('div', 'font-size:20px;font-weight:700;margin-bottom:.6rem;', 'Zakończyć mecz?'));
        el.oknoOpis = stworz('div', 'margin-bottom:.8rem;');
        el.oknoUwaga = stworz('div', 'margin-bottom:.8rem;color:#b02a37;font-weight:600;');
        const przyciski = stworz('div', 'display:flex;gap:.6rem;justify-content:flex-end;');
        el.oknoTak = stworz('button', 'font-size:16px;padding:.35rem 1rem;cursor:pointer;', 'Zakończ mecz');
        el.oknoTak.id = 'zakoncz-mecz-tak';
        el.oknoNie = stworz('button', 'font-size:16px;padding:.35rem 1rem;cursor:pointer;', 'Nie teraz');
        el.oknoNie.id = 'zakoncz-mecz-nie';
        przyciski.append(el.oknoTak, el.oknoNie);
        karta.append(el.oknoOpis, el.oknoUwaga, przyciski);
        el.okno.append(karta);
        document.body.append(el.pasek, el.odrzucone, el.nz, el.okno);
        el.ponow.addEventListener('click', () => post('/api/wp-zapis/ponow').then(odswiez));
        el.przelacz.addEventListener('click', () => post('/api/wp-zapis/wlacznik', { wlaczony: !(ostatni && ostatni.wlaczony) }).then(odswiez));
        const zakoncz = () => zakonczMecz();
        el.nzPrzycisk.addEventListener('click', zakoncz);
        el.oknoTak.addEventListener('click', zakoncz);
        el.oknoNie.addEventListener('click', () => { el.okno.style.display = 'none'; });
    }

    function post(url, ciało) {
        return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(ciało || {}) })
            .then(r => r.json()).catch(() => null);
    }

    function zakonczMecz() {
        const m = ostatni && ostatni.niezakonczone && ostatni.niezakonczone[0];
        if (!m) return Promise.resolve();
        return post(`/api/games/${m.game_id}/finish`).then(() => {
            el.okno.style.display = 'none';
            return odswiez().then(() => { if (typeof global._showPeriodChoiceFrame === 'function') global._showPeriodChoiceFrame(); });
        });
    }

    function pokaz(s) {
        ostatni = s;
        zbuduj();
        const opis = opisPaska(s);
        if (opis) {
            el.pasek.style.display = 'flex';
            el.pasek.style.background = KOLORY[opis.kolor];
            el.tekst.textContent = opis.tekst;
            el.ponow.style.display = opis.pokazPonow ? '' : 'none';
            el.przelacz.style.display = opis.pokazPrzelacznik ? '' : 'none';
            el.przelacz.textContent = s.wlaczony ? 'Wyłącz zapis' : 'Włącz zapis';
        } else {
            el.pasek.style.display = 'none';
        }
        const odrzucone = opis ? odrzuconeTeksty(s) : [];
        el.odrzucone.style.display = odrzucone.length ? 'block' : 'none';
        el.odrzucone.textContent = odrzucone.join(' | ');
        const nz = (s.niezakonczone || [])[0];
        el.nz.style.display = nz ? 'flex' : 'none';
        if (nz) el.nzTekst.textContent = `Mecz nie jest zakończony: ${nz.nazwa} (${nz.wynik})` + (nz.remis_bez_rozstrzygniecia ? ' · remis bez rozstrzygnięcia' : '');
        const oferta = czyOferowacOkno(s, oferowane);
        if (oferta) {
            oferowane.add(oferta.game_id);
            el.oknoOpis.textContent = `${oferta.nazwa}, wynik ${oferta.wynik}. Wszystkie części meczu są zakończone.`;
            el.oknoUwaga.textContent = oferta.remis_bez_rozstrzygniecia ? 'Uwaga: remis bez rozstrzygnięcia (czy był konkurs rzutów karnych?).' : '';
            el.okno.style.display = 'flex';
        }
    }

    function odswiez() {
        return fetch('/api/wp-zapis/status').then(r => r.json()).then(pokaz).catch(() => pokaz({ brak_odpowiedzi: true, niezakonczone: [], odrzucone: [] }));
    }

    function start() {
        odswiez();
        setInterval(odswiez, ODSWIEZ_MS);
    }

    global.WpZapisUI = { opisPaska, odrzuconeTeksty, czyOferowacOkno, odswiez, start, zakonczMecz };
    global.wpZapisOdswiez = odswiez;
    if (typeof document !== 'undefined' && !global.__BM_TEST) {
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
    }
})(typeof window !== 'undefined' ? window : globalThis);
