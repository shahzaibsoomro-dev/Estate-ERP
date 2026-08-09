import { $, esc, loadingHtml } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort } from '../format.js';
import { state } from '../state.js';
import { openModal, closeModal } from '../modal.js';
import { projectFilterQuery } from '../project-filter.js';

let allVendors = [];
let allPOs = [];
let vpayMax = null;

function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function vendorBadge(v) {
  if ((v.status || '').toLowerCase() === 'inactive') return ['bg-grey', 'Inactive'];
  if ((v.balance || 0) <= 0) return ['bg-green', 'Clear'];
  return ['bg-yellow', 'Due'];
}

function poStatusBadge(status) {
  if (status === 'completed') return 'bg-green';
  if (status === 'payment_pending') return 'bg-red';
  if (status === 'approved') return 'bg-blue';
  return 'bg-grey';
}

function grnLabel(g) {
  if (g === 'done') return 'Done';
  if (g === 'na') return '—';
  return 'Pending';
}

/* ---------- Vendors ---------- */

export async function loadVendors() {
  allVendors = await api('/api/vendors');
  const totalPay = allVendors.reduce((a, v) => a + (v.total_payable || 0), 0);
  const totalPaid = allVendors.reduce((a, v) => a + (v.total_paid || 0), 0);
  if ($('v-payable')) $('v-payable').textContent = fmtShort(totalPay);
  if ($('v-paid')) $('v-paid').textContent = fmtShort(totalPaid);
  if ($('v-bal')) $('v-bal').textContent = fmtShort(totalPay - totalPaid);
  renderVendors();
}

function filteredVendors() {
  const q = ($('vendor-search')?.value || '').trim().toLowerCase();
  if (!q) return allVendors;
  return allVendors.filter((v) =>
    [v.name, v.category, v.contact, v.description].filter(Boolean).join(' ').toLowerCase().includes(q));
}

function renderVendors() {
  const rows = filteredVendors();
  const tbody = $('vendor-tbody');
  if (!tbody) return;
  tbody.innerHTML = rows.length
    ? rows.map((v) => {
        const [cls, label] = vendorBadge(v);
        return `
      <tr>
        <td class="td-b">${esc(v.name)}</td>
        <td>${esc(v.category || '—')}</td>
        <td>${esc(v.contact || '—')}</td>
        <td>${fmt(v.total_payable)}</td>
        <td class="td-green">${fmt(v.total_paid)}</td>
        <td class="${v.balance > 0 ? 'td-red' : 'td-green'}">${fmt(v.balance)}</td>
        <td><span class="badge ${cls}">${esc(label)}</span></td>
        <td style="white-space:nowrap">
          <button type="button" class="btn sm" data-v-view="${v.id}">View</button>
          <button type="button" class="btn sm" data-v-edit="${v.id}">Edit</button>
          <button type="button" class="btn sm danger" data-v-del="${v.id}">Delete</button>
        </td>
      </tr>`;
      }).join('')
    : '<tr><td colspan="8" style="text-align:center;color:var(--g400);padding:20px">No vendors found</td></tr>';

  tbody.querySelectorAll('[data-v-view]').forEach((b) => {
    b.addEventListener('click', () => openVendorDetail(parseInt(b.dataset.vView, 10)));
  });
  tbody.querySelectorAll('[data-v-edit]').forEach((b) => {
    b.addEventListener('click', () => openVendorForm(parseInt(b.dataset.vEdit, 10)));
  });
  tbody.querySelectorAll('[data-v-del]').forEach((b) => {
    b.addEventListener('click', () => deleteVendor(parseInt(b.dataset.vDel, 10)));
  });
}

export async function openVendorDetail(id) {
  openModal('vendor-detail-modal');
  $('vd-title').textContent = 'Loading…';
  $('vd-body').innerHTML = loadingHtml('Loading vendor…');
  let v;
  try {
    v = await api(`/api/vendors/${id}`);
  } catch (e) {
    $('vd-body').innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
    return;
  }
  const [cls, label] = vendorBadge(v);
  $('vd-title').textContent = v.name;
  const pos = v.purchase_orders || [];
  const pays = v.payments || [];
  const poRows = pos.length
    ? pos.map((p) => `
        <tr>
          <td class="td-mono">${esc(p.po_no)}</td>
          <td>${esc(p.project_name || '—')}</td>
          <td>${esc(p.material)}</td>
          <td>${fmt(p.total)}</td>
          <td>${fmt(p.paid || 0)}</td>
          <td><span class="badge ${poStatusBadge(p.status)}">${esc(p.status)}</span></td>
        </tr>`).join('')
    : '<tr><td colspan="6" style="text-align:center;color:var(--g400)">No purchase orders</td></tr>';
  const payRows = pays.length
    ? pays.map((p) => `
        <tr>
          <td>${esc(p.payment_date)}</td>
          <td>${esc(p.po_no || '—')}</td>
          <td class="td-green">${fmt(p.amount)}</td>
          <td>${esc(p.payment_method || '—')}</td>
          <td>${esc(p.reference_number || '—')}</td>
        </tr>`).join('')
    : '<tr><td colspan="5" style="text-align:center;color:var(--g400)">No payments</td></tr>';
  $('vd-body').innerHTML = `
    <div class="g2" style="margin-bottom:14px">
      <div>
        <div class="sum-row"><span class="sum-lbl">Category</span><span class="sum-val">${esc(v.category || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Contact</span><span class="sum-val">${esc(v.contact || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Status</span><span class="sum-val"><span class="badge ${cls}">${esc(label)}</span></span></div>
      </div>
      <div>
        <div class="sum-row"><span class="sum-lbl">Payable</span><span class="sum-val">${fmt(v.total_payable)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Paid</span><span class="sum-val">${fmt(v.total_paid)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Balance</span><span class="sum-val">${fmt(v.balance)}</span></div>
      </div>
    </div>
    ${v.description ? `<div class="detail-block" style="margin-bottom:14px"><div class="detail-block-lbl">Notes</div><div class="detail-block-txt">${esc(v.description)}</div></div>` : ''}
    <div class="detail-section-title">Purchase orders</div>
    <div class="tbl-wrap" style="margin-bottom:14px"><table>
      <thead><tr><th>PO #</th><th>Project</th><th>Material</th><th>Total</th><th>Paid</th><th>Status</th></tr></thead>
      <tbody>${poRows}</tbody>
    </table></div>
    <div class="detail-section-title">Payments</div>
    <div class="tbl-wrap" style="margin-bottom:14px"><table>
      <thead><tr><th>Date</th><th>PO</th><th>Amount</th><th>Method</th><th>Ref</th></tr></thead>
      <tbody>${payRows}</tbody>
    </table></div>
    <div style="display:flex;justify-content:flex-end;gap:8px">
      <button type="button" class="btn" data-v-edit="${v.id}">Edit</button>
      <button type="button" class="btn primary" data-v-pay="${v.id}">Record payment</button>
    </div>`;
  $('vd-body').querySelector('[data-v-edit]')?.addEventListener('click', () => openVendorForm(v.id));
  $('vd-body').querySelector('[data-v-pay]')?.addEventListener('click', () => openVendorPay({ vendor: v }));
}

function resetVendorForm() {
  ['nv-id', 'nv-name', 'nv-category', 'nv-contact', 'nv-description'].forEach((id) => {
    if ($(id)) $(id).value = '';
  });
  if ($('nv-status')) $('nv-status').value = 'active';
  if ($('vendor-modal-title')) $('vendor-modal-title').textContent = 'Add Vendor';
}

export async function openVendorForm(id = null) {
  closeModal('vendor-detail-modal');
  resetVendorForm();
  openModal('vendor-modal');
  if (!id) return;
  $('vendor-modal-title').textContent = 'Edit Vendor';
  try {
    const v = await api(`/api/vendors/${id}`);
    $('nv-id').value = String(v.id);
    $('nv-name').value = v.name || '';
    $('nv-category').value = v.category || '';
    $('nv-contact').value = v.contact || '';
    $('nv-description').value = v.description || '';
    $('nv-status').value = (v.status || 'active').toLowerCase() === 'inactive' ? 'inactive' : 'active';
  } catch {
    closeModal('vendor-modal');
  }
}

async function submitVendor() {
  const payload = {
    name: $('nv-name').value.trim(),
    category: $('nv-category').value.trim(),
    contact: $('nv-contact').value.trim(),
    description: $('nv-description').value.trim(),
    status: $('nv-status').value,
  };
  if (!payload.name) {
    toast('Vendor name is required', 'error');
    return;
  }
  const id = parseInt($('nv-id').value, 10);
  try {
    if (id) {
      await api(`/api/vendors/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      toast('Vendor updated');
    } else {
      await api('/api/vendors', { method: 'POST', body: JSON.stringify(payload) });
      toast('Vendor added');
    }
    closeModal('vendor-modal');
    await loadVendors();
  } catch { /* toasted */ }
}

async function deleteVendor(id) {
  const v = allVendors.find((x) => x.id === id);
  const name = v?.name || 'this vendor';
  let msg = `Delete vendor "${name}"?\n\nThis cannot be undone.`;
  if (v?.total_payable) msg += '\n\nVendors with purchase orders cannot be deleted.';
  if (!confirm(msg)) return;
  try {
    await api(`/api/vendors/${id}`, { method: 'DELETE' });
    toast(`Vendor "${name}" deleted`);
    closeModal('vendor-detail-modal');
    await loadVendors();
  } catch { /* toasted */ }
}

/* ---------- Vendor pay ---------- */

export function openVendorPay({ vendor, po } = {}) {
  if (!vendor && !po) return;
  const vendorId = vendor?.id || po?.vendor_id;
  const remaining = po ? (po.remaining ?? Math.max((po.total || 0) - (po.paid || 0), 0)) : (vendor?.balance || 0);
  if (!po && remaining <= 0) {
    toast('Nothing outstanding for this vendor.', 'error');
    return;
  }
  vpayMax = remaining;
  $('vpay-vendor-id').value = String(vendorId || '');
  $('vpay-po-id').value = po?.id ? String(po.id) : '';
  $('vpay-amount').value = remaining ? String(remaining) : '';
  $('vpay-date').value = todayISO();
  $('vpay-method').value = 'Bank Transfer';
  $('vpay-ref').value = '';
  $('vpay-notes').value = '';
  $('vpay-summary').innerHTML = po
    ? `<div class="bk-dname">${esc(po.po_no)}</div>
       <div class="sum-row"><span class="sum-lbl">Vendor</span><span class="sum-val">${esc(po.vendor_name || vendor?.name || '—')}</span></div>
       <div class="sum-row"><span class="sum-lbl">Remaining</span><span class="sum-val">${fmt(remaining)}</span></div>`
    : `<div class="bk-dname">${esc(vendor.name)}</div>
       <div class="sum-row"><span class="sum-lbl">Outstanding</span><span class="sum-val">${fmt(vendor.balance || 0)}</span></div>`;
  closeModal('vendor-detail-modal');
  closeModal('po-detail-modal');
  openModal('vpay-modal');
}

async function submitVendorPay() {
  const vendorId = parseInt($('vpay-vendor-id').value, 10);
  const poId = parseInt($('vpay-po-id').value, 10);
  const amount = parseInt($('vpay-amount').value, 10);
  if (!vendorId || !amount || amount < 1) {
    toast('Enter a payment amount.', 'error');
    return;
  }
  if (vpayMax != null && vpayMax >= 0 && amount > vpayMax) {
    toast('Amount cannot exceed remaining due.', 'error');
    return;
  }
  if (!confirm(`Record vendor payment of ${fmt(amount)}?`)) return;
  try {
    await api('/api/vendor-payments', {
      method: 'POST',
      body: JSON.stringify({
        vendor_id: vendorId,
        purchase_order_id: poId || null,
        amount,
        payment_date: $('vpay-date').value || todayISO(),
        payment_method: $('vpay-method').value,
        reference_number: $('vpay-ref').value.trim() || null,
        notes: $('vpay-notes').value.trim() || null,
      }),
    });
    closeModal('vpay-modal');
    toast('Payment recorded');
    await loadVendors();
    await loadProcurement();
  } catch { /* toasted */ }
}

/* ---------- Procurement ---------- */

export async function loadProcurement() {
  allPOs = await api(`/api/purchase-orders${projectFilterQuery()}`);
  if ($('po-total')) $('po-total').textContent = allPOs.length;
  if ($('po-draft')) $('po-draft').textContent = allPOs.filter((p) => p.status === 'draft' || p.status === 'approved').length;
  if ($('po-done')) $('po-done').textContent = allPOs.filter((p) => p.status === 'completed').length;
  if ($('po-pay')) $('po-pay').textContent = allPOs.filter((p) => p.status === 'payment_pending').length;
  renderPOs();
}

function filteredPOs() {
  const q = ($('po-search')?.value || '').trim().toLowerCase();
  if (!q) return allPOs;
  return allPOs.filter((p) =>
    [p.po_no, p.vendor_name, p.material, p.project_name, p.site, p.status]
      .filter(Boolean).join(' ').toLowerCase().includes(q));
}

function poNextAction(p) {
  if (p.status === 'draft') {
    return `<button type="button" class="btn sm primary" data-approve-po="${p.id}">Approve</button>`;
  }
  if (p.status === 'approved') {
    return `<button type="button" class="btn sm" data-grn-po="${p.id}">GRN</button>`;
  }
  if (p.status === 'payment_pending') {
    return `<button type="button" class="btn sm primary" data-pay-po="${p.id}">Pay</button>`;
  }
  return '';
}

function renderPOs() {
  const rows = filteredPOs();
  const tbody = $('po-tbody');
  if (!tbody) return;
  tbody.innerHTML = rows.length
    ? rows.map((p) => `
      <tr>
        <td class="td-mono">${esc(p.po_no)}</td>
        <td>${esc(p.order_date || '—')}</td>
        <td class="td-b">${esc(p.vendor_name)}</td>
        <td>${esc(p.material)}</td>
        <td>${esc(p.quantity || p.qty || '—')}</td>
        <td>${fmt(p.total)}</td>
        <td>${esc(p.project_name || '—')}</td>
        <td><span class="badge ${p.grn_status === 'done' ? 'bg-green' : p.grn_status === 'na' ? 'bg-grey' : 'bg-yellow'}">${esc(grnLabel(p.grn_status))}</span></td>
        <td><span class="badge ${poStatusBadge(p.status)}">${esc(p.status)}</span></td>
        <td style="white-space:nowrap">
          <button type="button" class="btn sm" data-po-view="${p.id}">View</button>
          ${poNextAction(p)}
        </td>
      </tr>`).join('')
    : '<tr><td colspan="10" style="text-align:center;color:var(--g400);padding:20px">No purchase orders</td></tr>';

  tbody.querySelectorAll('[data-po-view]').forEach((b) => {
    b.addEventListener('click', () => openPODetail(parseInt(b.dataset.poView, 10)));
  });
  tbody.querySelectorAll('[data-approve-po]').forEach((b) => {
    b.addEventListener('click', () => setPOStatus(parseInt(b.dataset.approvePo, 10), 'approved', 'Approve this PO?'));
  });
  tbody.querySelectorAll('[data-grn-po]').forEach((b) => {
    b.addEventListener('click', () => setPOStatus(parseInt(b.dataset.grnPo, 10), 'grn', 'Record GRN for this PO?'));
  });
  tbody.querySelectorAll('[data-pay-po]').forEach((b) => {
    b.addEventListener('click', () => {
      const po = allPOs.find((x) => x.id === parseInt(b.dataset.payPo, 10));
      if (po) openVendorPay({ po });
    });
  });
}

async function setPOStatus(id, status, msg) {
  if (!confirm(msg)) return;
  try {
    await api(`/api/purchase-orders/${id}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    });
    closeModal('po-detail-modal');
    toast(status === 'grn' ? 'GRN recorded' : 'PO approved');
    await loadProcurement();
    await loadVendors();
  } catch { /* toasted */ }
}

export async function openPODetail(id) {
  openModal('po-detail-modal');
  $('pod-title').textContent = 'Loading…';
  $('pod-body').innerHTML = loadingHtml('Loading PO…');
  let p;
  try {
    p = await api(`/api/purchase-orders/${id}`);
  } catch (e) {
    $('pod-body').innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
    return;
  }
  $('pod-title').textContent = p.po_no;
  $('pod-body').innerHTML = `
    <div class="g2">
      <div>
        <div class="sum-row"><span class="sum-lbl">Vendor</span><span class="sum-val">${esc(p.vendor_name)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Project</span><span class="sum-val">${esc(p.project_name)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Material</span><span class="sum-val">${esc(p.material)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Quantity</span><span class="sum-val">${esc(p.quantity || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Site</span><span class="sum-val">${esc(p.site || '—')}</span></div>
      </div>
      <div>
        <div class="sum-row"><span class="sum-lbl">Date</span><span class="sum-val">${esc(p.order_date || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Total</span><span class="sum-val">${fmt(p.total)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Paid</span><span class="sum-val">${fmt(p.paid || 0)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Remaining</span><span class="sum-val">${fmt(p.remaining || 0)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Status</span><span class="sum-val"><span class="badge ${poStatusBadge(p.status)}">${esc(p.status)}</span></span></div>
      </div>
    </div>
    ${p.notes ? `<div class="detail-block" style="margin-top:12px"><div class="detail-block-lbl">Notes</div><div class="detail-block-txt">${esc(p.notes)}</div></div>` : ''}
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px">
      ${p.status === 'draft' ? `<button type="button" class="btn primary" data-approve-po="${p.id}">Approve</button>` : ''}
      ${p.status === 'approved' ? `<button type="button" class="btn" data-grn-po="${p.id}">GRN</button>` : ''}
      ${p.status === 'payment_pending' ? `<button type="button" class="btn primary" data-pay-po="${p.id}">Pay</button>` : ''}
    </div>`;
  $('pod-body').querySelector('[data-approve-po]')?.addEventListener('click', () => {
    setPOStatus(p.id, 'approved', 'Approve this PO?');
  });
  $('pod-body').querySelector('[data-grn-po]')?.addEventListener('click', () => {
    setPOStatus(p.id, 'grn', 'Record GRN for this PO?');
  });
  $('pod-body').querySelector('[data-pay-po]')?.addEventListener('click', () => openVendorPay({ po: p }));
}

function calcPOTotal() {
  const unit = parseFloat($('npo-unit')?.value);
  const qtyRaw = ($('npo-qty')?.value || '').trim();
  const qtyN = parseFloat(qtyRaw);
  if (Number.isFinite(unit) && Number.isFinite(qtyN) && $('npo-total')) {
    $('npo-total').value = String(Math.round(unit * qtyN));
  }
}

async function openNewPO(prefillVendorId) {
  openModal('po-modal');
  ['npo-material', 'npo-qty', 'npo-unit', 'npo-total', 'npo-site', 'npo-notes'].forEach((id) => {
    if ($(id)) $(id).value = '';
  });
  try {
    const [vendors, categories] = await Promise.all([
      allVendors.length ? allVendors : api('/api/vendors'),
      api('/api/budget/categories'),
    ]);
    if (!allVendors.length) allVendors = vendors;
    const projects = state.projects || [];
    $('npo-vendor').innerHTML = '<option value="">Select…</option>' + vendors.map((v) =>
      `<option value="${v.id}">${esc(v.name)}</option>`).join('');
    $('npo-project').innerHTML = '<option value="">Select…</option>' + projects.map((p) =>
      `<option value="${p.id}">${esc(p.name)}</option>`).join('');
    $('npo-cat').innerHTML = '<option value="">None</option>' + (categories || []).map((c) =>
      `<option value="${c.id}">${esc(c.name)}</option>`).join('');
    if (prefillVendorId) $('npo-vendor').value = String(prefillVendorId);
  } catch { /* form still usable */ }
}

async function submitPO() {
  const vendorId = parseInt($('npo-vendor').value, 10);
  const projectId = parseInt($('npo-project').value, 10);
  const material = $('npo-material').value.trim();
  const total = parseInt($('npo-total').value, 10);
  if (!vendorId || !projectId || !material || !total) {
    toast('Vendor, project, material and total are required.', 'error');
    return;
  }
  const catId = parseInt($('npo-cat').value, 10);
  try {
    await api('/api/purchase-orders', {
      method: 'POST',
      body: JSON.stringify({
        vendor_id: vendorId,
        project_id: projectId,
        material,
        qty: $('npo-qty').value.trim() || null,
        unit_cost: parseInt($('npo-unit').value, 10) || null,
        total,
        site: $('npo-site').value.trim() || null,
        notes: $('npo-notes').value.trim() || null,
        budget_category_id: catId || null,
        category: $('npo-cat').selectedOptions[0]?.text !== 'None'
          ? $('npo-cat').selectedOptions[0]?.text : null,
      }),
    });
    closeModal('po-modal');
    toast('Purchase order created');
    await loadProcurement();
    await loadVendors();
  } catch { /* toasted */ }
}

export function initOperationsEvents() {
  $('vendor-search')?.addEventListener('input', renderVendors);
  $('btn-add-vendor')?.addEventListener('click', () => openVendorForm());
  $('btn-save-vendor')?.addEventListener('click', submitVendor);
  $('btn-save-vpay')?.addEventListener('click', submitVendorPay);
  $('po-search')?.addEventListener('input', renderPOs);
  $('btn-new-po')?.addEventListener('click', () => openNewPO());
  $('btn-save-po')?.addEventListener('click', submitPO);
  $('npo-qty')?.addEventListener('input', calcPOTotal);
  $('npo-unit')?.addEventListener('input', calcPOTotal);
}
