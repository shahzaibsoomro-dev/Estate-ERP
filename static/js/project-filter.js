import { $, esc } from './dom.js';
import { state } from './state.js';
import { getCurrentScreen, reloadCurrentScreen } from './nav.js';

/** Screens that show the project multi-select filter */
export const FILTER_SCREENS = new Set(['dashboard', 'recovery', 'demand', 'site', 'procurement', 'budget', 'inventory', 'contractors', 'partners', 'investors']);

/** Screens that show + New Booking in top bar */
export const BOOKING_CTA_SCREENS = new Set(['dashboard', 'units']);

let menuOpen = false;

export function initProjectFilter() {
  $('proj-filter-btn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleMenu();
  });
  document.addEventListener('click', () => closeMenu());
  $('proj-filter-menu')?.addEventListener('click', (e) => e.stopPropagation());

  $('pf-all')?.addEventListener('change', (e) => {
    if (e.target.checked) selectAllProjects();
    else if (state.selectedProjectIds.length === state.projects.length) {
      // unchecking All when all were selected → keep first project only
      selectProjects([state.projects[0]?.id].filter(Boolean));
    }
    renderProjectCheckboxes();
    applyFilterChange();
  });
}

function toggleMenu() {
  menuOpen = !menuOpen;
  $('proj-filter-menu')?.classList.toggle('open', menuOpen);
}

function closeMenu() {
  menuOpen = false;
  $('proj-filter-menu')?.classList.remove('open');
}

export function syncTopbar(screenId) {
  const showFilter = FILTER_SCREENS.has(screenId);
  const showBooking = BOOKING_CTA_SCREENS.has(screenId);
  $('proj-filter-wrap')?.toggleAttribute('hidden', !showFilter);
  $('tb-cta-wrap')?.toggleAttribute('hidden', !showBooking);
  if (showFilter) updateFilterLabel();
}

export function loadProjectFilterOptions(projects) {
  state.projects = projects;
  if (state.projectFilterAll) {
    state.selectedProjectIds = projects.map((p) => p.id);
  } else if (!state.selectedProjectIds.length && projects.length) {
    selectAllProjects(false);
  } else {
    state.selectedProjectIds = state.selectedProjectIds.filter((id) =>
      projects.some((p) => p.id === id));
    if (!state.selectedProjectIds.length && projects.length) selectAllProjects(false);
  }
  renderProjectCheckboxes();
  updateFilterLabel();
}

function renderProjectCheckboxes() {
  const list = $('pf-list');
  if (!list) return;
  const allChecked = state.projectFilterAll;
  if ($('pf-all')) $('pf-all').checked = allChecked;

  list.innerHTML = state.projects.map((p) => `
    <label class="pf-item">
      <input type="checkbox" data-pf-id="${p.id}" ${state.selectedProjectIds.includes(p.id) ? 'checked' : ''}>
      <span>${esc(p.name)}</span>
    </label>`).join('');

  list.querySelectorAll('[data-pf-id]').forEach((cb) => {
    cb.addEventListener('change', () => {
      const id = parseInt(cb.dataset.pfId, 10);
      let ids = [...state.selectedProjectIds];
      if (cb.checked) {
        if (!ids.includes(id)) ids.push(id);
      } else {
        ids = ids.filter((x) => x !== id);
      }
      if (!ids.length && state.projects.length) {
        cb.checked = true;
        toastNeedOne();
        return;
      }
      state.selectedProjectIds = ids;
      state.projectFilterAll = ids.length === state.projects.length;
      if ($('pf-all')) $('pf-all').checked = state.projectFilterAll;
      updateFilterLabel();
      applyFilterChange();
    });
  });
}

function toastNeedOne() {
  import('./api.js').then(({ toast }) => toast('Select at least one project', 'error'));
}

function selectAllProjects(apply = true) {
  state.projectFilterAll = true;
  state.selectedProjectIds = state.projects.map((p) => p.id);
  if ($('pf-all')) $('pf-all').checked = true;
  updateFilterLabel();
  if (apply) applyFilterChange();
}

export function selectProjects(ids) {
  state.projectFilterAll = state.projects.length > 0 && ids.length === state.projects.length;
  state.selectedProjectIds = [...ids];
  renderProjectCheckboxes();
  updateFilterLabel();
}

function updateFilterLabel() {
  const btn = $('proj-filter-btn');
  if (!btn) return;
  if (state.projectFilterAll || state.selectedProjectIds.length === state.projects.length) {
    btn.textContent = 'All Projects ▾';
  } else if (state.selectedProjectIds.length === 1) {
    const p = state.projects.find((x) => x.id === state.selectedProjectIds[0]);
    btn.textContent = `${p?.name || '1 Project'} ▾`;
  } else {
    btn.textContent = `${state.selectedProjectIds.length} Projects ▾`;
  }
}

let filterTimer = null;

function applyFilterChange() {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(() => {
    if (FILTER_SCREENS.has(getCurrentScreen())) reloadCurrentScreen();
  }, 250);
}

export function filterLabelShort() {
  if (state.projectFilterAll || state.selectedProjectIds.length === state.projects.length) {
    return 'All projects';
  }
  if (state.selectedProjectIds.length === 1) {
    return state.projects.find((p) => p.id === state.selectedProjectIds[0])?.name || '1 project';
  }
  return `${state.selectedProjectIds.length} projects`;
}

/** Build query string for project filter. Omits param when all projects selected. */
export function projectFilterQuery(extra = {}) {
  const p = new URLSearchParams();
  if (!state.projectFilterAll && state.selectedProjectIds.length
      && state.selectedProjectIds.length < state.projects.length) {
    p.set('project_ids', state.selectedProjectIds.join(','));
  }
  Object.entries(extra).forEach(([k, v]) => {
    if (v != null && v !== '') p.set(k, v);
  });
  const s = p.toString();
  return s ? `?${s}` : '';
}

export function activeProjectIds() {
  if (!state.projects.length) return [];
  if (state.projectFilterAll || state.selectedProjectIds.length >= state.projects.length) {
    return state.projects.map((p) => p.id);
  }
  return [...state.selectedProjectIds];
}

export function isMultiProjectView() {
  return activeProjectIds().length > 1;
}
