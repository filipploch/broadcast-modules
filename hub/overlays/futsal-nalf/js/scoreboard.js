/* ════════════════════════════════════════════════════════════════
   SCOREBOARD.JS — Animacje i aktualizacje scoreboard futsal-nalf
   ════════════════════════════════════════════════════════════════ */

/* Wybór trybu wyświetlania fauli: 'badge' (liczba na czerwonym tle)
   lub 'dots' (kropki zmieniające kolor).                          */
const FOULS_DISPLAY_MODE = 'badge';

/* Łączny czas animacji sb-hide: ostatnia animacja startuje 300ms,
   trwa 400ms → razem 700ms. Czyszczenie klasy po tym czasie.      */
const SB_HIDE_DURATION_MS = 750;

function showScoreboard() {
    const container = document.getElementById('scoreboard-container');
    if (!container) return;
    container.classList.remove('sb-hide');
    container.classList.add('sb-show');

    ['home-team-fouls', 'away-team-fouls'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        const count = parseInt(el.dataset.foulsCount ?? '0') || 0;
        const target = count > 0 ? 'translateY(0)' : 'translateY(35px)';
        console.log(`[showScoreboard] ${id}: foulsCount="${el.dataset.foulsCount}" → count=${count} → transform=${target}`);
        el.style.transition = 'none';
        el.style.transform = target;
        requestAnimationFrame(() => el.style.removeProperty('transition'));
    });

    const logoImg = document.getElementById('nalf-logo-img');
    if (logoImg && !logoImg.getAttribute('src')) {
        logoImg.src = rootApp + setLeagueLogo();
    }
}

function hideScoreboard() {
    const container = document.getElementById('scoreboard-container');
    if (!container) return;
    container.classList.remove('sb-show');
    container.classList.add('sb-hide');
    setTimeout(() => container.classList.remove('sb-hide'), SB_HIDE_DURATION_MS);
}

/* ── Fouls display ───────────────────────────────────────────── */

function updateFoulsAsBadge(count, el) {
    if (!el) return;
    const n = parseInt(count);
    const newCount = (isNaN(n) || count === null || count === '') ? 0 : n;
    const prevCount = parseInt(el.dataset.foulsCount ?? '0') || 0;

    console.log(`[updateFouls] id=${el.id} raw="${count}" newCount=${newCount} prevCount=${prevCount}`);

    if (newCount === prevCount) return;
    el.dataset.foulsCount = String(newCount);

    if (newCount > 0 && prevCount === 0) {
        // 0 → N: zaktualizuj wartość, slide up zza main-scoreboard
        el.textContent = newCount;
        el.style.transition = 'transform 0.35s ease-out';
        el.style.transform = 'translateY(0)';
    } else if (newCount === 0 && prevCount > 0) {
        // N → 0: slide down za main-scoreboard, po zakończeniu wyczyść wartość
        el.style.transition = 'transform 0.35s ease-in';
        el.style.transform = 'translateY(35px)';
        if (el._foulsTimer) clearTimeout(el._foulsTimer);
        el._foulsTimer = setTimeout(() => {
            el.textContent = '';
            el._foulsTimer = null;
        }, 400);
    } else {
        // N → M (oba > 0): tylko aktualizacja liczby
        el.textContent = newCount;
    }
}

function updateFoulsAsDots(count, el) {
    if (!el) return;
    const n = parseInt(count);
    if (isNaN(n) || count === null || count === '') {
        el.textContent = '';
        return;
    }
    if (n >= 0 && n < 6) {
        el.textContent = '●'.repeat(n);
        el.style.color = n >= 5 ? 'red' : n >= 4 ? '' : 'white';
    }
}

function updateFoulsElement(count, el) {
    if (FOULS_DISPLAY_MODE === 'badge') {
        updateFoulsAsBadge(count, el);
    } else {
        updateFoulsAsDots(count, el);
    }
}

/* ── Game info slideshow ─────────────────────────────────────── */

const GAME_INFO_SLIDE_IDS = [
    'scoreboard-season-info',
    'scoreboard-league-info',
    'scoreboard-round-info',
];

let _gameInfoSlideIndex = 0;
let _gameInfoSlideTimer = null;

function renderSeasonName(seasonNumber) {
    if (seasonNumber == null) return '';
    return 'NALFx' + seasonNumber;
}

function renderRoundName(roundName) {
    if (!roundName) return '';
    if (roundName.includes('Mecz o 3. miejsce')) return 'MAŁY FINAŁ';
    if (roundName.includes('Puchar')) return roundName.replace(' Pucharu Ligi', '');
    if (roundName.includes('Dywizji')) return roundName.slice(0, -10);
    return '';
}

function updateGameInfo(data) {
    const leagueEl = document.getElementById('scoreboard-league-info');
    const seasonEl = document.getElementById('scoreboard-season-info');
    const roundEl  = document.getElementById('scoreboard-round-info');
    if (!leagueEl || !seasonEl || !roundEl) return;

    leagueEl.textContent = data.league_name ?? '';
    seasonEl.textContent = renderSeasonName(data.season_number);
    roundEl.textContent  = renderRoundName(data.round_name);

    _startGameInfoSlideshow();
}

const GAME_INFO_SLIDE_DURATION_MS = 400;

function _startGameInfoSlideshow() {
    if (_gameInfoSlideTimer) clearInterval(_gameInfoSlideTimer);

    GAME_INFO_SLIDE_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.style.transition = 'none'; el.style.transform = 'translateX(100%)'; }
    });
    const first = document.getElementById(GAME_INFO_SLIDE_IDS[0]);
    if (first) first.style.transform = 'translateX(0)';
    _gameInfoSlideIndex = 0;

    _gameInfoSlideTimer = setInterval(() => {
        const nextIndex = (_gameInfoSlideIndex + 1) % GAME_INFO_SLIDE_IDS.length;
        _advanceGameInfoSlide(nextIndex);
    }, 5000);
}

function _advanceGameInfoSlide(nextIndex) {
    const prevIndex = _gameInfoSlideIndex;
    const prevEl = document.getElementById(GAME_INFO_SLIDE_IDS[prevIndex]);
    const nextEl = document.getElementById(GAME_INFO_SLIDE_IDS[nextIndex]);
    if (!prevEl || !nextEl) return;

    nextEl.style.transition = 'none';
    nextEl.style.transform = 'translateX(100%)';
    void nextEl.offsetWidth;

    const t = `transform ${GAME_INFO_SLIDE_DURATION_MS}ms ease`;
    prevEl.style.transition = t;
    prevEl.style.transform = 'translateX(-100%)';
    nextEl.style.transition = t;
    nextEl.style.transform = 'translateX(0)';

    _gameInfoSlideIndex = nextIndex;

    setTimeout(() => {
        prevEl.style.transition = 'none';
        prevEl.style.transform = 'translateX(100%)';
    }, GAME_INFO_SLIDE_DURATION_MS + 50);
}
