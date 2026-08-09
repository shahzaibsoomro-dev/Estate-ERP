import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort, overdueBadge } from '../format.js';
import { projectFilterQuery } from '../project-filter.js';
import { openModal, closeModal } from '../modal.js';
import { openCustomerDetail } from './customers.js';
import { loadDashboard } from './dashboard.js';

let recoveryOverdue = [];
let ageFilter = null;

function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function ageBucket(days) {
  if (days <= 30) return 'd30';
  if (days <= 60) return 'd60';
  return 'd90';
}

function ageingFromRows() {
  const out = {
    d30: { count: 0, amount: 0 },
    d60: { count: 0, amount: 0 },
    d90: { count: 0, amount: 0 },
  };
  recoveryOverdue.forEach((o) => {
    const key = ageBucket(o.days_overdue || 0);
    out[key].count += 1;
    out[key].amount += o.amount || 0;
  });
  return out;
}

function filteredOverdue() {
  const q = ($('rec-search')?.value || '').trim().toLowerCase();
  return recoveryOverdue.filter((o) => {
    if (ageFilter && ageBucket(o.days_overdue || 0) !== ageFilter) return false;
    if (!q) return true;
    const blob = [o.customer_name, o.unit_no, o.project_name, o.phone, o.cnic]
      .filter(Boolean).join(' ').toLowerCase();
    return blob.includes(q);
  });
}

export async function loadRecovery() {
  const d = await api(`/api/recovery${projectFilterQuery()}`);
  recoveryOverdue = Array.isArray(d.overdue) ? d.overdue : [];
  if ($('r-recv')) $('r-recv').textContent = fmtShort(d.receivable);
  if ($('r-over')) $('r-over').textContent = fmtShort(d.overdue_amt);
  if ($('r-coll')) $('r-coll').textContent = fmtShort(d.collected_month);
  if ($('r-cases')) $('r-cases').textContent = recoveryOverdue.length;
  paintAgeing(d.ageing && d.ageing.d30 ? d.ageing : ageingFromRows());
  renderRecoveryTable();
}

function paintAgeing(ageing) {
  ['d30', 'd60', 'd90'].forEach((key) => {
    const b = ageing[key] || { count: 0, amount: 0 };
    if ($(`age-${key}-amt`)) $(`age-${key}-amt`).textContent = fmtShort(b.amount);
    if ($(`age-${key}-cnt`)) $(`age-${key}-cnt`).textContent = `${b.count} case${b.count === 1 ? '' : 's'}`;
  });
  document.querySelectorAll('.age-card').forEach((el) => {
    el.classList.toggle('active', el.dataset.age === ageFilter);
  });
}

function renderRecoveryTable() {
  const rows = filteredOverdue();
  const tbody = $('recovery-tbody');
  if (!tbody) return;
  tbody.innerHTML = rows.length
    ? rows.map((o) => {
        const days = o.days_overdue || 0;
        const bucket = ageBucket(days);
        return `
      <tr class="rec-${bucket}">
        <td class="td-b">${esc(o.customer_name)}</td>
        <td>${esc(o.unit_no)}</td>
        <td>${esc(o.project_name)}</td>
        <td class="td-red">${fmt(o.amount)}</td>
        <td>${esc(o.due_date)}</td>
        <td><span class="badge ${overdueBadge(days)}">${days} Days</span></td>
        <td style="font-family:monospace;font-size:11px">${esc(o.phone || '—')}</td>
        <td style="white-space:nowrap">
          <button type="button" class="btn sm" data-rec-view="${o.customer_id}">View</button>
          <button type="button" class="btn sm primary" data-rec-pay="${o.id}">Pay</button>
        </td>
      </tr>`;
      }).join('')
    : `<tr><td colspan="8" style="text-align:center;color:var(--g400);padding:20px">${
      recoveryOverdue.length ? 'No matching installments' : 'No overdue installments'
    }</td></tr>`;

  tbody.querySelectorAll('[data-rec-view]').forEach((btn) => {
    btn.addEventListener('click', () => openCustomerDetail(parseInt(btn.dataset.recView, 10)));
  });
  tbody.querySelectorAll('[data-rec-pay]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const row = recoveryOverdue.find((x) => x.id === parseInt(btn.dataset.recPay, 10));
      if (row) openPayModal(row);
    });
  });
}

function resetPayForm() {
  ['pay-inst-id', 'pay-bk-id', 'pay-cust-id', 'pay-amount', 'pay-ref', 'pay-notes'].forEach((id) => {
    if ($(id)) $(id).value = '';
  });
  if ($('pay-method')) $('pay-method').value = 'Cash';
  if ($('pay-date')) $('pay-date').value = todayISO();
  if ($('pay-summary')) {
    $('pay-summary').hidden = true;
    $('pay-summary').innerHTML = '';
  }
  if ($('pay-pick-wrap')) $('pay-pick-wrap').hidden = true;
  if ($('pay-pick')) $('pay-pick').innerHTML = '<option value="">Select…</option>';
}

function fillPayFromRow(row) {
  $('pay-inst-id').value = String(row.id);
  $('pay-bk-id').value = String(row.booking_id);
  $('pay-cust-id').value = String(row.customer_id);
  $('pay-amount').value = String(row.amount || row.remaining_amount || '');
  $('pay-summary').hidden = false;
  $('pay-summary').innerHTML = `
    <div class="bk-dname">${esc(row.customer_name)}</div>
    <div class="sum-row"><span class="sum-lbl">Unit</span><span class="sum-val">${esc(row.unit_no)} · ${esc(row.project_name)}</span></div>
    <div class="sum-row"><span class="sum-lbl">Due</span><span class="sum-val">${esc(row.due_date)} · ${row.days_overdue || 0}d overdue</span></div>
    <div class="sum-row"><span class="sum-lbl">Remaining</span><span class="sum-val td-red">${fmt(row.amount)}</span></div>`;
}

function openPayModal(row = null) {
  resetPayForm();
  openModal('pay-modal');
  if (row) {
    fillPayFromRow(row);
    return;
  }
  if (!recoveryOverdue.length) {
    closeModal('pay-modal');
    toast('No overdue installments.', 'error');
    return;
  }
  $('pay-pick-wrap').hidden = false;
  $('pay-pick').innerHTML = '<option value="">Select…</option>' + recoveryOverdue.map((o) =>
    `<option value="${o.id}">${esc(o.customer_name)} · ${esc(o.unit_no)} · ${fmt(o.amount)}</option>`).join('');
}

function onPayPickChange() {
  const id = parseInt($('pay-pick')?.value, 10);
  const row = recoveryOverdue.find((x) => x.id === id);
  if (row) fillPayFromRow(row);
  else {
    $('pay-summary').hidden = true;
    ['pay-inst-id', 'pay-bk-id', 'pay-cust-id', 'pay-amount'].forEach((i) => { if ($(i)) $(i).value = ''; });
  }
}

async function submitPayment() {
  const instId = parseInt($('pay-inst-id').value, 10);
  const bkId = parseInt($('pay-bk-id').value, 10);
  const custId = parseInt($('pay-cust-id').value, 10);
  const amount = parseInt($('pay-amount').value, 10);
  const row = recoveryOverdue.find((x) => x.id === instId);
  const due = row?.amount || 0;
  if (!instId || !bkId || !custId) {
    toast('Select an installment.', 'error');
    return;
  }
  if (!amount || amount < 1) {
    toast('Enter a payment amount.', 'error');
    return;
  }
  if (due && amount > due) {
    toast('Amount cannot exceed remaining due.', 'error');
    return;
  }
  const who = row ? `${row.customer_name} / ${row.unit_no}` : 'this installment';
  if (!confirm(`Record payment of ${fmt(amount)} for ${who}?`)) return;
  try {
    const r = await api('/api/payments', {
      method: 'POST',
      body: JSON.stringify({
        installment_id: instId,
        booking_id: bkId,
        customer_id: custId,
        amount,
        payment_date: $('pay-date').value || todayISO(),
        method: $('pay-method').value || 'Cash',
        reference_number: $('pay-ref').value.trim() || null,
        notes: $('pay-notes').value.trim() || null,
      }),
    });
    closeModal('pay-modal');
    toast(`Payment recorded · ${r.receipt}`);
    await loadRecovery();
    try { await loadDashboard(); } catch { /* badge refresh is best-effort */ }
  } catch {
    /* api() already toasts */
  }
}

export function initRecoveryEvents() {
  $('rec-search')?.addEventListener('input', renderRecoveryTable);
  $('btn-rec-pay')?.addEventListener('click', () => openPayModal(null));
  $('pay-pick')?.addEventListener('change', onPayPickChange);
  $('btn-save-payment')?.addEventListener('click', submitPayment);
  document.querySelectorAll('.age-card').forEach((el) => {
    el.addEventListener('click', () => {
      const key = el.dataset.age;
      ageFilter = ageFilter === key ? null : key;
      paintAgeing(ageingFromRows());
      renderRecoveryTable();
    });
  });
}
