/* Platform console for super admins: companies, subscriptions, payments, plans, support access. */
import { icon } from './icons.js';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = (n) => `PKR ${Math.round(Number(n) || 0).toLocaleString('en-PK')}`;
const fdate = (s) => {
  if (!s) return '—';
  const d = new Date(`${String(s).slice(0, 10)}T00:00:00`);
  return Number.isNaN(d.getTime()) ? esc(s) : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
};
const fdt = (s) => {
  if (!s) return '<span class="muted">Never</span>';
  const d = new Date(`${String(s).replace(' ', 'T')}Z`);
  return Number.isNaN(d.getTime()) ? esc(s) : esc(d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }));
};
const today = () => new Date().toISOString().slice(0, 10);

let me = null;
let csrf = '';
let meta = { plans: [], payment_methods: [] };

const STATE_BADGE = { trial: 'bg-blue', active: 'bg-green', grace: 'bg-orange', expired: 'bg-red', suspended: 'bg-red', none: 'bg-grey' };
const STATE_SHORT = { trial: 'Trial', active: 'Active', grace: 'Grace period', expired: 'Expired', suspended: 'Suspended', none: 'No plan' };
const stateBadge = (st) => `<span class="badge ${STATE_BADGE[st.state] || 'bg-grey'}">${STATE_SHORT[st.state] || esc(st.state)}</span>`;

function toast(msg, type) {
  const t = $('toast');
  t.textContent = msg;
  t.style.background = type === 'error' ? '#DC2626' : '#0B1B2E';
  t.classList.add('show');
  clearTimeout(t._t);
  t._t = setTimeout(() => t.classList.remove('show'), 3200);
}

async function api(path, opts = {}) {
  const method = (opts.method || 'GET').toUpperCase();
  const headers = { 'Content-Type': 'application/json' };
  if (method !== 'GET') headers['X-CSRF-Token'] = csrf;
  const r = await fetch(path, { ...opts, method, headers, body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (r.status === 401) { location.replace('/login?reason=expired&next=/console'); throw new Error('Session ended'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = data.detail;
    const msg = typeof d === 'string' ? d : Array.isArray(d) ? d.map((x) => `${x.loc?.slice(-1)[0]}: ${x.msg}`).join('; ') : `Error ${r.status}`;
    throw new Error(msg);
  }
  return data;
}

function hydrateIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach((el) => { el.innerHTML = icon(el.dataset.icon, Number(el.dataset.size) || 18); });
}

// ------------------------------------------------------------ modal form helper
let submitHandler = null;

function field(f) {
  const id = `f-${f.name}`;
  const cls = f.full ? 'fg full' : 'fg';
  const hint = (extra = '') => {
    if (!f.hint && !f.liveHint && !extra) return '';
    return `<span class="fg-hint" id="${id}-hint">${extra || esc(f.hint || '')}</span>`;
  };
  if (f.type === 'section') return `<div class="form-sec">${esc(f.label)}</div>`;
  if (f.type === 'note') return `<p class="fg-hint full" style="margin:0 0 12px">${f.html}</p>`;
  if (f.type === 'plan-preview') return `<div class="plan-preview full" id="${id}"></div>`;
  if (f.type === 'select') {
    return `<div class="${cls}"><label for="${id}">${esc(f.label)}${f.required ? ' *' : ''}</label><select id="${id}" name="${f.name}">${
      f.options.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(f.value ?? '') ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>${hint()}</div>`;
  }
  if (f.type === 'checkbox') {
    return `<label class="check-row full"><input type="checkbox" id="${id}" name="${f.name}" ${f.value ? 'checked' : ''}> ${esc(f.label)}</label>`;
  }
  if (f.type === 'textarea') {
    return `<div class="${cls}"><label for="${id}">${esc(f.label)}</label><textarea id="${id}" name="${f.name}" maxlength="${f.max || 1000}" placeholder="${esc(f.placeholder || '')}">${esc(f.value || '')}</textarea>${hint()}</div>`;
  }
  const attrs = [
    f.min != null ? `min="${f.min}"` : '',
    f.max != null && f.type === 'number' ? `max="${f.max}"` : '',
    f.max != null && f.type !== 'number' ? `maxlength="${f.max}"` : '',
    f.placeholder ? `placeholder="${esc(f.placeholder)}"` : '',
    f.type === 'tel' ? 'inputmode="tel"' : '',
  ].filter(Boolean).join(' ');
  return `<div class="${cls}"><label for="${id}">${esc(f.label)}${f.required ? ' *' : ''}</label><input id="${id}" name="${f.name}" type="${f.type || 'text'}" value="${esc(f.value ?? '')}" ${attrs} autocomplete="off">${hint()}</div>`;
}

const SKIP_FIELDS = new Set(['section', 'note', 'plan-preview']);

function openForm({ title, fields, submit, onSubmit, width = 620, danger = false, onReady }) {
  $('cn-modal-title').textContent = title;
  $('cn-modal-box').style.maxWidth = `${width}px`;
  $('cn-form').innerHTML = `<div class="form-err" id="cn-err" hidden></div><div class="cn-form-grid">${fields.map(field).join('')}</div>
    <div class="modal-actions"><span style="flex:1"></span><button type="button" class="btn" id="cn-cancel">Cancel</button>
    <button type="submit" class="btn ${danger ? 'danger' : 'primary'}" id="cn-submit">${esc(submit)}</button></div>`;
  $('cn-cancel').onclick = closeForm;
  submitHandler = async () => {
    const values = {};
    fields.forEach((f) => {
      if (!f.name || SKIP_FIELDS.has(f.type)) return;
      const el = $(`f-${f.name}`);
      if (!el) return;
      if (f.type === 'checkbox') values[f.name] = el.checked;
      else if (f.type === 'number') values[f.name] = el.value === '' ? null : Number(el.value);
      else values[f.name] = el.value.trim() === '' ? null : el.value.trim();
    });
    const missing = fields.filter((f) => f.required && (values[f.name] == null || values[f.name] === ''));
    if (missing.length) { showErr(`Please fill in: ${missing.map((f) => f.label).join(', ')}`); return; }
    for (const f of fields) {
      const err = f.validate?.(values[f.name]);
      if (err) { showErr(err); return; }
    }
    $('cn-submit').disabled = true;
    try {
      await onSubmit(values);
    } catch (e) {
      showErr(e.message);
    } finally {
      $('cn-submit').disabled = false;
    }
  };
  $('cn-modal').classList.add('open');
  onReady?.(fields);
  setTimeout(() => $('cn-form').querySelector('input,select,textarea')?.focus(), 30);
}

function showErr(msg) {
  $('cn-err').textContent = msg;
  $('cn-err').hidden = false;
}

function closeForm() {
  $('cn-modal').classList.remove('open');
}

function showSecret({ title, name, password, email }) {
  $('cn-modal-title').textContent = title;
  $('cn-modal-box').style.maxWidth = '500px';
  $('cn-form').innerHTML = `
    <p style="margin-bottom:12px">One-time password for <b>${esc(name)}</b>:</p>
    <div class="temp-pw"><code id="secret">${esc(password)}</code><button type="button" class="btn sm" id="copy-secret">Copy</button></div>
    <ul class="tp-notes"><li>Shown <b>only once</b>. Share it privately.</li><li>Sign-in: <b>${esc(email)}</b> at ${esc(location.origin)}/login</li>
    <li>They must choose their own password at first sign-in.</li></ul>
    <div class="modal-actions"><span style="flex:1"></span><button type="button" class="btn primary" id="secret-done">Done</button></div>`;
  $('copy-secret').onclick = async () => {
    try { await navigator.clipboard.writeText(password); toast('Copied'); } catch { toast('Select and copy the password manually', 'error'); }
  };
  $('secret-done').onclick = closeForm;
  submitHandler = null;
  $('cn-modal').classList.add('open');
}

// ------------------------------------------------------------ views
function setTitle(title, crumb = 'Platform') {
  $('tb-title').textContent = title;
  $('tb-crumb').textContent = crumb;
  document.title = `${title} · Platform console`;
}

function planOptions(selected) {
  return meta.plans.filter((p) => p.is_active || p.id === selected).map((p) => [p.id, `${p.name} — ${money(p.price_monthly)}/mo`]);
}

const PK_AREA3 = new Set(['021', '022', '040', '041', '042', '043', '044', '046', '047', '048', '049',
  '051', '052', '053', '054', '055', '056', '057', '061', '062', '063', '064', '065', '068', '071', '081', '086', '091']);

function normalizePhone(raw) {
  const text = String(raw || '').trim();
  if (!text) return { value: null };
  if (/[A-Za-z]/.test(text)) return { error: 'Phone number cannot contain letters' };
  let plus = text.startsWith('+') || text.startsWith('00');
  let d = text.replace(/\D/g, '');
  if (text.startsWith('00')) { d = d.startsWith('00') ? d.slice(2) : d; plus = true; }
  const bad = 'Enter a Pakistani mobile (03XX-XXXXXXX), a landline, or an international number starting with +';
  if (!d || d.length < 10 || d.length > 15) return { error: bad };
  if (d.startsWith('92') && d.length >= 12) { d = `0${d.slice(2)}`; plus = false; }
  if (d.length === 10 && d.startsWith('3')) d = `0${d}`;
  if (d.startsWith('03')) {
    if (d.length !== 11) return { error: 'Pakistani mobiles are 11 digits, e.g. 0300-1234567' };
    return { value: `${d.slice(0, 4)}-${d.slice(4)}` };
  }
  if (d.startsWith('0') && d.length >= 10 && d.length <= 11) {
    const n = PK_AREA3.has(d.slice(0, 3)) ? 3 : 4;
    return { value: `${d.slice(0, n)}-${d.slice(n)}` };
  }
  if (plus && d.length >= 10 && d.length <= 15) return { value: `+${d}` };
  return { error: bad };
}

function phoneError(v) {
  return normalizePhone(v).error || null;
}

function bindPhone(name = 'contact_phone') {
  const el = $(`f-${name}`);
  const hint = $(`f-${name}-hint`);
  if (!el) return;
  const paint = () => {
    const raw = el.value.trim();
    if (!hint) return;
    if (!raw) {
      hint.textContent = 'Mobile 03XX-XXXXXXX, landline, or +country code';
      hint.className = 'fg-hint';
      return;
    }
    const r = normalizePhone(raw);
    hint.textContent = r.error || `Will be saved as ${r.value}`;
    hint.className = `fg-hint ${r.error ? 'phone-bad' : 'phone-ok'}`;
  };
  el.addEventListener('input', () => {
    el.value = el.value.replace(/[^\d+\-\s()]/g, '');
    paint();
  });
  el.addEventListener('blur', () => {
    const r = normalizePhone(el.value);
    if (r.value) el.value = r.value;
    paint();
  });
  paint();
}

function planPreviewHtml(plan, cycle, trialDays) {
  if (!plan) return '<span class="muted">Choose a plan to see limits and list price.</span>';
  const yearly = cycle === 'yearly';
  const list = yearly ? plan.price_yearly : plan.price_monthly;
  const staff = plan.max_employees == null ? 'Unlimited' : plan.max_employees;
  const projects = plan.max_projects == null ? 'Unlimited' : plan.max_projects;
  const save = (plan.price_monthly || 0) * 12 - (plan.price_yearly || 0);
  const trial = Number(trialDays);
  const trialNote = Number.isFinite(trial)
    ? (trial > 0 ? ` · ${trial}-day trial` : ' · no trial — billing starts today')
    : '';
  return `<div class="pp-name"><b>${esc(plan.name)}</b> · ${money(list)} / ${yearly ? 'year' : 'month'}${trialNote}</div>
    ${plan.description ? `<div class="pp-desc">${esc(plan.description)}</div>` : ''}
    <div class="pp-row"><span>Staff</span><b>${staff}</b><span>Projects</span><b>${projects}</b>
      ${yearly && save > 0 ? `<span>Yearly saving</span><b>${money(save)}</b>` : ''}</div>`;
}

function bindPlanPrice({ fillNow = false } = {}) {
  const planEl = $('f-plan_id');
  const cycleEl = $('f-billing_cycle');
  const amountEl = $('f-amount');
  const preview = $('f-plan_preview');
  const trialEl = $('f-trial_days');
  if (!planEl) return;
  const state = () => {
    const plan = meta.plans.find((p) => p.id === Number(planEl.value));
    const cycle = cycleEl?.value || 'monthly';
    return { plan, cycle, list: plan ? (cycle === 'yearly' ? plan.price_yearly : plan.price_monthly) : null };
  };
  const render = (overwriteAmount) => {
    const { plan, cycle, list } = state();
    if (preview) preview.innerHTML = planPreviewHtml(plan, cycle, trialEl?.value);
    if (overwriteAmount && amountEl && list != null) amountEl.value = list;
    const hint = $('f-amount-hint');
    if (hint && list != null && amountEl) {
      const cur = amountEl.value === '' ? null : Number(amountEl.value);
      hint.textContent = cur == null || cur === list
        ? 'Filled from the selected plan. Change it for a custom deal.'
        : `Custom price — list is ${money(list)} per ${cycle === 'yearly' ? 'year' : 'month'}.`;
    }
  };
  planEl.addEventListener('change', () => render(true));
  cycleEl?.addEventListener('change', () => render(true));
  amountEl?.addEventListener('input', () => render(false));
  trialEl?.addEventListener('input', () => render(false));
  render(fillNow);
}

function bindAdminFromContact() {
  const src = $('f-contact_name');
  const dest = $('f-admin_name');
  if (!src || !dest) return;
  src.addEventListener('blur', () => {
    if (!dest.value.trim() && src.value.trim()) dest.value = src.value.trim();
  });
}

function bindOpeningToggle() {
  const cb = $('f-record_opening_balance');
  const ids = ['opening_cash', 'opening_bank', 'opening_date'];
  const sync = () => {
    const on = !!cb?.checked;
    ids.forEach((n) => {
      const wrap = $(`f-${n}`)?.closest('.fg');
      if (wrap) wrap.hidden = !on;
    });
  };
  cb?.addEventListener('change', sync);
  sync();
}

function emailError(v) {
  if (!v) return null;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? null : 'Enter a valid email address';
}

async function viewOverview() {
  setTitle('Overview');
  const d = await api('/api/console/overview');
  meta.plans = d.plans;
  meta.payment_methods = d.payment_methods;
  const s = d.by_state;
  $('view').innerHTML = `
    <div class="cn-kpis">
      <div class="cn-kpi"><span>Companies</span><b>${d.companies}</b><div class="state-pills">${Object.entries(s).map(([k, v]) => `<span class="badge ${STATE_BADGE[k]}">${v} ${STATE_SHORT[k]}</span>`).join('')}</div></div>
      <div class="cn-kpi"><span>Monthly recurring revenue</span><b>${money(d.mrr)}</b><small>Active & grace subscriptions</small></div>
      <div class="cn-kpi"><span>Collected this month</span><b>${money(d.collected_this_month)}</b><small>Recorded payments</small></div>
      <div class="cn-kpi"><span>Needs attention</span><b>${(s.grace || 0) + (s.expired || 0) + (s.suspended || 0)}</b><small>Grace, expired or suspended</small></div>
    </div>
    <div class="row">
      <div class="col">
        <div class="card"><div class="card-hd"><div><div class="card-title">Renewals due (next 14 days)</div><div class="card-sub">Including trials and overdue accounts</div></div></div>
          <div class="tbl-wrap"><table><thead><tr><th>Company</th><th>Status</th><th>Ends</th><th style="text-align:right">Amount</th><th></th></tr></thead><tbody>
          ${d.renewals_due.length ? d.renewals_due.map((c) => `<tr>
            <td class="td-b"><a href="#company/${c.id}">${esc(c.name)}</a></td><td>${stateBadge(c.state)}</td>
            <td>${fdate(c.state.period_end)}<div class="cust-sub">${c.state.days_left >= 0 ? `${c.state.days_left} days left` : `${-c.state.days_left} days overdue`}</div></td>
            <td class="num" style="text-align:right">${money(c.amount)}<div class="cust-sub">per ${c.billing_cycle === 'yearly' ? 'year' : 'month'}</div></td>
            <td><button type="button" class="btn sm primary" data-pay="${c.id}">Record payment</button></td></tr>`).join('')
            : '<tr><td colspan="5"><div class="empty"><b>Nothing due</b>No renewals in the next two weeks.</div></td></tr>'}
          </tbody></table></div></div>
      </div>
      <div class="col">
        <div class="card"><div class="card-hd"><div class="card-title">Latest payments</div><a class="btn sm" href="#payments">All payments</a></div>
          <div class="tbl-wrap"><table><thead><tr><th>Company</th><th>Paid</th><th style="text-align:right">Amount</th></tr></thead><tbody>
          ${d.recent_payments.length ? d.recent_payments.map((p) => `<tr${p.voided_at ? ' style="opacity:.5"' : ''}>
            <td><div class="td-b">${esc(p.company_name)}</div><div class="cust-sub">${esc(p.receipt_no)} · ${esc(p.method)}</div></td>
            <td>${fdate(p.paid_on)}</td><td class="num td-b" style="text-align:right">${money(p.amount)}</td></tr>`).join('')
            : '<tr><td colspan="3"><div class="empty">No payments recorded yet</div></td></tr>'}
          </tbody></table></div></div>
      </div>
    </div>`;
  $('view').querySelectorAll('[data-pay]').forEach((b) => b.addEventListener('click', () => recordPayment(+b.dataset.pay)));
}

async function viewCompanies() {
  setTitle('Companies');
  const list = await api('/api/console/companies');
  $('view').innerHTML = `
    <div class="card filter-card"><div class="toolbar">
      <input type="search" id="co-q" placeholder="Search company, contact or city">
      <select id="co-f"><option value="">All statuses</option>${Object.entries(STATE_SHORT).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select>
    </div></div>
    <div class="card"><div class="tbl-wrap"><table>
      <thead><tr><th>Company</th><th>Plan</th><th>Status</th><th>Period ends</th><th>Users</th><th>Last staff sign-in</th><th style="text-align:right">Total paid</th><th></th></tr></thead>
      <tbody id="co-tbody"></tbody></table></div></div>`;
  const render = () => {
    const q = $('co-q').value.trim().toLowerCase();
    const f = $('co-f').value;
    const rows = list.filter((c) => (!f || c.subscription.state === f)
      && (!q || [c.name, c.contact_name, c.contact_email, c.contact_phone, c.city, c.address, c.slug].some((v) => String(v || '').toLowerCase().includes(q))));
    $('co-tbody').innerHTML = rows.length ? rows.map((c) => `<tr>
      <td><a class="td-b" href="#company/${c.id}">${esc(c.name)}</a><div class="cust-sub">${esc([c.contact_name, c.city].filter(Boolean).join(' · ') || c.slug)}</div></td>
      <td>${esc(c.plan_name || '—')}<div class="cust-sub">${c.amount != null ? `${money(c.amount)} / ${c.billing_cycle === 'yearly' ? 'yr' : 'mo'}` : ''}</div></td>
      <td>${stateBadge(c.subscription)}</td>
      <td>${fdate(c.current_period_end)}${c.subscription.days_left != null ? `<div class="cust-sub">${c.subscription.days_left >= 0 ? `${c.subscription.days_left} days left` : `${-c.subscription.days_left} days ago`}</div>` : ''}</td>
      <td>${c.admins} admin · ${c.employees} staff<div class="cust-sub">${c.customer_logins} owner logins</div></td>
      <td>${fdt(c.last_staff_login)}</td>
      <td class="num" style="text-align:right">${money(c.total_paid)}<div class="cust-sub">${c.last_paid_on ? `last ${fdate(c.last_paid_on)}` : 'no payments'}</div></td>
      <td><a class="btn sm" href="#company/${c.id}">Open</a></td></tr>`).join('')
      : '<tr><td colspan="8"><div class="empty"><b>No companies match</b></div></td></tr>';
  };
  $('co-q').addEventListener('input', render);
  $('co-f').addEventListener('change', render);
  render();
}

async function viewCompany(id) {
  const c = await api(`/api/console/companies/${id}`);
  setTitle(c.name, 'Companies');
  const s = c.subscription || {};
  const st = c.state;
  $('view').innerHTML = `
    <a class="back-link" href="#companies">← All companies</a>
    <div class="co-head">
      <div><h2>${esc(c.name)} ${stateBadge(st)}</h2><div class="card-sub">${esc(c.slug)} · since ${fdate(c.created_at)}${c.city ? ` · ${esc(c.city)}` : ''}</div></div>
      <div class="co-actions">
        <button type="button" class="btn" id="co-support" title="Open this company's ERP as support (logged)">Open workspace (support)</button>
        <button type="button" class="btn" id="co-edit">Edit details</button>
        <button type="button" class="btn ${c.status === 'active' ? 'danger' : 'primary'}" id="co-status">${c.status === 'active' ? 'Suspend' : 'Reactivate'}</button>
      </div>
    </div>
    <div class="row">
      <div class="col" style="flex:1.2">
        <div class="card">
          <div class="card-hd"><div class="card-title">Subscription</div>
            <div class="co-actions"><button type="button" class="btn sm" id="co-sub-edit">Change plan / dates</button><button type="button" class="btn sm primary" id="co-pay">Record payment</button></div></div>
          <div class="card-bd"><div class="kv">
            <div><span>Plan</span><b>${esc(s.plan_name || '—')}</b></div>
            <div><span>Price</span><b>${money(s.amount)} / ${s.billing_cycle === 'yearly' ? 'year' : 'month'}</b></div>
            <div><span>Status</span><b>${esc(st.label)}</b></div>
            <div><span>Period ends</span><b>${fdate(s.current_period_end)}</b></div>
            <div><span>Grace period</span><b>${s.grace_days ?? 0} days (to ${fdate(st.grace_ends)})</b></div>
            <div><span>Limits</span><b>${s.max_employees ?? '∞'} staff · ${s.max_projects ?? '∞'} projects</b></div>
          </div>${s.notes ? `<p class="fg-hint" style="margin-top:10px">${esc(s.notes)}</p>` : ''}</div>
        </div>
      </div>
      <div class="col">
        <div class="card">
          <div class="card-hd"><div class="card-title">Company</div></div>
          <div class="card-bd"><div class="kv">
            <div><span>Contact</span><b>${esc(c.contact_name || '—')}</b></div>
            <div><span>Phone</span><b>${esc(c.contact_phone || '—')}</b></div>
            <div><span>Email</span><b>${esc(c.contact_email || '—')}</b></div>
            <div><span>Address</span><b>${esc(c.address || '—')}</b></div>
            <div><span>Usage</span><b>${c.counts.projects} projects · ${c.counts.units} units</b></div>
            <div><span>Customers</span><b>${c.counts.customers} (${c.customer_logins} with portal)</b></div>
            <div><span>Active bookings</span><b>${c.counts.bookings}</b></div>
          </div>${c.notes ? `<p class="fg-hint" style="margin-top:10px">${esc(c.notes)}</p>` : ''}</div>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-hd"><div><div class="card-title">Admins & employees</div><div class="card-sub">Help users who are locked out or forgot their password</div></div>
        <button type="button" class="btn sm primary" id="co-add-admin">+ Add admin</button></div>
      <div class="tbl-wrap"><table><thead><tr><th>Name</th><th>Role</th><th>Status</th><th>Last sign-in</th><th>Actions</th></tr></thead><tbody>
      ${c.users.length ? c.users.map((u) => `<tr>
        <td><div class="td-b">${esc(u.name)}</div><div class="cust-sub">${esc(u.email)}</div></td>
        <td>${u.role === 'admin' ? '<span class="badge bg-purple">Admin</span>' : `<span class="badge bg-blue">Employee</span><div class="cust-sub">${esc(u.job_title || '')}</div>`}</td>
        <td>${u.is_active ? (u.must_change_password ? '<span class="badge bg-yellow">Invite pending</span>' : '<span class="badge bg-green">Active</span>') : '<span class="badge bg-red">Disabled</span>'} <span data-lock="${u.id}"></span></td>
        <td>${fdt(u.last_login_at)}</td>
        <td><button type="button" class="btn sm" data-reset="${u.id}">Reset password</button>
          <button type="button" class="btn sm" data-unlock="${u.id}">Unlock</button>
          <button type="button" class="btn sm" data-revoke="${u.id}">Sign out everywhere</button>
          <button type="button" class="btn sm ${u.is_active ? 'danger' : ''}" data-toggle="${u.id}">${u.is_active ? 'Disable' : 'Enable'}</button></td></tr>`).join('')
        : '<tr><td colspan="5"><div class="empty">No staff accounts</div></td></tr>'}
      </tbody></table></div>
    </div>
    <div class="card">
      <div class="card-hd"><div class="card-title">Subscription payments</div></div>
      <div class="tbl-wrap"><table><thead><tr><th>Receipt</th><th>Paid on</th><th>Method</th><th>Covers</th><th>Recorded by</th><th style="text-align:right">Amount</th><th></th></tr></thead><tbody>
      ${c.payments.length ? c.payments.map((p, i) => `<tr${p.voided_at ? ' style="opacity:.55"' : ''}>
        <td class="td-mono">${esc(p.receipt_no)}${p.voided_at ? `<div class="cust-sub">Voided: ${esc(p.void_reason)}</div>` : ''}</td>
        <td>${fdate(p.paid_on)}</td><td>${esc(p.method)}${p.reference ? `<div class="cust-sub">${esc(p.reference)}</div>` : ''}</td>
        <td>${fdate(p.period_start)} → ${fdate(p.period_end)}</td><td>${esc(p.recorded_by_name || '—')}</td>
        <td class="num td-b" style="text-align:right">${money(p.amount)}</td>
        <td>${!p.voided_at && i === c.payments.findIndex((x) => !x.voided_at) ? `<button type="button" class="btn sm danger" data-void="${p.id}">Void</button>` : ''}</td></tr>`).join('')
        : '<tr><td colspan="7"><div class="empty"><b>No payments yet</b></div></td></tr>'}
      </tbody></table></div>
    </div>
    <div class="card">
      <div class="card-hd"><div class="card-title">Recent activity</div><a class="btn sm" href="#activity/${c.id}">Full log</a></div>
      <div class="tbl-wrap"><table><tbody id="co-activity"><tr><td class="loading"><span class="spinner"></span></td></tr></tbody></table></div>
    </div>`;

  $('co-support').onclick = async () => {
    const r = await api(`/api/console/companies/${id}/support`, { method: 'POST' });
    location.href = r.home;
  };
  $('co-edit').onclick = () => openForm({
    title: `Edit ${c.name}`, submit: 'Save',
    fields: [
      { name: 'name', label: 'Company name', value: c.name, required: true, full: true },
      { name: 'contact_name', label: 'Contact person', value: c.contact_name },
      { name: 'contact_phone', label: 'Phone', type: 'tel', value: c.contact_phone, placeholder: '0300-1234567', max: 20, liveHint: true,
        hint: 'Mobile 03XX-XXXXXXX, landline, or +country code', validate: phoneError },
      { name: 'contact_email', label: 'Email', value: c.contact_email, type: 'email', validate: emailError },
      { name: 'city', label: 'City', value: c.city },
      { name: 'address', label: 'Address (letterheads & documents)', value: c.address, type: 'textarea', full: true, max: 300 },
      { name: 'notes', label: 'Internal notes', value: c.notes, type: 'textarea', full: true },
    ],
    onReady: () => bindPhone(),
    onSubmit: async (v) => { await api(`/api/console/companies/${id}`, { method: 'PATCH', body: v }); closeForm(); toast('Saved'); route(); },
  });
  $('co-status').onclick = () => {
    const suspend = c.status === 'active';
    openForm({
      title: suspend ? `Suspend ${c.name}?` : `Reactivate ${c.name}?`, submit: suspend ? 'Suspend' : 'Reactivate', danger: suspend, width: 480,
      fields: [{ type: 'note', html: suspend
        ? 'Admins and employees are signed out immediately and cannot sign in. Owners can still use their portal. Data is kept.'
        : 'Admins and employees will be able to sign in again.' }],
      onSubmit: async () => {
        await api(`/api/console/companies/${id}`, { method: 'PATCH', body: { status: suspend ? 'suspended' : 'active' } });
        closeForm(); toast(suspend ? 'Company suspended' : 'Company reactivated'); route();
      },
    });
  };
  $('co-sub-edit').onclick = () => openForm({
    title: 'Change subscription', submit: 'Save changes',
    fields: [
      { name: 'plan_id', label: 'Plan', type: 'select', options: planOptions(s.plan_id), value: s.plan_id, required: true, full: true },
      { name: 'plan_preview', type: 'plan-preview' },
      { name: 'billing_cycle', label: 'Billing cycle', type: 'select', options: [['monthly', 'Monthly'], ['yearly', 'Yearly']], value: s.billing_cycle },
      { name: 'amount', label: 'Agreed price per cycle (PKR)', type: 'number', min: 0, value: s.amount, liveHint: true,
        hint: 'Filled from the selected plan. Change it for a custom deal.' },
      { name: 'current_period_end', label: 'Current period ends', type: 'date', value: s.current_period_end },
      { name: 'grace_days', label: 'Grace days after expiry', type: 'number', min: 0, max: 90, value: s.grace_days,
        hint: 'Days after the period ends before the workspace becomes read-only' },
      { name: 'is_trial', label: 'This period is a free trial', type: 'checkbox', value: !!s.is_trial },
      { name: 'notes', label: 'Deal notes (discounts, agreements)', type: 'textarea', value: s.notes, full: true },
    ],
    onReady: () => bindPlanPrice({ fillNow: false }),
    onSubmit: async (v) => {
      v.plan_id = Number(v.plan_id);
      await api(`/api/console/companies/${id}/subscription`, { method: 'PUT', body: v });
      closeForm(); toast('Subscription updated'); route();
    },
  });
  $('co-pay').onclick = () => recordPayment(id, s);
  $('co-add-admin').onclick = () => openForm({
    title: `Add admin to ${c.name}`, submit: 'Create admin', width: 480,
    fields: [
      { name: 'name', label: 'Full name', required: true, full: true },
      { name: 'email', label: 'Email', type: 'email', required: true, full: true },
    ],
    onSubmit: async (v) => {
      const r = await api(`/api/console/companies/${id}/admins`, { method: 'POST', body: v });
      showSecret({ title: 'Admin created', name: r.user.name, password: r.temporary_password, email: r.user.email });
      route();
    },
  });
  const find = (uid) => c.users.find((u) => u.id === +uid);
  $('view').querySelectorAll('[data-reset]').forEach((b) => b.addEventListener('click', () => {
    const u = find(b.dataset.reset);
    openForm({
      title: `Reset password for ${u.name}?`, submit: 'Reset password', width: 480,
      fields: [{ type: 'note', html: 'A one-time password is generated. They are signed out everywhere and any sign-in lockout is cleared.' }],
      onSubmit: async () => {
        const r = await api(`/api/console/users/${u.id}/reset-password`, { method: 'POST' });
        showSecret({ title: 'Password reset', name: u.name, password: r.temporary_password, email: u.email });
        route();
      },
    });
  }));
  $('view').querySelectorAll('[data-unlock]').forEach((b) => b.addEventListener('click', async () => {
    await api(`/api/console/users/${b.dataset.unlock}/unlock`, { method: 'POST' });
    toast('Failed sign-in attempts cleared');
    route();
  }));
  $('view').querySelectorAll('[data-revoke]').forEach((b) => b.addEventListener('click', async () => {
    await api(`/api/console/users/${b.dataset.revoke}/revoke-sessions`, { method: 'POST' });
    toast('Signed out on all devices');
  }));
  $('view').querySelectorAll('[data-toggle]').forEach((b) => b.addEventListener('click', async () => {
    const u = find(b.dataset.toggle);
    await api(`/api/console/users/${u.id}/status`, { method: 'POST', body: { is_active: !u.is_active } });
    toast(u.is_active ? 'User disabled' : 'User enabled');
    route();
  }));
  $('view').querySelectorAll('[data-void]').forEach((b) => b.addEventListener('click', () => openForm({
    title: 'Void payment', submit: 'Void payment', danger: true, width: 480,
    fields: [
      { type: 'note', html: 'Voiding removes this payment and moves the period end back to where it was before it.' },
      { name: 'reason', label: 'Reason', required: true, full: true, placeholder: 'e.g. cheque bounced, entered twice' },
    ],
    onSubmit: async (v) => { await api(`/api/console/payments/${b.dataset.void}/void`, { method: 'POST', body: v }); closeForm(); toast('Payment voided'); route(); },
  })));
  // lock indicators + activity (non-blocking)
  c.users.forEach(async (u) => {
    try {
      const l = await api(`/api/console/users/${u.id}/locked`);
      const el = $('view').querySelector(`[data-lock="${u.id}"]`);
      if (l.locked && el) el.innerHTML = '<span class="badge bg-orange">Locked out</span>';
    } catch { /* ignore */ }
  });
  const acts = await api(`/api/console/activity?company_id=${id}&limit=12`);
  $('co-activity').innerHTML = activityRows(acts, false) || '<tr><td><div class="empty">No activity yet</div></td></tr>';
}

async function recordPayment(companyId, sub = null) {
  if (!sub) sub = (await api(`/api/console/companies/${companyId}`)).subscription;
  if (!meta.payment_methods.length) meta = { ...meta, ...(await api('/api/console/overview')) };
  openForm({
    title: 'Record subscription payment', submit: 'Record payment',
    fields: [
      { type: 'note', html: `Plan <b>${esc(sub.plan_name)}</b> at <b>${money(sub.amount)}</b> per ${sub.billing_cycle === 'yearly' ? 'year' : 'month'}. Current period ends <b>${fdate(sub.current_period_end)}</b>.` },
      { name: 'amount', label: 'Amount received (PKR)', type: 'number', min: 1, value: sub.amount, required: true },
      { name: 'periods', label: `Number of ${sub.billing_cycle === 'yearly' ? 'years' : 'months'} paid`, type: 'number', min: 1, value: 1, required: true },
      { name: 'paid_on', label: 'Payment date', type: 'date', value: today(), required: true },
      { name: 'method', label: 'Method', type: 'select', options: meta.payment_methods.map((m) => [m, m]), value: 'Bank transfer' },
      { name: 'reference', label: 'Reference / transaction ID', full: true },
      { name: 'notes', label: 'Notes', type: 'textarea', full: true },
    ],
    onSubmit: async (v) => {
      const p = await api(`/api/console/companies/${companyId}/payments`, { method: 'POST', body: v });
      closeForm();
      toast(`${p.receipt_no} recorded — paid through ${fdate(p.period_end)}`);
      route();
    },
  });
}

async function viewPayments() {
  setTitle('Subscription payments');
  const list = await api('/api/console/payments');
  const total = list.filter((p) => !p.voided_at).reduce((a, p) => a + p.amount, 0);
  $('view').innerHTML = `<div class="card"><div class="card-hd"><div><div class="card-title">All payments</div><div class="card-sub">${list.length} records · ${money(total)} received</div></div></div>
    <div class="tbl-wrap"><table><thead><tr><th>Receipt</th><th>Company</th><th>Paid on</th><th>Method</th><th>Covers</th><th>Recorded by</th><th style="text-align:right">Amount</th></tr></thead><tbody>
    ${list.length ? list.map((p) => `<tr${p.voided_at ? ' style="opacity:.5"' : ''}>
      <td class="td-mono">${esc(p.receipt_no)}${p.voided_at ? ' <span class="badge bg-grey">Voided</span>' : ''}</td>
      <td><a class="td-b" href="#company/${p.company_id}">${esc(p.company_name)}</a></td>
      <td>${fdate(p.paid_on)}</td><td>${esc(p.method)}${p.reference ? `<div class="cust-sub">${esc(p.reference)}</div>` : ''}</td>
      <td>${fdate(p.period_start)} → ${fdate(p.period_end)}</td><td>${esc(p.recorded_by_name || '—')}</td>
      <td class="num td-b" style="text-align:right">${money(p.amount)}</td></tr>`).join('')
      : '<tr><td colspan="7"><div class="empty"><b>No payments yet</b></div></td></tr>'}
    </tbody></table></div></div>`;
}

function planForm(p = null) {
  openForm({
    title: p ? `Edit ${p.name}` : 'New plan', submit: 'Save plan',
    fields: [
      { name: 'name', label: 'Plan name', value: p?.name, required: true },
      { name: 'is_active', label: 'Available for new subscriptions', type: 'checkbox', value: p ? !!p.is_active : true },
      { name: 'price_monthly', label: 'Monthly price (PKR)', type: 'number', min: 0, value: p?.price_monthly ?? 0 },
      { name: 'price_yearly', label: 'Yearly price (PKR)', type: 'number', min: 0, value: p?.price_yearly ?? 0 },
      { name: 'max_employees', label: 'Max employees', type: 'number', min: 0, value: p?.max_employees, hint: 'Leave empty for unlimited' },
      { name: 'max_projects', label: 'Max projects', type: 'number', min: 0, value: p?.max_projects, hint: 'Leave empty for unlimited' },
      { name: 'description', label: 'Description', full: true, value: p?.description },
    ],
    onSubmit: async (v) => {
      await api(p ? `/api/console/plans/${p.id}` : '/api/console/plans', { method: p ? 'PUT' : 'POST', body: v });
      closeForm(); toast('Plan saved'); route();
    },
  });
}

async function viewPlans() {
  setTitle('Plans');
  const plans = await api('/api/console/plans');
  meta.plans = plans;
  $('view').innerHTML = `<div class="page-hd"><div><p>Plans set default prices and limits. You can agree a custom price per company on its subscription.</p></div>
    <button type="button" class="btn primary" id="plan-new">+ New plan</button></div>
    <div class="plan-grid">${plans.map((p) => `<div class="plan-card">
      <div style="display:flex;justify-content:space-between;align-items:center"><h3>${esc(p.name)}</h3>
      <span class="badge ${p.is_active ? 'bg-green' : 'bg-grey'}">${p.is_active ? 'Active' : 'Hidden'}</span></div>
      <div class="plan-price">${money(p.price_monthly)} <span>/ month</span></div>
      <div class="cust-sub">${money(p.price_yearly)} / year</div>
      <p class="fg-hint">${esc(p.description || '')}</p>
      <div class="kv" style="margin:6px 0 10px"><div><span>Employees</span><b>${p.max_employees ?? 'Unlimited'}</b></div><div><span>Projects</span><b>${p.max_projects ?? 'Unlimited'}</b></div></div>
      <button type="button" class="btn sm" data-plan="${p.id}">Edit</button></div>`).join('')}</div>`;
  $('plan-new').onclick = () => planForm(null);
  $('view').querySelectorAll('[data-plan]').forEach((b) => b.addEventListener('click', () => planForm(plans.find((p) => p.id === +b.dataset.plan))));
}

async function viewTeam() {
  setTitle('Platform team');
  const list = await api('/api/console/superadmins');
  $('view').innerHTML = `<div class="page-hd"><div><p>Super admins can see every company, record payments and open any workspace in support mode.</p></div>
    <button type="button" class="btn primary" id="sa-new">+ Add super admin</button></div>
    <div class="card"><div class="tbl-wrap"><table><thead><tr><th>Name</th><th>Status</th><th>Last sign-in</th><th></th></tr></thead><tbody>
    ${list.map((u) => `<tr><td><div class="td-b">${esc(u.name)}${u.id === me.id ? ' <span class="muted">(you)</span>' : ''}</div><div class="cust-sub">${esc(u.email)}</div></td>
      <td>${u.is_active ? '<span class="badge bg-green">Active</span>' : '<span class="badge bg-red">Disabled</span>'}</td>
      <td>${fdt(u.last_login_at)}</td>
      <td>${u.id === me.id ? '' : `<button type="button" class="btn sm ${u.is_active ? 'danger' : ''}" data-sa="${u.id}" data-active="${u.is_active ? 1 : 0}">${u.is_active ? 'Disable' : 'Enable'}</button>`}</td></tr>`).join('')}
    </tbody></table></div></div>`;
  $('sa-new').onclick = () => openForm({
    title: 'Add super admin', submit: 'Create', width: 480,
    fields: [
      { type: 'note', html: 'Super admins have full access to every company. Only add trusted developers.' },
      { name: 'name', label: 'Full name', required: true, full: true },
      { name: 'email', label: 'Email', type: 'email', required: true, full: true },
    ],
    onSubmit: async (v) => {
      const r = await api('/api/console/superadmins', { method: 'POST', body: v });
      showSecret({ title: 'Super admin created', name: r.user.name, password: r.temporary_password, email: r.user.email });
      route();
    },
  });
  $('view').querySelectorAll('[data-sa]').forEach((b) => b.addEventListener('click', async () => {
    await api(`/api/console/superadmins/${b.dataset.sa}/status`, { method: 'POST', body: { is_active: b.dataset.active !== '1' } });
    route();
  }));
}

const ACTION_LABEL = {
  'auth.login': ['Signed in', 'bg-green'], 'auth.login_failed': ['Failed sign-in', 'bg-red'], 'auth.logout': ['Signed out', 'bg-grey'],
  'auth.password_change': ['Password changed', 'bg-blue'], 'user.password_reset': ['Password reset', 'bg-yellow'],
  'user.create': ['User created', 'bg-blue'], 'user.update': ['User updated', 'bg-grey'], 'user.unlock': ['User unlocked', 'bg-blue'],
  'employee.access': ['Access changed', 'bg-purple'], 'company.create': ['Company created', 'bg-green'],
  'company.update': ['Company updated', 'bg-grey'], 'company.migrate': ['Company migrated', 'bg-grey'],
  'subscription.update': ['Subscription changed', 'bg-purple'], 'payment.record': ['Payment recorded', 'bg-green'],
  'payment.void': ['Payment voided', 'bg-red'], 'plan.save': ['Plan saved', 'bg-grey'],
  'support.enter': ['Support session started', 'bg-orange'], 'support.exit': ['Support session ended', 'bg-grey'],
};

function activityRows(list, withCompany) {
  return list.map((a) => {
    const [label, cls] = ACTION_LABEL[a.action] || [a.action, 'bg-grey'];
    let det = '';
    try {
      const d = JSON.parse(a.details || '{}');
      det = Object.entries(d).filter(([, v]) => v != null && v !== '').slice(0, 4)
        .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.length : v}`).join(' · ');
    } catch { /* ignore */ }
    return `<tr><td>${fdt(a.created_at)}</td><td><span class="badge ${cls}">${esc(label)}</span></td>
      ${withCompany ? `<td>${a.company_id ? `<a href="#company/${a.company_id}">${esc(a.company_name)}</a>` : '<span class="muted">Platform</span>'}</td>` : ''}
      <td>${a.user_name ? `<div class="td-b">${esc(a.user_name)}</div><div class="cust-sub">${esc(a.user_role)}</div>` : '<span class="muted">—</span>'}</td>
      <td class="td-mono">${esc(a.ip || '')}</td><td class="cust-sub wrap">${esc(det)}</td></tr>`;
  }).join('');
}

async function viewActivity(companyId) {
  setTitle('Audit log');
  const list = await api(`/api/console/activity?limit=300${companyId ? `&company_id=${companyId}` : ''}`);
  $('view').innerHTML = `<div class="card"><div class="card-hd"><div class="card-title">${companyId ? 'Company activity' : 'All platform activity'}</div>
    ${companyId ? '<a class="btn sm" href="#activity">Show all</a>' : ''}</div>
    <div class="tbl-wrap"><table><thead><tr><th>When</th><th>Event</th><th>Company</th><th>By</th><th>IP</th><th>Details</th></tr></thead>
    <tbody>${activityRows(list, true) || '<tr><td colspan="6"><div class="empty">No activity</div></td></tr>'}</tbody></table></div></div>`;
}

function newCompany() {
  openForm({
    title: 'New company', submit: 'Create company', width: 720,
    fields: [
      { type: 'section', label: 'Company' },
      { name: 'name', label: 'Company name', required: true },
      { name: 'city', label: 'City' },
      { name: 'address', label: 'Address (letterheads & documents)', type: 'textarea', full: true, max: 300,
        placeholder: 'Office / site address printed on receipts and allotment letters' },
      { name: 'contact_name', label: 'Contact person' },
      { name: 'contact_email', label: 'Contact email', type: 'email', validate: emailError },
      { name: 'contact_phone', label: 'Phone', type: 'tel', full: true, placeholder: '0300-1234567', max: 20, liveHint: true,
        hint: 'Mobile 03XX-XXXXXXX, landline, or +country code', validate: phoneError },
      { type: 'section', label: 'Subscription' },
      { name: 'plan_id', label: 'Plan', type: 'select', options: planOptions(), value: meta.plans[0]?.id, required: true, full: true },
      { name: 'plan_preview', type: 'plan-preview' },
      { name: 'billing_cycle', label: 'Billing cycle', type: 'select', options: [['monthly', 'Monthly'], ['yearly', 'Yearly']], value: 'monthly' },
      { name: 'amount', label: 'Agreed price per cycle (PKR)', type: 'number', min: 0, liveHint: true,
        hint: 'Filled from the selected plan. Change it for a custom deal.' },
      { name: 'trial_days', label: 'Free trial (days)', type: 'number', min: 0, max: 90, value: 14,
        hint: '0 = start billing immediately' },
      { name: 'grace_days', label: 'Grace days after expiry', type: 'number', min: 0, max: 90, value: 7,
        hint: 'Days after the period ends before the workspace becomes read-only' },
      { name: 'subscription_notes', label: 'Deal notes (discount, custom terms)', type: 'textarea', full: true, max: 1000 },
      { name: 'seed_sample', label: 'Start with sample demo data', type: 'checkbox', value: false },
      { type: 'section', label: 'Opening cash (only if they already have money in hand)' },
      { name: 'record_opening_balance', label: 'Record current cash / bank for this company', type: 'checkbox', value: false },
      { name: 'opening_cash', label: 'Cash in hand (PKR)', type: 'number', min: 0, value: 0,
        hint: 'Leave unchecked above if they start from zero' },
      { name: 'opening_bank', label: 'Bank balance (PKR)', type: 'number', min: 0, value: 0 },
      { name: 'opening_date', label: 'As of date', type: 'date', value: today() },
      { type: 'section', label: 'First admin account' },
      { name: 'admin_name', label: 'Admin full name', required: true },
      { name: 'admin_email', label: 'Admin email', type: 'email', required: true, validate: emailError },
    ],
    onReady: () => {
      bindPhone();
      bindPlanPrice({ fillNow: true });
      bindAdminFromContact();
      bindOpeningToggle();
    },
    onSubmit: async (v) => {
      v.plan_id = Number(v.plan_id);
      if (v.trial_days == null) v.trial_days = 0;
      if (v.grace_days == null) v.grace_days = 7;
      if (!v.record_opening_balance) {
        delete v.opening_cash;
        delete v.opening_bank;
        delete v.opening_date;
      }
      const r = await api('/api/console/companies', { method: 'POST', body: v });
      showSecret({ title: `${r.company.name} created`, name: r.admin.name, password: r.temporary_password, email: r.admin.email });
      location.hash = `company/${r.company.id}`;
    },
  });
}

// ------------------------------------------------------------ routing & chrome
async function route() {
  const [view, arg] = (location.hash.slice(1) || 'overview').split('/');
  document.querySelectorAll('#cn-nav .ni').forEach((n) => n.classList.toggle('active', n.dataset.v === view || (view === 'company' && n.dataset.v === 'companies')));
  document.body.classList.remove('sb-open');
  try {
    if (view === 'companies') await viewCompanies();
    else if (view === 'company' && arg) await viewCompany(+arg);
    else if (view === 'payments') await viewPayments();
    else if (view === 'plans') await viewPlans();
    else if (view === 'team') await viewTeam();
    else if (view === 'activity') await viewActivity(arg ? +arg : null);
    else await viewOverview();
  } catch (e) {
    if (e.message !== 'Session ended') {
      $('view').innerHTML = `<div class="empty"><b>Could not load this page</b>${esc(e.message)}</div>`;
    }
  }
}

async function init() {
  hydrateIcons();
  $('sb-close').innerHTML = icon('collapse', 18);
  const r = await fetch('/api/auth/me');
  if (r.status === 401) { location.replace('/login?next=/console'); return; }
  me = await r.json();
  if (me.must_change_password) { location.replace('/account/password'); return; }
  if (me.role !== 'superadmin') { location.replace(me.home); return; }
  if (me.support_mode) {
    // Coming back from a company workspace: leave support mode first.
    await fetch('/api/auth/exit-support', { method: 'POST', headers: { 'X-CSRF-Token': me.csrf_token } });
  }
  csrf = me.csrf_token;
  $('u-av').textContent = String(me.name || '?').split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
  $('u-name').textContent = me.name;
  $('um-name').textContent = me.name;
  $('um-email').textContent = me.email;
  $('ucard').addEventListener('click', (e) => { e.stopPropagation(); $('umenu').hidden = !$('umenu').hidden; });
  document.addEventListener('click', () => { $('umenu').hidden = true; });
  $('btn-logout').addEventListener('click', async () => {
    try { await api('/api/auth/logout', { method: 'POST' }); } finally { location.replace('/login?reason=signedout'); }
  });
  $('tb-menu').addEventListener('click', () => document.body.classList.add('sb-open'));
  $('sb-backdrop').addEventListener('click', () => document.body.classList.remove('sb-open'));
  $('sb-close').addEventListener('click', () => document.body.classList.toggle(matchMedia('(max-width:1024px)').matches ? 'sb-open' : 'sb-rail'));
  $('cn-modal-x').addEventListener('click', closeForm);
  $('cn-modal').addEventListener('click', (e) => { if (e.target === $('cn-modal')) closeForm(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeForm(); });
  $('cn-form').addEventListener('submit', (e) => { e.preventDefault(); submitHandler?.(); });
  $('btn-new-company').addEventListener('click', async () => {
    if (!meta.plans.length) meta = { ...meta, ...(await api('/api/console/overview')) };
    newCompany();
  });
  window.addEventListener('hashchange', route);
  route();
}

init();
