// W8a2: przycisk „Pobierz” (źródło zewnętrzne -> WP -> moduł): ukryty, gdy moduł nie ma źródła; w trakcie pracy nieaktywny z licznikiem czasu;
// po zakończeniu okno z podsumowaniem (źródło: zmienione, pominięte przez flagę, błędy; moduł: co zmieniło się w bazie, kopia).
// Dane: GET /api/zrodlo/status (odpytywane co sekundę tylko w trakcie pracy), POST /api/zrodlo/pobierz {league_id}.
// Logika decyzji (opisPrzycisku, tytulWyniku) jest osobno od DOM i ma test w Node (tests/modules/js/zrodlo_pobierz_test.js).
(function (global) {
    'use strict';
    const ODPYTYWANIE_MS = 1000;

    // ── logika (bez DOM) ────────────────────────────────────────────────
    function opisPrzycisku(s, tekstSpoczynkowy) {
        // przycisk jest widoczny tylko przy dostępnym źródle; w trakcie pracy nieaktywny z etapem i czasem
        if (!s || !s.dostepne) return { widoczny: false, nieaktywny: true, tekst: tekstSpoczynkowy };
        if (s.w_toku) {
            const etap = s.etap === 'moduł' ? 'moduł' : 'źródło';
            return { widoczny: true, nieaktywny: true, tekst: `⏳ ${etap}${s.trwa_s ? ' ' + Math.round(s.trwa_s) + ' s' : ''}` };
        }
        return { widoczny: true, nieaktywny: false, tekst: tekstSpoczynkowy };
    }

    function tytulWyniku(w) {
        if (!w) return 'Pobieranie zakończone';
        if (w.ok) return 'Pobieranie zakończone';
        const z = w.zrodlo || {};
        if (!z.ok && z.blad && !z.tekst) return 'Pobieranie: źródło nie odpowiedziało albo błąd importu';
        return 'Pobieranie zakończone z błędami';
    }

    // ── DOM ─────────────────────────────────────────────────────────────
    let okno = null;
    function pokazOkno(w) {
        const d = global.document;
        if (!okno) {
            okno = d.createElement('div');
            okno.id = 'zrodlo-pobierz-okno';
            okno.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:3000;align-items:center;justify-content:center;';
            const pudelko = d.createElement('div');
            pudelko.style.cssText = 'background:#222;color:#ddd;border-radius:6px;padding:1rem;max-width:80vw;max-height:80vh;display:flex;flex-direction:column;gap:.5rem;';
            const tytul = d.createElement('div');
            tytul.id = 'zrodlo-pobierz-tytul';
            tytul.style.cssText = 'font-weight:700;';
            const tekst = d.createElement('pre');
            tekst.id = 'zrodlo-pobierz-tekst';
            tekst.style.cssText = 'margin:0;overflow:auto;white-space:pre-wrap;font-size:12px;';
            const zamknij = d.createElement('button');
            zamknij.id = 'zrodlo-pobierz-zamknij';
            zamknij.type = 'button';
            zamknij.textContent = 'Zamknij';
            zamknij.addEventListener('click', () => { okno.style.display = 'none'; });
            pudelko.append(tytul, tekst, zamknij);
            okno.append(pudelko);
            d.body.append(okno);
        }
        okno.children[0].children[0].textContent = tytulWyniku(w);
        okno.children[0].children[1].textContent = (w && w.tekst) || '';
        okno.style.display = 'flex';
    }

    // Podłącza przycisk: opcje.leagueId() daje id ligi modułu (albo null = wybór domyślny rozgrywek), opcje.poZakonczeniu(wynik) odświeża widok.
    function podlacz(przycisk, opcje) {
        opcje = opcje || {};
        const spoczynek = przycisk.textContent || '⬇ Pobierz';
        let czasomierz = null;
        let ostatni = null;

        function pokaz(s) {
            ostatni = s;
            const o = opisPrzycisku(s, spoczynek);
            przycisk.style.display = o.widoczny ? '' : 'none';
            przycisk.disabled = o.nieaktywny;
            przycisk.textContent = o.tekst;
        }

        function odpytuj() {
            return fetch('/api/zrodlo/status').then(r => r.json()).then(s => {
                const bylo = ostatni && ostatni.w_toku;
                pokaz(s);
                if (s.w_toku) {
                    if (!czasomierz) czasomierz = setTimeout(() => { czasomierz = null; odpytuj(); }, ODPYTYWANIE_MS);
                } else if (bylo) {                                    // praca właśnie się skończyła: okno z podsumowaniem i odświeżenie widoku
                    pokazOkno(s.wynik);
                    if (typeof opcje.poZakonczeniu === 'function') opcje.poZakonczeniu(s.wynik);
                }
                return s;
            }).catch(() => pokaz(null));
        }

        przycisk.addEventListener('click', () => {
            if (przycisk.disabled) return;
            const lid = typeof opcje.leagueId === 'function' ? opcje.leagueId() : null;
            przycisk.disabled = true;
            fetch('/api/zrodlo/pobierz', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ league_id: lid }) })
                .then(r => r.json().then(j => ({ ok: r.ok, j })))
                .then(({ ok, j }) => {
                    if (!ok) { global.alert((j && (j.error || j.blad)) || 'Nie udało się rozpocząć pobierania'); return odpytuj(); }
                    ostatni = { dostepne: true, w_toku: true, etap: 'źródło' };
                    pokaz(ostatni);
                    return odpytuj();
                })
                .catch(e => { global.alert('Błąd: ' + e.message); odpytuj(); });
        });
        return odpytuj();                                          // stan początkowy: ukryty bez źródła; wznowienie, gdy praca już trwa
    }

    global.ZrodloPobierz = { opisPrzycisku, tytulWyniku, podlacz };
})(typeof window !== 'undefined' ? window : globalThis);
