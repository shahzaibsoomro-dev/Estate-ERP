import { icon } from './icons.js';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = (n) => `PKR ${Math.round(Number(n) || 0).toLocaleString('en-PK')}`;
const moneyShort = (n) => {
  n = Number(n) || 0;
  if (n >= 10000000) return `PKR ${(n / 10000000).toFixed(2)} Cr`;
  if (n >= 100000) return `PKR ${(n / 100000).toFixed(1)} Lac`;
  return money(n);
};
const fdate = (s) => {
  if (!s) return '—';
  const d = new Date(`${String(s).slice(0, 10)}T00:00:00`);
  return Number.isNaN(d.getTime()) ? String(s) : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
};

let me = null;
let csrf = '';
let data = null;
let docs = [];
let bookingId = null;
let planFilter = 'all';

const STATUS = {
  paid: ['Paid', 'b-green'],
  partial: ['Partly paid', 'b-orange'],
  overdue: ['Overdue', 'b-red'],
  pending: ['Upcoming', 'b-grey'],
  scheduled: ['On milestone', 'b-blue'],
  cancelled: ['Cancelled', 'b-grey'],
};
const badge = (s) => {
  const [l, c] = STATUS[String(s || '').toLowerCase()] || [s || '—', 'b-grey'];
  return `<span class="badge ${c}">${esc(l)}</span>`;
};

function hydrateIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach((el) => { el.innerHTML = icon(el.dataset.icon, Number(el.dataset.size) || 20); });
}

async function getJSON(url) {
  const r = await fetch(url);
  if (r.status === 401) { location.replace('/login?reason=expired&next=/portal'); throw new Error('auth'); }
  if (r.status === 403) {
    const d = await r.json().catch(() => ({}));
    if (d.detail === 'password_change_required') location.replace('/account/password');
    else location.replace('/login');
    throw new Error('forbidden');
  }
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

const booking = () => data?.bookings.find((b) => b.id === bookingId);
const liveInstallments = (b) => (b?.installments || []).filter((i) => i.status !== 'cancelled');

function nextDue(b) {
  return liveInstallments(b)
    .filter((i) => ['pending', 'partial', 'overdue'].includes(i.status) && (i.remaining_amount || 0) > 0)
    .sort((a, c) => String(a.due_date).localeCompare(String(c.due_date)))[0];
}

function ring(pct) {
  const r = 50;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.min(100, Math.max(0, pct)) / 100);
  return `<svg class="ring" viewBox="0 0 120 120" role="img" aria-label="${pct}% paid">
    <circle cx="60" cy="60" r="${r}" fill="none" stroke="#EDF1F6" stroke-width="12"/>
    <circle cx="60" cy="60" r="${r}" fill="none" stroke="#2563EB" stroke-width="12" stroke-linecap="round"
      stroke-dasharray="${c}" stroke-dashoffset="${off}" transform="rotate(-90 60 60)"/>
    <text x="60" y="58" text-anchor="middle" font-size="21" font-weight="700" fill="#0B1B2E">${pct}%</text>
    <text x="60" y="78" text-anchor="middle" font-size="11" fill="#5B6B82">paid</text></svg>`;
}

function emptyState(ico, title, text) {
  return `<div class="empty">${icon(ico, 36)}<b>${esc(title)}</b>${esc(text)}</div>`;
}

// ------------------------------------------------------------------ views
function viewOverview(b) {
  const s = b.summary;
  const nd = nextDue(b);
  const overdue = liveInstallments(b).filter((i) => i.status === 'overdue');
  const overdueAmt = overdue.reduce((a, i) => a + (i.remaining_amount || 0), 0);
  const u = b.unit || {};
  const typeLine = [u.unit_type, u.residential_type].filter(Boolean).join(' · ');
  const scheduledLeft = liveInstallments(b).reduce((a, i) => a + (i.remaining_amount || 0), 0);
  const unscheduled = Math.max(0, (s.outstanding || 0) - scheduledLeft);
  return `
    ${unscheduled > 0 ? `<div class="alert alert-info">${icon('clock', 18)}<div><b>${money(unscheduled)}</b> of your balance is not yet on an installment schedule. Our office will confirm when it becomes due.</div></div>` : ''}
    ${overdueAmt > 0 ? `<div class="alert alert-error">${icon('alert', 18)}<div><b>${money(overdueAmt)} is overdue</b> across ${overdue.length} installment${overdue.length > 1 ? 's' : ''}. Please contact our office or pay at your earliest convenience.</div></div>` : ''}
    <div class="kpis">
      <div class="kpi hl"><span>Next payment</span><b>${nd ? money(nd.remaining_amount) : '—'}</b><small>${nd ? `Due ${fdate(nd.due_date)}` : 'Nothing due right now'}</small></div>
      <div class="kpi"><span>Total paid</span><b>${moneyShort(s.total_paid)}</b><small>${s.pct_paid}% of sale price</small></div>
      <div class="kpi"><span>Balance</span><b>${moneyShort(s.outstanding)}</b><small>Remaining on this unit</small></div>
      <div class="kpi"><span>Sale price</span><b>${moneyShort(s.sale_price)}</b><small>Booked ${fdate(b.booking_date)}</small></div>
    </div>
    <div class="grid-2">
      <div class="card">
        <div class="card-hd"><h2>Payment progress</h2><a href="#plan" class="btn btn-light btn-sm">View full plan</a></div>
        <div class="card-bd pay-prog">
          ${ring(s.pct_paid)}
          <dl>
            <dt>Sale price</dt><dd>${money(s.sale_price)}</dd>
            <dt>Paid so far</dt><dd style="color:var(--green)">${money(s.total_paid)}</dd>
            <dt>Balance</dt><dd>${money(s.outstanding)}</dd>
            <dt>Overdue</dt><dd style="color:${overdueAmt ? 'var(--red)' : 'inherit'}">${money(overdueAmt)}</dd>
            <dt>Installments paid</dt><dd>${liveInstallments(b).filter((i) => i.status === 'paid').length} / ${liveInstallments(b).length}</dd>
          </dl>
        </div>
      </div>
      <div class="card">
        <div class="card-hd"><h2>Your unit</h2><span class="badge b-blue">${esc(b.booking_no)}</span></div>
        <div class="card-bd">
          <div class="facts">
            <div><span>Unit</span><b>${esc(b.unit_no)}</b></div>
            <div><span>Type</span><b>${esc(typeLine || '—')}</b></div>
            <div><span>Project</span><b>${esc(b.project_name)}</b></div>
            <div><span>Floor</span><b>${u.floor_number ?? '—'}</b></div>
            <div><span>Area</span><b>${u.area_ghaz ? `${u.area_ghaz} sq. yd` : '—'}</b></div>
            <div><span>Possession</span><b>${fdate(b.possession_date)}</b></div>
          </div>
          <p class="muted" style="margin-top:12px">${icon('pin', 14)} ${esc(b.project_location || '')}</p>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-hd"><h2>Upcoming installments</h2><a href="#plan" class="muted">See all</a></div>
      ${planTable(liveInstallments(b).filter((i) => ['pending', 'partial', 'overdue'].includes(i.status)).slice(0, 4), nd)}
    </div>`;
}

function planTable(rows, nd) {
  if (!rows.length) return emptyState('check', 'All caught up', 'There are no installments in this view.');
  return `<div class="tbl-scroll"><table class="tbl stack">
    <thead><tr><th>#</th><th>Installment</th><th>Due</th><th class="r">Amount</th><th class="r">Paid</th><th class="r">Balance</th><th>Status</th></tr></thead>
    <tbody>${rows.map((i) => {
      const due = i.status === 'scheduled'
        ? `<span class="muted">${esc(i.trigger_label || 'Construction milestone')}</span>`
        : `${fdate(i.due_date)}${i.days_overdue ? `<div class="muted" style="color:var(--red)">${i.days_overdue} days late</div>` : ''}`;
      return `<tr class="${nd && nd.id === i.id ? 'is-next' : ''}">
        <td data-hide-sm class="muted">${esc(i.installment_no)}</td>
        <td><b>${esc(i.type || 'Installment')}</b></td>
        <td>${due}</td>
        <td class="r">${money(i.amount)}</td>
        <td class="r" data-hide-sm>${money(i.paid_amount)}</td>
        <td class="r" data-hide-sm>${money(i.remaining_amount)}</td>
        <td>${badge(i.status)}</td>
      </tr>`;
    }).join('')}</tbody></table></div>`;
}

function viewPlan(b) {
  const all = liveInstallments(b);
  const counts = { all: all.length };
  all.forEach((i) => { counts[i.status] = (counts[i.status] || 0) + 1; });
  const pills = [['all', 'All'], ['overdue', 'Overdue'], ['partial', 'Partly paid'], ['pending', 'Upcoming'], ['scheduled', 'Milestone'], ['paid', 'Paid']]
    .filter(([k]) => k === 'all' || counts[k])
    .map(([k, l]) => `<button type="button" class="pill ${planFilter === k ? 'on' : ''}" data-filter="${k}">${l} · ${counts[k] || 0}</button>`).join('');
  const rows = planFilter === 'all' ? all : all.filter((i) => i.status === planFilter);
  const total = all.reduce((a, i) => a + (i.amount || 0), 0);
  return `<div class="card">
    <div class="card-hd"><div><h2>Payment plan</h2><div class="sub">${esc(b.unit_no)} · ${esc(b.project_name)} · ${all.length} installments totalling ${money(total)}</div></div>
      <div class="filters">${pills}</div></div>
    ${planTable(rows, nextDue(b))}
  </div>
  <p class="muted">Milestone installments become due once construction reaches the stated stage. Figures are updated as soon as our office records a payment.</p>`;
}

function viewPayments(b) {
  const pays = b.payments || [];
  const total = pays.reduce((a, p) => a + (p.amount || 0), 0);
  return `<div class="card">
    <div class="card-hd"><div><h2>Payments received</h2><div class="sub">${pays.length} payment${pays.length === 1 ? '' : 's'} · ${money(total)}</div></div></div>
    ${pays.length ? `<div class="tbl-scroll"><table class="tbl stack">
      <thead><tr><th>Date</th><th>Receipt</th><th>Against</th><th>Method</th><th class="r">Amount</th></tr></thead>
      <tbody>${pays.map((p) => `<tr>
        <td><b>${fdate(p.payment_date)}</b></td>
        <td class="r" style="text-align:left">${esc(p.receipt_no || '—')}</td>
        <td data-hide-sm>${esc(p.inst_type || 'General')}</td>
        <td data-hide-sm>${esc(p.payment_method || '—')}</td>
        <td class="r"><b>${money(p.amount)}</b></td></tr>`).join('')}</tbody></table></div>`
    : emptyState('wallet', 'No payments yet', 'Payments will appear here once recorded by our office.')}
  </div>`;
}

function viewDocuments(b) {
  const list = docs.filter((d) => !d.booking_id || d.booking_id === b.id);
  return `<div class="card">
    <div class="card-hd"><div><h2>Documents</h2><div class="sub">Issued to you by Haven Builders. Open a document to print or save it as PDF.</div></div></div>
    <div class="card-bd">
      ${list.length ? `<div class="doc-list">${list.map((d) => `
        <div class="doc">
          <div class="doc-ico">${icon('file', 20)}</div>
          <div><div class="doc-t">${esc(d.title)}</div><div class="doc-m">${esc(d.doc_no)} · ${fdate(d.created_at)}${d.unit_no ? ` · Unit ${esc(d.unit_no)}` : ''}</div></div>
          <a class="btn btn-light btn-sm" href="/documents/${d.id}" target="_blank" rel="noopener">${icon('download', 16)} Open</a>
        </div>`).join('')}</div>`
      : emptyState('file', 'No documents yet', 'Allotment letters and statements will show up here when our office issues them.')}
    </div>
  </div>`;
}

const VIEWS = { overview: viewOverview, plan: viewPlan, payments: viewPayments, documents: viewDocuments };

function render() {
  const tab = VIEWS[location.hash.slice(1)] ? location.hash.slice(1) : 'overview';
  document.querySelectorAll('.pt-tabs a').forEach((a) => a.classList.toggle('active', a.dataset.tab === tab));
  const b = booking();
  const view = $('view');
  if (!b) {
    view.innerHTML = `<div class="card">${emptyState('units', 'No active bookings', 'Once a booking is registered in your name it will appear here.')}</div>`
      + (tab === 'documents' && docs.length ? viewDocuments({ id: null }) : '');
    return;
  }
  view.innerHTML = VIEWS[tab](b);
  view.querySelectorAll('[data-filter]').forEach((p) => p.addEventListener('click', () => { planFilter = p.dataset.filter; render(); }));
}

function initMenu() {
  const btn = $('user-btn');
  const menu = $('user-menu');
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    menu.hidden = !menu.hidden;
    btn.setAttribute('aria-expanded', String(!menu.hidden));
  });
  document.addEventListener('click', () => { menu.hidden = true; btn.setAttribute('aria-expanded', 'false'); });
  menu.addEventListener('click', (e) => e.stopPropagation());
  $('logout').addEventListener('click', async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST', headers: { 'X-CSRF-Token': csrf } });
    } finally {
      location.replace('/login?reason=signedout');
    }
  });
}

async function init() {
  hydrateIcons();
  initMenu();
  me = await getJSON('/api/auth/me');
  if (me.role !== 'customer') { location.replace(me.home); return; }
  csrf = me.csrf_token;
  const first = String(me.name || '').split(/\s+/)[0] || 'there';
  $('user-first').textContent = first;
  $('user-av').textContent = String(me.name || '?').split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
  $('menu-name').textContent = me.name;
  $('menu-email').textContent = me.email;

  [data, docs] = await Promise.all([getJSON('/api/me/overview'), getJSON('/api/me/documents')]);
  const hour = new Date().getHours();
  $('greet').textContent = `${hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'}, ${first}`;
  const n = data.bookings.length;
  $('greet-sub').textContent = n ? `You have ${n} active booking${n > 1 ? 's' : ''} with us.` : 'Welcome to your owner portal.';
  bookingId = data.bookings[0]?.id ?? null;
  const sw = $('bk-switch');
  if (n > 1) {
    sw.innerHTML = data.bookings.map((b) => `<option value="${b.id}">${esc(b.unit_no)} · ${esc(b.project_name)}</option>`).join('');
    sw.hidden = false;
    sw.addEventListener('change', () => { bookingId = Number(sw.value); planFilter = 'all'; render(); });
  }
  render();
  window.addEventListener('hashchange', render);
}

init().catch((e) => {
  if (e.message !== 'auth' && e.message !== 'forbidden') {
    $('view').innerHTML = '<div class="card"><div class="empty"><b>Something went wrong</b>Please refresh the page. If this keeps happening, contact our office.</div></div>';
    console.error(e);
  }
});
