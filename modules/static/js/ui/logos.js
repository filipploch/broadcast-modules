function getSelectedLogo() {
    const selected = document.querySelector('input[name="selected-logo"]:checked');
    const logoInput = document.getElementById('logo_path');
    if (selected) {
        const logoPath = selected.value;
        logoInput.value = logoPath;
        document.getElementById('selected-logo-preview').innerHTML = `
            <img src="/${logoPath}" alt="Wybrane logo"
            style="max-height: 100px; max-width: 100px; object-fit: contain;">
        `;
        closeModal();
    } else {
        alert('Wybierz logo!');
    }
}
