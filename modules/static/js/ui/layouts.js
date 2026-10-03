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
