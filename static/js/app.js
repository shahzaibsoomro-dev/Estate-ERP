import { $, esc } from './dom.js';
import { api, toast } from './api.js';
import { initModals, closeModal } from './modal.js';
import { initAppDialog } from './dialog.js';
import { initUnitFormEvents } from './unit-form.js';
import { goScreen, registerScreen } from './nav.js';
import { renderSidebar, SCREEN_META, canOpen } from './sidebar.js';
import { initCmdk } from './cmdk.js';
import { loadSession, logout, exitSupport, isAdmin, readOnly, session } from './session.js';
import { initGuard } from './guard.js';
import { loadEmployees, initEmployeeEvents } from './screens/employees.js';
import { loadSubscription } from './screens/subscription.js';
import { loadDocuments, initDocumentEvents } from './screens/documents.js';
import { loadAccess, initAccessEvents } from './screens/access.js';
import { initProjectFilter, loadProjectFilterOptions, syncTopbar } from './project-filter.js';
import { loadDashboard, initDashboardEvents } from './screens/dashboard.js';
import { loadProjects, initProjectEvents, refreshProjectSelects } from './screens/projects.js';
import { loadUnits, initUnitsFilters } from './screens/units.js';
import { initBooking, initBookingEvents } from './screens/booking.js';
import { loadDemand, loadCustomers, initCustomerEvents } from './screens/customers.js';
import { loadRecovery, initRecoveryEvents } from './screens/recovery.js';
import { loadProcurement, loadVendors, initOperationsEvents } from './screens/operations.js';
import { loadSite, initSiteEvents } from './screens/site.js';
import { loadAccounts, initAccountsEvents } from './screens/finance.js';
import { loadAgents, initAgentEvents } from './screens/agents.js';
import { initReportsEvents } from './screens/finance-extra.js';
import { loadPortal, initPortalEvents } from './screens/portal.js';
import { loadInvestors, initInvestorEvents } from './screens/investors.js';
import { loadPartners, initPartnerEvents } from './screens/partners.js';
import { loadParties, initPartyEvents } from './screens/parties.js';
import {
  loadContractors, initContractorEvents,
  loadInventory, initInventoryEvents,
  loadBudget, initBudgetEvents,
  loadPayPlans, initPayPlanEvents,
} from './screens/ops-extra.js';
import { loadActivity } from './screens/activity.js';

registerScreen('dashboard', loadDashboard);
registerScreen('projects', loadProjects);
registerScreen('units', loadUnits);
registerScreen('activity', loadActivity);
registerScreen('booking', () => initBooking());
registerScreen('demand', loadDemand);
registerScreen('customers', loadCustomers);
registerScreen('recovery', loadRecovery);
registerScreen('procurement', loadProcurement);
registerScreen('vendors', loadVendors);
registerScreen('contractors', loadContractors);
registerScreen('inventory', loadInventory);
registerScreen('site', loadSite);
registerScreen('accounts', loadAccounts);
registerScreen('budget', loadBudget);
registerScreen('payplans', loadPayPlans);
registerScreen('agents', loadAgents);
registerScreen('investors', loadInvestors);
registerScreen('partners', loadPartners);
registerScreen('parties', loadParties);
registerScreen('reports', () => {});
registerScreen('portal', loadPortal);
registerScreen('documents', loadDocuments);
registerScreen('access', loadAccess);
registerScreen('employees', loadEmployees);
registerScreen('subscription', loadSubscription);

function initNavigation() {
  renderSidebar(goScreen);
  initCmdk(goScreen);
  $('tb-cta')?.addEventListener('click', () => goScreen('booking'));
  if (!canOpen('booking') || readOnly()) $('tb-cta')?.remove();
}

function initGlobalHandlers() {
  document.querySelectorAll('[data-close-modal]').forEach((btn) => {
    btn.addEventListener('click', () => closeModal(btn.dataset.closeModal));
  });
}

const ROLE_LABEL = { superadmin: 'Platform support', admin: 'Admin', employee: 'Employee' };

function initAccountMenu(me) {
  const initialsOf = (n) => String(n || '?').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
  $('u-av').textContent = initialsOf(me.name);
  $('u-name').textContent = me.name;
  $('u-role').textContent = me.role === 'employee' && me.job_title ? me.job_title : (ROLE_LABEL[me.role] || me.role);
  const logoName = document.querySelector('.sb-logo-name');
  if (logoName && me.company) logoName.textContent = me.company.name;
  $('um-name').textContent = me.name;
  $('um-email').textContent = me.email;
  const btn = $('ucard');
  const menu = $('umenu');
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    menu.hidden = !menu.hidden;
    btn.setAttribute('aria-expanded', String(!menu.hidden));
  });
  document.addEventListener('click', () => { menu.hidden = true; btn.setAttribute('aria-expanded', 'false'); });
  menu.addEventListener('click', (e) => e.stopPropagation());
  $('btn-logout').addEventListener('click', logout);
  document.body.classList.toggle('is-admin', isAdmin());
  if (me.support_mode) {
    const exit = document.createElement('button');
    exit.type = 'button';
    exit.textContent = 'Back to platform console';
    exit.addEventListener('click', exitSupport);
    menu.insertBefore(exit, $('btn-logout'));
  }
}

function renderBanner(me) {
  const el = $('app-banner');
  const sub = me.subscription;
  let html = '';
  let tone = '';
  if (me.support_mode) {
    tone = 'support';
    html = `<b>Support mode</b> — you are inside <b>${esc(me.company.name)}</b> as platform support. Every action is logged and visible to the company admin. <button type="button" id="banner-exit">Exit support mode</button>`;
  } else if (sub && sub.state === 'expired') {
    tone = 'danger';
    html = '<b>Subscription expired.</b> The system is read-only — you can view everything, but adding or changing records is paused until the subscription is renewed.';
  } else if (sub && sub.state === 'grace') {
    tone = 'warn';
    html = `<b>Subscription payment overdue.</b> Everything keeps working until ${esc(sub.grace_ends)}. ${isAdmin() ? '<a href="#subscription">View subscription</a>' : 'Please let your admin know.'}`;
  } else if (sub && sub.warn && isAdmin()) {
    tone = 'info';
    html = `Your ${sub.state === 'trial' ? 'trial' : 'subscription'} ends in <b>${sub.days_left} day${sub.days_left === 1 ? '' : 's'}</b>. <a href="#subscription">View subscription</a>`;
  }
  if (!html) return;
  el.className = `app-banner ${tone}`;
  el.innerHTML = html;
  el.hidden = false;
  $('banner-exit')?.addEventListener('click', exitSupport);
}

async function init() {
  const me = await loadSession();
  if (!me) return;
  initAccountMenu(me);
  renderBanner(me);
  document.body.classList.toggle('read-only', readOnly());
  const safe = (label, fn) => {
    try { fn(); } catch (e) { console.error(label, e); }
  };
  safe('modals', initModals);
  safe('dialogs', initAppDialog);
  safe('nav', initNavigation);
  safe('dashboard', initDashboardEvents);
  safe('global', initGlobalHandlers);
  safe('projectFilter', initProjectFilter);
  safe('unitsFilters', initUnitsFilters);
  safe('bookingEvents', initBookingEvents);
  safe('customerEvents', initCustomerEvents);
  safe('recoveryEvents', initRecoveryEvents);
  safe('projectEvents', initProjectEvents);
  safe('unitForm', initUnitFormEvents);
  safe('operations', initOperationsEvents);
  safe('site', initSiteEvents);
  safe('accounts', initAccountsEvents);
  safe('agents', initAgentEvents);
  safe('reports', initReportsEvents);
  safe('portal', initPortalEvents);
  safe('investors', initInvestorEvents);
  safe('partners', initPartnerEvents);
  safe('parties', initPartyEvents);
  safe('contractors', initContractorEvents);
  safe('inventory', initInventoryEvents);
  safe('budget', initBudgetEvents);
  safe('payplans', initPayPlanEvents);
  safe('documents', initDocumentEvents);
  safe('access', initAccessEvents);
  safe('employees', initEmployeeEvents);
  safe('guard', initGuard);
  try {
    await refreshProjectSelects();
  } catch (e) {
    console.error('Failed to load projects for selects', e);
  }
  const start = location.hash.slice(1);
  const first = SCREEN_META[start] && canOpen(start) ? start : 'dashboard';
  try { syncTopbar(first); } catch (e) { console.error(e); }
  goScreen(first);
  window.addEventListener('hashchange', () => {
    const h = location.hash.slice(1);
    if (SCREEN_META[h]) goScreen(h);
  });
}

init().catch((e) => console.error('App init failed', e));

window.goScreen = goScreen;
window.toast = toast;
