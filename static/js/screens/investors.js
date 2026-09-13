import { $, esc, loadingHtml } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort } from '../format.js';
import { closeModal, openModal } from '../modal.js';
import { askConfirm } from '../dialog.js';
import { projectFilterQuery } from '../project-filter.js';

let allInvestors = [];

function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function invBadge(inv) {
  const st = (inv.status || 'active').toLowerCase();
  if (st === 'completed') return ['bg-blue', 'Completed'];
  if (st === 'withdrawn' || st === 'inactive') return ['bg-grey', 'Withdrawn'];
  return ['bg-green', 'Active'];
}

function catchUpLabel(inv) {
  const p = inv.catch_up_policy || 'lump_sum';
  if (p === 'spread') return `Spread ${inv.catch_up_months || '?'} mo`;
  if (p === 'none') return 'None';
  return 'Lump sum';
}

function syncInvestorFormVisibility() {
  const type = $('ni-type')?.value || 'Profit Sharing';
  const catchUp = $('ni-catch-up')?.value || 'lump_sum';
  if ($('ni-catch-up-months-row')) {
    $('ni-catch-up-months-row').style.display = catchUp === 'spread' ? '' : 'none';
  }
  if ($('ni-profit-basis-row')) {
    const basisFg = $('ni-profit-basis')?.closest('.fg');
    if (basisFg) basisFg.style.display = type === 'Profit Sharing' ? '' : 'none';
  }
}

export async function loadInvestors() {
  closeModal('imoney-modal');
  allInvestors = await api(`/api/investors${projectFilterQuery()}`);
  if ($('inv-total')) $('inv-total').textContent = allInvestors.length;
  if ($('inv-kpi-in')) {
    $('inv-kpi-in').textContent = fmtShort(allInvestors.reduce((a, i) => a + (i.investment_amount || 0), 0));
  }
  if ($('inv-kpi-dist')) {
    $('inv-kpi-dist').textContent = fmtShort(allInvestors.reduce((a, i) => a + (i.total_return_received || 0), 0));
  }
  renderInvestors();
}

function filteredInvestors() {
  const q = ($('inv-search')?.value || '').trim().toLowerCase();
  if (!q) return allInvestors;
  return allInvestors.filter((i) =>
    [i.name, i.mobile_number, i.contact, i.cnic, i.email, i.description, i.investor_type, i.project_name]
      .filter(Boolean).join(' ').toLowerCase().includes(q));
}

function renderInvestors() {
  const tbody = $('inv-tbody');
  if (!tbody) return;
  const rows = filteredInvestors();
  tbody.innerHTML = rows.length
    ? rows.map((inv) => {
        const [cls, label] = invBadge(inv);
        const inn = inv.investment_amount || 0;
        const out = inv.total_return_received || 0;
        const due = inv.return_due ?? Math.max((inv.accrued_return || 0) - out, 0);
        const sub = [inv.email, inv.description].filter(Boolean).join(' · ');
        return `
      <tr>
        <td class="td-b">${esc(inv.name)}${sub ? `<div style="font-size:11px;color:var(--g400);font-weight:400;max-width:220px;white-space:normal">${esc(sub)}</div>` : ''}</td>
        <td>${esc(inv.cnic || '—')}</td>
        <td>${esc(inv.mobile_number || inv.contact || '—')}</td>
        <td>${esc(inv.investor_type || '—')}</td>
        <td>${esc(inv.project_name || 'Company')}</td>
        <td>${fmt(inv.agreed_amount || 0)}</td>
        <td>${esc(inv.investment_date || '—')}</td>
        <td>${esc(inv.returns_start_date || '—')}</td>
        <td>${esc(catchUpLabel(inv))}</td>
        <td class="td-green">${fmt(inn)}</td>
        <td>${fmt(out)}</td>
        <td>${fmt(due)}</td>
        <td><span class="badge ${cls}">${esc(label)}</span></td>
        <td style="white-space:nowrap">
          <button type="button" class="btn sm" data-inv-view="${inv.id}">View</button>
          <button type="button" class="btn sm" data-inv-edit="${inv.id}">Edit</button>
          <button type="button" class="btn sm danger" data-inv-del="${inv.id}">Delete</button>
        </td>
      </tr>`;
      }).join('')
    : '<tr><td colspan="14" style="text-align:center;color:var(--g400);padding:20px">No investors found</td></tr>';

  tbody.querySelectorAll('[data-inv-view]').forEach((b) => {
    b.addEventListener('click', () => openInvestorDetail(parseInt(b.dataset.invView, 10)));
  });
  tbody.querySelectorAll('[data-inv-edit]').forEach((b) => {
    b.addEventListener('click', () => openInvestorForm(parseInt(b.dataset.invEdit, 10)));
  });
  tbody.querySelectorAll('[data-inv-del]').forEach((b) => {
    b.addEventListener('click', () => deleteInvestor(parseInt(b.dataset.invDel, 10)));
  });
}

export async function openInvestorDetail(id) {
  openModal('inv-detail-modal');
  $('id-title').textContent = 'Loading…';
  $('id-body').innerHTML = loadingHtml('Loading investor…');
  let inv;
  try {
    inv = await api(`/api/investors/${id}`);
  } catch (e) {
    $('id-body').innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
    return;
  }
  const [cls, label] = invBadge(inv);
  $('id-title').textContent = inv.name;
  const contribs = inv.contributions || [];
  const dists = inv.distributions || [];
  const inRows = contribs.length
    ? contribs.map((c) => `
        <tr><td>${esc(c.contribution_date)}</td><td class="td-green">${fmt(c.amount)}</td><td>${esc(c.notes || '—')}</td></tr>`).join('')
    : '<tr><td colspan="3" style="text-align:center;color:var(--g400)">No contributions</td></tr>';
  const outRows = dists.length
    ? dists.map((c) => `
        <tr><td>${esc(c.distribution_date)}</td><td>${fmt(c.amount)}</td><td>${esc(c.notes || '—')}</td></tr>`).join('')
    : '<tr><td colspan="3" style="text-align:center;color:var(--g400)">No distributions</td></tr>';
  const basis = inv.investor_type === 'Profit Sharing'
    ? (inv.profit_share_basis || 'project')
    : '—';
  $('id-body').innerHTML = `
    <div class="g2" style="margin-bottom:14px">
      <div>
        <div class="sum-row"><span class="sum-lbl">Mobile</span><span class="sum-val">${esc(inv.mobile_number || inv.contact || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">CNIC</span><span class="sum-val">${esc(inv.cnic || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Email</span><span class="sum-val">${esc(inv.email || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Type</span><span class="sum-val">${esc(inv.investor_type || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Profit basis</span><span class="sum-val">${esc(basis)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Project</span><span class="sum-val">${esc(inv.project_name || 'Company')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Status</span><span class="sum-val"><span class="badge ${cls}">${esc(label)}</span></span></div>
      </div>
      <div>
        <div class="sum-row"><span class="sum-lbl">Agreed amount</span><span class="sum-val">${fmt(inv.agreed_amount || 0)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Investment date</span><span class="sum-val">${esc(inv.investment_date || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Returns start</span><span class="sum-val">${esc(inv.returns_start_date || '—')}${inv.returns_active ? ' · active' : ' · deferred'}</span></div>
        <div class="sum-row"><span class="sum-lbl">Catch-up</span><span class="sum-val">${esc(catchUpLabel(inv))}${inv.catch_up_total ? ` · ${fmt(inv.catch_up_total)}` : ''}</span></div>
        <div class="sum-row"><span class="sum-lbl">Silent months</span><span class="sum-val">${inv.silent_months ?? '—'}</span></div>
        <div class="sum-row"><span class="sum-lbl">Monthly return</span><span class="sum-val">${inv.monthly_return_pct != null ? `${inv.monthly_return_pct}%` : '—'}${inv.monthly_return_amount ? ` (${fmt(inv.monthly_return_amount)})` : ''}</span></div>
        <div class="sum-row"><span class="sum-lbl">Profit share</span><span class="sum-val">${inv.profit_share_pct != null ? `${inv.profit_share_pct}%` : '—'}</span></div>
        <div class="sum-row"><span class="sum-lbl">Received (cash)</span><span class="sum-val">${fmt(inv.investment_amount)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Distributed</span><span class="sum-val">${fmt(inv.total_return_received)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Accrued / due</span><span class="sum-val">${fmt(inv.accrued_return || 0)} / ${fmt(inv.return_due || 0)}</span></div>
      </div>
    </div>
    <div class="detail-block" style="margin-bottom:14px"><div class="detail-block-lbl">Description</div><div class="detail-block-txt">${esc(inv.description || '—')}</div></div>
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
      <button type="button" class="btn" data-inv-edit="${inv.id}">Edit</button>
      <button type="button" class="btn primary" data-inv-in="${inv.id}">Record in</button>
      <button type="button" class="btn" data-inv-out="${inv.id}">Pay out</button>
    </div>`;
  $('id-body').querySelector('[data-inv-edit]')?.addEventListener('click', () => openInvestorForm(inv.id));
  $('id-body').querySelector('[data-inv-in]')?.addEventListener('click', () => openInvestorMoney(inv, 'in'));
  $('id-body').querySelector('[data-inv-out]')?.addEventListener('click', () => openInvestorMoney(inv, 'out'));
}

function resetInvestorForm() {
  ['ni-id', 'ni-name', 'ni-contact', 'ni-cnic', 'ni-email', 'ni-description', 'ni-agreed', 'ni-monthly', 'ni-profit', 'ni-catch-up-months'].forEach((id) => {
    if ($(id)) $(id).value = '';
  });
  if ($('ni-status')) $('ni-status').value = 'active';
  if ($('ni-type')) $('ni-type').value = 'Profit Sharing';
  if ($('ni-proj')) $('ni-proj').value = '';
  if ($('ni-date')) $('ni-date').value = todayISO();
  if ($('ni-returns-start')) $('ni-returns-start').value = todayISO();
  if ($('ni-catch-up')) $('ni-catch-up').value = 'lump_sum';
  if ($('ni-profit-basis')) $('ni-profit-basis').value = 'project';
  if ($('inv-modal-title')) $('inv-modal-title').textContent = 'Add Investor';
  syncInvestorFormVisibility();
}

export async function openInvestorForm(id = null) {
  closeModal('inv-detail-modal');
  resetInvestorForm();
  openModal('inv-modal');
  if (!id) return;
  $('inv-modal-title').textContent = 'Edit Investor';
  try {
    const inv = await api(`/api/investors/${id}`);
    $('ni-id').value = String(inv.id);
    $('ni-name').value = inv.name || '';
    $('ni-contact').value = inv.mobile_number || inv.contact || '';
    $('ni-cnic').value = inv.cnic || '';
    $('ni-email').value = inv.email || '';
    $('ni-description').value = inv.description || '';
    const st = (inv.status || 'active').toLowerCase();
    $('ni-status').value = st === 'completed' ? 'completed' : (st === 'withdrawn' || st === 'inactive' ? 'withdrawn' : 'active');
    if ($('ni-type')) $('ni-type').value = inv.investor_type === 'Monthly Return' ? 'Monthly Return' : 'Profit Sharing';
    if ($('ni-proj')) $('ni-proj').value = inv.project_id ? String(inv.project_id) : '';
    if ($('ni-agreed')) $('ni-agreed').value = inv.agreed_amount ? String(inv.agreed_amount) : '';
    if ($('ni-date')) $('ni-date').value = inv.investment_date || todayISO();
    if ($('ni-returns-start')) $('ni-returns-start').value = inv.returns_start_date || inv.investment_date || todayISO();
    if ($('ni-catch-up')) $('ni-catch-up').value = inv.catch_up_policy || 'lump_sum';
    if ($('ni-catch-up-months')) $('ni-catch-up-months').value = inv.catch_up_months != null ? String(inv.catch_up_months) : '';
    if ($('ni-monthly')) $('ni-monthly').value = inv.monthly_return_pct != null ? String(inv.monthly_return_pct) : '';
    if ($('ni-profit')) $('ni-profit').value = inv.profit_share_pct != null ? String(inv.profit_share_pct) : '';
    if ($('ni-profit-basis')) $('ni-profit-basis').value = inv.profit_share_basis || 'project';
    syncInvestorFormVisibility();
  } catch {
    closeModal('inv-modal');
  }
}

async function submitInvestor() {
  const catchUp = $('ni-catch-up')?.value || 'lump_sum';
  const payload = {
    name: $('ni-name').value.trim(),
    mobile_number: $('ni-contact').value.trim(),
    cnic: $('ni-cnic').value.trim(),
    email: $('ni-email').value.trim(),
    description: $('ni-description').value.trim(),
    status: $('ni-status').value,
    investor_type: $('ni-type')?.value || 'Profit Sharing',
    project_id: parseInt($('ni-proj')?.value, 10) || null,
    agreed_amount: parseInt($('ni-agreed')?.value, 10) || 0,
    investment_date: $('ni-date')?.value || todayISO(),
    returns_start_date: $('ni-returns-start')?.value || $('ni-date')?.value || todayISO(),
    catch_up_policy: catchUp,
    catch_up_months: catchUp === 'spread' ? (parseInt($('ni-catch-up-months')?.value, 10) || null) : null,
    monthly_return_pct: $('ni-monthly')?.value === '' ? null : parseFloat($('ni-monthly').value),
    profit_share_pct: $('ni-profit')?.value === '' ? null : parseFloat($('ni-profit').value),
    profit_share_basis: $('ni-type')?.value === 'Profit Sharing' ? ($('ni-profit-basis')?.value || 'project') : null,
  };
  if (!payload.name) {
    toast('Investor name is required', 'error');
    return;
  }
  if (catchUp === 'spread' && (!payload.catch_up_months || payload.catch_up_months < 1)) {
    toast('Enter catch-up months (N)', 'error');
    return;
  }
  const id = parseInt($('ni-id').value, 10);
  try {
    if (id) {
      await api(`/api/investors/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      toast('Investor updated');
    } else {
      await api('/api/investors', { method: 'POST', body: JSON.stringify(payload) });
      toast('Investor added');
    }
    closeModal('inv-modal');
    await loadInvestors();
  } catch { /* toasted */ }
}

async function deleteInvestor(id) {
  const inv = allInvestors.find((x) => x.id === id);
  const name = inv?.name || 'this investor';
  if (!await askConfirm(`Delete investor "${name}"?\n\nInvestors with money history cannot be deleted.`, {
    title: 'Delete investor', confirmLabel: 'Delete', danger: true,
  })) return;
  try {
    await api(`/api/investors/${id}`, { method: 'DELETE' });
    toast(`Investor "${name}" deleted`);
    closeModal('inv-detail-modal');
    await loadInvestors();
  } catch { /* toasted */ }
}

function openInvestorMoney(inv, kind) {
  $('imoney-id').value = String(inv.id);
  $('imoney-kind').value = kind;
  $('imoney-amount').value = '';
  $('imoney-date').value = todayISO();
  $('imoney-notes').value = '';
  $('imoney-title').textContent = kind === 'in' ? 'Record contribution' : 'Pay distribution';
  const start = inv.returns_start_date || '—';
  const lockNote = kind === 'out'
    ? `<div class="sum-row"><span class="sum-lbl">Returns start</span><span class="sum-val">${esc(start)}${inv.returns_active ? '' : ' · locked'}</span></div>
       ${inv.returns_active ? '' : `<div style="font-size:11px;color:var(--danger);margin-top:6px">Cannot pay before ${esc(start)}</div>`}`
    : '';
  if (kind === 'out' && inv.returns_start_date && $('imoney-date')) {
    $('imoney-date').min = inv.returns_start_date;
    if (($('imoney-date').value || '') < inv.returns_start_date) $('imoney-date').value = inv.returns_start_date;
  } else if ($('imoney-date')) {
    $('imoney-date').removeAttribute('min');
  }
  $('imoney-summary').innerHTML = `
    <div class="bk-dname">${esc(inv.name)}</div>
    <div class="sum-row"><span class="sum-lbl">Project</span><span class="sum-val">${esc(inv.project_name || 'Company')}</span></div>
    <div class="sum-row"><span class="sum-lbl">Contributed</span><span class="sum-val">${fmt(inv.investment_amount)}</span></div>
    <div class="sum-row"><span class="sum-lbl">Distributed</span><span class="sum-val">${fmt(inv.total_return_received)}</span></div>
    <div class="sum-row"><span class="sum-lbl">Return due</span><span class="sum-val">${fmt(inv.return_due || 0)}</span></div>
    ${lockNote}`;
  closeModal('inv-detail-modal');
  openModal('imoney-modal');
}

async function submitInvestorMoney() {
  const id = parseInt($('imoney-id').value, 10);
  const kind = $('imoney-kind').value;
  const amount = parseInt($('imoney-amount').value, 10);
  if (!id || !amount || amount < 1) {
    toast('Enter an amount.', 'error');
    return;
  }
  const label = kind === 'in' ? 'contribution' : 'distribution';
  if (!await askConfirm(`Record ${label} of ${fmt(amount)}?`, {
    title: `Record ${label}`, confirmLabel: 'Record',
  })) return;
  const path = kind === 'in' ? `/api/investors/${id}/contribute` : `/api/investors/${id}/distribute`;
  const body = kind === 'in'
    ? { amount, contribution_date: $('imoney-date').value || todayISO(), notes: $('imoney-notes').value.trim() || null }
    : { amount, distribution_date: $('imoney-date').value || todayISO(), notes: $('imoney-notes').value.trim() || null };
  try {
    await api(path, { method: 'POST', body: JSON.stringify(body) });
    closeModal('imoney-modal');
    toast(kind === 'in' ? 'Contribution recorded' : 'Distribution recorded');
    await loadInvestors();
  } catch { /* toasted */ }
}

export function initInvestorEvents() {
  $('inv-search')?.addEventListener('input', renderInvestors);
  $('btn-add-investor')?.addEventListener('click', () => openInvestorForm());
  $('btn-save-investor')?.addEventListener('click', submitInvestor);
  $('btn-save-imoney')?.addEventListener('click', submitInvestorMoney);
  $('ni-type')?.addEventListener('change', syncInvestorFormVisibility);
  $('ni-catch-up')?.addEventListener('change', syncInvestorFormVisibility);
}
