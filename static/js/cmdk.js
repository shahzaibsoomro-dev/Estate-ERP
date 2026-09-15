import { SCREEN_META, visibleNav, canOpen, SCREEN_MODULE } from './sidebar.js';
import { can } from './session.js';
import { icon } from './icons.js';
import { esc } from './dom.js';

/** Quick actions: go to a screen, then click its primary button. */
const ACTIONS = [
  { label: 'New booking', screen: 'booking', ico: 'booking', action: 'add' },
  { label: 'New project', screen: 'projects', btn: 'btn-new-project', ico: 'plus' },
  { label: 'Add unit', screen: 'units', btn: 'btn-add-unit', ico: 'plus' },
  { label: 'Add customer', screen: 'customers', btn: 'btn-add-customer', ico: 'plus' },
  { label: 'Record customer payment', screen: 'recovery', btn: 'btn-rec-pay', ico: 'wallet' },
  { label: 'New purchase order', screen: 'procurement', btn: 'btn-new-po', ico: 'plus' },
  { label: 'Add vendor', screen: 'vendors', btn: 'btn-add-vendor', ico: 'plus' },
  { label: 'Daily site entry', screen: 'site', btn: 'btn-site-log', ico: 'plus' },
  { label: 'Add agent', screen: 'agents', btn: 'btn-add-agent', ico: 'plus' },
  { label: 'Add investor', screen: 'investors', btn: 'btn-add-investor', ico: 'plus' },
  { label: 'Generate customer document', screen: 'documents', btn: 'btn-gen-doc', ico: 'documents' },
  { label: 'Enable customer portal login', screen: 'access', ico: 'access' },
  { label: 'Add employee', screen: 'employees', btn: 'btn-new-emp', ico: 'plus' },
];

let items = [];
let sel = 0;
let goFn = () => {};

function allEntries() {
  const pages = visibleNav().flatMap((g) => g.items.map((it) => ({
    kind: 'Page', label: it.label, sub: g.label, screen: it.s, ico: it.s,
    hay: `${it.label} ${g.label} ${it.keywords || ''}`.toLowerCase(),
  })));
  const allowed = ACTIONS.filter((a) => canOpen(a.screen)
    && (SCREEN_MODULE[a.screen] ? can(SCREEN_MODULE[a.screen], a.action || (a.btn ? 'add' : 'view')) : true));
  const acts = allowed.map((a) => ({
    kind: 'Action', label: a.label, sub: SCREEN_META[a.screen]?.title || '', screen: a.screen, btn: a.btn, ico: a.ico,
    hay: `${a.label} ${a.screen}`.toLowerCase(),
  }));
  return [...acts, ...pages];
}

function render(q) {
  const query = q.trim().toLowerCase();
  const all = allEntries();
  items = query ? all.filter((e) => query.split(/\s+/).every((w) => e.hay.includes(w))) : all;
  sel = Math.min(sel, Math.max(items.length - 1, 0));
  const list = document.getElementById('cmdk-list');
  if (!items.length) {
    list.innerHTML = '<div class="cmdk-empty">No matching pages or actions</div>';
    return;
  }
  let lastKind = '';
  list.innerHTML = items.map((e, i) => {
    const head = e.kind !== lastKind ? `<div class="cmdk-sec">${e.kind === 'Page' ? 'Pages' : 'Quick actions'}</div>` : '';
    lastKind = e.kind;
    return `${head}<button type="button" class="cmdk-item ${i === sel ? 'sel' : ''}" data-i="${i}">
      <span class="cmdk-ico">${icon(e.ico, 16)}</span>
      <span class="cmdk-lbl">${esc(e.label)}</span>
      <span class="cmdk-sub">${esc(e.sub)}</span>
    </button>`;
  }).join('');
  list.querySelectorAll('.cmdk-item').forEach((b) => {
    b.addEventListener('click', () => run(items[+b.dataset.i]));
    b.addEventListener('mousemove', () => { if (sel !== +b.dataset.i) { sel = +b.dataset.i; highlight(); } });
  });
}

function highlight() {
  document.querySelectorAll('#cmdk-list .cmdk-item').forEach((b) => {
    const on = +b.dataset.i === sel;
    b.classList.toggle('sel', on);
    if (on) b.scrollIntoView({ block: 'nearest' });
  });
}

function run(entry) {
  if (!entry) return;
  close();
  goFn(entry.screen);
  if (entry.btn) setTimeout(() => document.getElementById(entry.btn)?.click(), 150);
}

export function openCmdk() {
  const bg = document.getElementById('cmdk');
  const input = document.getElementById('cmdk-input');
  if (!bg) return;
  bg.hidden = false;
  input.value = '';
  sel = 0;
  render('');
  setTimeout(() => input.focus(), 10);
}

function close() {
  const bg = document.getElementById('cmdk');
  if (bg) bg.hidden = true;
}

export function initCmdk(go) {
  goFn = go;
  const bg = document.getElementById('cmdk');
  const input = document.getElementById('cmdk-input');
  if (!bg || !input) return;
  document.getElementById('tb-search')?.addEventListener('click', openCmdk);
  bg.addEventListener('click', (e) => { if (e.target === bg) close(); });
  input.addEventListener('input', () => { sel = 0; render(input.value); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(sel + 1, items.length - 1); highlight(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(sel - 1, 0); highlight(); }
    else if (e.key === 'Enter') { e.preventDefault(); run(items[sel]); }
    else if (e.key === 'Escape') { close(); }
  });
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      if (bg.hidden) openCmdk(); else close();
    }
  });
}
