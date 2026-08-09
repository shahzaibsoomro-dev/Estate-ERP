import { $, esc, loadingHtml } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, overdueBadge } from '../format.js';
import { state } from '../state.js';
import { closeModal, openModal } from '../modal.js';
import { projectFilterQuery } from '../project-filter.js';
import { customerDetailsHtml, customerStatusBadgeClass } from '../detail.js';
import { confirmCancelBooking } from '../booking-actions.js';
import { askConfirm } from '../dialog.js';

export async function loadDemand() {
  state.demandData = await api(`/api/demand-notices${projectFilterQuery()}`);
  $('demand-tbody').innerHTML = state.demandData.length
    ? state.demandData.map((n, idx) => `
      <tr>
        <td class="td-b">${esc(n.customer_name)}</td>
        <td>${esc(n.unit_no)}</td>
        <td class="td-red">${fmt(n.amount)}</td>
        <td><span class="badge ${overdueBadge(n.days_overdue)}">${n.days_overdue}d</span></td>
        <td><button class="btn sm" data-notice-idx="${idx}">Preview</button></td>
      </tr>`).join('')
    : '<tr><td colspan="5" style="text-align:center;color:var(--g400);padding:20px">No overdue notices</td></tr>';

  $('demand-tbody').querySelectorAll('[data-notice-idx]').forEach((btn) => {
    btn.addEventListener('click', () => showNotice(parseInt(btn.dataset.noticeIdx, 10)));
  });
}

function showNotice(idx) {
  const n = state.demandData[idx];
  const fee = Math.round(n.amount * 0.05);
  $('notice-area').innerHTML = `
    <div class="notice">
      <div class="notice-lh">
        <div style="font-size:26px">🏗️</div>
        <div><div style="font-weight:900;font-size:16px;color:var(--navy)">Haven Builders (Pvt.) Ltd.</div>
        <div style="font-size:10.5px;color:var(--g400)">Head Office: Main Blvd, Lahore</div></div>
      </div>
      <div style="font-size:11px;font-weight:700;color:var(--g500);text-align:right;margin-bottom:12px">CNIC: ${esc(n.cnic)}</div>
      <div class="notice-body">
        <p><strong>To:</strong> ${esc(n.customer_name)} &nbsp;|&nbsp; <strong>Unit:</strong> ${esc(n.unit_no)}, ${esc(n.project_name)}</p><br>
        <p>Dear ${esc(n.customer_name)},</p><br>
        <p>This is a formal demand notice for your overdue installment payment.</p><br>
        <table class="notice-table">
          <tr><td>Amount Due</td><td><strong>${fmt(n.amount)}</strong></td></tr>
          <tr><td>Days Overdue</td><td><strong style="color:var(--danger)">${n.days_overdue} Days</strong></td></tr>
          <tr><td>Late Fee (5%)</td><td>${fmt(fee)}</td></tr>
          <tr><td>Total Payable</td><td><strong style="color:var(--danger)">${fmt(n.amount + fee)}</strong></td></tr>
        </table>
        <p>Please clear within <strong>7 working days</strong> to avoid legal action.</p>
      </div>
      <div style="display:flex;gap:8px;margin-top:12px">
        <button class="btn primary" style="flex:1" data-wa>💬 WA</button>
        <button class="btn" style="flex:1" data-email>📧 Email</button>
        <button class="btn" data-pdf>🖨 PDF</button>
      </div>
    </div>`;
  $('notice-area').querySelector('[data-wa]')?.addEventListener('click', () => toast(`WA sent to ${n.customer_name}!`));
  $('notice-area').querySelector('[data-email]')?.addEventListener('click', () => toast('Email sent!'));
  $('notice-area').querySelector('[data-pdf]')?.addEventListener('click', () => toast('PDF downloaded!'));
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
}

function resetCustomerForm() {
  ['nc-id', 'nc-name', 'nc-cnic', 'nc-father', 'nc-phone', 'nc-emergency', 'nc-email', 'nc-address', 'nc-description']
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
  if (!p.name && !p.cnic && !p.phone && !p.father_name && !p.address) {
    box.hidden = true;
    box.innerHTML = '';
    return;
  }
  box.hidden = false;
  const bits = [
    p.father_name ? `S/O ${p.father_name}` : '',
    p.cnic, p.phone, p.emergency_contact_number, p.email,
  ].filter(Boolean);
  box.innerHTML = `
    <h4>Details preview</h4>
    <div class="bk-dname">${esc(p.name || 'New customer')}</div>
    ${bits.length ? `<div class="bk-dsub">${esc(bits.join(' · '))}</div>` : ''}
    ${p.address ? `<div class="bk-dsub" style="margin-top:6px">${esc(p.address)}</div>` : ''}
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
    ].filter(Boolean).join(' ').toLowerCase();
    return blob.includes(s);
  });
}

export function filterCustomers() {
  renderCustomers(filterCustomerRows(state.allCustomers || [], $('cust-search').value));
}

export function initCustomerEvents() {
  $('cust-search')?.addEventListener('input', filterCustomers);
  $('btn-add-customer')?.addEventListener('click', openAddCustomer);
  $('btn-save-customer')?.addEventListener('click', submitCustomer);
  ['nc-name', 'nc-cnic', 'nc-father', 'nc-phone', 'nc-emergency', 'nc-email', 'nc-address', 'nc-description']
    .forEach((id) => $(id)?.addEventListener('input', paintCustomerPreview));
}
