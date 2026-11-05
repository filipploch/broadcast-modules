// W8b: PRAWDZIWY kod modules/static/js/pages/wp-tabela.js w Node: dane do widoku tabeli (oficjalna/wirtualna), opis ostrzeżeń, błędy bez wyjątków.
// Uruchomienie: node wp_tabela_test.js   (kod wyjścia 0 = wszystko przeszło)
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const src = fs.readFileSync(path.resolve(__dirname, '..', '..', '..', 'modules', 'static', 'js', 'pages', 'wp-tabela.js'), 'utf8');

function srodowisko(odpowiedzi) {
  const zadania = [];
  const ctx = {
    fetch: (url) => {
      zadania.push(url);
      const o = odpowiedzi(url);
      if (o instanceof Error) return Promise.reject(o);
      return Promise.resolve({ status: o.status || 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(o.json))) });
    },
    encodeURIComponent,
    Promise, JSON, console,
  };
  ctx.window = ctx;
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  return { zadania, WT: ctx.WpTabela };
}

const wiersz = (n) => ({ position: n, team_name: 'D' + n, points: 10 - n });
const oficjalna = { ok: true, mode: 'final', rows: [wiersz(1), wiersz(2)], warnings: [], computed_at: '2026-11-05T12:34:56+00:00', engine: 'SAH2H', live_matches: 0, needs_draw: true, interpretacja: { wariant: 'do potwierdzenia' } };
const wirtualna = { ok: true, mode: 'live', rows: [wiersz(2), wiersz(1)], warnings: [{ mecz: 'A - B', opis: 'Mecz trwa, ale nie ma wyniku na żywo.', wplyw: 'pominięty w tabeli live' }], computed_at: '2026-11-05T12:35:00+00:00', engine: 'SAH2H', live_matches: 1 };
const eq = (a, b) => assert.deepStrictEqual(JSON.parse(JSON.stringify(a)), JSON.parse(JSON.stringify(b)));
const wyniki = [];
const ok = async (nazwa, fn) => { await fn(); wyniki.push(nazwa); };

(async () => {
await ok('tabela oficjalna: jedno żądanie final, dane w kształcie widoku', async () => {
  const e = srodowisko((url) => ({ json: oficjalna }));
  const d = await e.WT.dane(12, false);
  eq(e.zadania, ['/api/wp-tabela?league_id=12&mode=final']);
  eq(d.official.map((r) => r.team_name), ['D1', 'D2']);
  eq([d.virtual, d.has_live, d.zrodlo, d.engine], [[], false, 'wp', 'SAH2H']);
  eq([d.needs_draw, d.interpretacja.wariant], [true, 'do potwierdzenia']);
});

await ok('tabela wirtualna: dwa żądania (final i live), has_live z liczby meczów live, ostrzeżenia z trybu live', async () => {
  const e = srodowisko((url) => ({ json: url.includes('mode=live') ? wirtualna : oficjalna }));
  const d = await e.WT.dane(12, true);
  eq(e.zadania, ['/api/wp-tabela?league_id=12&mode=final', '/api/wp-tabela?league_id=12&mode=live']);
  eq([d.official.length, d.virtual.length, d.has_live, d.live_matches], [2, 2, true, 1]);
  eq(d.warnings.length, 1);
  assert.strictEqual(d.computed_at, '2026-11-05T12:35:00+00:00');
});

await ok('błąd WP (503) zatrzymuje widok z komunikatem: brak wierszy, żadnej tabeli z pamięci', async () => {
  const e = srodowisko(() => ({ status: 503, json: { ok: false, kind: 'connection', error: 'Tabela niedostępna: WP nie odpowiada (brak połączenia).' } }));
  const d = await e.WT.dane(12, true);
  eq(d, { blad: 'Tabela niedostępna: WP nie odpowiada (brak połączenia).', kind: 'connection' });
});

await ok('błąd jednego z dwóch trybów też zatrzymuje widok; sieć niedostępna to wynik, nie wyjątek', async () => {
  let n = 0;
  const e = srodowisko((url) => (url.includes('mode=live') ? { status: 404, json: { ok: false, kind: 'brak_tabeli', error: 'Rozgrywki tej ligi nie mają tabeli (np. puchar).' } } : { json: oficjalna }));
  const d = await e.WT.dane(5, true);
  eq([d.blad, d.kind], ['Rozgrywki tej ligi nie mają tabeli (np. puchar).', 'brak_tabeli']);
  const e2 = srodowisko(() => new Error('sieć'));
  const w = await e2.WT.pobierz(5, 'final');
  eq([w.ok, w.kind], [false, 'modul']);
  assert.ok(w.error.includes('Moduł nie odpowiada'));
});

await ok('opis ostrzeżeń i godzina policzenia', () => {
  const { WT } = srodowisko(() => ({ json: oficjalna }));
  eq(WT.opisOstrzezen(wirtualna.warnings), ['A - B: Mecz trwa, ale nie ma wyniku na żywo. [pominięty w tabeli live]']);
  eq(WT.opisOstrzezen(null), []);
  eq(WT.opisOstrzezen([{ opis: 'Brak kryteriów.' }]), ['Brak kryteriów.']);
  assert.strictEqual(WT.godzina('2026-11-05T12:34:56+00:00'), '12:34:56 UTC');
  assert.strictEqual(WT.godzina(''), '');
});

console.log('OK ' + wyniki.length + ' przypadków: ' + wyniki.join('; '));
})().catch((e) => { console.error(e); process.exit(1); });
