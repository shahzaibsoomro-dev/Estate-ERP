export function openModal(id) {
  document.getElementById(id)?.classList.add('open');
  document.body.classList.add('modal-open');
}

export function closeModal(id) {
  document.getElementById(id)?.classList.remove('open');
  if (!document.querySelector('.modal-bg.open')) {
    document.body.classList.remove('modal-open');
  }
}

export function initModals() {
  document.querySelectorAll('.modal-bg').forEach((bg) => {
    bg.addEventListener('click', (e) => {
      if (e.target === bg) {
        bg.classList.remove('open');
        if (!document.querySelector('.modal-bg.open')) {
          document.body.classList.remove('modal-open');
        }
      }
    });
  });
}
