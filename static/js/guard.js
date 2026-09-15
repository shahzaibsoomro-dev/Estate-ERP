/**
 * UI-side permission hints. The server enforces every permission; this only hides
 * buttons the signed-in employee cannot use so they don't hit "permission denied".
 */
import { can, isAdmin, readOnly } from './session.js';
import { SCREEN_MODULE } from './sidebar.js';

const ADD_RX = /^\s*(\+|add\b|new\b|record\b|generate\b|daily entry|bulk)/i;
const EDIT_RX = /^\s*(edit|revise|transfer|release|update|mark|change|save|complete|hold|possession|status|enable|disable|reset)\b/i;
const DELETE_RX = /^\s*(delete|remove|cancel booking|cancel\b(?! *$)|revoke|void)\b/i;
const NEUTRAL_RX = /^\s*(view|open|details|preview|close|done|copy|back|cancel)\s*$/i;

function classify(btn) {
  if (btn.dataset.perm) return btn.dataset.perm;
  const text = (btn.textContent || '').trim();
  if (!text || NEUTRAL_RX.test(text)) return null;
  if (btn.classList.contains('danger') || DELETE_RX.test(text)) return 'delete';
  if (ADD_RX.test(text)) return 'add';
  if (EDIT_RX.test(text)) return 'edit';
  return null;
}

function applyTo(root, module) {
  if (isAdmin() && !readOnly()) return;
  root.querySelectorAll('button.btn, a.btn, .add-inst').forEach((btn) => {
    if (btn.closest('.modal-bg#app-dialog, .sb, .topbar, .cmdk, #temp-pw-modal')) return;
    const action = classify(btn);
    if (!action) return;
    const allowed = !readOnly() && can(module, action);
    if (!allowed) {
      btn.hidden = true;
      btn.dataset.permHidden = '1';
    } else if (btn.dataset.permHidden) {
      btn.hidden = false;
      delete btn.dataset.permHidden;
    }
  });
}

export function initGuard() {
  if (isAdmin() && !readOnly()) return;
  const run = () => {
    document.querySelectorAll('.screen').forEach((scr) => {
      const module = SCREEN_MODULE[scr.id.replace(/^s-/, '')];
      if (module) applyTo(scr, module);
    });
  };
  let pending = false;
  new MutationObserver(() => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; run(); });
  }).observe(document.querySelector('.content') || document.body, { childList: true, subtree: true });
  run();
}
