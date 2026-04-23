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

    createTeamSquad = function (_arr, _logo) {
        // Jeśli żaden element nie ma pola `role` — użyj oryginału (kompatybilność)
        if (!Array.isArray(_arr) || _arr.length === 0 || _arr[0].role === undefined) {
            return _originalCreateTeamSquad(_arr, _logo);
        }

        var starters    = _arr.filter(function (p) { return p.role === 'starter'; });
        var substitutes = _arr.filter(function (p) { return p.role === 'substitute'; });

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

        function buildCoachRow(element, playerLength) {
            var row = document.createElement('div');
            var coachName  = element.coach;
            if(coachName === null) return row; 
            row.classList.add(
                'squad-player-row',
                'specific-colors',
                'rotate-show-element',
                'rotate-show-element' + playerLength,
                'animated-element'
            );
            row.dataset.animationOrder = '3';
            row.innerHTML = '<span class="squad-player-number"> trener </span>' +
                '<span class="squad-coach-name">' + coachName + '</span>';
            return row;
        }

        function buildCoachSection(players) {
            if (players.length === 0) return;
            var section = document.createElement('div');
            section.classList.add('squad-section');

            let element = players.at(-1);
            console.log('element-1:', element);
            section.appendChild(buildCoachRow(element, players.length));

            addClassName(section, 'coach');
            squadContent.appendChild(section);
        }

        buildSection(starters,    'starters',   0);
        buildSection(substitutes, 'substitutes', starters.length);
        buildCoachSection(_arr);

        return squadContent;
    };
});
