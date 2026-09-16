import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { openModal, closeModal } from '../modal.js';
import { askConfirm } from '../dialog.js';
import { isAdmin, can } from '../session.js';
import { initials, avatarColor, waLink } from './dashboard.js';

let rows = [];
let tab = 'customers';

const when = (s) => {
  if (!s) return '<span class="muted">Never</span>';
  const d = new Date(`${s.replace(' ', 'T')}Z`);
  if (Number.isNaN(d.getTime())) return esc(s);
  return esc(d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }));
};

export function showTempPassword({ name, password, loginHint, phone }) {
  $('tp-intro').innerHTML = `Temporary password for <b>${esc(name)}</b>:`;
  $('tp-value').textContent = password;
  $('tp-login-hint').textContent = loginHint;
  const wa = waLink(phone, `Assalam o Alaikum ${name}, your Haven Builders owner portal is ready.\nSign in at ${location.origin}/login\n${loginHint}\nTemporary password: ${password}\nYou will be asked to choose your own password.`);
  const waBtn = $('btn-tp-wa');
  waBtn.hidden = !wa;
  waBtn.onclick = () => window.open(wa, '_blank', 'noopener');
  openModal('temp-pw-modal');
}

// ---------------------------------------------------------------- customers
function status(r) {
  if (!r.user_id) return '<span class="badge bg-grey">No login</span>';
  if (!r.is_active) return '<span class="badge bg-red">Disabled</span>';
  if (r.must_change_password) return '<span class="badge bg-yellow">Invite pending</span>';
  return '<span class="badge bg-green">Active</span>';
}

function renderStats() {
  const withLogin = rows.filter((r) => r.user_id);
  const active = withLogin.filter((r) => r.is_active && !r.must_change_password);
  const booked = rows.filter((r) => r.active_bookings > 0);
  const bookedNoLogin = booked.filter((r) => !r.user_id);
  $('acc-stats').innerHTML = [
    ['Customers with bookings', booked.length, 'var(--navy)'],
    ['Portal active', active.length, 'var(--success)'],
    ['Invites pending', withLogin.filter((r) => r.is_active && r.must_change_password).length, 'var(--warn)'],
    ['Booked, no login yet', bookedNoLogin.length, 'var(--blue)'],
  ].map(([l, v, c]) => `<div class="sm" style="color:${c}"><div class="sm-v">${v}</div><div class="sm-l">${l}</div></div>`).join('');
}

function renderCustomers() {
  const q = ($('acc-q').value || '').trim().toLowerCase();
  const f = $('acc-f').value;
  const list = rows.filter((r) => {
    if (f === 'active' && !(r.user_id && r.is_active)) return false;
    if (f === 'none' && r.user_id) return false;
    if (f === 'disabled' && !(r.user_id && !r.is_active)) return false;
    if (!q) return true;
    return [r.name, r.cnic, r.login_email, r.customer_email].some((v) => String(v || '').toLowerCase().includes(q));
  });
  $('acc-tbody').innerHTML = list.length ? list.map((r) => `
    <tr>
      <td><div class="cust-cell"><div class="av" style="background:${avatarColor(r.name)}">${esc(initials(r.name))}</div>
        <div><div class="td-b">${esc(r.name)}</div><div class="cust-sub">${esc(r.login_email || r.customer_email || 'No email on file')}</div></div></div></td>
      <td class="td-mono">${esc(r.cnic || '—')}</td>
      <td>${r.active_bookings ? `<span class="badge bg-blue">${r.active_bookings} active</span>` : '<span class="muted">None</span>'}</td>
      <td>${status(r)}</td>
      <td>${r.user_id ? when(r.last_login_at) : '—'}</td>
      <td>${!r.user_id
        ? (can('customer_logins', 'add') ? `<button type="button" class="btn sm ${r.active_bookings ? 'primary' : ''}" data-enable="${r.customer_id}">Enable portal</button>` : '<span class="muted">—</span>')
        : `<button type="button" class="btn sm" data-reset="${r.user_id}">Reset password</button>
           <button type="button" class="btn sm ${r.is_active ? 'danger' : ''}" data-toggle="${r.user_id}" data-active="${r.is_active ? 1 : 0}">${r.is_active ? 'Disable' : 'Enable'}</button>`}
      </td>
    </tr>`).join('')
    : '<tr><td colspan="6"><div class="empty"><b>No customers match</b>Try a different search or filter.</div></td></tr>';

  const tb = $('acc-tbody');
  tb.querySelectorAll('[data-enable]').forEach((b) => b.addEventListener('click', () => {
    const r = rows.find((x) => x.customer_id === +b.dataset.enable);
    $('pe-cid').value = r.customer_id;
    $('pe-name').textContent = r.name;
    $('pe-email').value = r.customer_email || '';
    openModal('portal-enable-modal');
    setTimeout(() => $('pe-email').focus(), 50);
  }));
  tb.querySelectorAll('[data-reset]').forEach((b) => b.addEventListener('click', async () => {
    const r = rows.find((x) => x.user_id === +b.dataset.reset);
    if (!await askConfirm(`Reset the portal password for ${r.name}? Their current password stops working and they will be signed out.`, { title: 'Reset password', confirmLabel: 'Reset' })) return;
    const d = await api(`/api/portal-access/${r.user_id}/reset-password`, { method: 'POST' });
    showTempPassword({ name: r.name, password: d.temporary_password, phone: r.phone,
      loginHint: `Sign in with ${r.login_email} or CNIC ${r.cnic || ''}`.trim() });
    loadCustomers();
  }));
  tb.querySelectorAll('[data-toggle]').forEach((b) => b.addEventListener('click', async () => {
    const r = rows.find((x) => x.user_id === +b.dataset.toggle);
    const enable = b.dataset.active !== '1';
    if (!enable && !await askConfirm(`Disable portal access for ${r.name}? They will be signed out immediately.`, { title: 'Disable access', confirmLabel: 'Disable', danger: true })) return;
    await api(`/api/portal-access/${r.user_id}/status`, { method: 'POST', body: JSON.stringify({ is_active: enable }) });
    toast(enable ? 'Portal access enabled' : 'Portal access disabled');
    loadCustomers();
  }));
}

async function loadCustomers() {
  rows = await api('/api/portal-access');
  renderStats();
  renderCustomers();
}

async function enablePortal() {
  const cid = +$('pe-cid').value;
  const email = $('pe-email').value.trim();
  if (!email) { toast('Enter an email address', 'error'); return; }
  const btn = $('btn-pe-save');
  btn.disabled = true;
  try {
    const d = await api('/api/portal-access', { method: 'POST', body: JSON.stringify({ customer_id: cid, email }) });
    closeModal('portal-enable-modal');
    const r = rows.find((x) => x.customer_id === cid) || {};
    showTempPassword({ name: d.user.name, password: d.temporary_password, phone: r.phone,
      loginHint: `Sign in with ${d.user.email}${r.cnic ? ` or CNIC ${r.cnic}` : ''}` });
    loadCustomers();
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------- activity
const EVENT = {
  'auth.login': ['Signed in', 'bg-green'],
  'auth.login_failed': ['Failed sign-in', 'bg-red'],
  'auth.logout': ['Signed out', 'bg-grey'],
  'auth.password_change': ['Password changed', 'bg-blue'],
  'user.password_reset': ['Password reset', 'bg-yellow'],
  'user.create': ['Account created', 'bg-blue'],
  'user.update': ['Account updated', 'bg-grey'],
  'user.unlock': ['Account unlocked', 'bg-blue'],
  'employee.access': ['Access changed', 'bg-purple'],
  'support.enter': ['Platform support opened your account', 'bg-orange'],
  'support.exit': ['Platform support left', 'bg-grey'],
};

async function loadActivity() {
  const list = await api('/api/company/activity?limit=200');
  $('activity-auth-tbody').innerHTML = list.map((a) => {
    const [label, cls] = EVENT[a.action] || [a.action, 'bg-grey'];
    let details = '';
    try {
      const d = JSON.parse(a.details || '{}');
      details = d.identifier ? `as ${d.identifier}` : d.email ? d.email
        : d.modules ? `${d.modules.length} pages · ${d.all_projects ? 'all projects' : `${(d.projects || []).length} project(s)`}`
        : d.role ? `role: ${d.role}` : '';
    } catch { /* ignore */ }
    return `<tr><td>${when(a.created_at)}</td><td><span class="badge ${cls}">${esc(label)}</span></td>
      <td>${a.email ? `<div class="td-b">${esc(a.name)}</div><div class="cust-sub">${esc(a.email)} · ${esc(a.role)}</div>` : '<span class="muted">Unknown account</span>'}</td>
      <td class="td-mono">${esc(a.ip || '—')}</td><td class="cust-sub">${esc(details)}</td></tr>`;
  }).join('') || '<tr><td colspan="5"><div class="empty">No activity yet</div></td></tr>';
}

// ---------------------------------------------------------------- tabs
function switchTab(next) {
  if (!isAdmin() && next !== 'customers') next = 'customers';
  tab = next;
  document.querySelectorAll('[data-atab]').forEach((b) => b.classList.toggle('active', b.dataset.atab === tab));
  ['customers', 'activity'].forEach((t) => { $(`atab-${t}`).hidden = t !== tab; });
  if (tab === 'customers') loadCustomers();
  if (tab === 'activity') loadActivity();
}

export function loadAccess() {
  document.querySelectorAll('#s-access [data-admin-only]').forEach((el) => { el.hidden = !isAdmin(); });
  switchTab(tab);
}

export function initAccessEvents() {
  document.querySelectorAll('[data-atab]').forEach((b) => b.addEventListener('click', () => switchTab(b.dataset.atab)));
  $('acc-q')?.addEventListener('input', renderCustomers);
  $('acc-f')?.addEventListener('change', renderCustomers);
  $('btn-pe-save')?.addEventListener('click', enablePortal);
  $('btn-tp-copy')?.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText($('tp-value').textContent);
      toast('Copied');
    } catch {
      toast('Copy failed — select the password and copy it manually', 'error');
    }
  });
}
