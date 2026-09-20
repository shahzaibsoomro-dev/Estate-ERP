import { $, esc, loadingHtml } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort } from '../format.js';
import { closeModal, openModal } from '../modal.js';
import { askConfirm } from '../dialog.js';
import { state } from '../state.js';
import { projectFilterQuery } from '../project-filter.js';

function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/* ── Contractors ─────────────────────────────────────────── */
let allCtr = [];

export async function loadContractors() {
  allCtr = await api(`/api/contractors${projectFilterQuery()}`);
  if ($('ctr-total')) $('ctr-total').textContent = allCtr.length;
  if ($('ctr-contracted')) $('ctr-contracted').textContent = fmtShort(allCtr.reduce((a, c) => a + (c.total_contracted || 0), 0));
  if ($('ctr-balance')) $('ctr-balance').textContent = fmtShort(allCtr.reduce((a, c) => a + (c.balance || 0), 0));
  renderCtr();
}

function renderCtr() {
  const q = ($('ctr-search')?.value || '').trim().toLowerCase();
  const rows = !q ? allCtr : allCtr.filter((c) =>
    [c.name, c.company_name, c.specialty, c.ntn, c.contact, c.city, c.pec_no, c.master_id].filter(Boolean).join(' ').toLowerCase().includes(q));
  const tbody = $('ctr-tbody');
  if (!tbody) return;
  tbody.innerHTML = rows.length ? rows.map((c) => `
    <tr>
      <td class="td-mono">${esc(c.master_id || `CTR-${c.id}`)}</td>
      <td class="td-b">${esc(c.name)}</td>
      <td>${esc(c.specialty || '—')}</td>
      <td class="td-mono">${esc(c.ntn || '—')}</td>
      <td>${esc(c.contact || '—')}</td>
      <td>${fmt(c.total_contracted)}</td>
      <td class="td-green">${fmt(c.total_paid)}</td>
      <td>${fmt(c.balance)}</td>
      <td><span class="badge ${c.status === 'active' ? 'bg-green' : 'bg-grey'}">${esc(c.status)}</span></td>
      <td style="white-space:nowrap">
        <button type="button" class="btn sm" data-ctr-view="${c.id}">View</button>
        <button type="button" class="btn sm" data-ctr-edit="${c.id}">Edit</button>
      </td>
    </tr>`).join('') : '<tr><td colspan="10" style="text-align:center;color:var(--g400);padding:20px">No contractors</td></tr>';
  tbody.querySelectorAll('[data-ctr-view]').forEach((b) => b.addEventListener('click', () => openCtrDetail(+b.dataset.ctrView)));
  tbody.querySelectorAll('[data-ctr-edit]').forEach((b) => b.addEventListener('click', () => openCtrForm(+b.dataset.ctrEdit)));
}

async function openCtrDetail(id) {
  openModal('ctr-detail-modal');
  $('ctrd-title').textContent = 'Loading…';
  $('ctrd-body').innerHTML = loadingHtml('Loading…');
  let c;
  try { c = await api(`/api/contractors/${id}`); }
  catch (e) { $('ctrd-body').innerHTML = `<div class="error-box">${esc(e.message)}</div>`; return; }
  $('ctrd-title').textContent = `${c.master_id} · ${c.name}`;
  const asg = (c.assignments || []).map((a) => `
    <tr><td>${esc(a.project_name)}</td><td>${esc(a.role || '—')}</td><td>${fmt(a.contract_amount)}</td>
    <td>${esc(a.start_date || '—')}</td><td>${esc(a.status)}</td></tr>`).join('')
    || '<tr><td colspan="5" style="text-align:center;color:var(--g400)">No assignments</td></tr>';
  const pays = (c.payments || []).map((p) => `
    <tr><td>${esc(p.payment_date)}</td><td>${esc(p.project_name || '—')}</td><td>${fmt(p.amount)}</td>
    <td>${esc(p.payment_method || '—')}</td><td>${esc(p.reference_number || '—')}</td></tr>`).join('')
    || '<tr><td colspan="5" style="text-align:center;color:var(--g400)">No payments</td></tr>';
  $('ctrd-body').innerHTML = `
    <div class="g2" style="margin-bottom:14px">
      <div>
        <div class="sum-row"><span class="sum-lbl">Company</span><span class="sum-val">${esc(c.company_name || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Specialty</span><span class="sum-val">${esc(c.specialty || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">NTN</span><span class="sum-val">${esc(c.ntn || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">PEC</span><span class="sum-val">${esc(c.pec_no || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Contact</span><span class="sum-val">${esc(c.contact || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">City</span><span class="sum-val">${esc(c.city || '—')}</span></div>
      </div>
      <div>
        <div class="sum-row"><span class="sum-lbl">Email</span><span class="sum-val">${esc(c.email || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Bank</span><span class="sum-val">${esc(c.bank_name || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Account</span><span class="sum-val">${esc(c.account_no || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Contracted</span><span class="sum-val">${fmt(c.total_contracted)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Paid</span><span class="sum-val">${fmt(c.total_paid)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Balance</span><span class="sum-val">${fmt(c.balance)}</span></div>
      </div>
    </div>
    <div class="detail-section-title">Project assignments</div>
    <div class="tbl-wrap" style="margin-bottom:14px"><table>
      <thead><tr><th>Project</th><th>Role</th><th>Amount</th><th>Start</th><th>Status</th></tr></thead>
      <tbody>${asg}</tbody></table></div>
    <div class="detail-section-title">Payments</div>
    <div class="tbl-wrap" style="margin-bottom:14px"><table>
      <thead><tr><th>Date</th><th>Project</th><th>Amount</th><th>Method</th><th>Ref</th></tr></thead>
      <tbody>${pays}</tbody></table></div>
    <div style="display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap">
      <button type="button" class="btn" id="ctr-btn-assign">Assign project</button>
      <button type="button" class="btn primary" id="ctr-btn-pay">Record payment</button>
    </div>`;
  $('ctr-btn-assign')?.addEventListener('click', () => openCtrAssign(id, c));
  $('ctr-btn-pay')?.addEventListener('click', () => openCtrPay(id, c));
}

async function fillProjectSelect(sel, selected = '', includeBlank = false) {
  if (!sel) return;
  const projects = state.projects?.length ? state.projects : await api('/api/projects');
  const opts = (projects || []).map((p) =>
    `<option value="${p.id}" ${String(p.id) === String(selected) ? 'selected' : ''}>${esc(p.name)}</option>`).join('');
  sel.innerHTML = (includeBlank ? '<option value="">—</option>' : '') + opts;
}

function openCtrAssign(id, c) {
  $('ctr-asg-id').value = String(id);
  $('ctr-asg-role').value = 'Main contractor';
  $('ctr-asg-amount').value = '0';
  $('ctr-asg-start').value = todayISO();
  $('ctr-asg-end').value = '';
  $('ctr-asg-notes').value = '';
  fillProjectSelect($('ctr-asg-proj'));
  openModal('ctr-assign-modal');
}

function openCtrPay(id, c) {
  $('ctr-pay-id').value = String(id);
  $('ctr-pay-amount').value = '';
  $('ctr-pay-date').value = todayISO();
  $('ctr-pay-method').value = 'Bank Transfer';
  $('ctr-pay-ref').value = '';
  $('ctr-pay-notes').value = '';
  const assigned = (c.assignments || []).map((a) => a.project_id);
  fillProjectSelect($('ctr-pay-proj'), assigned[0] || '', true);
  openModal('ctr-pay-modal');
}

function openCtrForm(id = null) {
  closeModal('ctr-detail-modal');
  ['nctr-id', 'nctr-name', 'nctr-company', 'nctr-father', 'nctr-specialty', 'nctr-contact', 'nctr-emergency',
    'nctr-ntn', 'nctr-cnic', 'nctr-email', 'nctr-city', 'nctr-address', 'nctr-pec',
    'nctr-bank', 'nctr-title', 'nctr-account', 'nctr-description'].forEach((x) => { if ($(x)) $(x).value = ''; });
  if ($('nctr-status')) $('nctr-status').value = 'active';
  $('ctr-modal-title').textContent = id ? 'Edit Contractor' : 'Add Contractor';
  openModal('ctr-modal');
  if (!id) return;
  api(`/api/contractors/${id}`).then((c) => {
    $('nctr-id').value = String(c.id);
    $('nctr-name').value = c.name || '';
    if ($('nctr-company')) $('nctr-company').value = c.company_name || '';
    if ($('nctr-father')) $('nctr-father').value = c.father_name || '';
    $('nctr-specialty').value = c.specialty || '';
    $('nctr-contact').value = c.contact || '';
    if ($('nctr-emergency')) $('nctr-emergency').value = c.emergency_contact || '';
    $('nctr-ntn').value = c.ntn || '';
    $('nctr-cnic').value = c.cnic || '';
    if ($('nctr-email')) $('nctr-email').value = c.email || '';
    if ($('nctr-city')) $('nctr-city').value = c.city || '';
    if ($('nctr-address')) $('nctr-address').value = c.address || '';
    if ($('nctr-pec')) $('nctr-pec').value = c.pec_no || '';
    if ($('nctr-bank')) $('nctr-bank').value = c.bank_name || '';
    if ($('nctr-title')) $('nctr-title').value = c.account_title || '';
    if ($('nctr-account')) $('nctr-account').value = c.account_no || '';
    $('nctr-description').value = c.description || '';
    $('nctr-status').value = c.status || 'active';
  }).catch(() => closeModal('ctr-modal'));
}

async function saveCtr() {
  const payload = {
    name: $('nctr-name').value.trim(),
    company_name: ($('nctr-company')?.value || '').trim(),
    father_name: ($('nctr-father')?.value || '').trim(),
    specialty: $('nctr-specialty').value.trim(),
    contact: $('nctr-contact').value.trim(),
    emergency_contact: ($('nctr-emergency')?.value || '').trim(),
    ntn: $('nctr-ntn').value.trim(),
    cnic: $('nctr-cnic').value.trim(),
    email: ($('nctr-email')?.value || '').trim(),
    city: ($('nctr-city')?.value || '').trim(),
    address: ($('nctr-address')?.value || '').trim(),
    pec_no: ($('nctr-pec')?.value || '').trim(),
    bank_name: ($('nctr-bank')?.value || '').trim(),
    account_title: ($('nctr-title')?.value || '').trim(),
    account_no: ($('nctr-account')?.value || '').trim(),
    description: $('nctr-description').value.trim(),
    status: $('nctr-status').value,
  };
  if (!payload.name) { toast('Name required', 'error'); return; }
  const id = parseInt($('nctr-id').value, 10);
  try {
    if (id) await api(`/api/contractors/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
    else await api('/api/contractors', { method: 'POST', body: JSON.stringify(payload) });
    closeModal('ctr-modal'); toast('Contractor saved'); await loadContractors();
  } catch { /* toasted */ }
}

export function initContractorEvents() {
  $('ctr-search')?.addEventListener('input', renderCtr);
  $('btn-add-ctr')?.addEventListener('click', () => openCtrForm());
  $('btn-save-ctr')?.addEventListener('click', saveCtr);
  $('btn-save-ctr-asg')?.addEventListener('click', async () => {
    const id = parseInt($('ctr-asg-id').value, 10);
    const project_id = parseInt($('ctr-asg-proj').value, 10);
    if (!id || !project_id) { toast('Select a project', 'error'); return; }
    try {
      await api(`/api/contractors/${id}/assign`, {
        method: 'POST',
        body: JSON.stringify({
          project_id,
          role: $('ctr-asg-role').value.trim() || null,
          contract_amount: parseInt($('ctr-asg-amount').value, 10) || 0,
          start_date: $('ctr-asg-start').value || todayISO(),
          end_date: $('ctr-asg-end').value || null,
          notes: $('ctr-asg-notes').value.trim() || null,
        }),
      });
      closeModal('ctr-assign-modal');
      toast('Assigned to project');
      openCtrDetail(id);
      loadContractors();
    } catch { /* toasted */ }
  });
  $('btn-save-ctr-pay')?.addEventListener('click', async () => {
    const id = parseInt($('ctr-pay-id').value, 10);
    const amount = parseInt($('ctr-pay-amount').value, 10) || 0;
    if (!id || amount <= 0) { toast('Enter a valid amount', 'error'); return; }
    const project_id = parseInt($('ctr-pay-proj').value, 10) || null;
    try {
      await api(`/api/contractors/${id}/pay`, {
        method: 'POST',
        body: JSON.stringify({
          amount,
          project_id,
          payment_date: $('ctr-pay-date').value || todayISO(),
          payment_method: $('ctr-pay-method').value,
          reference_number: $('ctr-pay-ref').value.trim() || null,
          notes: $('ctr-pay-notes').value.trim() || null,
        }),
      });
      closeModal('ctr-pay-modal');
      toast('Payment recorded');
      openCtrDetail(id);
      loadContractors();
    } catch { /* toasted */ }
  });
}

/* ── Inventory ───────────────────────────────────────────── */
let allInv = [];

export async function loadInventory() {
  allInv = await api(`/api/inventory${projectFilterQuery()}`);
  if ($('invmat-total')) $('invmat-total').textContent = allInv.length;
  if ($('invmat-ok')) $('invmat-ok').textContent = allInv.filter((i) => !i.low_stock).length;
  if ($('invmat-low')) $('invmat-low').textContent = allInv.filter((i) => i.low_stock).length;
  renderInv();
}

function renderInv() {
  const q = ($('invmat-search')?.value || '').trim().toLowerCase();
  const rows = !q ? allInv : allInv.filter((i) =>
    [i.name, i.sku, i.category, i.project_name, i.master_id].filter(Boolean).join(' ').toLowerCase().includes(q));
  const tbody = $('invmat-tbody');
  if (!tbody) return;
  tbody.innerHTML = rows.length ? rows.map((i) => `
    <tr>
      <td class="td-mono">${esc(i.master_id || `MAT-${i.id}`)}</td>
      <td class="td-b">${esc(i.name)}${i.sku ? `<div style="font-size:11px;color:var(--g400)">${esc(i.sku)}</div>` : ''}</td>
      <td>${esc(i.category || '—')}</td>
      <td>${esc(i.project_name || 'Company')}</td>
      <td>${esc(i.unit || 'pcs')}</td>
      <td class="${i.low_stock ? 'td-red' : 'td-green'}">${i.on_hand ?? 0}</td>
      <td>${i.min_stock ?? 0}</td>
      <td><span class="badge ${i.low_stock ? 'bg-red' : 'bg-green'}">${i.low_stock ? 'Low' : 'OK'}</span></td>
      <td style="white-space:nowrap">
        <button type="button" class="btn sm" data-inv-view="${i.id}">View</button>
        <button type="button" class="btn sm" data-inv-out="${i.id}">Issue</button>
      </td>
    </tr>`).join('') : '<tr><td colspan="9" style="text-align:center;color:var(--g400);padding:20px">No inventory items</td></tr>';
  tbody.querySelectorAll('[data-inv-view]').forEach((b) => b.addEventListener('click', () => openInvDetail(+b.dataset.invView)));
  tbody.querySelectorAll('[data-inv-out]').forEach((b) => b.addEventListener('click', async () => {
    const qty = parseFloat(prompt('Issue quantity?') || '0');
    if (!qty) return;
    try {
      await api(`/api/inventory/${b.dataset.invOut}/move`, {
        method: 'POST', body: JSON.stringify({ direction: 'out', quantity: qty, movement_date: todayISO() }),
      });
      toast('Stock issued'); loadInventory();
    } catch { /* toasted */ }
  }));
}

async function openInvDetail(id) {
  openModal('invmat-detail-modal');
  $('invmatd-title').textContent = 'Loading…';
  $('invmatd-body').innerHTML = loadingHtml('Loading…');
  let item;
  try { item = await api(`/api/inventory/${id}`); }
  catch (e) { $('invmatd-body').innerHTML = `<div class="error-box">${esc(e.message)}</div>`; return; }
  $('invmatd-title').textContent = `${item.master_id} · ${item.name}`;
  const mov = (item.movements || []).map((m) => `
    <tr><td>${esc(m.movement_date)}</td><td>${esc(m.direction)}</td><td>${m.quantity}</td>
    <td>${esc(m.project_name || '—')}</td><td>${esc(m.reference_type || '—')}</td><td>${esc(m.notes || '—')}</td></tr>`).join('')
    || '<tr><td colspan="6" style="text-align:center;color:var(--g400)">No movements</td></tr>';
  $('invmatd-body').innerHTML = `
    <div class="g2" style="margin-bottom:14px">
      <div>
        <div class="sum-row"><span class="sum-lbl">Category</span><span class="sum-val">${esc(item.category || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Project</span><span class="sum-val">${esc(item.project_name || 'Company')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Unit</span><span class="sum-val">${esc(item.unit)}</span></div>
      </div>
      <div>
        <div class="sum-row"><span class="sum-lbl">On hand</span><span class="sum-val">${item.on_hand ?? 0}</span></div>
        <div class="sum-row"><span class="sum-lbl">Min stock</span><span class="sum-val">${item.min_stock ?? 0}</span></div>
      </div>
    </div>
    <div class="detail-section-title">Movements</div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Date</th><th>Dir</th><th>Qty</th><th>Project</th><th>Ref</th><th>Notes</th></tr></thead>
      <tbody>${mov}</tbody></table></div>`;
}

async function openInvForm() {
  ['ninv-id', 'ninv-name', 'ninv-sku', 'ninv-category', 'ninv-notes'].forEach((x) => { if ($(x)) $(x).value = ''; });
  if ($('ninv-unit')) $('ninv-unit').value = 'pcs';
  if ($('ninv-min')) $('ninv-min').value = '0';
  if ($('ninv-opening')) $('ninv-opening').value = '0';
  if ($('ninv-cost')) $('ninv-cost').value = '0';
  const projects = state.projects?.length ? state.projects : await api('/api/projects');
  if ($('ninv-proj')) {
    $('ninv-proj').innerHTML = '<option value="">Company-wide</option>' + projects.map((p) =>
      `<option value="${p.id}">${esc(p.name)}</option>`).join('');
  }
  if ($('ninv-opening-row')) $('ninv-opening-row').style.display = '';
  $('invmat-modal-title').textContent = 'Add Inventory Item';
  openModal('invmat-modal');
}

async function saveInv() {
  const payload = {
    name: $('ninv-name').value.trim(), sku: $('ninv-sku').value.trim(),
    category: $('ninv-category').value.trim(), unit: $('ninv-unit').value.trim() || 'pcs',
    project_id: parseInt($('ninv-proj').value, 10) || null,
    min_stock: parseFloat($('ninv-min').value) || 0,
    opening_stock: parseFloat($('ninv-opening').value) || 0,
    unit_cost: parseInt($('ninv-cost').value, 10) || 0,
    notes: $('ninv-notes').value.trim(),
  };
  if (!payload.name) { toast('Name required', 'error'); return; }
  try {
    await api('/api/inventory', { method: 'POST', body: JSON.stringify(payload) });
    closeModal('invmat-modal'); toast('Item added'); await loadInventory();
  } catch { /* toasted */ }
}

export function initInventoryEvents() {
  $('invmat-search')?.addEventListener('input', renderInv);
  $('btn-add-invmat')?.addEventListener('click', () => openInvForm());
  $('btn-save-invmat')?.addEventListener('click', saveInv);
}

/* ── Budget ──────────────────────────────────────────────── */
let budCats = [];
let budSummary = [];

export async function loadBudget() {
  const pid = parseInt($('bud-project')?.value, 10) || null;
  const projects = state.projects?.length ? state.projects : await api('/api/projects');
  if ($('bud-project') && !$('bud-project').dataset.ready) {
    $('bud-project').innerHTML = '<option value="">All projects</option>' + projects.map((p) =>
      `<option value="${p.id}">${esc(p.name)}</option>`).join('');
    $('bud-project').dataset.ready = '1';
  }
  [budCats, budSummary] = await Promise.all([
    api('/api/budget/categories'),
    api(`/api/budget/summary${pid ? `?project_id=${pid}` : ''}`),
  ]);
  const planned = budSummary.reduce((a, r) => a + (r.planned_amount || 0), 0);
  const spent = budSummary.reduce((a, r) => a + (r.actual_spent || 0), 0);
  if ($('bud-planned')) $('bud-planned').textContent = fmtShort(planned);
  if ($('bud-spent')) $('bud-spent').textContent = fmtShort(spent);
  if ($('bud-var')) $('bud-var').textContent = fmtShort(planned - spent);
  if ($('bud-cat-tbody')) {
    $('bud-cat-tbody').innerHTML = budCats.length ? budCats.map((c) => `
      <tr><td class="td-b">${esc(c.name)}</td><td>${c.sort_order ?? 0}</td>
      <td><button type="button" class="btn sm danger" data-bud-cat-del="${c.id}">Delete</button></td></tr>`).join('')
      : '<tr><td colspan="3" style="text-align:center;color:var(--g400)">No categories</td></tr>';
    $('bud-cat-tbody').querySelectorAll('[data-bud-cat-del]').forEach((b) => b.addEventListener('click', async () => {
      if (!await askConfirm('Delete this category?', { title: 'Delete category', danger: true, confirmLabel: 'Delete' })) return;
      try { await api(`/api/budget/categories/${b.dataset.budCatDel}`, { method: 'DELETE' }); toast('Deleted'); loadBudget(); }
      catch { /* toasted */ }
    }));
  }
  if ($('bud-sum-tbody')) {
    $('bud-sum-tbody').innerHTML = budSummary.length ? budSummary.map((r) => `
      <tr>
        <td>${esc(r.project_name)}</td><td>${esc(r.category_name)}</td>
        <td>${fmt(r.planned_amount)}</td><td>${fmt(r.actual_spent)}</td>
        <td class="${r.variance < 0 ? 'td-red' : 'td-green'}">${fmt(r.variance)}</td>
        <td>${r.pct_used}%</td>
        <td><span class="badge ${r.status === 'Exceeded' ? 'bg-red' : r.status === 'Near Limit' ? 'bg-yellow' : 'bg-green'}">${esc(r.status)}</span></td>
        <td><button type="button" class="btn sm" data-bud-rev="${r.project_id}:${r.category_id}:${r.planned_amount}">Revise</button></td>
      </tr>`).join('')
      : '<tr><td colspan="8" style="text-align:center;color:var(--g400)">No budget lines</td></tr>';
    $('bud-sum-tbody').querySelectorAll('[data-bud-rev]').forEach((b) => b.addEventListener('click', async () => {
      const [projectId, categoryId, oldAmt] = b.dataset.budRev.split(':');
      const lines = await api(`/api/budget/lines?project_id=${projectId}`);
      const line = lines.find((l) => String(l.category_id) === categoryId);
      if (!line) { toast('Line not found', 'error'); return; }
      const amt = parseInt(prompt('New planned amount?', String(oldAmt)) || '0', 10);
      if (!amt) return;
      try {
        await api(`/api/budget/lines/${line.id}/revise`, { method: 'POST', body: JSON.stringify({ planned_amount: amt }) });
        toast('Budget revised'); loadBudget();
      } catch { /* toasted */ }
    }));
  }
}

async function openBudLineForm() {
  const projects = state.projects?.length ? state.projects : await api('/api/projects');
  if (!budCats.length) budCats = await api('/api/budget/categories');
  $('bl-project').innerHTML = projects.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
  $('bl-category').innerHTML = budCats.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
  $('bl-planned').value = '';
  $('bl-notes').value = '';
  openModal('bud-line-modal');
}

export function initBudgetEvents() {
  $('bud-project')?.addEventListener('change', () => loadBudget());
  $('btn-add-bud-cat')?.addEventListener('click', async () => {
    const name = (prompt('Category name?') || '').trim();
    if (!name) return;
    try {
      await api('/api/budget/categories', { method: 'POST', body: JSON.stringify({ name, sort_order: budCats.length + 1 }) });
      toast('Category added'); loadBudget();
    } catch { /* toasted */ }
  });
  $('btn-add-bud-line')?.addEventListener('click', () => openBudLineForm());
  $('btn-save-bud-line')?.addEventListener('click', async () => {
    const payload = {
      project_id: parseInt($('bl-project').value, 10),
      category_id: parseInt($('bl-category').value, 10),
      planned_amount: parseInt($('bl-planned').value, 10),
      notes: $('bl-notes').value.trim() || null,
    };
    if (!payload.project_id || !payload.category_id || !payload.planned_amount) {
      toast('Project, category and amount required', 'error'); return;
    }
    try {
      await api('/api/budget/lines', { method: 'POST', body: JSON.stringify(payload) });
      closeModal('bud-line-modal'); toast('Budget line added'); loadBudget();
    } catch { /* toasted */ }
  });
}

/* ── Pay plans ───────────────────────────────────────────── */
function pctFromBps(bps) { return ((bps || 0) / 100).toFixed(2); }

export async function loadPayPlans() {
  const rows = await api('/api/projects/pay-plans');
  const tbody = $('payplan-tbody');
  if (!tbody) return;
  tbody.innerHTML = rows.length ? rows.map((r) => `
    <tr>
      <td class="td-b">${esc(r.project_name)}</td>
      <td>${esc(r.template_name || '—')}</td>
      <td>${r.rule_count || 0}</td>
      <td>${r.default_booking_bps != null ? pctFromBps(r.default_booking_bps) + '%' : '—'}</td>
      <td>${r.revision ?? '—'}</td>
      <td><span class="badge ${r.has_template ? 'bg-green' : 'bg-grey'}">${r.has_template ? 'Active' : 'None'}</span></td>
      <td><button type="button" class="btn sm primary" data-pp-edit="${r.project_id}">Edit plan</button></td>
    </tr>`).join('') : '<tr><td colspan="7" style="text-align:center;color:var(--g400)">No projects</td></tr>';
  tbody.querySelectorAll('[data-pp-edit]').forEach((b) => b.addEventListener('click', () => openPayPlan(+b.dataset.ppEdit)));
}

function ppRuleRow(rule = {}) {
  const bps = rule.amount_bps != null ? rule.amount_bps / 100 : '';
  const kind = rule.trigger_kind || 'construction';
  return `<div class="form-row pp-rule" style="align-items:end;margin-bottom:8px">
    <div class="fg"><label>Label</label><input class="pp-label" value="${esc(rule.label || '')}"></div>
    <div class="fg"><label>%</label><input class="pp-pct" type="number" min="0" step="0.01" value="${bps}"></div>
    <div class="fg"><label>Trigger</label>
      <select class="pp-kind"><option value="construction" ${kind === 'construction' ? 'selected' : ''}>Construction</option>
      <option value="time" ${kind === 'time' ? 'selected' : ''}>Time</option></select></div>
    <div class="fg"><label>Progress %</label><input class="pp-prog" type="number" min="0" max="100" value="${rule.milestone_progress ?? ''}"></div>
    <button type="button" class="btn sm danger pp-del">✕</button>
  </div>`;
}

async function openPayPlan(projectId) {
  $('pp-project-id').value = String(projectId);
  const tmpl = await api(`/api/projects/${projectId}/installment-template`);
  const plans = await api('/api/projects/pay-plans');
  const row = plans.find((p) => p.project_id === projectId);
  $('payplan-modal-title').textContent = `Pay plan · ${row?.project_name || projectId}`;
  $('pp-name').value = tmpl?.name || 'Standard plan';
  $('pp-enable').value = tmpl?.id ? '1' : '0';
  const rules = tmpl?.rules?.length ? tmpl.rules : [{ label: 'Foundation', amount_bps: 2500, trigger_kind: 'construction', milestone_progress: 10 }];
  $('pp-rules').innerHTML = rules.map(ppRuleRow).join('');
  bindPpRules();
  openModal('payplan-modal');
}

function bindPpRules() {
  $('pp-rules')?.querySelectorAll('.pp-del').forEach((b) => b.addEventListener('click', () => {
    b.closest('.pp-rule')?.remove();
  }));
}

export function initPayPlanEvents() {
  $('btn-add-pp-rule')?.addEventListener('click', () => {
    $('pp-rules').insertAdjacentHTML('beforeend', ppRuleRow());
    bindPpRules();
  });
  $('btn-save-payplan')?.addEventListener('click', async () => {
    const projectId = parseInt($('pp-project-id').value, 10);
    if ($('pp-enable').value === '0') {
      await api(`/api/projects/${projectId}/installment-template`, { method: 'DELETE' });
      closeModal('payplan-modal'); toast('Pay plan removed'); loadPayPlans(); return;
    }
    const rules = [...$('pp-rules').querySelectorAll('.pp-rule')].map((row) => ({
      label: row.querySelector('.pp-label').value.trim(),
      amount_bps: Math.round(parseFloat(row.querySelector('.pp-pct').value || '0') * 100),
      trigger_kind: row.querySelector('.pp-kind').value,
      milestone_progress: row.querySelector('.pp-kind').value === 'construction'
        ? parseInt(row.querySelector('.pp-prog').value, 10) : null,
      installment_count: 1,
      interval_months: 1,
      due_days_after_trigger: 0,
    }));
    try {
      await api(`/api/projects/${projectId}/installment-template`, {
        method: 'PUT',
        body: JSON.stringify({ name: $('pp-name').value.trim() || 'Pay plan', default_booking_bps: 1000, rules }),
      });
      closeModal('payplan-modal'); toast('Pay plan saved'); loadPayPlans();
    } catch { /* toasted */ }
  });
}
