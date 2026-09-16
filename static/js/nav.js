import { SCREEN_META, markActive, canOpen, visibleNav } from './sidebar.js';

const loaders = {};
let currentScreen = 'dashboard';

export function registerScreen(id, loader) {
  loaders[id] = loader;
}

export function getCurrentScreen() {
  return currentScreen;
}

export function reloadCurrentScreen() {
  if (loaders[currentScreen]) loaders[currentScreen]();
}

export function firstAllowedScreen() {
  return visibleNav()[0]?.items[0]?.s || null;
}

export function goScreen(id) {
  if (!canOpen(id)) {
    const fallback = firstAllowedScreen();
    if (!fallback || fallback === id) {
      document.querySelector('.content').innerHTML = '<div class="empty" style="margin-top:80px"><b>No pages assigned yet</b>Ask your company admin to give you access.</div>';
      return;
    }
    id = fallback;
  }
  currentScreen = id;
  document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
  document.getElementById('s-' + id)?.classList.add('active');
  markActive(id);
  const m = SCREEN_META[id] || { title: id, crumb: '' };
  const title = document.getElementById('tb-title');
  const crumb = document.getElementById('tb-crumb');
  if (title) title.textContent = m.title;
  if (crumb) crumb.textContent = m.crumb;
  document.title = `${m.title} · Haven Builders ERP`;
  if (location.hash !== '#' + id) history.replaceState(null, '', '#' + id);
  document.querySelector('.content')?.scrollTo({ top: 0 });
  import('./project-filter.js').then(({ syncTopbar }) => syncTopbar(id));
  if (loaders[id]) loaders[id]();
}
