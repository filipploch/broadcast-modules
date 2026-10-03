// Karta "MOTYWY" (/layouts/) — wybór motywu z bazy (tabela layouts).
// Wybór pustej pozycji = powrót do mechanizmu podstawowego.

function applyOverlayStylingClass() {
    const select = document.getElementById('overlay-styling-class-select');
    const layoutId = select.value;
    socket.emit('select_layout', { layout_id: layoutId || null });
}

socket.on('styling_class_applied', data => {
    const status = document.getElementById('overlay-styling-class-status');
    if (!status) return;
    if (data.success) {
        status.textContent = data.styling_class ? `Zastosowano: ${data.styling_class}` : 'Przywrócono podstawowy';
        status.style.color = 'green';
    } else {
        status.textContent = `Błąd: ${data.error}`;
        status.style.color = 'red';
    }
});

// Folder motywu znaleziony na dysku bez rekordu w bazie (patrz skan w
// list_layouts()) — tu tylko dopisujemy brakujący rekord, folder już
// istnieje, więc hub nie jest w to zaangażowany.
function registerExistingLayout(name) {
    socket.emit('register_layout', { name });
}

// Nowy motyw: pusty albo skopiowany z innego — obie ścieżki idą przez
// huba (hub/styling.go: handleCreateStylingClass), bo to on jest
// właścicielem zapisu w folderze style/.
function createLayout() {
    const nameInput = document.getElementById('new-layout-name');
    const sourceSelect = document.getElementById('new-layout-source');
    const name = (nameInput.value || '').trim();
    if (!name) return;
    socket.emit('create_layout', { name, source_layout_id: sourceSelect.value || null });
}

socket.on('layout_created', data => {
    if (data.success) {
        location.reload();
    } else {
        const status = document.getElementById('new-layout-status');
        if (status) {
            status.textContent = `Błąd: ${data.error}`;
            status.style.color = 'red';
        }
    }
});
