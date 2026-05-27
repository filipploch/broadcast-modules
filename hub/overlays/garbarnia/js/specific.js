// specific.js — moduł garbarnia
// Ładowany PRZED overlay.js — używa window.addEventListener('load')
// żeby podmienić createTeamSquad po załadowaniu wszystkich skryptów.

function setLeagueName() {
    return 'Texom Małopolska 4. Liga';
}

function setLeagueLogo() {
    return '/static/images/TM4L/logoTM4L.png';
}

// Podmień createTeamSquad po załadowaniu overlay.js.
//
// get_squad() garbarni zwraca płaską tablicę gdzie każdy element
// ma pole `role` ('starter' | 'substitute') — podstawowi pierwsi,
// potem rezerwa. Ta wersja buduje dwie sekcje z nagłówkami.
window.addEventListener('load', function () {

    // Zachowaj oryginał jako fallback
    var _originalCreateTeamSquad = createTeamSquad;

    createTeamSquad = function (_arr, _logo, _coach) {
        // Jeśli żaden element nie ma pola `role` — użyj oryginału (kompatybilność)
        if (!Array.isArray(_arr) || _arr.length === 0 || _arr[0].role === undefined) {
            return _originalCreateTeamSquad(_arr, _logo);
        }

        var starters    = _arr.filter(function (p) { return p.role === 'starter'; });
        var substitutes = _arr.filter(function (p) { return p.role === 'substitute'; });
        var coach = _coach;

        var squadContent = document.createElement('div');
        squadContent.classList.add('team-squad-content', 'squad-content');

        function buildPlayerRow(element, globalIndex) {
            var goalkeeper = element.is_goalkeeper ? ' (B) ' : '';
            var captain    = element.is_captain    ? ' (C) ' : '';
            var youth      = element.is_youth      ? ' (M) ' : '';
            var number     = element.number != null ? element.number : '';

            var row = document.createElement('div');
            row.classList.add(
                'squad-player-row',
                'specific-colors',
                'rotate-show-element',
                'rotate-show-element' + globalIndex,
                'animated-element'
            );
            row.dataset.animationOrder = '3';
            row.innerHTML =
                '<span class="squad-player-number">' + number + '</span>' +
                '<span class="squad-player-name">' + element.player_name + '</span>' +
                '<span class="squad-player-func">' + goalkeeper + captain + youth + '</span>';
            return row;
        }

        function buildSection(players, className, startIndex) {
            if (players.length === 0) return;
            var section = document.createElement('div');
            section.classList.add('squad-section');

            players.forEach(function (element, idx) {
                section.appendChild(buildPlayerRow(element, startIndex + idx));
            });

            squadContent.appendChild(section);
            addClassName(section, className);
        }

        function buildCoachRow(element, rotateElementNr) {
            var row = document.createElement('div');
            if(coach === null) return row;
            let coachTitle = document.createElement('div');
            coachTitle.classList.add(
                'squad-player-row',
                'specific-colors-reversed',
                'rotate-show-element',
                'rotate-show-element' + rotateElementNr,
                'animated-element',
                'coach-row'
            );
            coachTitle.innerHTML = 'trener';
            let coachContent = document.createElement('div');

            coachContent.classList.add(
                'squad-player-row',
                'specific-colors',
                'rotate-show-element',
                'rotate-show-element' + parseInt(rotateElementNr+1),
                'animated-element',
                'coach-row'
            );
            coachContent.dataset.animationOrder = '3';
            if(coach[0] !== null){
                coachContent.innerHTML = coach;
            }else{
                row.style.display = 'none';
            }
            row.appendChild(coachTitle);
            row.appendChild(coachContent);
            return row;
        }

        function buildCoachSection(players) {
            if (players.length === 0) return;
            var section = document.createElement('div');
            section.classList.add('squad-section');

            let rotateElNr = players.length + 1;

            section.appendChild(buildCoachRow(coach, rotateElNr));

            addClassName(section, 'coach');
            squadContent.appendChild(section);
        }

        buildSection(starters,    'starters',   0);
        buildSection(substitutes, 'substitutes', starters.length);
        buildCoachSection(_arr);

        // Tymczasowo wstaw squadContent do body — cały kontekst CSS (.starters > div itp.) zachowany
        squadContent.style.position   = 'absolute';
        squadContent.style.visibility = 'hidden';
        document.body.appendChild(squadContent);
        var _firstRow = squadContent.querySelector('.squad-player-row');
        if (_firstRow) {
            var _h = _firstRow.offsetHeight;
            var _w = _firstRow.offsetWidth;
            if (_h > 0 && _w > 0) {
                var _polygon = makePolygonTilt(_h, _w, 'both');
                squadContent.querySelectorAll('.squad-player-row').forEach(function(row) {
                    row.style.clipPath = _polygon;
                });
            }
        }
        document.body.removeChild(squadContent);
        squadContent.style.position   = '';
        squadContent.style.visibility = '';

        return squadContent;
    };
});
