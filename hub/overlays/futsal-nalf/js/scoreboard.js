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
