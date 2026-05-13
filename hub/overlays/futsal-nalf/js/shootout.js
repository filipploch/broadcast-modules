function makeShootoutContainer(){
    let shootoutContainer = document.querySelector('#shootout-container');
    let shootoutContent = `
    <div id="shootout-logo-container" style="z-index: 3; position: absolute; bottom: 70px; width: 100%; height: 65px; background-color: rgba(0,0,0,0); display: flex; filter: drop-shadow(0px 3px 3px black);">
        <div id="shootout-home-team-logo" class="shootout-team-logo"><img src="ukr.png"></div>
        <div class="shootout-break"></div>
        <div id="shootout-away-team-logo" class="shootout-team-logo"><img src="opp.png"></div>
    </div>
    <div id="shootout-content" style="z-index: 1; position: absolute; bottom: 0; width: 100%; height: 85px; background-color: rgba(0,0,0,0.8); display: block;">
        <div id="shootout-content2" style="z-index: 2; position: absolute; bottom: 85px; width: 100%; height: 70px; background-color: rgba(255,255,255,1); display: block; filter: drop-shadow(0px 5px 5px black);">
            <div id="shootout-content3">
                <div id="shootout-home-team-name" style="text-align: right;	" class="shootout-team-name">UKRAINIAN LEGION</div>
                <div style="width: 20%; display: flex; justify-content: center; align-items: center;">
                    <div id="shootout-result-container">
                        <div id="shootout-home-team-result" style="justify-content: right;" class="shootout-result-element">0</div>
                        <div style="justify-content: center;" class="shootout-result-element">:</div>
                        <div id="shootout-away-team-result" style="justify-content: left;" class="shootout-result-element">0</div>
                    </div>
                </div>
                <div id="shootout-away-team-name" class="shootout-team-name">ODDZIAŁ PREWENCJI POLICJI</div>
            </div>
        </div>
    </div>
    <div id="shootout-content" style="z-index: 3; position: absolute; bottom: 1vw; width: 100%; height: 2.5vw; display: flex; filter: drop-shadow(0px 3px 3px black);">
        <div style="justify-content: right;" class="shootout-points-container">
            <div data-round-nr="13" class="shootout-point shootout-home-team-point shootout-point-hidden">13</div>
            <div data-round-nr="12" class="shootout-point shootout-home-team-point shootout-point-hidden">12</div>
            <div data-round-nr="11" class="shootout-point shootout-home-team-point shootout-point-hidden">11</div>
            <div data-round-nr="10" class="shootout-point shootout-home-team-point shootout-point-hidden">10</div>
            <div data-round-nr="9" class="shootout-point shootout-home-team-point shootout-point-hidden">9</div>
            <div data-round-nr="8" class="shootout-point shootout-home-team-point shootout-point-hidden">8</div>
            <div data-round-nr="7" class="shootout-point shootout-home-team-point shootout-point-hidden">7</div>
            <div data-round-nr="6" class="shootout-point shootout-home-team-point shootout-point-hidden">6</div>
            <div data-round-nr="5" class="shootout-point shootout-home-team-point shootout-point-hidden">5</div>
            <div data-round-nr="4" class="shootout-point shootout-home-team-point shootout-point-hidden">4</div>
            <div data-round-nr="3" class="shootout-point shootout-home-team-point shootout-point-null">3</div>
            <div data-round-nr="2" class="shootout-point shootout-home-team-point shootout-point-null">2</div>
            <div data-round-nr="1" class="shootout-point shootout-home-team-point shootout-point-null">1</div>
        </div>
        <div style="width: 12%; display: flex; justify-content: center; align-items: center;"></div>
        <div style="justify-content: left;" class="shootout-points-container">
            <div data-round-nr="1" class="shootout-point shootout-away-team-point shootout-point-null">1</div>
            <div data-round-nr="2" class="shootout-point shootout-away-team-point shootout-point-null">2</div>
            <div data-round-nr="3" class="shootout-point shootout-away-team-point shootout-point-null">3</div>
            <div data-round-nr="4" class="shootout-point shootout-away-team-point shootout-point-hidden">4</div>
            <div data-round-nr="5" class="shootout-point shootout-away-team-point shootout-point-hidden">5</div>
            <div data-round-nr="6" class="shootout-point shootout-away-team-point shootout-point-hidden">6</div>
            <div data-round-nr="7" class="shootout-point shootout-away-team-point shootout-point-hidden">7</div>
            <div data-round-nr="8" class="shootout-point shootout-away-team-point shootout-point-hidden">8</div>
            <div data-round-nr="9" class="shootout-point shootout-away-team-point shootout-point-hidden">9</div>
            <div data-round-nr="10" class="shootout-point shootout-away-team-point shootout-point-hidden">10</div>
            <div data-round-nr="11" class="shootout-point shootout-away-team-point shootout-point-hidden">11</div>
            <div data-round-nr="12" class="shootout-point shootout-away-team-point shootout-point-hidden">12</div>
            <div data-round-nr="13" class="shootout-point shootout-away-team-point shootout-point-hidden">13</div>
        </div>
    </div>`;
    shootoutContainer.innerHTML = shootoutContent;
};

function fillShootoutContainer(data) {
    let homeTeamLogoImg = document.querySelector('#shootout-home-team-logo img');
    let awayTeamLogoImg = document.querySelector('#shootout-away-team-logo img');
    let homeTeamNameElement = document.querySelector('#shootout-home-team-name');
    let awayTeamNameElement = document.querySelector('#shootout-away-team-name');
    let homeTeamResult = document.querySelector('#shootout-away-team-result');
    let awayTeamResult = document.querySelector('#shootout-away-team-result');

    homeTeamNameElement.innerText = data.home_team_name;
    awayTeamNameElement.innerText = data.away_team_name;
    homeTeamResult.innerText = data.home_team_shootouts;
    awayTeamResult.innerText = data.away_team_shootouts;
    homeTeamLogoImg.src = rootApp+`${data.home_team_logo}`;
    awayTeamLogoImg.src = rootApp+`${data.away_team_logo}`;
}

makeShootoutContainer();