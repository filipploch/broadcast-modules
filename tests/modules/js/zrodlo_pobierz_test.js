// W8a2: PRAWDZIWY kod modules/static/js/pages/zrodlo-pobierz.js w Node: przycisk „Pobierz” ukryty bez źródła, nieaktywny w trakcie pracy, okno z podsumowaniem po zakończeniu.
// Uruchomienie: node zrodlo_pobierz_test.js   (kod wyjścia 0 = wszystko przeszło)
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const src = fs.readFileSync(path.resolve(__dirname, '..', '..', '..', 'modules', 'static', 'js', 'pages', 'zrodlo-pobierz.js'), 'utf8');

function srodowisko(odpowiedzi, opcjeFetch) {
  const zadania = [];
  const elementy = [];
  const alerty = [];
  const mk = () => {
    const e = { style: {}, textContent: '', children: [], listeners: {}, id: '', disabled: false };
    e.append = (...c) => { e.children.push(...c); };
    e.addEventListener = (t, f) => { (e.listeners[t] = e.listeners[t] || []).push(f); };
    e.click = () => (e.listeners.click || []).forEach((f) => f());
    elementy.push(e);
    return e;
  };
  const ctx = {
    document: { createElement: mk, body: { append() {} } },
    setTimeout: (f) => { ctx.__zaplanowane.push(f); return ctx.__zaplanowane.length; },
    __zaplanowane: [],
    alert: (t) => alerty.push(t),
    fetch: (url, opts) => {
      zadania.push({ url, metoda: (opts && opts.method) || 'GET', cialo: opts && opts.body });
      const o = (opcjeFetch && opcjeFetch(url, opts)) || { ok: true, json: odpowiedzi.shift() || odpowiedzi.ostatnia };
      return Promise.resolve({ ok: o.ok, json: () => Promise.resolve(o.json) });
    },
    console,
  };
  ctx.window = ctx;
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  const przycisk = mk();
  przycisk.textContent = '⬇ Pobierz';
  return { ctx, zadania, alerty, elementy, przycisk, ZP: ctx.ZrodloPobierz, znajdz: (id) => elementy.find((e) => e.id === id) };
}

const wyniki = [];
const ok = async (nazwa, fn) => { await fn(); wyniki.push(nazwa); };
const eq = (a, b) => assert.deepStrictEqual(JSON.parse(JSON.stringify(a)), JSON.parse(JSON.stringify(b)));
const bezZrodla = { dostepne: false, powod: 'ten moduł nie ma źródła zewnętrznego', w_toku: false };
const gotowy = { dostepne: true, w_toku: false, typ: 'nalffutsal' };
const czeka = () => new Promise((r) => setTimeout(r, 10));

(async () => {
await ok('opis przycisku: ukryty bez źródła, aktywny w spoczynku, nieaktywny z etapem i czasem w trakcie pracy', () => {
  const { ZP } = srodowisko([]);
  eq(ZP.opisPrzycisku(bezZrodla, '⬇ Pobierz'), { widoczny: false, nieaktywny: true, tekst: '⬇ Pobierz' });
  eq(ZP.opisPrzycisku(null, '⬇ Pobierz').widoczny, false);
  eq(ZP.opisPrzycisku(gotowy, '⬇ Pobierz'), { widoczny: true, nieaktywny: false, tekst: '⬇ Pobierz' });
  eq(ZP.opisPrzycisku({ ...gotowy, w_toku: true, etap: 'źródło', trwa_s: 3.4 }, 'x'), { widoczny: true, nieaktywny: true, tekst: '⏳ źródło 3 s' });
  assert.ok(ZP.opisPrzycisku({ ...gotowy, w_toku: true, etap: 'moduł' }, 'x').tekst.includes('moduł'));
});

await ok('moduł bez źródła: przycisk zostaje ukryty i nie wysyła nic poza zapytaniem o stan', async () => {
  const e = srodowisko([bezZrodla]);
  await e.ZP.podlacz(e.przycisk, { leagueId: () => 5 });
  assert.strictEqual(e.przycisk.style.display, 'none');
  eq(e.zadania.map((z) => z.url), ['/api/zrodlo/status']);
});

await ok('moduł ze źródłem: przycisk widoczny; klik wysyła id ligi, w trakcie pracy nieaktywny, po zakończeniu okno z podsumowaniem i odświeżenie widoku', async () => {
  const wynik = { ok: true, tekst: 'ODŚWIEŻENIE WYNIKÓW: Dywizja A\nZmieniono meczów: 1', zrodlo: { ok: true, tekst: 'x' }, czas_s: 4 };
  const odp = [gotowy, { dostepne: true, w_toku: true, etap: 'źródło', trwa_s: 1 }, { dostepne: true, w_toku: true, etap: 'moduł', trwa_s: 3 },
    { dostepne: true, w_toku: false, wynik }];
  const e = srodowisko(odp, (url, opts) => (opts && opts.method === 'POST' ? { ok: true, json: { ok: true, status: 'started' } } : null));
  let odswiezono = null;
  await e.ZP.podlacz(e.przycisk, { leagueId: () => 7, poZakonczeniu: (w) => { odswiezono = w; } });
  assert.strictEqual(e.przycisk.style.display, '');
  assert.strictEqual(e.przycisk.disabled, false);
  e.przycisk.click();
  await czeka();
  const post = e.zadania.find((z) => z.metoda === 'POST');
  assert.strictEqual(post.url, '/api/zrodlo/pobierz');
  eq(JSON.parse(post.cialo), { league_id: 7 });
  assert.strictEqual(e.przycisk.disabled, true);                               // w trakcie pracy
  assert.ok(e.przycisk.textContent.includes('⏳'));
  e.przycisk.click();                                                          // drugi klik w trakcie pracy: nic nie wysyła
  assert.strictEqual(e.zadania.filter((z) => z.metoda === 'POST').length, 1);
  for (let i = 0; i < 4 && e.ctx.__zaplanowane.length; i++) { e.ctx.__zaplanowane.shift()(); await czeka(); }
  assert.strictEqual(e.przycisk.disabled, false);
  assert.strictEqual(e.znajdz('zrodlo-pobierz-okno').style.display, 'flex');
  assert.ok(e.znajdz('zrodlo-pobierz-tekst').textContent.includes('Zmieniono meczów: 1'));
  assert.strictEqual(e.znajdz('zrodlo-pobierz-tytul').textContent, 'Pobieranie zakończone');
  assert.strictEqual(odswiezono.ok, true);
  e.znajdz('zrodlo-pobierz-zamknij').click();
  assert.strictEqual(e.znajdz('zrodlo-pobierz-okno').style.display, 'none');
});

await ok('odmowa serwera (np. liga nie z WP) pokazuje komunikat i przywraca przycisk; praca nie startuje', async () => {
  const e = srodowisko([gotowy], (url, opts) => (opts && opts.method === 'POST' ? { ok: false, json: { ok: false, error: 'Ta liga nie pochodzi z WP' } } : null));
  e.ZP.podlacz(e.przycisk, { leagueId: () => 9 });
  await czeka();
  e.przycisk.click();
  await czeka();
  assert.deepStrictEqual(e.alerty, ['Ta liga nie pochodzi z WP']);
  assert.strictEqual(e.znajdz('zrodlo-pobierz-okno'), undefined);
});

await ok('wynik z błędem źródła ma tytuł o błędzie, a wznowienie po odświeżeniu strony widzi pracę w toku', async () => {
  const { ZP } = srodowisko([]);
  assert.strictEqual(ZP.tytulWyniku({ ok: false, zrodlo: { ok: false, blad: 'ŹRÓDŁO NIE ODPOWIADA' } }), 'Pobieranie: źródło nie odpowiedziało albo błąd importu');
  assert.strictEqual(ZP.tytulWyniku({ ok: false, zrodlo: { ok: true, tekst: 't' } }), 'Pobieranie zakończone z błędami');
  const e = srodowisko([{ dostepne: true, w_toku: true, etap: 'źródło', trwa_s: 12 }]);
  await e.ZP.podlacz(e.przycisk, {});
  assert.strictEqual(e.przycisk.disabled, true);
  assert.strictEqual(e.ctx.__zaplanowane.length, 1);                           // odpytuje dalej, dopóki praca trwa
});

console.log('OK ' + wyniki.length + ' przypadków: ' + wyniki.join('; '));
})().catch((e) => { console.error(e); process.exit(1); });
