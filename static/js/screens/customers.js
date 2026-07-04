import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, instStatusBadge, overdueBadge } from '../format.js';
import { state } from '../state.js';
import { closeModal, openModal } from '../modal.js';
import { projectFilterQuery } from '../project-filter.js';

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
    : '<tr><td colspan="5" style="text-align:center;color:var(--g400);padding:20px">✅ No overdue notices</td></tr>';

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

export async function loadCustomers() {
  state.allCustomers = await api('/api/customers');
  $('c-total').textContent = state.allCustomers.length;
  $('c-overdue').textContent = state.allCustomers.filter((c) => c.cust_status === 'Overdue').length;
  $('c-cleared').textContent = state.allCustomers.filter((c) => c.cust_status !== 'Overdue').length;
  renderCustomers(state.allCustomers);
}

export function renderCustomers(custs) {
  $('cust-tbody').innerHTML = custs.length
    ? custs.map((c) => `
      <tr>
        <td><div class="td-b">${esc(c.name)}</div><div class="td-sm">${esc(c.phone || '—')}</div></td>
        <td class="td-mono">${esc(c.cnic)}</td>
        <td>${c.units ? c.units.split(',').map((u) => `<span class="badge bg-blue" style="margin:1px">${esc(u.trim())}</span>`).join(' ') : '—'}</td>
        <td>${c.total_value ? fmt(c.total_value) : '—'}</td>
        <td class="td-green">${fmt(c.total_paid)}</td>
        <td class="${c.outstanding > 0 ? 'td-red' : 'td-green'}">${fmt(c.outstanding)}</td>
        <td class="td-sm">${esc(c.last_payment || '—')}</td>
        <td><span class="badge ${c.cust_status === 'Overdue' ? 'bg-red' : c.cust_status === 'Cleared' ? 'bg-green' : 'bg-blue'}">${esc(c.cust_status || '—')}</span></td>
        <td style="white-space:nowrap">
          <button class="btn sm" data-stmt="${esc(c.name)}">Stmt</button>
          ${!c.units && !c.total_paid ? `<button class="btn sm danger" data-delete-customer="${c.id}">Delete</button>` : ''}
        </td>
      </tr>`).join('')
    : '<tr><td colspan="9" style="text-align:center;color:var(--g400);padding:20px">No customers found</td></tr>';

  $('cust-tbody').querySelectorAll('[data-stmt]').forEach((btn) => {
    btn.addEventListener('click', () => toast(`Statement for ${btn.dataset.stmt} downloaded!`));
  });
  $('cust-tbody').querySelectorAll('[data-delete-customer]').forEach((btn) => {
    btn.addEventListener('click', () => deleteCustomer(parseInt(btn.dataset.deleteCustomer, 10)));
  });
}

async function deleteCustomer(id) {
  const c = state.allCustomers.find((x) => x.id === id);
  const name = c?.name || 'Customer';
  if (!confirm(`Delete customer "${name}"?\n\nOnly customers with no bookings or payments can be deleted.`)) return;
  await api(`/api/customers/${id}`, { method: 'DELETE' });
  toast(`Customer "${name}" deleted`);
  loadCustomers();
}

export function filterCustomers() {
  const q = $('cust-search').value.toLowerCase();
  renderCustomers(state.allCustomers.filter((c) =>
    c.name.toLowerCase().includes(q) || (c.cnic && c.cnic.includes(q))));
}

export function openAddCustomer() {
  openModal('cust-modal');
}

export async function submitCustomer() {
  const name = $('nc-name').value.trim();
  const cnic = $('nc-cnic').value.trim();
  if (!name || !cnic) {
    toast('Name and CNIC required', 'error');
    return;
  }
  await api('/api/customers', {
    method: 'POST',
    body: JSON.stringify({
      name,
      cnic,
      phone: $('nc-phone').value,
      email: $('nc-email').value,
      address: $('nc-address').value,
    }),
  });
  closeModal('cust-modal');
  toast('✅ Customer added!');
  loadCustomers();
}

export function initCustomerEvents() {
  $('cust-search')?.addEventListener('input', filterCustomers);
  $('btn-add-customer')?.addEventListener('click', openAddCustomer);
  $('btn-save-customer')?.addEventListener('click', submitCustomer);
}
