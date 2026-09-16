import { $, esc, loadingHtml } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort } from '../format.js';
import { closeModal, openModal } from '../modal.js';
import { askConfirm } from '../dialog.js';
import { projectFilterQuery } from '../project-filter.js';

let allPartners = [];

function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function parBadge(p) {
  const st = (p.status || 'active').toLowerCase();
  if (st === 'completed') return ['bg-blue', 'Completed'];
  if (st === 'withdrawn' || st === 'inactive') return ['bg-grey', 'Withdrawn'];
  return ['bg-green', 'Active'];
}

function catchUpLabel(p) {
  const policy = p.catch_up_policy || 'lump_sum';
  if (policy === 'spread') return `Spread ${p.catch_up_months || '?'} mo`;
  if (policy === 'none') return 'None';
  return 'Lump sum';
}

function syncPartnerFormVisibility() {
  const type = $('np-type')?.value || 'Profit Sharing';
  const catchUp = $('np-catch-up')?.value || 'lump_sum';
  if ($('np-catch-up-months-row')) {
    $('np-catch-up-months-row').style.display = catchUp === 'spread' ? '' : 'none';
  }
  const basisFg = $('np-profit-basis')?.closest('.fg');
  if (basisFg) basisFg.style.display = type === 'Profit Sharing' ? '' : 'none';
}

export async function loadPartners() {
  closeModal('pmoney-modal');
  allPartners = await api(`/api/partners${projectFilterQuery()}`);
  if ($('par-total')) $('par-total').textContent = allPartners.length;
  if ($('par-kpi-in')) {
    $('par-kpi-in').textContent = fmtShort(allPartners.reduce((a, i) => a + (i.investment_amount || 0), 0));
  }
  if ($('par-kpi-dist')) {
    $('par-kpi-dist').textContent = fmtShort(allPartners.reduce((a, i) => a + (i.total_return_received || 0), 0));
  }
  renderPartners();
}

function filteredPartners() {
  const q = ($('par-search')?.value || '').trim().toLowerCase();
  if (!q) return allPartners;
  return allPartners.filter((i) =>
    [i.name, i.mobile_number, i.contact, i.cnic, i.email, i.description, i.partner_type || i.investor_type, i.project_name]
      .filter(Boolean).join(' ').toLowerCase().includes(q));
}

function renderPartners() {
  const tbody = $('par-tbody');
  if (!tbody) return;
  const rows = filteredPartners();
  tbody.innerHTML = rows.length
    ? rows.map((p) => {
        const [cls, label] = parBadge(p);
        const inn = p.investment_amount || 0;
        const out = p.total_return_received || 0;
        const due = p.return_due ?? Math.max((p.accrued_return || 0) - out, 0);
        const sub = [p.email, p.description].filter(Boolean).join(' · ');
        const rtype = p.partner_type || p.investor_type || '—';
        return `
      <tr>
        <td class="td-b">${esc(p.name)}${sub ? `<div style="font-size:11px;color:var(--g400);font-weight:400;max-width:220px;white-space:normal">${esc(sub)}</div>` : ''}</td>
        <td>${esc(p.cnic || '—')}</td>
        <td>${esc(p.mobile_number || p.contact || '—')}</td>
        <td>${esc(rtype)}</td>
        <td>${esc(p.project_name || 'Company')}</td>
        <td>${fmt(p.agreed_amount || 0)}</td>
        <td>${esc(p.investment_date || '—')}</td>
        <td>${esc(p.returns_start_date || '—')}</td>
        <td>${esc(catchUpLabel(p))}</td>
        <td class="td-green">${fmt(inn)}</td>
        <td>${fmt(out)}</td>
        <td>${fmt(due)}</td>
        <td><span class="badge ${cls}">${esc(label)}</span></td>
        <td style="white-space:nowrap">
          <button type="button" class="btn sm" data-par-view="${p.id}">View</button>
          <button type="button" class="btn sm" data-par-edit="${p.id}">Edit</button>
          <button type="button" class="btn sm danger" data-par-del="${p.id}">Delete</button>
        </td>
      </tr>`;
      }).join('')
    : '<tr><td colspan="14" style="text-align:center;color:var(--g400);padding:20px">No partners found</td></tr>';

  tbody.querySelectorAll('[data-par-view]').forEach((b) => {
    b.addEventListener('click', () => openPartnerDetail(parseInt(b.dataset.parView, 10)));
  });
  tbody.querySelectorAll('[data-par-edit]').forEach((b) => {
    b.addEventListener('click', () => openPartnerForm(parseInt(b.dataset.parEdit, 10)));
  });
  tbody.querySelectorAll('[data-par-del]').forEach((b) => {
    b.addEventListener('click', () => deletePartner(parseInt(b.dataset.parDel, 10)));
  });
}

export async function openPartnerDetail(id) {
  openModal('par-detail-modal');
  $('pd-title').textContent = 'Loading…';
  $('pd-body').innerHTML = loadingHtml('Loading partner…');
  let p;
  try {
    p = await api(`/api/partners/${id}`);
  } catch (e) {
    $('pd-body').innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
    return;
  }
  const [cls, label] = parBadge(p);
  $('pd-title').textContent = p.name;
  const contribs = p.contributions || [];
  const dists = p.distributions || [];
  const inRows = contribs.length
    ? contribs.map((c) => `
        <tr><td>${esc(c.contribution_date)}</td><td class="td-green">${fmt(c.amount)}</td><td>${esc(c.notes || '—')}</td></tr>`).join('')
    : '<tr><td colspan="3" style="text-align:center;color:var(--g400)">No contributions</td></tr>';
  const outRows = dists.length
    ? dists.map((c) => `
        <tr><td>${esc(c.distribution_date)}</td><td>${fmt(c.amount)}</td><td>${esc(c.notes || '—')}</td></tr>`).join('')
    : '<tr><td colspan="3" style="text-align:center;color:var(--g400)">No distributions</td></tr>';
  const rtype = p.partner_type || p.investor_type || '—';
  const basis = rtype === 'Profit Sharing' ? (p.profit_share_basis || 'project') : '—';
  $('pd-body').innerHTML = `
    <div class="g2" style="margin-bottom:14px">
      <div>
        <div class="sum-row"><span class="sum-lbl">Mobile</span><span class="sum-val">${esc(p.mobile_number || p.contact || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">CNIC</span><span class="sum-val">${esc(p.cnic || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Email</span><span class="sum-val">${esc(p.email || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Type</span><span class="sum-val">${esc(rtype)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Profit basis</span><span class="sum-val">${esc(basis)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Project</span><span class="sum-val">${esc(p.project_name || 'Company')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Status</span><span class="sum-val"><span class="badge ${cls}">${esc(label)}</span></span></div>
      </div>
      <div>
        <div class="sum-row"><span class="sum-lbl">Agreed amount</span><span class="sum-val">${fmt(p.agreed_amount || 0)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Investment date</span><span class="sum-val">${esc(p.investment_date || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Returns start</span><span class="sum-val">${esc(p.returns_start_date || '—')}${p.returns_active ? ' · active' : ' · deferred'}</span></div>
        <div class="sum-row"><span class="sum-lbl">Catch-up</span><span class="sum-val">${esc(catchUpLabel(p))}${p.catch_up_total ? ` · ${fmt(p.catch_up_total)}` : ''}</span></div>
        <div class="sum-row"><span class="sum-lbl">Silent months</span><span class="sum-val">${p.silent_months ?? '—'}</span></div>
        <div class="sum-row"><span class="sum-lbl">Monthly return</span><span class="sum-val">${p.monthly_return_pct != null ? `${p.monthly_return_pct}%` : '—'}${p.monthly_return_amount ? ` (${fmt(p.monthly_return_amount)})` : ''}</span></div>
        <div class="sum-row"><span class="sum-lbl">Profit share</span><span class="sum-val">${p.profit_share_pct != null ? `${p.profit_share_pct}%` : '—'}</span></div>
        <div class="sum-row"><span class="sum-lbl">Received (cash)</span><span class="sum-val">${fmt(p.investment_amount)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Distributed</span><span class="sum-val">${fmt(p.total_return_received)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Accrued / due</span><span class="sum-val">${fmt(p.accrued_return || 0)} / ${fmt(p.return_due || 0)}</span></div>
      </div>
    </div>
    <div class="detail-block" style="margin-bottom:14px"><div class="detail-block-lbl">Description</div><div class="detail-block-txt">${esc(p.description || '—')}</div></div>
    <div class="detail-section-title">Contributions</div>
    <div class="tbl-wrap" style="margin-bottom:14px"><table>
      <thead><tr><th>Date</th><th>Amount</th><th>Notes</th></tr></thead>
      <tbody>${inRows}</tbody>
    </table></div>
    <div class="detail-section-title">Distributions</div>
    <div class="tbl-wrap" style="margin-bottom:14px"><table>
      <thead><tr><th>Date</th><th>Amount</th><th>Notes</th></tr></thead>
      <tbody>${outRows}</tbody>
    </table></div>
    <div style="display:flex;justify-content:flex-end;gap:8px">
      <button type="button" class="btn" data-par-edit="${p.id}">Edit</button>
      <button type="button" class="btn primary" data-par-in="${p.id}">Record in</button>
      <button type="button" class="btn" data-par-out="${p.id}" ${p.returns_active ? '' : 'title="Returns start date not reached yet"'}>Pay out</button>
    </div>`;
  $('pd-body').querySelector('[data-par-edit]')?.addEventListener('click', () => openPartnerForm(p.id));
  $('pd-body').querySelector('[data-par-in]')?.addEventListener('click', () => openPartnerMoney(p, 'in'));
  $('pd-body').querySelector('[data-par-out]')?.addEventListener('click', () => openPartnerMoney(p, 'out'));
}

function resetPartnerForm() {
  ['np-id', 'np-name', 'np-contact', 'np-cnic', 'np-email', 'np-description', 'np-agreed', 'np-monthly', 'np-profit', 'np-catch-up-months'].forEach((id) => {
    if ($(id)) $(id).value = '';
  });
  if ($('np-status')) $('np-status').value = 'active';
  if ($('np-type')) $('np-type').value = 'Profit Sharing';
  if ($('np-proj')) $('np-proj').value = '';
  if ($('np-date')) $('np-date').value = todayISO();
  if ($('np-returns-start')) $('np-returns-start').value = todayISO();
  if ($('np-catch-up')) $('np-catch-up').value = 'lump_sum';
  if ($('np-profit-basis')) $('np-profit-basis').value = 'project';
  if ($('par-modal-title')) $('par-modal-title').textContent = 'Add Partner';
  syncPartnerFormVisibility();
}

export async function openPartnerForm(id = null) {
  closeModal('par-detail-modal');
  resetPartnerForm();
  openModal('par-modal');
  if (!id) return;
  $('par-modal-title').textContent = 'Edit Partner';
  try {
    const p = await api(`/api/partners/${id}`);
    $('np-id').value = String(p.id);
    $('np-name').value = p.name || '';
    $('np-contact').value = p.mobile_number || p.contact || '';
    $('np-cnic').value = p.cnic || '';
    $('np-email').value = p.email || '';
    $('np-description').value = p.description || '';
    const st = (p.status || 'active').toLowerCase();
    $('np-status').value = st === 'completed' ? 'completed' : (st === 'withdrawn' || st === 'inactive' ? 'withdrawn' : 'active');
    const rtype = p.partner_type || p.investor_type;
    if ($('np-type')) $('np-type').value = rtype === 'Monthly Return' ? 'Monthly Return' : 'Profit Sharing';
    if ($('np-proj')) $('np-proj').value = p.project_id ? String(p.project_id) : '';
    if ($('np-agreed')) $('np-agreed').value = p.agreed_amount ? String(p.agreed_amount) : '';
    if ($('np-date')) $('np-date').value = p.investment_date || todayISO();
    if ($('np-returns-start')) $('np-returns-start').value = p.returns_start_date || p.investment_date || todayISO();
    if ($('np-catch-up')) $('np-catch-up').value = p.catch_up_policy || 'lump_sum';
    if ($('np-catch-up-months')) $('np-catch-up-months').value = p.catch_up_months != null ? String(p.catch_up_months) : '';
    if ($('np-monthly')) $('np-monthly').value = p.monthly_return_pct != null ? String(p.monthly_return_pct) : '';
    if ($('np-profit')) $('np-profit').value = p.profit_share_pct != null ? String(p.profit_share_pct) : '';
    if ($('np-profit-basis')) $('np-profit-basis').value = p.profit_share_basis || 'project';
    syncPartnerFormVisibility();
  } catch {
    closeModal('par-modal');
  }
}

async function submitPartner() {
  const catchUp = $('np-catch-up')?.value || 'lump_sum';
  const payload = {
    name: $('np-name').value.trim(),
    mobile_number: $('np-contact').value.trim(),
    cnic: $('np-cnic').value.trim(),
    email: $('np-email').value.trim(),
    description: $('np-description').value.trim(),
    status: $('np-status').value,
    partner_type: $('np-type')?.value || 'Profit Sharing',
    project_id: parseInt($('np-proj')?.value, 10) || null,
    agreed_amount: parseInt($('np-agreed')?.value, 10) || 0,
    investment_date: $('np-date')?.value || todayISO(),
    returns_start_date: $('np-returns-start')?.value || $('np-date')?.value || todayISO(),
    catch_up_policy: catchUp,
    catch_up_months: catchUp === 'spread' ? (parseInt($('np-catch-up-months')?.value, 10) || null) : null,
    monthly_return_pct: $('np-monthly')?.value === '' ? null : parseFloat($('np-monthly').value),
    profit_share_pct: $('np-profit')?.value === '' ? null : parseFloat($('np-profit').value),
    profit_share_basis: $('np-type')?.value === 'Profit Sharing' ? ($('np-profit-basis')?.value || 'project') : null,
  };
  if (!payload.name) {
    toast('Partner name is required', 'error');
    return;
  }
  if (!payload.project_id) {
    toast('Select a project for this partner', 'error');
    return;
  }
  if (catchUp === 'spread' && (!payload.catch_up_months || payload.catch_up_months < 1)) {
    toast('Enter catch-up months (N)', 'error');
    return;
  }
  const id = parseInt($('np-id').value, 10);
  try {
    if (id) {
      await api(`/api/partners/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      toast('Partner updated');
    } else {
      await api('/api/partners', { method: 'POST', body: JSON.stringify(payload) });
      toast('Partner added');
    }
    closeModal('par-modal');
    await loadPartners();
  } catch { /* toasted */ }
}

async function deletePartner(id) {
  const p = allPartners.find((x) => x.id === id);
  const name = p?.name || 'this partner';
  if (!await askConfirm(`Delete partner "${name}"?\n\nPartners with money history cannot be deleted.`, {
    title: 'Delete partner', confirmLabel: 'Delete', danger: true,
  })) return;
  try {
    await api(`/api/partners/${id}`, { method: 'DELETE' });
    toast(`Partner "${name}" deleted`);
    closeModal('par-detail-modal');
    await loadPartners();
  } catch { /* toasted */ }
}

function openPartnerMoney(p, kind) {
  $('pmoney-id').value = String(p.id);
  $('pmoney-kind').value = kind;
  $('pmoney-amount').value = '';
  $('pmoney-date').value = todayISO();
  $('pmoney-notes').value = '';
  $('pmoney-title').textContent = kind === 'in' ? 'Record contribution' : 'Pay distribution';
  const start = p.returns_start_date || '—';
  const lockNote = kind === 'out'
    ? `<div class="sum-row"><span class="sum-lbl">Returns start</span><span class="sum-val">${esc(start)}${p.returns_active ? '' : ' · locked'}</span></div>
       ${p.returns_active ? '' : `<div style="font-size:11px;color:var(--danger);margin-top:6px">Cannot pay before ${esc(start)}</div>`}`
    : '';
  if (kind === 'out' && p.returns_start_date && $('pmoney-date')) {
    $('pmoney-date').min = p.returns_start_date;
    if (($('pmoney-date').value || '') < p.returns_start_date) $('pmoney-date').value = p.returns_start_date;
  } else if ($('pmoney-date')) {
    $('pmoney-date').removeAttribute('min');
  }
  $('pmoney-summary').innerHTML = `
    <div class="bk-dname">${esc(p.name)}</div>
    <div class="sum-row"><span class="sum-lbl">Project</span><span class="sum-val">${esc(p.project_name || '—')}</span></div>
    <div class="sum-row"><span class="sum-lbl">Contributed</span><span class="sum-val">${fmt(p.investment_amount)}</span></div>
    <div class="sum-row"><span class="sum-lbl">Distributed</span><span class="sum-val">${fmt(p.total_return_received)}</span></div>
    <div class="sum-row"><span class="sum-lbl">Return due</span><span class="sum-val">${fmt(p.return_due || 0)}</span></div>
    ${lockNote}`;
  closeModal('par-detail-modal');
  openModal('pmoney-modal');
}

async function submitPartnerMoney() {
  const id = parseInt($('pmoney-id').value, 10);
  const kind = $('pmoney-kind').value;
  const amount = parseInt($('pmoney-amount').value, 10);
  if (!id || !amount || amount < 1) {
    toast('Enter an amount.', 'error');
    return;
  }
  const label = kind === 'in' ? 'contribution' : 'distribution';
  if (!await askConfirm(`Record ${label} of ${fmt(amount)}?`, {
    title: `Record ${label}`, confirmLabel: 'Record',
  })) return;
  const path = kind === 'in' ? `/api/partners/${id}/contribute` : `/api/partners/${id}/distribute`;
  const body = kind === 'in'
    ? { amount, contribution_date: $('pmoney-date').value || todayISO(), notes: $('pmoney-notes').value.trim() || null }
    : { amount, distribution_date: $('pmoney-date').value || todayISO(), notes: $('pmoney-notes').value.trim() || null };
  try {
    await api(path, { method: 'POST', body: JSON.stringify(body) });
    closeModal('pmoney-modal');
    toast(kind === 'in' ? 'Contribution recorded' : 'Distribution recorded');
    await loadPartners();
  } catch { /* toasted */ }
}

export function initPartnerEvents() {
  $('par-search')?.addEventListener('input', renderPartners);
  $('btn-add-partner')?.addEventListener('click', () => openPartnerForm());
  $('btn-save-partner')?.addEventListener('click', submitPartner);
  $('btn-save-pmoney')?.addEventListener('click', submitPartnerMoney);
  $('np-type')?.addEventListener('change', syncPartnerFormVisibility);
  $('np-catch-up')?.addEventListener('change', syncPartnerFormVisibility);
}
