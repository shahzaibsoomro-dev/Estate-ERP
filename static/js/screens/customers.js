import { $, esc, loadingHtml } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, overdueBadge } from '../format.js';
import { state } from '../state.js';
import { closeModal, openModal } from '../modal.js';
import { projectFilterQuery } from '../project-filter.js';
import { customerDetailsHtml, customerStatusBadgeClass } from '../detail.js';
import { confirmCancelBooking } from '../booking-actions.js';
import { askConfirm } from '../dialog.js';

function demandRows() {
  const q = ($('demand-q')?.value || '').trim().toLowerCase();
  return (state.demandData || []).filter((n) => {
    if (!q) return true;
    return [n.customer_name, n.unit_no, n.project_name, n.phone, n.cnic, n.type, n.trigger_label, n.reason]
      .filter(Boolean).join(' ').toLowerCase().includes(q);
  });
}

export async function loadDemand() {
  state.demandData = await api(`/api/demand-notices${projectFilterQuery()}`);
  renderDemandList();
  if ($('notice-area') && !state.demandData?.length) {
    $('notice-area').innerHTML = `<div class="demand-empty">No overdue installments — nothing to demand.</div>`;
  }
}

function renderDemandList() {
  const rows = demandRows();
  const tbody = $('demand-tbody');
  if (!tbody) return;
  tbody.innerHTML = rows.length
    ? rows.map((n) => `
      <tr class="demand-row${state.demandSelectedId === n.id ? ' active' : ''}" data-notice-id="${n.id}">
        <td>
          <div class="td-b">${esc(n.customer_name)}</div>
          <div class="td-sm">${esc(n.unit_no)} · ${esc(n.project_name || '')}</div>
        </td>
        <td>
          <div>${esc(n.trigger_label || n.type || 'Installment')}</div>
          <div class="td-sm">${esc(n.when || `${n.days_overdue}d overdue`)}</div>
        </td>
        <td class="td-red">${fmt(n.amount)}</td>
        <td><span class="badge ${overdueBadge(n.days_overdue)}">${n.days_overdue}d</span></td>
      </tr>`).join('')
    : `<tr><td colspan="4" style="text-align:center;color:var(--g400);padding:20px">${
      (state.demandData || []).length ? 'No matching notices' : 'No overdue installments'
    }</td></tr>`;
  tbody.querySelectorAll('[data-notice-id]').forEach((row) => {
    row.addEventListener('click', () => showNotice(parseInt(row.dataset.noticeId, 10)));
  });
}

function showNotice(id) {
  const n = (state.demandData || []).find((x) => x.id === id);
  if (!n) return;
  state.demandSelectedId = id;
  renderDemandList();
  const instLabel = n.trigger_label || n.type || 'Installment';
  $('notice-area').innerHTML = `
    <div class="notice">
      <div class="notice-lh">
        <div>
          <div class="notice-kicker">Demand notice · preview</div>
          <div style="font-weight:800;font-size:16px;color:var(--navy)">${esc(n.customer_name)}</div>
          <div class="td-sm">${esc(n.unit_no)} · ${esc(n.project_name || '')}${n.booking_no ? ` · ${esc(n.booking_no)}` : ''}</div>
        </div>
        <span class="badge ${overdueBadge(n.days_overdue)}">${n.days_overdue} days overdue</span>
      </div>
      <div class="notice-why">
        <div><span>Why</span><b>${esc(n.why || instLabel)}</b></div>
        <div><span>When</span><b>${esc(n.when || n.due_date || '—')}</b></div>
        <div><span>What</span><b>${esc(n.what || fmt(n.amount))}</b></div>
      </div>
      <div class="notice-body">
        <p>Dear ${esc(n.customer_name)},</p>
        <p>${esc(n.reason || `Your ${instLabel.toLowerCase()} for unit ${n.unit_no} is overdue.`)}</p>
        <table class="notice-table">
          <tr><td>Installment</td><td>${esc(instLabel)}</td></tr>
          <tr><td>Due date</td><td>${esc(n.due_date || '—')}</td></tr>
          <tr><td>Original amount</td><td>${fmt(n.original_amount || n.amount)}</td></tr>
          <tr><td>Received so far</td><td>${fmt(n.paid_amount || 0)}</td></tr>
          <tr><td>Still unpaid</td><td><strong class="td-red">${fmt(n.amount)}</strong></td></tr>
          ${n.last_payment ? `<tr><td>Last payment</td><td>${esc(n.last_payment)}</td></tr>` : ''}
          ${n.notes ? `<tr><td>Notes</td><td>${esc(n.notes)}</td></tr>` : ''}
        </table>
        <p>Please clear this installment within <strong>7 working days</strong> to stay on the agreed payment plan. Late charges, if any, follow the booking terms — they are not calculated here.</p>
        <p class="td-sm">This is an in-app preview. Issue a formal notice as a document to keep a copy on the booking and in the customer portal. WhatsApp and email sending are not connected yet.</p>
      </div>
      <div class="notice-actions">
        <button type="button" class="btn sm" data-dn-view="${n.customer_id}">View customer</button>
        <button type="button" class="btn sm primary" data-dn-pay="${n.id}">Record payment</button>
        <button type="button" class="btn sm" data-dn-doc="${n.id}">Issue as document</button>
      </div>
    </div>`;
  $('notice-area').querySelector('[data-dn-view]')?.addEventListener('click', () => openCustomerDetail(n.customer_id));
  $('notice-area').querySelector('[data-dn-pay]')?.addEventListener('click', async () => {
    const { openPayForInstallment } = await import('./recovery.js');
    openPayForInstallment(n);
  });
  $('notice-area').querySelector('[data-dn-doc]')?.addEventListener('click', async () => {
    const { openGenerate } = await import('./documents.js');
    await openGenerate({ customerId: n.customer_id, bookingId: n.booking_id, kind: 'notice' });
  });
}

function displayStatus(c) {
  return c.cust_status || 'New';
}

export async function loadCustomers() {
  state.allCustomers = await api('/api/customers');
  const rows = state.allCustomers || [];
  if ($('c-total')) $('c-total').textContent = rows.length;
  if ($('c-overdue')) $('c-overdue').textContent = rows.filter((c) => c.cust_status === 'Overdue').length;
  if ($('c-track')) $('c-track').textContent = rows.filter((c) => c.cust_status === 'On Track').length;
  if ($('c-cleared')) $('c-cleared').textContent = rows.filter((c) => c.cust_status === 'Cleared').length;
  const q = $('cust-search')?.value || '';
  renderCustomers(q ? filterCustomerRows(rows, q) : rows);
}

function bindCustomerRowActions(root) {
  root.querySelectorAll('[data-cust-view]').forEach((btn) => {
    btn.addEventListener('click', () => openCustomerDetail(parseInt(btn.dataset.custView, 10)));
  });
  root.querySelectorAll('[data-cust-edit]').forEach((btn) => {
    btn.addEventListener('click', () => openEditCustomer(parseInt(btn.dataset.custEdit, 10)));
  });
  root.querySelectorAll('[data-cust-delete]').forEach((btn) => {
    btn.addEventListener('click', () => deleteCustomer(parseInt(btn.dataset.custDelete, 10)));
  });
}

export function renderCustomers(custs) {
  $('cust-tbody').innerHTML = custs.length
    ? custs.map((c) => {
        const status = displayStatus(c);
        return `
      <tr>
        <td><div class="td-b">${esc(c.name)}</div><div class="td-sm">${esc(c.phone || '—')}</div></td>
        <td class="td-mono">${esc(c.cnic || '—')}</td>
        <td>${c.units ? c.units.split(',').map((u) => `<span class="badge bg-blue" style="margin:1px">${esc(u.trim())}</span>`).join(' ') : '—'}</td>
        <td>${c.total_value ? fmt(c.total_value) : '—'}</td>
        <td class="td-green">${fmt(c.total_paid)}</td>
        <td class="${c.outstanding > 0 ? 'td-red' : 'td-green'}">${fmt(c.outstanding)}</td>
        <td class="td-sm">${esc(c.last_payment || '—')}</td>
        <td><span class="badge ${customerStatusBadgeClass(status)}">${esc(status)}</span></td>
        <td style="white-space:nowrap">
          <button type="button" class="btn sm" data-cust-view="${c.id}">View</button>
          <button type="button" class="btn sm" data-cust-edit="${c.id}">Edit</button>
          <button type="button" class="btn sm danger" data-cust-delete="${c.id}">Delete</button>
        </td>
      </tr>`;
      }).join('')
    : '<tr><td colspan="9" style="text-align:center;color:var(--g400);padding:20px">No customers found</td></tr>';

  bindCustomerRowActions($('cust-tbody'));
}

export async function openCustomerDetail(id) {
  openModal('customer-detail-modal');
  $('cd-title').textContent = 'Loading…';
  $('cd-body').innerHTML = loadingHtml('Loading customer…');
  let c;
  try {
    c = await api(`/api/customers/${id}`);
  } catch (e) {
    $('cd-body').innerHTML = `<div class="error-box">Could not load customer: ${esc(e.message)}</div>`;
    return;
  }
  $('cd-title').textContent = c.name || 'Customer';
  $('cd-body').innerHTML = customerDetailsHtml(c);
  $('cd-body').scrollTop = 0;
  bindCustomerRowActions($('cd-body'));
  $('cd-body').querySelectorAll('[data-cancel-booking]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (await confirmCancelBooking(parseInt(btn.dataset.cancelBooking, 10))) {
        await loadCustomers();
        openCustomerDetail(id);
      }
    });
  });
  $('cd-body').querySelector('[data-cust-doc]')?.addEventListener('click', async () => {
    const { openGenerate } = await import('./documents.js');
    const first = (c.bookings || []).find((b) => b.status === 'active');
    await openGenerate({ customerId: id, bookingId: first?.id || null });
  });
}

function resetCustomerForm() {
  ['nc-id', 'nc-name', 'nc-cnic', 'nc-father', 'nc-phone', 'nc-emergency', 'nc-email', 'nc-address', 'nc-description',
    'nc-nok-name', 'nc-nok-rel', 'nc-nok-phone', 'nc-nok-cnic', 'nc-nok-address']
    .forEach((id) => { if ($(id)) $(id).value = ''; });
  if ($('cust-modal-title')) $('cust-modal-title').textContent = 'Add Customer';
  if ($('btn-save-customer')) $('btn-save-customer').textContent = 'Save Customer';
  if ($('nc-computed')) { $('nc-computed').hidden = true; $('nc-computed').innerHTML = ''; }
}

function fillCustomerForm(c) {
  $('nc-id').value = String(c.id || '');
  $('nc-name').value = c.name || '';
  $('nc-cnic').value = c.cnic || '';
  $('nc-father').value = c.father_name || '';
  $('nc-phone').value = c.phone || c.contact_number || '';
  $('nc-emergency').value = c.emergency_contact_number || '';
  $('nc-email').value = c.email || '';
  $('nc-address').value = c.address || c.residential_address || '';
  $('nc-description').value = c.description || '';
  if ($('nc-nok-name')) $('nc-nok-name').value = c.nok_name || '';
  if ($('nc-nok-rel')) $('nc-nok-rel').value = c.nok_relationship || '';
  if ($('nc-nok-phone')) $('nc-nok-phone').value = c.nok_phone || '';
  if ($('nc-nok-cnic')) $('nc-nok-cnic').value = c.nok_cnic || '';
  if ($('nc-nok-address')) $('nc-nok-address').value = c.nok_address || '';
  const box = $('nc-computed');
  if (box) {
    box.hidden = false;
    box.innerHTML = `
      <h4>Computed (from bookings)</h4>
      <div class="sum-row"><span class="sum-lbl">Units</span><span class="sum-val">${esc(c.units || '—')}</span></div>
      <div class="sum-row"><span class="sum-lbl">Total value</span><span class="sum-val">${c.total_value ? fmt(c.total_value) : '—'}</span></div>
      <div class="sum-row"><span class="sum-lbl">Paid</span><span class="sum-val">${fmt(c.total_paid || 0)}</span></div>
      <div class="sum-row"><span class="sum-lbl">Outstanding</span><span class="sum-val">${fmt(c.outstanding || 0)}</span></div>
      <div class="sum-row"><span class="sum-lbl">Last payment</span><span class="sum-val">${esc(c.last_payment || '—')}</span></div>
      <div class="sum-row"><span class="sum-lbl">Status</span><span class="sum-val">${esc(c.cust_status || 'New')}</span></div>`;
  }
  paintCustomerPreview();
}

function paintCustomerPreview() {
  const box = $('nc-preview');
  if (!box) return;
  const p = readCustomerForm();
  if (!p.name && !p.cnic && !p.phone && !p.father_name && !p.address && !p.nok_name) {
    box.hidden = true;
    box.innerHTML = '';
    return;
  }
  box.hidden = false;
  const bits = [
    p.father_name ? `S/O ${p.father_name}` : '',
    p.cnic, p.phone, p.emergency_contact_number, p.email,
  ].filter(Boolean);
  const nok = [p.nok_name, p.nok_relationship, p.nok_phone, p.nok_cnic].filter(Boolean).join(' · ');
  box.innerHTML = `
    <h4>Details preview</h4>
    <div class="bk-dname">${esc(p.name || 'New customer')}</div>
    ${bits.length ? `<div class="bk-dsub">${esc(bits.join(' · '))}</div>` : ''}
    ${p.address ? `<div class="bk-dsub" style="margin-top:6px">${esc(p.address)}</div>` : ''}
    ${nok ? `<div class="bk-dsub" style="margin-top:6px">NOK: ${esc(nok)}</div>` : ''}
    ${p.nok_address ? `<div class="bk-dsub">${esc(p.nok_address)}</div>` : ''}
    ${p.description ? `<div class="bk-dsub" style="margin-top:4px">${esc(p.description)}</div>` : ''}`;
}

export function openAddCustomer() {
  resetCustomerForm();
  paintCustomerPreview();
  openModal('cust-modal');
}

export async function openEditCustomer(id) {
  closeModal('customer-detail-modal');
  resetCustomerForm();
  openModal('cust-modal');
  $('cust-modal-title').textContent = 'Edit Customer';
  $('btn-save-customer').textContent = 'Save Changes';
  try {
    const c = await api(`/api/customers/${id}`);
    fillCustomerForm(c);
  } catch {
    closeModal('cust-modal');
  }
}

function readCustomerForm() {
  return {
    name: $('nc-name').value.trim(),
    cnic: $('nc-cnic').value.trim(),
    father_name: $('nc-father').value.trim(),
    phone: $('nc-phone').value.trim(),
    emergency_contact_number: $('nc-emergency').value.trim(),
    email: $('nc-email').value.trim(),
    address: $('nc-address').value.trim(),
    description: $('nc-description').value.trim(),
    nok_name: ($('nc-nok-name')?.value || '').trim(),
    nok_relationship: ($('nc-nok-rel')?.value || '').trim(),
    nok_phone: ($('nc-nok-phone')?.value || '').trim(),
    nok_cnic: ($('nc-nok-cnic')?.value || '').trim(),
    nok_address: ($('nc-nok-address')?.value || '').trim(),
  };
}

export async function submitCustomer() {
  const payload = readCustomerForm();
  if (!payload.name || !payload.cnic) {
    toast('Name and CNIC required', 'error');
    return;
  }
  const id = parseInt($('nc-id').value, 10);
  try {
    if (id) {
      await api(`/api/customers/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      toast('Customer updated');
    } else {
      await api('/api/customers', { method: 'POST', body: JSON.stringify(payload) });
      toast('Customer added');
    }
    closeModal('cust-modal');
    await loadCustomers();
  } catch {
    /* api() already toasts */
  }
}

async function deleteCustomer(id) {
  const listed = (state.allCustomers || []).find((x) => x.id === id);
  const name = listed?.name || 'this customer';
  let msg = `Delete customer "${name}"?\n\nThis cannot be undone.`;
  if (listed?.units || listed?.total_paid) {
    msg += '\n\nThis customer has bookings or payments and cannot be deleted.';
  }
  if (!await askConfirm(msg, { title: 'Delete customer', confirmLabel: 'Delete', danger: true })) return;
  try {
    await api(`/api/customers/${id}`, { method: 'DELETE' });
    toast(`Customer "${name}" deleted`);
    closeModal('customer-detail-modal');
    await loadCustomers();
  } catch {
    /* api() already toasts the server reason */
  }
}

function filterCustomerRows(rows, q) {
  const s = q.trim().toLowerCase();
  if (!s) return rows;
  return rows.filter((c) => {
    const blob = [
      c.name, c.cnic, c.phone, c.contact_number, c.email,
      c.father_name, c.address, c.residential_address, c.units,
      c.nok_name, c.nok_phone, c.nok_cnic, c.nok_relationship,
    ].filter(Boolean).join(' ').toLowerCase();
    return blob.includes(s);
  });
}

export function filterCustomers() {
  renderCustomers(filterCustomerRows(state.allCustomers || [], $('cust-search').value));
}

export function initCustomerEvents() {
  $('cust-search')?.addEventListener('input', filterCustomers);
  $('demand-q')?.addEventListener('input', renderDemandList);
  $('btn-add-customer')?.addEventListener('click', openAddCustomer);
  $('btn-save-customer')?.addEventListener('click', submitCustomer);
  ['nc-name', 'nc-cnic', 'nc-father', 'nc-phone', 'nc-emergency', 'nc-email', 'nc-address', 'nc-description']
    .forEach((id) => $(id)?.addEventListener('input', paintCustomerPreview));
}
