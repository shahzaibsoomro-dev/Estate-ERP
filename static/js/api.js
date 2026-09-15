import { $ } from './dom.js';
import { session, handleAuthFailure, friendlyError } from './session.js';

export function toast(msg, type) {
  const t = $('toast');
  if (!t) return;
  t.textContent = msg;
  t.style.background = type === 'error' ? '#DC2626' : '#0B1B2E';
  t.classList.add('show');
  clearTimeout(t._t);
  t._t = setTimeout(() => t.classList.remove('show'), 3000);
}

const SAFE = new Set(['GET', 'HEAD', 'OPTIONS']);

export async function api(path, opts = {}) {
  const method = (opts.method || 'GET').toUpperCase();
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (!SAFE.has(method) && session.csrf) headers['X-CSRF-Token'] = session.csrf;
  try {
    const r = await fetch(path, { ...opts, method, headers, credentials: 'same-origin' });
    if (!r.ok) {
      const txt = await r.text();
      let msg = txt.slice(0, 150);
      let detail = null;
      let action = null;
      try {
        const j = JSON.parse(txt);
        detail = j.detail;
        action = j.action;
        if (typeof j.detail === 'string') msg = j.detail;
        else if (Array.isArray(j.detail)) msg = j.detail.map((d) => d.msg).join('; ');
      } catch { /* plain text error */ }
      if (handleAuthFailure(r.status, detail)) throw new Error('Session ended');
      throw new Error(friendlyError(r.status, detail, action) || msg);
    }
    return await r.json();
  } catch (e) {
    if (e.message !== 'Session ended') toast('⚠ ' + e.message, 'error');
    console.error(e);
    throw e;
  }
}
