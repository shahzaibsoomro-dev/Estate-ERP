import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort } from '../format.js';

export async function loadProcurement() {
  const pos = await api('/api/purchase-orders');
  $('po-total').textContent = pos.length;
  $('po-draft').textContent = pos.filter((p) => p.status === 'draft' || p.status === 'approved').length;
  $('po-done').textContent = pos.filter((p) => p.status === 'completed').length;
  $('po-pay').textContent = pos.filter((p) => p.status === 'payment_pending').length;

  $('po-tbody').innerHTML = pos.map((p) => `
    <tr>
      <td class="td-mono">${esc(p.po_no)}</td>
      <td class="td-b">${esc(p.vendor_name)}</td>
      <td>${esc(p.material)}</td>
      <td>${esc(p.qty || p.quantity || '—')}</td>
      <td>${fmt(p.total)}</td>
      <td>${esc(p.site || '—')}</td>
      <td><span class="badge ${p.grn_status === 'done' ? 'bg-green' : p.grn_status === 'na' ? 'bg-grey' : 'bg-yellow'}">${esc(p.grn_status)}</span></td>
      <td><span class="badge ${p.status === 'completed' ? 'bg-green' : p.status === 'payment_pending' ? 'bg-red' : p.status === 'approved' ? 'bg-blue' : 'bg-grey'}">${esc(p.status)}</span></td>
      <td>${poActions(p)}</td>
    </tr>`).join('');

  $('po-tbody').querySelectorAll('[data-approve-po]').forEach((btn) => {
    btn.addEventListener('click', () => approvePO(parseInt(btn.dataset.approvePo, 10)));
  });
  $('po-tbody').querySelectorAll('[data-grn]').forEach((btn) => {
    btn.addEventListener('click', () => toast('GRN recorded!'));
  });
  $('po-tbody').querySelectorAll('[data-pay-po]').forEach((btn) => {
    btn.addEventListener('click', () => toast('Payment recorded!'));
  });
}

function poActions(p) {
  if (p.status === 'draft') return `<button class="btn sm primary" data-approve-po="${p.id}">Approve</button>`;
  if (p.status === 'approved') return `<button class="btn sm" data-grn>GRN</button>`;
  if (p.status === 'payment_pending') return `<button class="btn sm danger" data-pay-po>Pay</button>`;
  return '';
}

async function approvePO(id) {
  await api(`/api/purchase-orders/${id}/status`, {
    method: 'PUT',
    body: JSON.stringify({ status: 'approved' }),
  });
  toast('✅ PO approved!');
  loadProcurement();
}

export async function loadVendors() {
  const vendors = await api('/api/vendors');
  const totalPay = vendors.reduce((a, v) => a + v.total_payable, 0);
  const totalPaid = vendors.reduce((a, v) => a + v.total_paid, 0);
  $('v-payable').textContent = fmtShort(totalPay);
  $('v-paid').textContent = fmtShort(totalPaid);
  $('v-bal').textContent = fmtShort(totalPay - totalPaid);

  $('vendor-tbody').innerHTML = vendors.map((v) => {
    const rating = v.rating || 4;
    return `
    <tr>
      <td class="td-b">${esc(v.name)}</td>
      <td>${esc(v.category || '—')}</td>
      <td>${fmt(v.total_payable)}</td>
      <td class="td-green">${fmt(v.total_paid)}</td>
      <td class="${v.balance > 0 ? 'td-red' : 'td-green'}">${fmt(v.balance)}</td>
      <td>${'⭐'.repeat(Math.min(rating, 5))}</td>
      <td><span class="badge ${v.balance <= 0 ? 'bg-green' : v.balance > 5000000 ? 'bg-red' : 'bg-yellow'}">${v.balance <= 0 ? 'Clear' : v.balance > 5000000 ? 'Overdue' : 'Due'}</span></td>
    </tr>`;
  }).join('');
}
