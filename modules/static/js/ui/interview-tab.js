// interview-tab.js — zakładka "WYWIAD": lista uczestników + modal dodawania.
//
// Serwer: core/socketio_events/base.py — search_interview_person,
// add_interview_participant, remove_interview_participant,
// reset_interview_participants, toggle_interview_participant,
// + content_type 'interview' w request_ui_monitor_content.
//
// Ładowany PO ui-jinja.js (patrz ui-jinja.html) — korzysta z globalnego
// `socket` zdefiniowanego tam.

const INTERVIEW_TYPE_LABELS = {
    redaktor: 'Redaktor',
    zawodnik: 'Zawodnik',
    trener:   'Trener',
    sedzia:   'Sędzia',
    inne:     'Inne',
};

const INTERVIEW_DEFAULT_DESCRIPTIONS = {
    redaktor: 'NALFvideo',
    zawodnik: 'Zawodnik',
    trener:   'Trener',
    sedzia:   'Sędzia',
    inne:     '',
};

// Te 5 plików trzeba dołożyć w modules/static/images/interview/ — nie istnieją jeszcze.
const INTERVIEW_DEFAULT_IMAGES = {
    redaktor: '/static/images/interview/redaktor.png',
    zawodnik: '/static/images/interview/zawodnik.png',
    trener:   '/static/images/interview/trener.png',
    sedzia:   '/static/images/interview/sedzia.png',
    inne:     '/static/images/interview/inne.png',
};

// Stan roboczy modala dodawania — żyje tylko między openInterviewAddModal()
// i closeInterviewAddModal()/confirmAddInterviewParticipant().
let _interviewDraft = null;
let _interviewSearchTimer = null;

// ── Budowa zakładki ──────────────────────────────────────────────────────

function buildInterviewTab(container, participants) {
    let resetBtn = document.createElement('button');
    resetBtn.type = 'button';
    resetBtn.textContent = 'RESET';
    resetBtn.ondblclick = resetInterviewParticipants;

    let table = document.createElement('table');
    table.id = 'interview-table';
    let tbody = document.createElement('tbody');
    tbody.id = 'interview-table-body';
    table.appendChild(tbody);

    let addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.textContent = 'DODAJ';
    addBtn.onclick = openInterviewAddModal;

    container.appendChild(resetBtn);
    container.appendChild(table);
    container.appendChild(addBtn);
    container.appendChild(buildInterviewModal());

    renderInterviewRows(participants || []);
}

function renderInterviewRows(participants) {
    let tbody = document.getElementById('interview-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    participants.forEach(p => {
        let tr = document.createElement('tr');
        let typeLabel = INTERVIEW_TYPE_LABELS[p.interview_type] || p.interview_type;
        if (p.team_short_name) {
            typeLabel += ` (${p.team_short_name})`;
        }
        tr.innerHTML = `
            <td>${p.name}</td>
            <td>${typeLabel}</td>
            <td><button type="button" class="event-btn interview-btn"
                style="background-color:${p.is_active ? 'green' : 'gray'}; color: white; font-weight: 700;"
                onclick="toggleInterviewParticipant(${p.id})">W</button></td>
            <td><button type="button" class="event-btn"
                style="background-color:red; color: white; font-weight: 700;"
                ondblclick="removeInterviewParticipant(${p.id})">X</button></td>
        `;
        tbody.appendChild(tr);
    });
}

socket.on('interview_participants_updated', data => {
    renderInterviewRows(data.participants || []);
});

// ── Akcje wiersza / RESET ────────────────────────────────────────────────

function resetInterviewParticipants() {
    socket.emit('reset_interview_participants', {});
}

function toggleInterviewParticipant(id) {
    socket.emit('toggle_interview_participant', { id: id });
}

function removeInterviewParticipant(id) {
    socket.emit('remove_interview_participant', { id: id });
}

// ── Modal dodawania ──────────────────────────────────────────────────────

function buildInterviewModal() {
    let overlay = document.createElement('div');
    overlay.id = 'interview-modal-overlay';
    overlay.className = 'interview-modal-overlay';
    overlay.style.display = 'none';
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeInterviewAddModal();
    });

    let modal = document.createElement('div');
    modal.id = 'interview-modal';
    modal.className = 'interview-modal';
    modal.addEventListener('click', (e) => e.stopPropagation());

    const typeButtons = Object.keys(INTERVIEW_TYPE_LABELS).map(type => `
        <button type="button" class="interview-type-btn" data-type="${type}"
            onclick="selectInterviewType('${type}')">${INTERVIEW_TYPE_LABELS[type]}</button>
    `).join('');

    modal.innerHTML = `
        <div id="interview-type-selector" class="interview-type-selector">${typeButtons}</div>
        <div class="interview-name-field">
            <input type="text" id="interview-name-input" placeholder="Imię i nazwisko"
                oninput="handleInterviewNameInput(this.value)" autocomplete="off">
            <div id="interview-name-suggestions" class="interview-name-suggestions" style="display:none;"></div>
        </div>
        <div id="interview-team-options" class="interview-team-options" style="display:none;">
            <label>
                <input type="checkbox" id="interview-use-crest" onchange="toggleInterviewTeamCrest(this.checked)">
                Użyj herbu drużyny jako zdjęcia
            </label>
            <div class="interview-description-source">
                <label><input type="radio" name="interview-desc-source" value="default" checked
                    onchange="selectInterviewDescriptionSource('default')"> Domyślny opis</label>
                <label><input type="radio" name="interview-desc-source" value="name"
                    onchange="selectInterviewDescriptionSource('name')"> Nazwa drużyny</label>
                <label><input type="radio" name="interview-desc-source" value="name_14"
                    onchange="selectInterviewDescriptionSource('name_14')"> Nazwa drużyny (skrócona)</label>
            </div>
        </div>
        <div class="interview-modal-actions">
            <button type="button" onclick="confirmAddInterviewParticipant()">Dodaj</button>
            <button type="button" onclick="closeInterviewAddModal()">Zamknij</button>
        </div>
    `;

    overlay.appendChild(modal);
    return overlay;
}

function openInterviewAddModal() {
    _interviewDraft = {
        interview_type: 'redaktor',
        name: '',
        description: INTERVIEW_DEFAULT_DESCRIPTIONS.redaktor,
        image_path: INTERVIEW_DEFAULT_IMAGES.redaktor,
        matched_player_id: null,
        matched_referee_id: null,
        matched_commentator_id: null,
        matched_team_id: null,
        use_team_crest: false,
        team_name: null,
        team_name_14: null,
        team_short_name: null,
        team_logo: null,
        description_source: 'default',
    };
    let overlay = document.getElementById('interview-modal-overlay');
    if (!overlay) return;
    document.getElementById('interview-name-input').value = '';
    document.getElementById('interview-name-suggestions').style.display = 'none';
    document.getElementById('interview-team-options').style.display = 'none';
    document.getElementById('interview-use-crest').checked = false;
    _highlightInterviewTypeButton('redaktor');
    overlay.style.display = 'flex';
}

function closeInterviewAddModal() {
    let overlay = document.getElementById('interview-modal-overlay');
    if (overlay) overlay.style.display = 'none';
    _interviewDraft = null;
}

function _highlightInterviewTypeButton(type) {
    // addClassName/removeClassName — modules/static/js/core/utils.js
    document.querySelectorAll('.interview-type-btn').forEach(btn => {
        if (btn.dataset.type === type) {
            addClassName(btn, 'active');
        } else {
            removeClassName(btn, 'active');
        }
    });
}

function selectInterviewType(type) {
    if (!_interviewDraft) return;
    _interviewDraft.interview_type = type;
    _interviewDraft.description = INTERVIEW_DEFAULT_DESCRIPTIONS[type] || '';
    _interviewDraft.image_path = INTERVIEW_DEFAULT_IMAGES[type] || '';
    _interviewDraft.matched_player_id = null;
    _interviewDraft.matched_referee_id = null;
    _interviewDraft.matched_commentator_id = null;
    _interviewDraft.matched_team_id = null;
    _interviewDraft.use_team_crest = false;
    _interviewDraft.description_source = 'default';
    _highlightInterviewTypeButton(type);
    document.getElementById('interview-team-options').style.display = 'none';
    document.getElementById('interview-use-crest').checked = false;
    document.getElementById('interview-name-suggestions').style.display = 'none';
    // Imię zostaje — zmiana typu nie czyści tego co operator już wpisał,
    // tylko odświeża domyślny opis/obrazek i filtr podpowiedzi.
}

// ── Podpowiedzi imienia/nazwiska (autocomplete) ─────────────────────────

function handleInterviewNameInput(value) {
    if (!_interviewDraft) return;
    _interviewDraft.name = value;

    // Dalsze wpisywanie po wyborze podpowiedzi = powrót do czystego wolnego
    // tekstu (czyści dopasowanie) — zgodnie ze specyfikacją: użytkownik może
    // sam wpisać imię i nazwisko i zignorować podpowiedzi.
    _interviewDraft.matched_player_id = null;
    _interviewDraft.matched_referee_id = null;
    _interviewDraft.matched_commentator_id = null;
    _interviewDraft.matched_team_id = null;
    _interviewDraft.use_team_crest = false;
    _interviewDraft.description = INTERVIEW_DEFAULT_DESCRIPTIONS[_interviewDraft.interview_type] || '';
    _interviewDraft.image_path = INTERVIEW_DEFAULT_IMAGES[_interviewDraft.interview_type] || '';
    document.getElementById('interview-team-options').style.display = 'none';

    clearTimeout(_interviewSearchTimer);
    let suggestionsEl = document.getElementById('interview-name-suggestions');
    if (!value || value.trim().length < 2) {
        suggestionsEl.style.display = 'none';
        return;
    }
    _interviewSearchTimer = setTimeout(() => {
        socket.emit('search_interview_person', {
            query: value,
            interview_type: _interviewDraft.interview_type,
        });
    }, 250);
}

socket.on('interview_person_results', data => {
    renderInterviewSuggestions(data.results || []);
});

function renderInterviewSuggestions(results) {
    let suggestionsEl = document.getElementById('interview-name-suggestions');
    if (!suggestionsEl) return;
    if (!results.length) {
        suggestionsEl.style.display = 'none';
        suggestionsEl.innerHTML = '';
        return;
    }
    suggestionsEl.innerHTML = results.map((r, idx) => `
        <div class="interview-suggestion" onclick="selectInterviewSuggestion(${idx})">${r.label}</div>
    `).join('');
    suggestionsEl.style.display = 'block';
    suggestionsEl._results = results;
}

function selectInterviewSuggestion(idx) {
    let suggestionsEl = document.getElementById('interview-name-suggestions');
    let results = suggestionsEl && suggestionsEl._results;
    if (!results || !results[idx] || !_interviewDraft) return;
    let r = results[idx];

    _interviewDraft.name = r.name;
    _interviewDraft.matched_player_id = r.matched_player_id || null;
    _interviewDraft.matched_referee_id = r.matched_referee_id || null;
    _interviewDraft.matched_commentator_id = r.matched_commentator_id || null;
    _interviewDraft.matched_team_id = r.matched_team_id || null;
    _interviewDraft.team_name = r.team_name || null;
    _interviewDraft.team_name_14 = r.team_name_14 || null;
    _interviewDraft.team_short_name = r.team_short_name || null;
    _interviewDraft.team_logo = r.team_logo || null;
    _interviewDraft.use_team_crest = false;
    _interviewDraft.description_source = 'default';
    _interviewDraft.description = INTERVIEW_DEFAULT_DESCRIPTIONS[_interviewDraft.interview_type] || '';
    _interviewDraft.image_path = INTERVIEW_DEFAULT_IMAGES[_interviewDraft.interview_type] || '';

    document.getElementById('interview-name-input').value = r.name;
    suggestionsEl.style.display = 'none';

    let teamOptions = document.getElementById('interview-team-options');
    let useCrestCheckbox = document.getElementById('interview-use-crest');
    let defaultDescRadio = document.querySelector('input[name="interview-desc-source"][value="default"]');
    if (_interviewDraft.matched_team_id) {
        teamOptions.style.display = 'block';
        if (useCrestCheckbox) useCrestCheckbox.checked = false;
        if (defaultDescRadio) defaultDescRadio.checked = true;
    } else {
        teamOptions.style.display = 'none';
    }
}

// ── Opcje drużynowe (herb / nazwa drużyny jako opis) ─────────────────────

function toggleInterviewTeamCrest(checked) {
    if (!_interviewDraft) return;
    _interviewDraft.use_team_crest = checked;
    _interviewDraft.image_path = (checked && _interviewDraft.team_logo)
        ? _interviewDraft.team_logo
        : INTERVIEW_DEFAULT_IMAGES[_interviewDraft.interview_type];
}

function selectInterviewDescriptionSource(source) {
    if (!_interviewDraft) return;
    _interviewDraft.description_source = source;
    if (source === 'name') {
        _interviewDraft.description = _interviewDraft.team_name || '';
    } else if (source === 'name_14') {
        _interviewDraft.description = _interviewDraft.team_name_14 || '';
    } else {
        _interviewDraft.description = INTERVIEW_DEFAULT_DESCRIPTIONS[_interviewDraft.interview_type] || '';
    }
}

// ── Zatwierdzenie ────────────────────────────────────────────────────────

function confirmAddInterviewParticipant() {
    if (!_interviewDraft) return;
    if (!_interviewDraft.name || !_interviewDraft.name.trim()) {
        alert('Wpisz imię i nazwisko.');
        return;
    }
    socket.emit('add_interview_participant', {
        interview_type:     _interviewDraft.interview_type,
        name:                _interviewDraft.name.trim(),
        description:         _interviewDraft.description,
        image_path:          _interviewDraft.image_path,
        matched_player_id:   _interviewDraft.matched_player_id,
        matched_referee_id:  _interviewDraft.matched_referee_id,
        matched_commentator_id: _interviewDraft.matched_commentator_id,
        matched_team_id:     _interviewDraft.matched_team_id,
        use_team_crest:      _interviewDraft.use_team_crest,
    });
    closeInterviewAddModal();
}
