import { $ } from './dom.js';

export function toast(msg, type) {
  const t = $('toast');
  if (!t) return;
  t.textContent = msg;
  t.style.background = type === 'error' ? '#E53E3E' : '#091830';
  t.classList.add('show');
  clearTimeout(t._t);
  t._t = setTimeout(() => t.classList.remove('show'), 3000);
}

export async function api(path, opts = {}) {
  try {
    const r = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...opts,
    });
    if (!r.ok) {
      const txt = await r.text();
      let msg = txt.slice(0, 150);
      try {
        const j = JSON.parse(txt);
        if (typeof j.detail === 'string') msg = j.detail;
      } catch { /* plain text error */ }
      throw new Error(msg);
    }
    return await r.json();
  } catch (e) {
    toast('⚠ ' + e.message, 'error');
    console.error(e);
    throw e;
  }
}
