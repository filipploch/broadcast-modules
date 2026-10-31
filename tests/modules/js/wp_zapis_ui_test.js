// W8a: PRAWDZIWY kod modules/static/js/pages/wp-zapis.js w Node: pasek zapisu do WP, pasek „Mecz nie jest zakończony”, okno „Zakończyć mecz?”.
// Uruchomienie: node wp_zapis_ui_test.js   (kod wyjścia 0 = wszystko przeszło)
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const src = fs.readFileSync(path.resolve(__dirname, '..', '..', '..', 'modules', 'static', 'js', 'pages', 'wp-zapis.js'), 'utf8');

function srodowisko(odpowiedzi, wIframe) {
  const posty = [];
  const elementy = [];
  const mk = () => {
    const e = { style: {}, textContent: '', children: [], listeners: {}, id: '' };
    e.append = (...c) => { e.children.push(...c); };
    e.addEventListener = (t, f) => { (e.listeners[t] = e.listeners[t] || []).push(f); };
    e.click = () => (e.listeners.click || []).forEach((f) => f());
    elementy.push(e);
    return e;
  };
  const ctx = {
    __BM_TEST: true,
    document: { createElement: mk, __ile: (id) => elementy.filter((e) => e.id === id).length, body: { append() {} }, readyState: 'complete', addEventListener() {} },
    setInterval: () => 0,
    fetch: (url, opts) => {
      if (opts && opts.method === 'POST') posty.push(url);
      const o = odpowiedzi.shift() || odpowiedzi.ostatnia;
      return Promise.resolve({ json: () => Promise.resolve(opts && opts.method === 'POST' ? { ok: true } : o) });
    },
    console,
  };
  ctx.window = ctx;
  ctx.globalThis = ctx;
  if (wIframe) ctx.top = { wpZapisOdswiez: () => { wIframe.odswiezenia = (wIframe.odswiezenia || 0) + 1; return Promise.resolve(); } };   // global.top !== global: jesteśmy w ramce
  else ctx.top = ctx;
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  const znajdz = (id) => elementy.find((e) => e.id === id);
  return { ctx, posty, znajdz, UI: ctx.WpZapisUI };
}

const wyniki = [];
const ok = async (nazwa, fn) => { await fn(); wyniki.push(nazwa); };
const eq = (a, b) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b));
const baza = { skonfigurowany: true, wlaczony: true, w_kolejce: 0, najstarszy_s: 0, ostatni_blad: null, odrzucone: [], niezakonczone: [] };

(async () => {
await ok('opis paska: kolory i teksty dla stanów kolejki', () => {
  const { UI } = srodowisko([baza]);
  eq(UI.opisPaska(baza), { kolor: 'zielony', tekst: 'WP: zapisane', pokazPonow: false, pokazPrzelacznik: true });
  assert.strictEqual(UI.opisPaska({ ...baza, w_kolejce: 2, najstarszy_s: 3 }).kolor, 'zolty');
  assert.strictEqual(UI.opisPaska({ ...baza, w_kolejce: 2, najstarszy_s: 25 }).kolor, 'czerwony');
  const blad = UI.opisPaska({ ...baza, w_kolejce: 1, najstarszy_s: 1, ostatni_blad: { tekst: 'brak połączenia z WP' } });
  assert.strictEqual(blad.kolor, 'czerwony');
  assert.ok(blad.tekst.includes('niezapisane: 1') && blad.tekst.includes('brak połączenia z WP') && blad.pokazPonow);
  const wyl = UI.opisPaska({ ...baza, wlaczony: false, w_kolejce: 3 });
  assert.strictEqual(wyl.kolor, 'szary');
  assert.ok(wyl.tekst.includes('WYŁĄCZONY') && wyl.tekst.includes('niezapisane: 3'));
});

await ok('pasek jest ZAWSZE widoczny: nieaktywny zapis (z powodem) i brak odpowiedzi modułu to szary pasek bez przycisków', async () => {
  const { UI } = srodowisko([baza]);
  eq(UI.opisPaska({ ...baza, skonfigurowany: false, powod: 'brak danych logowania do WP' }),
     { kolor: 'szary', tekst: 'Zapis do WP: NIEAKTYWNY (brak danych logowania do WP)', pokazPonow: false, pokazPrzelacznik: false });
  assert.strictEqual(UI.opisPaska(null).kolor, 'szary');
  // prawdziwy DOM-owy przepływ: odpowiedź „nieaktywny” i błąd pobrania statusu muszą dać widoczny pasek
  const nieakt = { skonfigurowany: false, wlaczony: false, powod: 'baza database-proba.db nie jest bazą operacyjną', odrzucone: [], niezakonczone: [] };
  const e = srodowisko([nieakt]);
  await e.UI.odswiez();
  const pasek = e.znajdz('wp-zapis-bar');
  assert.strictEqual(pasek.style.display, 'flex');
  assert.ok(pasek.children[0].textContent.includes('NIEAKTYWNY') && pasek.children[0].textContent.includes('database-proba.db'));
  assert.strictEqual(e.znajdz('wp-zapis-przelacz').style.display, 'none');
  const e2 = srodowisko([]);
  e2.ctx.fetch = () => Promise.reject(new Error('moduł nie odpowiada'));
  await e2.UI.odswiez();
  assert.strictEqual(e2.znajdz('wp-zapis-bar').style.display, 'flex');
  assert.ok(e2.znajdz('wp-zapis-bar').children[0].textContent.includes('brak odpowiedzi'));
});

await ok('odrzucone zapisy (409) mają nazwę meczu i powód', () => {
  const { UI } = srodowisko([baza]);
  eq(UI.odrzuconeTeksty({ odrzucone: [{ nazwa: 'A – B', powod: 'WP odrzucił zapis: WP ma inny wynik (5:0)' }] }), ['A – B: WP odrzucił zapis: WP ma inny wynik (5:0)']);
  eq(UI.odrzuconeTeksty(baza), []);
});

await ok('okno „Zakończyć mecz?” otwierane raz na mecz', () => {
  const { UI } = srodowisko([baza]);
  const nz = { game_id: 7, nazwa: 'A – B', wynik: '2:1', remis_bez_rozstrzygniecia: false };
  const oferowane = new Set();
  assert.strictEqual(UI.czyOferowacOkno(baza, oferowane), null);
  assert.strictEqual(UI.czyOferowacOkno({ ...baza, niezakonczone: [nz] }, oferowane).game_id, 7);
  oferowane.add(7);
  assert.strictEqual(UI.czyOferowacOkno({ ...baza, niezakonczone: [nz] }, oferowane), null);
});

await ok('przepływ: okno raz, „Nie teraz” zostawia pasek, „Zakończ mecz” wysyła zakończenie i zdejmuje pasek', async () => {
  const nz = { game_id: 7, nazwa: 'A – B', wynik: '2:1', remis_bez_rozstrzygniecia: true };
  const odp = [{ ...baza, niezakonczone: [nz] }, { ...baza, niezakonczone: [nz] }, { ...baza, niezakonczone: [] }];
  odp.ostatnia = { ...baza, niezakonczone: [] };
  const e = srodowisko(odp);
  await e.UI.odswiez();
  assert.strictEqual(e.znajdz('zakoncz-mecz-okno').style.display, 'flex');
  assert.strictEqual(e.znajdz('mecz-niezakonczony-bar').style.display, 'flex');
  assert.ok(e.znajdz('mecz-niezakonczony-bar').children[0].textContent.includes('Mecz nie jest zakończony: A – B (2:1)'));
  assert.ok(e.znajdz('mecz-niezakonczony-bar').children[0].textContent.includes('remis bez rozstrzygnięcia'));
  e.znajdz('zakoncz-mecz-nie').click();
  assert.strictEqual(e.znajdz('zakoncz-mecz-okno').style.display, 'none');
  await e.UI.odswiez();                                                                 // kolejne odświeżenie nie otwiera okna drugi raz
  assert.strictEqual(e.znajdz('zakoncz-mecz-okno').style.display, 'none');
  assert.strictEqual(e.znajdz('mecz-niezakonczony-bar').style.display, 'flex');         // trwały pasek zostaje
  e.znajdz('mecz-niezakonczony-zakoncz').click();
  await new Promise((r) => setTimeout(r, 20));
  assert.deepStrictEqual(e.posty, ['/api/games/7/finish']);
  assert.strictEqual(e.znajdz('mecz-niezakonczony-bar').style.display, 'none');
});

await ok('iframe (panel boczny) nie tworzy paska ani okna, nie wysyła żądań i zleca odświeżenie oknu głównemu; okno główne tworzy elementy raz', async () => {
  const nz = { game_id: 7, nazwa: 'A – B', wynik: '2:1', remis_bez_rozstrzygniecia: false };
  const stan = { ...baza, niezakonczone: [nz] };
  const rodzic = {};
  const ramka = srodowisko([stan], rodzic);
  ramka.ctx.fetch = () => { throw new Error('iframe nie może wysyłać żądań'); };
  await ramka.UI.odswiez();
  assert.strictEqual(rodzic.odswiezenia, 1);
  assert.strictEqual(ramka.znajdz('wp-zapis-bar'), undefined);
  assert.strictEqual(ramka.znajdz('zakoncz-mecz-okno'), undefined);
  assert.strictEqual(ramka.znajdz('mecz-niezakonczony-bar'), undefined);
  await ramka.UI.zakonczMecz();
  assert.deepStrictEqual(ramka.posty, []);
  const glowne = srodowisko([stan, stan]);
  await glowne.UI.odswiez();
  await glowne.UI.odswiez();
  for (const id of ['wp-zapis-bar', 'zakoncz-mecz-okno', 'mecz-niezakonczony-bar']) {
    assert.strictEqual(glowne.ctx.document.__ile(id), 1, id);                 // dokładnie jeden element o danym id
  }
  glowne.znajdz('mecz-niezakonczony-zakoncz').click();
  await new Promise((r) => setTimeout(r, 20));
  assert.deepStrictEqual(glowne.posty, ['/api/games/7/finish']);            // jedno żądanie zakończenia
});

console.log('OK ' + wyniki.length + ' przypadków: ' + wyniki.join('; '));
})().catch((e) => { console.error(e); process.exit(1); });
