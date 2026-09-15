import { icon } from './icons.js';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

document.querySelectorAll('[data-icon]').forEach((el) => { el.innerHTML = icon(el.dataset.icon, 18); });
document.querySelectorAll('[data-toggle]').forEach((b) => b.addEventListener('click', () => {
  const input = $(b.dataset.toggle);
  const show = input.type === 'password';
  input.type = show ? 'text' : 'password';
  b.innerHTML = icon(show ? 'eyeoff' : 'eye', 18);
}));

function strength(pw) {
  let s = 0;
  if (pw.length >= 10) s += 1;
  if (pw.length >= 14) s += 1;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s += 1;
  if (/\d/.test(pw)) s += 1;
  if (/[^A-Za-z0-9]/.test(pw)) s += 1;
  return s;
}
document.querySelectorAll('[data-meter]').forEach((m) => {
  $(m.dataset.meter).addEventListener('input', (e) => {
    const s = strength(e.target.value);
    m.style.width = `${(s / 5) * 100}%`;
    m.style.background = s <= 2 ? 'var(--red)' : s === 3 ? 'var(--amber)' : 'var(--green)';
  });
});

function localProblems(label, email, pw) {
  const out = [];
  if (pw.length < 10) out.push('at least 10 characters');
  if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) out.push('letters and numbers');
  const user = (email.split('@')[0] || '').toLowerCase();
  if (user.length >= 4 && pw.toLowerCase().includes(user)) out.push('not containing the email name');
  return out.length ? `${label} password needs ${out.join(', ')}.` : null;
}

function showError(msg) {
  $('setup-error').textContent = msg;
  $('setup-error').hidden = !msg;
  if (msg) $('setup-error').scrollIntoView({ block: 'center', behavior: 'smooth' });
}

$('admin-on').addEventListener('change', () => { $('admin-fields').hidden = !$('admin-on').checked; });

$('setup-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  showError('');
  const sa = { name: $('sa-name').value.trim(), email: $('sa-email').value.trim(), password: $('sa-pw').value };
  const wantAdmin = $('admin-on').checked;
  const ad = { name: $('ad-name').value.trim(), email: $('ad-email').value.trim(), password: $('ad-pw').value };
  if (!sa.name || !sa.email || !sa.password) { showError('Fill in all super admin fields.'); return; }
  if (wantAdmin && (!ad.name || !ad.email || !ad.password)) { showError('Fill in all company admin fields, or untick “Create a company admin account now”.'); return; }
  if (wantAdmin && ad.email.toLowerCase() === sa.email.toLowerCase()) { showError('Use a different email for the company admin.'); return; }
  const p1 = localProblems('Super admin', sa.email, sa.password);
  const p2 = wantAdmin ? localProblems('Admin', ad.email, ad.password) : null;
  if (p1 || p2) { showError(p1 || p2); return; }

  const btn = $('setup-btn');
  btn.disabled = true;
  btn.textContent = 'Creating…';
  try {
    const r = await fetch('/api/setup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ superadmin: sa, admin: wantAdmin ? ad : null, company_name: wantAdmin ? $('co-name').value.trim() : null }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const d = data.detail;
      throw new Error(typeof d === 'string' ? d : 'Please check the form and try again.');
    }
    $('setup-form').hidden = true;
    $('setup-result').innerHTML = `
      <div><span>Super admin → platform console</span><b>${esc(data.superadmin.email)}</b></div>
      ${data.admin ? `<div><span>Company admin → ERP</span><b>${esc(data.admin.email)}</b></div>` : ''}`;
    $('setup-success').hidden = false;
  } catch (err) {
    showError(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Create accounts';
  }
});

(async () => {
  try {
    const st = await (await fetch('/api/setup/status')).json();
    $('setup-loading').hidden = true;
    if (!st.needed) { $('setup-done').hidden = false; return; }
    if (!st.allowed_here) { $('setup-remote').hidden = false; return; }
    const c = st.company;
    if (c) {
      $('data-summary').textContent = `Found your data: ${c.projects} projects, ${c.units} units, ${c.customers} customers and ${c.bookings} active bookings.`;
      $('co-name').value = c.name || '';
    } else {
      $('data-summary').textContent = 'No company data found yet — you can add companies from the console later.';
      $('admin-step').hidden = true;
      $('admin-on').checked = false;
    }
    if (st.existing_admins?.length) {
      $('existing-admins').innerHTML = `This company already has an admin: <b>${st.existing_admins.map((a) => esc(a.email)).join(', ')}</b>. You can skip this step.`;
      $('existing-admins').hidden = false;
      $('admin-on').checked = false;
      $('admin-fields').hidden = true;
    }
    $('setup-form').hidden = false;
    $('sa-name').focus();
  } catch {
    $('setup-loading').textContent = 'Could not reach the server. Is it running?';
  }
})();
