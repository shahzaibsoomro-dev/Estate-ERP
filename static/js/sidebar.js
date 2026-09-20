import { icon } from './icons.js';
import { esc } from './dom.js';
import { can, isAdmin } from './session.js';

/** Single source of truth for navigation: groups, items, titles. */
export const NAV = [
  { id: 'overview', label: 'Overview', items: [
    { s: 'dashboard', label: 'Dashboard' },
    { s: 'activity', label: 'Activity Log' },
  ] },
  { id: 'inventory', label: 'Inventory', items: [
    { s: 'projects', label: 'Projects' },
    { s: 'units', label: 'Unit Inventory' },
  ] },
  { id: 'sales', label: 'Sales & CRM', items: [
    { s: 'booking', label: 'New Booking', keywords: 'sell sale book' },
    { s: 'customers', label: 'Customers', keywords: 'clients buyers members' },
    { s: 'demand', label: 'Demand Notices' },
    { s: 'documents', label: 'Documents', keywords: 'templates letters statements allotment pdf' },
    { s: 'recovery', label: 'Recovery', badge: 'overdue-badge', keywords: 'overdue dues receivable' },
  ] },
  { id: 'construction', label: 'Construction', items: [
    { s: 'procurement', label: 'Procurement', keywords: 'purchase orders po' },
    { s: 'vendors', label: 'Vendors', keywords: 'suppliers' },
    { s: 'contractors', label: 'Contractors' },
    { s: 'inventory', label: 'Materials', keywords: 'stock inventory' },
    { s: 'site', label: 'Site Management', keywords: 'site logs progress' },
  ] },
  { id: 'planning', label: 'Planning', items: [
    { s: 'planning', label: 'Structure of Work', keywords: 'sow stages tasks gantt schedule timeline programme' },
    { s: 'boq', label: 'Bill of Quantities', keywords: 'boq material estimate quantities takeoff' },
    { s: 'budget', label: 'Budget', keywords: 'cost plan planned vs actual' },
  ] },
  { id: 'finance', label: 'Finance', items: [
    { s: 'accounts', label: 'Accounts', keywords: 'cashbook ledger' },
    { s: 'payplans', label: 'Pay Plans', keywords: 'installment template' },
    { s: 'reports', label: 'Reports', keywords: 'ageing sales' },
  ] },
  { id: 'stakeholders', label: 'Stakeholders', items: [
    { s: 'agents', label: 'Agents', keywords: 'brokers commission' },
    { s: 'investors', label: 'Investors' },
    { s: 'partners', label: 'Partners' },
    { s: 'parties', label: 'Parties', keywords: 'master ids search cnic person entity' },
  ] },
  { id: 'admin', label: 'Administration', items: [
    { s: 'employees', label: 'Employees & Access', keywords: 'staff team users roles permissions', adminOnly: true },
    { s: 'access', label: 'Customer Logins', keywords: 'owner portal accounts password' },
    { s: 'subscription', label: 'Subscription', keywords: 'plan billing renewal payment invoice', adminOnly: true },
    { s: 'portal', label: 'Portal Preview', keywords: 'customer portal' },
  ] },
];

/** screen id -> permission module (see backend/auth/permissions.py) */
export const SCREEN_MODULE = {
  dashboard: 'dashboard', activity: 'activity', projects: 'projects', units: 'units', booking: 'booking',
  customers: 'customers', demand: 'demand', documents: 'documents', recovery: 'recovery',
  procurement: 'procurement', vendors: 'vendors', contractors: 'contractors', inventory: 'inventory',
  site: 'site', accounts: 'accounts', planning: 'planning', boq: 'boq', budget: 'budget',
  payplans: 'payplans', reports: 'reports',
  agents: 'agents', investors: 'investors', partners: 'partners', parties: 'parties',
  access: 'customer_logins', portal: 'portal',
};
const ADMIN_ONLY = new Set(NAV.flatMap((g) => g.items.filter((i) => i.adminOnly).map((i) => i.s)));

/** Pages the signed-in user may open. */
export function canOpen(screen) {
  if (ADMIN_ONLY.has(screen)) return isAdmin();
  return can(SCREEN_MODULE[screen], 'view');
}

export function visibleNav() {
  return NAV.map((g) => ({ ...g, items: g.items.filter((i) => canOpen(i.s)) })).filter((g) => g.items.length);
}

/** screen id -> { title, crumb, group } */
export const SCREEN_META = {};
NAV.forEach((g) => g.items.forEach((it) => {
  SCREEN_META[it.s] = { title: it.label, crumb: g.label, group: g.id, keywords: it.keywords || '' };
}));

const LS_COLLAPSED_GROUPS = 'erp.sb.closedGroups';
const LS_RAIL = 'erp.sb.rail';

function lsGet(key, fallback) {
  try { const v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); } catch { return fallback; }
}
function lsSet(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch { /* storage unavailable */ }
}

let closedGroups = new Set(lsGet(LS_COLLAPSED_GROUPS, []));
const mobileMq = window.matchMedia('(max-width: 1024px)');

export function renderSidebar(onNavigate) {
  const host = document.getElementById('sb-nav');
  if (!host) return;
  host.innerHTML = visibleNav().map((g) => `
    <div class="sb-group ${closedGroups.has(g.id) ? 'closed' : ''}" data-group="${g.id}">
      <button type="button" class="sb-group-hd" aria-expanded="${!closedGroups.has(g.id)}">
        <span>${esc(g.label)}</span>${icon('chevron', 14, 'sb-chev')}
      </button>
      <div class="sb-group-body"><div class="sb-group-inner">
        ${g.items.map((it) => `
          <a href="#${it.s}" class="ni" data-s="${it.s}" data-label="${esc(it.label)}" title="${esc(it.label)}">
            <span class="ni-ico">${icon(it.s)}</span>
            <span class="ni-txt">${esc(it.label)}</span>
            ${it.badge ? `<span class="ni-badge" id="${it.badge}" hidden>0</span>` : ''}
          </a>`).join('')}
      </div></div>
    </div>`).join('');

  host.querySelectorAll('.sb-group-hd').forEach((hd) => {
    hd.addEventListener('click', () => {
      const grp = hd.parentElement;
      const id = grp.dataset.group;
      const closed = grp.classList.toggle('closed');
      hd.setAttribute('aria-expanded', String(!closed));
      if (closed) closedGroups.add(id); else closedGroups.delete(id);
      lsSet(LS_COLLAPSED_GROUPS, [...closedGroups]);
    });
  });

  host.querySelectorAll('.ni[data-s]').forEach((el) => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      onNavigate(el.dataset.s);
    });
  });

  // Badge: hide when zero
  const badge = document.getElementById('overdue-badge');
  if (badge) {
    new MutationObserver(() => {
      const n = parseInt(badge.textContent, 10);
      badge.hidden = !n;
    }).observe(badge, { childList: true, characterData: true, subtree: true });
  }

  initChrome();
  initSidebarSearch();
}

function initChrome() {
  const collapseBtn = document.getElementById('sb-collapse');
  const menuBtn = document.getElementById('tb-menu');
  const backdrop = document.getElementById('sb-backdrop');
  if (collapseBtn) collapseBtn.innerHTML = icon('collapse', 18);
  if (menuBtn) menuBtn.innerHTML = icon('menu', 20);
  const tbSearchIco = document.querySelector('.tb-search-ico');
  if (tbSearchIco) tbSearchIco.innerHTML = icon('search', 16);

  if (lsGet(LS_RAIL, false)) document.body.classList.add('sb-rail');

  collapseBtn?.addEventListener('click', () => {
    if (mobileMq.matches) { closeDrawer(); return; }
    const on = document.body.classList.toggle('sb-rail');
    lsSet(LS_RAIL, on);
    collapseBtn.title = on ? 'Expand sidebar' : 'Collapse sidebar';
  });
  menuBtn?.addEventListener('click', openDrawer);
  backdrop?.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });
  mobileMq.addEventListener?.('change', () => closeDrawer());
}

export function openDrawer() { document.body.classList.add('sb-open'); }
export function closeDrawer() { document.body.classList.remove('sb-open'); }

function initSidebarSearch() {
  const input = document.getElementById('sb-search');
  if (!input) return;
  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    document.querySelectorAll('#sb-nav .sb-group').forEach((g) => {
      let any = false;
      g.querySelectorAll('.ni').forEach((ni) => {
        const meta = SCREEN_META[ni.dataset.s];
        const hit = !q || `${meta.title} ${meta.crumb} ${meta.keywords}`.toLowerCase().includes(q);
        ni.hidden = !hit;
        any = any || hit;
      });
      g.hidden = !any;
      g.classList.toggle('searching', !!q);
    });
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const first = document.querySelector('#sb-nav .ni:not([hidden])');
      first?.click();
      input.value = '';
      input.dispatchEvent(new Event('input'));
    }
  });
}

/** Called by nav on every screen change. */
export function markActive(id) {
  document.querySelectorAll('#sb-nav .ni').forEach((n) => n.classList.toggle('active', n.dataset.s === id));
  const grp = SCREEN_META[id]?.group;
  const el = grp && document.querySelector(`#sb-nav .sb-group[data-group="${grp}"]`);
  if (el?.classList.contains('closed')) {
    el.classList.remove('closed');
    el.querySelector('.sb-group-hd')?.setAttribute('aria-expanded', 'true');
    closedGroups.delete(grp);
    lsSet(LS_COLLAPSED_GROUPS, [...closedGroups]);
  }
  if (mobileMq.matches) closeDrawer();
}
