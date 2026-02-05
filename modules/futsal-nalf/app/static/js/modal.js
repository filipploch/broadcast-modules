function openModal(modalContentId) {
    const modal = document.getElementById('modal');
    let content = document.getElementById(modalContentId);
    const contents = document.querySelectorAll('.modal-content');

    contents.forEach(cont => {
	  addClassName(cont, 'nodisplayed')
	});

	removeClassName(content, 'nodisplayed');

	removeClassName(modal, 'invisible');
}

function closeModal() {
  const modal = document.getElementById('modal');
  const contents = document.querySelectorAll('.modal-content');

  contents.forEach(cont => {
    addClassName(cont, 'nodisplayed')
  });

  addClassName(modal, 'invisible');
}