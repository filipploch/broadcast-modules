// W7f-null: nakładki (futsal-nalf i garbarnia) nigdy nie pokazują tekstów "null", "undefined", "NaN" ani "None".
// Test uruchamia PRAWDZIWY kod nakładek (overlay.html + js/*.js) w atrapie przeglądarki (nakladki_dom.js), wysyła komunikaty jak HUB (ws.onmessage)
// i sprawdza wszystkie zapisy tekstu (textContent, innerText, innerHTML).
//   node nakladki_null_test.js                  -> wszystkie sprawdzenia (kod wyjścia 1 przy jakimkolwiek niepowodzeniu)
//   node nakladki_null_test.js --zapisz-wzorzec -> zapisuje wzorzec (nakladki_wzorzec.json) z kompletnych danych; robić na kodzie PRZED zmianą
// Sprawdzenia: (1) funkcja displayText (identyczna w obu nakładkach; 0 i false przechodzą bez zmian), (2) kompletne dane dają dokładnie ten sam tekst
// i strukturę co wzorzec, (3) dla każdego pola komunikatu wartości: brak, null, "None", "null", "undefined", "NaN" nie dają zakazanego tekstu.
const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { loadOverlayPage } = require('./nakladki_dom.js');

const WZORZEC = path.join(__dirname, 'nakladki_wzorzec.json');
const ZAPISZ = process.argv.includes('--zapisz-wzorzec');
const NAKLADKI = ['futsal-nalf', 'garbarnia'];
const ZAKAZANE_RE = /(^|[^\p{L}\p{N}_])(null|undefined|NaN|None|NULL|UNDEFINED|NAN|NONE)($|[^\p{L}\p{N}_])/u;      // także wielkie litery (nazwy w nakładkach bywają zamieniane na wielkie)
const ZAKAZANE = ZAKAZANE_RE;

// ── kompletne dane ───────────────────────────────────────────────────────────
const wiersz = (n, nazwa, pkt) => ({ team_name14: nazwa, team_short_name: nazwa.slice(0, 3).toUpperCase(), points: pkt, games: n, wins: 2, draws: 1, loses: 0, goals_scored: 9, goals_lost: 4, goal_difference: 5 });
const TABELA = [wiersz(3, 'Garbarnia', 7), wiersz(3, 'Chełmek', 4), wiersz(3, 'Żarłacze', 0)];
const GRACZE = (garb) => [
  { number: 1, player_name: 'Bramkarz Adam', is_goalkeeper: true, is_captain: false, is_youth: false, role: 'starter' },
  { number: 7, player_name: 'Kowalski Jan', is_goalkeeper: false, is_captain: true, is_youth: false, role: 'starter' },
  { number: 10, player_name: 'Nowak Piotr', is_goalkeeper: false, is_captain: false, is_youth: garb, role: 'substitute' },
];
const SKLAD = (garb, id) => ({ container_id: id, team_name: 'Garbarnia Kraków', team_short_name: 'GAR', team_squad: GRACZE(garb), logo: 'static/logos/gar.png', coach: 'Trener Jan' });
const STRZELCY = { scorers: [{ player_first_name: 'Jan', player_last_name: 'Kowalski', goals: [{ minute: 12, added_time: 0, is_own_goal: false }, { minute: 45, added_time: 2, is_own_goal: true }] }] };

function scenariusze(nakladka) {
  const garb = nakladka === 'garbarnia';
  const ukryjGre = (p) => { p.document.getElementById('game-container').style.display = 'none'; };
  const S = [];
  const add = (nazwa, msgs, o = {}) => S.push({ nazwa, msgs, ...o });
  const dane = {
    home_team_short_name: 'GAR', away_team_short_name: 'CHE', home_team_goals: 2, away_team_goals: 1, home_team_fouls: 3, away_team_fouls: 1,
    home_team_uniform: '["#ff0000","#ffffff"]', away_team_uniform: '["#0000ff"]', league_name: 'Dywizja A', season_number: 30, round_name: '1. kolejka Dywizji A',
    ...(garb ? { home_team_red_cards: 2, away_team_red_cards: 1, periods: [{ status: 1, added_time: 3 }] } : {}),
  };
  add('game_data', [['game_data', dane]]);
  add('scoreboard_data', [['scoreboard_data', { home_team_goals: 3, away_team_goals: 2, home_team_value2: 2, away_team_value2: 1 }]]);
  add('zegar', [['timer_updated', { timer_id: 'main', elapsed_time: 65000, initial_time: 0, limit: 2700000 }]]);
  if (garb) add('zegar_doliczony', [['timer_updated', { timer_id: 'main', elapsed_time: 2760000, initial_time: 0, limit: 2700000 }], ['added_time_updated', { added_time: 3 }]]);
  if (!garb) add('kary', [['penalty_state', { home: [{ id: 1, team: 'home', player_id: 7, limit_ms: 120000, start_offset_ms: 0, adjustment_ms: 0, state: 'running' }], away: [], main_elapsed_ms: 30000 }],
    ['timer_updated', { timer_id: 'main', elapsed_time: 45000, initial_time: 0, limit: 2700000 }]]);
  add('sklad_gospodarzy', [['show_overlay_container', SKLAD(garb, 'home-team-squad-container')]]);
  add('sklad_gosci', [['show_overlay_container', SKLAD(garb, 'away-team-squad-container')]]);
  add('start', [['show_overlay_container', {
    container_id: 'start-container', round_name: '1. kolejka', home_team_logo: 'static/logos/gar.png', away_team_logo: 'static/logos/che.png', home_team_name: 'Garbarnia', away_team_name: 'Chełmek',
    stadium: { name: 'Hala Garbarni', address: 'ul. Sportowa 1' }, referees: [{ name: 'Arbiter Jeden' }, { name: 'Arbiter Dwa' }], commentators: [{ name: 'Komentator Jan' }],
  }]]);
  add('przerwa', [['show_overlay_container', {
    container_id: 'break-container', round_name: '1. kolejka', home_team_logo: 'static/logos/gar.png', away_team_logo: 'static/logos/che.png', result: '2 : 1',
    home_team_scorers: STRZELCY, away_team_scorers: STRZELCY,
  }]]);
  const gry = [{ home_team_name14: 'Garbarnia', away_team_name14: 'Chełmek', home_team_goals: 2, away_team_goals: 1, status: 2 }, { home_team_name14: 'Żarłacze', away_team_name14: 'Nowa Dr.', home_team_goals: 0, away_team_goals: 0, status: 2 }];
  add('wyniki_pelne', [['results', { games: gry }]], { prep: ukryjGre });
  add('tabela_pelna', [['table', { rows: TABELA }]], { prep: ukryjGre });
  add('tabela_wirtualna_pelna', [['virtual_table', { official: TABELA, virtual: TABELA.slice().reverse() }]], { prep: ukryjGre });
  add('wyniki_widget', [['results', { games: gry }]]);
  add('tabela_widget', [['table', { rows: TABELA }]]);
  add('tabela_wirtualna_widget', [['virtual_table', { official: TABELA, virtual: TABELA.slice().reverse() }]]);
  add('dogrywka', [['show_overlay_container', { container_id: 'shootout-container', home_team_name: 'Garbarnia', away_team_name: 'Chełmek', home_team_shootouts: 4, away_team_shootouts: 3, home_team_logo: 'a.png', away_team_logo: 'b.png' }]]);
  add('zdarzenie', [['show_info', { event_image_path: 'static/e.png', game_time: 754, period_limit_s: 2700, period_start_s: 0, player_number: 7, player_name: 'Kowalski', player_team_short_name: 'GAR', event_type_id: 2, team_name: 'Garbarnia', game_event_id: 5 }]]);
  add('zdarzenie_bez_okresu', [['show_info', { event_image_path: 'static/e.png', game_time: 754, player_number: 7, player_name: 'Kowalski', player_team_short_name: 'GAR', event_type_id: 1, team_name: 'Garbarnia', game_event_id: 6 }]]);
  add('zmiana', [['show_substitution', { game_time_ms: 754000, period_end_s: 2700, period_start_s: 0, team_short_name: 'GAR',
    substitutions: [{ player_out_number: 7, player_out_name: 'Kowalski', player_in_number: 10, player_in_name: 'Nowak' }] }]]);
  add('wywiad', [['show_overlay_container', { container_id: 'interview-container', name: 'Jan Kowalski', description: 'Trener', image: 'static/x.png', participant_id: 3 }],
    ['update_interview', { name: 'Jan Kowalski', description: 'Trener', image: 'static/x.png' }], ['show_interview', { participant_id: 3 }]]);
  add('baner', [['banner_show', { source: '<div class="b">Baner</div>' }]]);
  add('gol', [['goal', { name_14: 'GARBARNIA' }]]);
  add('zera', [['game_data', { ...dane, home_team_goals: 0, away_team_goals: 0, home_team_fouls: 0, away_team_fouls: 0 }],
    ['scoreboard_data', { home_team_goals: 0, away_team_goals: 0, home_team_value2: 0, away_team_value2: 0 }],
    ['show_overlay_container', { ...SKLAD(garb, 'home-team-squad-container'), team_squad: [{ ...GRACZE(garb)[0], number: 0 }] }]]);
  return S;
}

// ── uruchomienie scenariusza ─────────────────────────────────────────────────
function uruchom(nakladka, scenariusz, msgs) {
  const p = loadOverlayPage(nakladka);
  p.send('registered', {});
  p.advance(100);
  p.log.length = 0;
  if (scenariusz.prep) scenariusz.prep(p);
  for (const [typ, payload] of msgs) { p.send(typ, JSON.parse(JSON.stringify(payload))); p.advance(30000); }
  return { log: p.log.slice(), tekst: p.visibleText(), errors: p.errors.slice() };
}

const skroc = (l) => (l.length > 400 ? l.slice(0, 200) + '…' + crypto.createHash('sha1').update(l).digest('hex').slice(0, 12) : l);

// ── liście komunikatu ────────────────────────────────────────────────────────
function liscie(obj, prefix = [], out = []) {
  if (Array.isArray(obj)) obj.forEach((v, i) => liscie(v, prefix.concat(i), out));
  else if (obj && typeof obj === 'object') Object.keys(obj).forEach((k) => liscie(obj[k], prefix.concat(k), out));
  else out.push(prefix);
  return out;
}
function ustaw(msgPayload, sciezka, tryb) {
  const kopia = JSON.parse(JSON.stringify(msgPayload));
  let o = kopia;
  for (let i = 0; i < sciezka.length - 1; i++) o = o[sciezka[i]];
  const k = sciezka[sciezka.length - 1];
  if (tryb === 'brak') { if (Array.isArray(o)) o[k] = null; else delete o[k]; } else o[k] = tryb === 'null' ? null : tryb;
  return kopia;
}
const TRYBY = ['brak', 'null', 'None', 'null-tekst', 'undefined', 'NaN'];
const tryb = (t) => (t === 'null-tekst' ? 'null' : t);

let niepowodzenia = 0;
const raportuj = (opis) => { niepowodzenia++; if (niepowodzenia <= 60) console.log('FAIL ' + opis); };

// ── 1. funkcja displayText ───────────────────────────────────────────────────
function testFunkcji() {
  const f = {};
  for (const n of NAKLADKI) {
    const src = fs.readFileSync(path.join(__dirname, '..', '..', '..', 'hub', 'overlays', n, 'js', 'utils.js'), 'utf8');
    const m = src.match(/function displayText[\s\S]*?\n}/);
    if (!m) { raportuj(`${n}: brak funkcji displayText w utils.js`); continue; }
    f[n] = m[0].replace(/\r\n/g, '\n');
    const fn = new Function(f[n] + '; return displayText;')();
    // wartości puste -> ""
    for (const v of [null, undefined, NaN, 'null', 'undefined', 'NaN', 'None']) if (fn(v) !== '') raportuj(`${n}: displayText(${String(v)}) = ${JSON.stringify(fn(v))}, oczekiwano ""`);
    // 0, false, zwykłe teksty, pusty tekst, fragmenty dłuższych tekstów: bez zmian
    for (const v of [0, false, 1, -3, 12.5, 'Kowalski', '', ' ', 'None Bis', 'Nonexistent', 'null pointer', 'NaN!', 'none', 'NULL', 'Undefined', ' None']) {
      if (fn(v) !== v) raportuj(`${n}: displayText(${JSON.stringify(v)}) zmienił wartość na ${JSON.stringify(fn(v))}`);
    }
    if (!Object.is(fn(0), 0) || fn(false) !== false) raportuj(`${n}: 0 albo false nie przechodzi bez zmian`);
  }
  if (f['futsal-nalf'] && f.garbarnia && f['futsal-nalf'] !== f.garbarnia) raportuj('displayText różni się między nakładkami');
}

// ── 2. kompletne dane = wzorzec ─────────────────────────────────────────────
function testWzorca(wzorzec) {
  const wynik = {};
  for (const n of NAKLADKI) {
    wynik[n] = {};
    for (const s of scenariusze(n)) {
      const r = uruchom(n, s, s.msgs);
      wynik[n][s.nazwa] = { log: r.log.map(skroc), tekst: skroc(r.tekst), errors: r.errors };
      for (const l of r.log) {
        const t = l.split('\t');
        if (/^(textContent|innerText|innerHTML)$/.test(t[1]) && ZAKAZANE.test(String(JSON.parse(t[2])).replace(/<[^>]*>/g, '|'))) raportuj(`${n}/${s.nazwa}: kompletne dane, ale zapis zawiera zakazany tekst: ${skroc(l)}`);
      }
    }
  }
  if (ZAPISZ) {
    fs.writeFileSync(WZORZEC, JSON.stringify(wynik, null, 1), 'utf8');
    console.log('Zapisano wzorzec: ' + WZORZEC);
    return;
  }
  for (const n of NAKLADKI) {
    for (const nazwa of Object.keys(wzorzec[n] || {})) {
      const a = JSON.stringify(wzorzec[n][nazwa]); const b = JSON.stringify(wynik[n][nazwa]);
      if (a !== b) {
        const la = wzorzec[n][nazwa].log; const lb = wynik[n][nazwa].log;
        let i = 0; while (i < Math.max(la.length, lb.length) && la[i] === lb[i]) i++;
        raportuj(`${n}/${nazwa}: wynik dla kompletnych danych różni się od wzorca (pierwsza różnica w zapisie nr ${i}): wzorzec ${JSON.stringify(la[i])} <> teraz ${JSON.stringify(lb[i])}`);
      }
    }
    for (const nazwa of Object.keys(wynik[n])) if (!(wzorzec[n] || {})[nazwa]) raportuj(`${n}/${nazwa}: brak w wzorcu`);
  }
}

// ── 3. mutacje pól ───────────────────────────────────────────────────────────
const grupy = new Map();
const wyjatki = new Map();
function testMutacji() {
  let liczba = 0;
  for (const n of NAKLADKI) {
    for (const s of scenariusze(n)) {
      s.msgs.forEach(([typ, payload], idx) => {
        for (const sciezka of liscie(payload)) {
          for (const t of TRYBY) {
            if (t === 'brak' && Array.isArray(payload) ) continue;
            const msgs = s.msgs.map((m, i) => (i === idx ? [typ, ustaw(payload, sciezka, tryb(t))] : m));
            const r = uruchom(n, s, msgs);
            liczba++;
            for (const e of r.errors) { const k = `${n}/${s.nazwa}: ${e.slice(0, 110)}`; const g = wyjatki.get(k) || { liczba: 0, przyklad: `${typ}.${sciezka.join('.')} = ${t}` }; g.liczba++; wyjatki.set(k, g); }
            for (const l of r.log) {
              const tt = l.split('\t');
              if (!/^(textContent|innerText|innerHTML)$/.test(tt[1])) continue;
              let wartosc; try { wartosc = JSON.parse(tt[2]); } catch (e) { continue; }
              const bezTagow = String(wartosc).replace(/<[^>]*>/g, '|');
              if (ZAKAZANE.test(bezTagow)) {
                niepowodzenia++;
                const klucz = `${n}/${s.nazwa} | ${tt[0]} ${tt[1]}`;
                const g = grupy.get(klucz) || { liczba: 0, przyklad: `${typ}.${sciezka.join('.')} = ${t} -> ${JSON.stringify(skroc(String(wartosc)))}` };
                g.liczba++; grupy.set(klucz, g);
                break;
              }
            }
          }
        }
      });
    }
  }
  return liczba;
}

// ── 2b. nagłówek zmiany: skrót drużyny w nawiasach tylko gdy niepusty ─────────────────────────────────────
function testNaglowkaZmiany() {
  const naglowek = (n, skrot) => {
    const p = loadOverlayPage(n); p.send('registered', {}); p.advance(100); p.log.length = 0;
    const payload = { game_time_ms: 754000, period_end_s: 2400, period_start_s: 0, substitutions: [{ player_out_number: 7, player_out_name: 'A', player_in_number: 10, player_in_name: 'B' }] };
    if (skrot !== undefined) payload.team_short_name = skrot;
    p.send('show_substitution', payload);
    const l = p.log.find((x) => x.startsWith('div#substitution-header'));
    return l ? JSON.parse(l.split('	')[2]) : null;
  };
  for (const n of NAKLADKI) {
    const oczek = [['GAR', "13' ZMIANA (GAR)"], ['', "13' ZMIANA"], [undefined, "13' ZMIANA"], [null, "13' ZMIANA"], ['None', "13' ZMIANA"], ['null', "13' ZMIANA"], ['NaN', "13' ZMIANA"]];
    for (const [skrot, wynik] of oczek) if (naglowek(n, skrot) !== wynik) raportuj(`${n}: nagłówek zmiany dla skrótu ${JSON.stringify(skrot)} = ${JSON.stringify(naglowek(n, skrot))}, oczekiwano ${JSON.stringify(wynik)}`);
  }
}

if (!ZAPISZ) { testFunkcji(); testNaglowkaZmiany(); }
let wzorzec = null;
if (!ZAPISZ) {
  if (!fs.existsSync(WZORZEC)) { console.log('Brak wzorca: uruchom z --zapisz-wzorzec na kodzie sprzed zmiany'); process.exit(2); }
  wzorzec = JSON.parse(fs.readFileSync(WZORZEC, 'utf8'));
}
testWzorca(wzorzec);
let mutacje = 0;
if (!ZAPISZ) mutacje = testMutacji();
if (wyjatki.size && process.env.BM_POKAZ_WYJATKI) { console.log(`--- wyjątki w nakładkach przy brakujących danych (${wyjatki.size}):`); wyjatki.forEach((g, k) => console.log(`${String(g.liczba).padStart(3)}x ${k}  np. ${g.przyklad}`)); }
if (grupy.size) { console.log(`--- miejsca z zakazanym tekstem (${grupy.size}):`); grupy.forEach((g, k) => console.log(`${String(g.liczba).padStart(3)}x ${k}
       np. ${g.przyklad}`)); }
if (niepowodzenia) { console.log(`${niepowodzenia} niepowodzeń`); process.exit(1); }
console.log(ZAPISZ ? 'OK wzorzec zapisany' : `OK displayText, wzorzec (${NAKLADKI.length} nakładki), ${mutacje} mutacji pól bez zakazanego tekstu`);
