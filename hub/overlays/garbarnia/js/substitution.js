
var _substOverlayTimer = null;
var SUBST_DISPLAY_MS   = 11000; // czas animacji z substitution.html
 
function showSubstitutionOverlay(data) {
    var container  = document.getElementById('substitutions-container');
    var innerWrap  = document.getElementById('substitutions');
    var header     = document.getElementById('substitution-header');
 
    if (!container || !innerWrap || !header) return;
 
    // Wyczyść poprzednią zawartość (poza headerem)
    var oldSlots = innerWrap.querySelectorAll('.substitution-slot');
    oldSlots.forEach(function (s) { s.remove(); });
 
    // Czas w minutach
    var totalSec   = Math.floor((data.game_time_ms || 0) / 1000);
    var periodEndS = data.period_end_s || 0;
    var timeDisplay = formatGameTimeDisplay(totalSec, periodEndS);
 
    // header.textContent = minutes + " ZMIANA (" + (data.team_short_name || '') + ")";
    header.textContent = timeDisplay + " ZMIANA (" + (data.team_short_name || '') + ")";
 
    // Zbuduj slot dla każdej pary
    (data.substitutions || []).forEach(function (sub) {
        var slot = document.createElement('div');
        slot.className = 'substitution-slot';
 
        var numOut  = sub.player_out_number != null ? sub.player_out_number + '.' : '';
        var numIn   = sub.player_in_number  != null ? sub.player_in_number  + '.' : '';
 
        slot.innerHTML =
            '<div class="substitution-row subst-player-out substitution-player">' +
                '<div class="substitution-out-icon substitution-icon">&#9660</div>' +
                '<div class="subst-player-number">' + numOut + '</div>' +
                '<div class="subst-player-name">'   + (sub.player_out_name || '') + '</div>' +
            '</div>' +
            '<div class="substitution-row subst-player-in substitution-player">' +
                '<div class="substitution-in-icon substitution-icon">&#9650</div>' +
                '<div class="subst-player-number">' + numIn + '</div>' +
                '<div class="subst-player-name">'   + (sub.player_in_name  || '') + '</div>' +
            '</div>';
 
        innerWrap.appendChild(slot);
    });
 
    // Dopasuj rozmiar kontenera do zawartości (jak w substitution.html)
    // requestAnimationFrame(function () {
    //     var children   = innerWrap.getElementsByClassName('substitution');
    //     var maxWidth   = 500;
    //     var totalHeight = 500;
    //     for (var i = 0; i < children.length; i++) {
    //         if (children[i].offsetWidth > maxWidth)   maxWidth    = children[i].offsetWidth;
    //         totalHeight += children[i].offsetHeight;
    //     }
    //     container.style.width  = maxWidth    + 'px';
    //     container.style.height = totalHeight + 'px';
    // });
    container.style.display = 'block';
 
    // Uruchom animację — resetuj przez podmianę elementu
    var fresh = innerWrap.cloneNode(true);
    innerWrap.parentNode.replaceChild(fresh, innerWrap);
    fresh.style.animation = 'none';
    void fresh.offsetWidth; // reflow
    fresh.style.animation  = 'showSubstitution ' + (SUBST_DISPLAY_MS / 1000) + 's';
    fresh.style.animationFillMode = 'both';
 
    // Ukryj po czasie animacji
    if (_substOverlayTimer) clearTimeout(_substOverlayTimer);
    _substOverlayTimer = setTimeout(function () {
        container.style.display = 'none';
    }, SUBST_DISPLAY_MS);
}