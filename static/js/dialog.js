import { $ } from './dom.js';

let resolver = null;

function finish(value) {
  const bg = $('app-dialog');
  if (bg) bg.classList.remove('open');
  if (!document.querySelector('.modal-bg.open')) {
    document.body.classList.remove('modal-open');
  }
  const r = resolver;
  resolver = null;
  if (r) r(value);
}

function showDialog({ title, message, confirmLabel, cancelLabel, danger, alertOnly }) {
  return new Promise((resolve) => {
    if (resolver) finish(false);
    resolver = resolve;
    if ($('app-dialog-title')) $('app-dialog-title').textContent = title;
    if ($('app-dialog-body')) $('app-dialog-body').textContent = message;
    const ok = $('app-dialog-ok');
    const cancel = $('app-dialog-cancel');
    if (ok) {
      ok.textContent = confirmLabel;
      ok.className = danger ? 'btn danger' : 'btn primary';
    }
    if (cancel) {
      cancel.textContent = cancelLabel;
      cancel.hidden = !!alertOnly;
    }
    $('app-dialog')?.classList.add('open');
    document.body.classList.add('modal-open');
    ok?.focus();
  });
}

export function askConfirm(message, {
  title = 'Please confirm',
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
} = {}) {
  return showDialog({ title, message, confirmLabel, cancelLabel, danger, alertOnly: false });
}

export function askAlert(message, {
  title = 'Notice',
  okLabel = 'OK',
} = {}) {
  return showDialog({
    title,
    message,
    confirmLabel: okLabel,
    cancelLabel: 'Cancel',
    danger: false,
    alertOnly: true,
  });
}

export function initAppDialog() {
  $('app-dialog-ok')?.addEventListener('click', () => finish(true));
  $('app-dialog-cancel')?.addEventListener('click', () => finish(false));
  $('app-dialog')?.addEventListener('click', (e) => {
    if (e.target === $('app-dialog')) finish(false);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (!$('app-dialog')?.classList.contains('open')) return;
    e.preventDefault();
    finish(false);
  });
}
