const meta = {
  dashboard: ['Dashboard', 'Home / Overview'],
  projects: ['Projects', 'Home / Projects'],
  units: ['Unit Inventory', 'Projects / Units'],
  activity: ['Activity', 'Home / Activity'],
  booking: ['New Booking', 'Sales / New Booking'],
  demand: ['Demand Notices', 'Sales / Notices'],
  customers: ['Customers', 'Sales / Customers'],
  recovery: ['Recovery', 'Finance / Receivables'],
  procurement: ['Procurement', 'Operations / Purchase'],
  vendors: ['Vendors', 'Operations / Vendors'],
  contractors: ['Contractors', 'Operations / Contractors'],
  inventory: ['Inventory', 'Operations / Materials'],
  site: ['Site Management', 'Operations / Site'],
  accounts: ['Accounts', 'Finance / Cashbook'],
  budget: ['Budget', 'Finance / Budget'],
  payplans: ['Pay Plans', 'Finance / Pay Plans'],
  agents: ['Agents', 'Finance / Commissions'],
  investors: ['Investors', 'Finance / Investors'],
  partners: ['Partners', 'Finance / Partners'],
  parties: ['Parties', 'Finance / Master IDs'],
  reports: ['Reports', 'Finance / Reports'],
  portal: ['Customer Portal', 'Portal / Customer view'],
};

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

export function goScreen(id) {
  currentScreen = id;
  document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
  document.querySelectorAll('.ni').forEach((n) => n.classList.remove('active'));
  document.getElementById('s-' + id)?.classList.add('active');
  document.querySelector(`[data-s="${id}"]`)?.classList.add('active');
  const m = meta[id] || [id, ''];
  const title = document.getElementById('tb-title');
  const crumb = document.getElementById('tb-crumb');
  if (title) title.textContent = m[0];
  if (crumb) crumb.textContent = m[1];
  import('./project-filter.js').then(({ syncTopbar }) => syncTopbar(id));
  if (loaders[id]) loaders[id]();
}
