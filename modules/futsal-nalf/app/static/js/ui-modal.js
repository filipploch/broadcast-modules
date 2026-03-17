function openModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.classList.remove('hidden');
    // renderPenaltyModal(); // odśwież zawartość, jeśli potrzebna
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.add('hidden');
}

// function renderPenaltyModal() {
//     const modalBody = document.getElementById('penalty-modal-body');

//     modalBody.innerHTML = `
//         ${fillPenaltiesTimersContainer('home')}
//         ${fillPenaltiesTimersContainer('away')}
//     `;
// }

function fillPenaltiesTimersContainer(_penalties, teamType){
    const penalties = _penalties;
    console.log('penalties:', penalties);
    // const penalties = Array.of(appState.penalties[team]);
    let penaltiesContainerId = `${teamType}-team-penalties-timers-container`;
    let penaltiesContainer = document.getElementById(penaltiesContainerId);
    let itemsHtml = '';
    if(penalties.length > 0) {
        penalties.forEach(penalty => {
            console.log('penalty:', teamType, penalty);
            itemsHtml += `
            <div class="penalty-element" data-timer-id="${penalty.timer_id}">
            <div class="penalty-element-content">
            <button class="penalty-modal-button bg_red remove-penalty-button" onclick="removeTimer('${penalty.timer_id}')">X</button>
            <div class="penalty-display" data-display-for="${penalty.timer_id}"></div>
            </div>
            <div class="penalty-element-controllers">
            <div class="gap"></div>
            <button class="penalty-modal-button adjust-penalty-time-button" onclick="adjustTimer('${penalty.timer_id}', -1000);">-</button>
            <button class="penalty-modal-button adjust-penalty-time-button" onclick="adjustTimer('${penalty.timer_id}', 1000);">+</button>
            </div>
            </div>
            `;
        });
    }

    if (penalties.length < 2) {
        itemsHtml += `<button class="add-penalty-button" onclick="addPenaltyTimer('${teamType}')">Dodaj</button>`;
    }

    penaltiesContainer.innerHTML = itemsHtml;
}