import { $ } from './dom.js';
import { api, toast } from './api.js';
import { initModals, closeModal } from './modal.js';
import { initAppDialog } from './dialog.js';
import { initUnitFormEvents } from './unit-form.js';
import { goScreen, registerScreen } from './nav.js';
import { initProjectFilter, loadProjectFilterOptions, syncTopbar } from './project-filter.js';
import { loadDashboard } from './screens/dashboard.js';
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
registerScreen('site', loadSite);
registerScreen('accounts', loadAccounts);
registerScreen('agents', loadAgents);
registerScreen('investors', loadInvestors);
registerScreen('reports', () => {});
registerScreen('portal', loadPortal);

function initNavigation() {
  document.querySelectorAll('.ni[data-s]').forEach((el) => {
    el.addEventListener('click', () => goScreen(el.dataset.s));
  });
  $('tb-cta')?.addEventListener('click', () => goScreen('booking'));
}

function initGlobalHandlers() {
  document.querySelectorAll('[data-close-modal]').forEach((btn) => {
    btn.addEventListener('click', () => closeModal(btn.dataset.closeModal));
  });
}

async function init() {
  const safe = (label, fn) => {
    try { fn(); } catch (e) { console.error(label, e); }
  };
  safe('modals', initModals);
  safe('dialogs', initAppDialog);
  safe('nav', initNavigation);
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
  try {
    await refreshProjectSelects();
  } catch (e) {
    console.error('Failed to load projects for selects', e);
  }
  try { syncTopbar('dashboard'); } catch (e) { console.error(e); }
  goScreen('dashboard');
}

init().catch((e) => console.error('App init failed', e));

window.goScreen = goScreen;
window.toast = toast;
