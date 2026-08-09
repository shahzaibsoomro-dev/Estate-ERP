import { $, esc, loadingHtml } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort } from '../format.js';
import { closeModal, openModal } from '../modal.js';
import { askConfirm } from '../dialog.js';

let allAgents = [];
let apayMax = null;

function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function agentBadge(ag) {
  if ((ag.status || '').toLowerCase() === 'inactive') return ['bg-grey', 'Inactive'];
  return ['bg-green', 'Active'];
}

export async function loadAgents() {
  allAgents = await api('/api/agents');
  if ($('ag-total')) $('ag-total').textContent = allAgents.length;
  if ($('ag-earned')) {
    $('ag-earned').textContent = fmtShort(allAgents.reduce((a, ag) => a + (ag.commission_earned || 0), 0));
  }
  if ($('ag-unpaid')) {
    $('ag-unpaid').textContent = fmtShort(allAgents.reduce((a, ag) => a + (ag.commission_unpaid || 0), 0));
  }
  renderAgents();
}

function filteredAgents() {
  const q = ($('agent-search')?.value || '').trim().toLowerCase();
  if (!q) return allAgents;
  return allAgents.filter((ag) =>
    [ag.name, ag.contact, ag.description, ag.category, ag.project].filter(Boolean).join(' ').toLowerCase().includes(q));
}

function renderAgents() {
  const tbody = $('agent-tbody');
  if (!tbody) return;
  const rows = filteredAgents();
  tbody.innerHTML = rows.length
    ? rows.map((ag) => {
        const [cls, label] = agentBadge(ag);
        const unpaid = ag.commission_unpaid || 0;
        return `
      <tr>
        <td class="td-b">${esc(ag.name)}</td>
        <td>${esc(ag.category || '—')}</td>
        <td>${esc(ag.contact || '—')}</td>
        <td title="${esc(ag.description || '')}" style="max-width:220px;white-space:normal;color:var(--g400)">${esc(ag.description || '—')}</td>
        <td>${ag.rate ?? ag.default_rate_pct ?? 0}%</td>
        <td>${ag.bookings_count || 0}</td>
        <td>${fmt(ag.commission_earned)}</td>
        <td class="td-green">${fmt(ag.commission_paid)}</td>
        <td class="${unpaid > 0 ? 'td-red' : 'td-green'}">${fmt(unpaid)}</td>
        <td><span class="badge ${cls}">${esc(label)}</span></td>
        <td style="white-space:nowrap">
          <button type="button" class="btn sm" data-ag-view="${ag.id}">View</button>
          <button type="button" class="btn sm" data-ag-edit="${ag.id}">Edit</button>
          ${unpaid > 0 ? `<button type="button" class="btn sm primary" data-ag-pay="${ag.id}">Pay</button>` : ''}
          <button type="button" class="btn sm danger" data-ag-del="${ag.id}">Delete</button>
        </td>
      </tr>`;
      }).join('')
    : '<tr><td colspan="11" style="text-align:center;color:var(--g400);padding:20px">No agents found</td></tr>';

  tbody.querySelectorAll('[data-ag-view]').forEach((b) => {
    b.addEventListener('click', () => openAgentDetail(parseInt(b.dataset.agView, 10)));
  });
  tbody.querySelectorAll('[data-ag-edit]').forEach((b) => {
    b.addEventListener('click', () => openAgentForm(parseInt(b.dataset.agEdit, 10)));
  });
  tbody.querySelectorAll('[data-ag-del]').forEach((b) => {
    b.addEventListener('click', () => deleteAgent(parseInt(b.dataset.agDel, 10)));
  });
  tbody.querySelectorAll('[data-ag-pay]').forEach((b) => {
    b.addEventListener('click', () => {
      const ag = allAgents.find((x) => x.id === parseInt(b.dataset.agPay, 10));
      if (ag) openAgentPay(ag);
    });
  });
}

export async function openAgentDetail(id) {
  openModal('agent-detail-modal');
  $('ad-title').textContent = 'Loading…';
  $('ad-body').innerHTML = loadingHtml('Loading agent…');
  let ag;
  try {
    ag = await api(`/api/agents/${id}`);
  } catch (e) {
    $('ad-body').innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
    return;
  }
  const [cls, label] = agentBadge(ag);
  $('ad-title').textContent = ag.name;
  const comms = ag.commissions || [];
  const pays = ag.payments || [];
  const commRows = comms.length
    ? comms.map((c) => `
        <tr>
          <td class="td-mono">${esc(c.booking_no)}</td>
          <td>${esc(c.customer_name || '—')}</td>
          <td>${esc(c.unit_no || '—')}</td>
          <td>${c.rate_pct}%</td>
          <td>${fmt(c.commission_amount)}</td>
          <td>${fmt(c.paid_amount)}</td>
          <td><span class="badge ${c.status === 'paid' ? 'bg-green' : c.status === 'reversed' ? 'bg-grey' : c.status === 'partial' ? 'bg-yellow' : 'bg-red'}">${esc(c.status)}</span></td>
        </tr>`).join('')
    : '<tr><td colspan="7" style="text-align:center;color:var(--g400)">No commissions yet</td></tr>';
  const payRows = pays.length
    ? pays.map((p) => `
        <tr>
          <td>${esc(p.payment_date)}</td>
          <td>${esc(p.booking_no || '—')}</td>
          <td class="td-green">${fmt(p.amount)}</td>
          <td>${esc(p.notes || '—')}</td>
        </tr>`).join('')
    : '<tr><td colspan="4" style="text-align:center;color:var(--g400)">No payments</td></tr>';
  $('ad-body').innerHTML = `
    <div class="g2" style="margin-bottom:14px">
      <div>
        <div class="sum-row"><span class="sum-lbl">Contact</span><span class="sum-val">${esc(ag.contact || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Category</span><span class="sum-val">${esc(ag.category || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Rate</span><span class="sum-val">${ag.rate ?? ag.default_rate_pct ?? 0}%</span></div>
        <div class="sum-row"><span class="sum-lbl">Status</span><span class="sum-val"><span class="badge ${cls}">${esc(label)}</span></span></div>
      </div>
      <div>
        <div class="sum-row"><span class="sum-lbl">Payable</span><span class="sum-val">${fmt(ag.commission_earned)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Paid</span><span class="sum-val">${fmt(ag.commission_paid)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Balance</span><span class="sum-val">${fmt(ag.commission_unpaid)}</span></div>
      </div>
    </div>
    <div class="detail-block" style="margin-bottom:14px"><div class="detail-block-lbl">Description</div><div class="detail-block-txt">${esc(ag.description || '—')}</div></div>
    <div class="detail-section-title">Commissions</div>
    <div class="tbl-wrap" style="margin-bottom:14px"><table>
      <thead><tr><th>Booking</th><th>Customer</th><th>Unit</th><th>Rate</th><th>Amount</th><th>Paid</th><th>Status</th></tr></thead>
      <tbody>${commRows}</tbody>
    </table></div>
    <div class="detail-section-title">Payments</div>
    <div class="tbl-wrap" style="margin-bottom:14px"><table>
      <thead><tr><th>Date</th><th>Booking</th><th>Amount</th><th>Notes</th></tr></thead>
      <tbody>${payRows}</tbody>
    </table></div>
    <div style="display:flex;justify-content:flex-end;gap:8px">
      <button type="button" class="btn" data-ag-edit="${ag.id}">Edit</button>
      ${(ag.commission_unpaid || 0) > 0 ? `<button type="button" class="btn primary" data-ag-pay="${ag.id}">Pay</button>` : ''}
    </div>`;
  $('ad-body').querySelector('[data-ag-edit]')?.addEventListener('click', () => openAgentForm(ag.id));
  $('ad-body').querySelector('[data-ag-pay]')?.addEventListener('click', () => openAgentPay(ag));
}

function resetAgentForm() {
  ['na-id', 'na-name', 'na-contact', 'na-category', 'na-description'].forEach((id) => {
    if ($(id)) $(id).value = '';
  });
  if ($('na-rate')) $('na-rate').value = '2';
  if ($('na-status')) $('na-status').value = 'active';
  if ($('agent-modal-title')) $('agent-modal-title').textContent = 'Add Agent';
  if ($('na-computed')) { $('na-computed').hidden = true; $('na-computed').innerHTML = ''; }
}

export async function openAgentForm(id = null) {
  closeModal('agent-detail-modal');
  resetAgentForm();
  openModal('agent-modal');
  if (!id) return;
  $('agent-modal-title').textContent = 'Edit Agent';
  try {
    const ag = await api(`/api/agents/${id}`);
    $('na-id').value = String(ag.id);
    $('na-name').value = ag.name || '';
    $('na-contact').value = ag.contact || '';
    if ($('na-category')) $('na-category').value = ag.category || '';
    $('na-description').value = ag.description || '';
    $('na-rate').value = String(ag.default_rate_pct ?? ag.rate ?? 2);
    $('na-status').value = (ag.status || 'active').toLowerCase() === 'inactive' ? 'inactive' : 'active';
    if ($('na-computed')) {
      $('na-computed').hidden = false;
      $('na-computed').innerHTML = `
        <h4>Computed</h4>
        <div class="sum-row"><span class="sum-lbl">Total payable</span><span class="sum-val">${fmt(ag.commission_earned || 0)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Paid</span><span class="sum-val">${fmt(ag.commission_paid || 0)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Balance</span><span class="sum-val">${fmt(ag.commission_unpaid || 0)}</span></div>`;
    }
  } catch {
    closeModal('agent-modal');
  }
}

async function submitAgent() {
  const payload = {
    name: $('na-name').value.trim(),
    contact: $('na-contact').value.trim(),
    category: ($('na-category')?.value || '').trim(),
    description: $('na-description').value.trim(),
    default_rate_pct: parseFloat($('na-rate').value) || 0,
    status: $('na-status').value,
  };
  if (!payload.name) {
    toast('Agent name is required', 'error');
    return;
  }
  const id = parseInt($('na-id').value, 10);
  try {
    if (id) {
      await api(`/api/agents/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      toast('Agent updated');
    } else {
      await api('/api/agents', { method: 'POST', body: JSON.stringify(payload) });
      toast('Agent added');
    }
    closeModal('agent-modal');
    await loadAgents();
  } catch { /* toasted */ }
}

async function deleteAgent(id) {
  const ag = allAgents.find((x) => x.id === id);
  const name = ag?.name || 'this agent';
  if (!await askConfirm(`Delete agent "${name}"?\n\nAgents with commissions cannot be deleted.`, {
    title: 'Delete agent', confirmLabel: 'Delete', danger: true,
  })) return;
  try {
    await api(`/api/agents/${id}`, { method: 'DELETE' });
    toast(`Agent "${name}" deleted`);
    closeModal('agent-detail-modal');
    await loadAgents();
  } catch { /* toasted */ }
}

export function openAgentPay(ag, commissionId = null) {
  const unpaid = ag.commission_unpaid ?? Math.max((ag.commission_earned || 0) - (ag.commission_paid || 0), 0);
  if (unpaid <= 0) {
    toast('Nothing outstanding for this agent.', 'error');
    return;
  }
  apayMax = unpaid;
  $('apay-agent-id').value = String(ag.id);
  $('apay-comm-id').value = commissionId ? String(commissionId) : '';
  $('apay-amount').value = String(unpaid);
  $('apay-date').value = todayISO();
  $('apay-notes').value = '';
  $('apay-summary').innerHTML = `
    <div class="bk-dname">${esc(ag.name)}</div>
    <div class="sum-row"><span class="sum-lbl">Unpaid commission</span><span class="sum-val">${fmt(unpaid)}</span></div>`;
  closeModal('agent-detail-modal');
  openModal('apay-modal');
}

async function submitAgentPay() {
  const agentId = parseInt($('apay-agent-id').value, 10);
  const amount = parseInt($('apay-amount').value, 10);
  const commId = parseInt($('apay-comm-id').value, 10);
  if (!agentId || !amount || amount < 1) {
    toast('Enter a payment amount.', 'error');
    return;
  }
  if (apayMax != null && amount > apayMax) {
    toast('Amount cannot exceed unpaid commission.', 'error');
    return;
  }
  if (!await askConfirm(`Record agent commission payment of ${fmt(amount)}?`, {
    title: 'Record payment', confirmLabel: 'Record payment',
  })) return;
  try {
    await api(`/api/agents/${agentId}/pay`, {
      method: 'POST',
      body: JSON.stringify({
        amount,
        payment_date: $('apay-date').value || todayISO(),
        notes: $('apay-notes').value.trim() || null,
        commission_id: commId || null,
      }),
    });
    closeModal('apay-modal');
    toast('Commission payment recorded');
    await loadAgents();
  } catch { /* toasted */ }
}

export function initAgentEvents() {
  $('agent-search')?.addEventListener('input', renderAgents);
  $('btn-add-agent')?.addEventListener('click', () => openAgentForm());
  $('btn-save-agent')?.addEventListener('click', submitAgent);
  $('btn-save-apay')?.addEventListener('click', submitAgentPay);
}
