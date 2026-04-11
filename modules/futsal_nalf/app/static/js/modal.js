function openModal(modalContentId, modalID='modal') {
    const modal = document.getElementById(modalID);
    console.log(modalContentId);
    let content = document.getElementById(modalContentId);
    const contents = document.querySelectorAll('.modal-content');
    contents.forEach(cont => {
      addClassName(cont, 'invisible')
    });
    removeClassName(content, 'invisible');
	removeClassName(modal, 'invisible');
}

function closeModal(modalID='modal') {
  const modal = document.getElementById(modalID);
  const contents = document.querySelectorAll('.modal-content')|null;
  if(!contents==null){
    contents.forEach(cont => {
      addClassName(cont, 'invisible')
    });
  }
  addClassName(modal, 'invisible');
}