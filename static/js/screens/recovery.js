import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort, overdueBadge } from '../format.js';
import { projectFilterQuery } from '../project-filter.js';
import { openModal, closeModal } from '../modal.js';
import { getCurrentScreen, reloadCurrentScreen } from '../nav.js';
import { openCustomerDetail } from './customers.js';
import { loadDashboard } from './dashboard.js';
import { askConfirm } from '../dialog.js';

let recoveryOverdue = [];
let recoverySoon = [];
let recTab = 'overdue';
let payChoices = [];
let ageFilter = null;
let payContext = null;
let calYear = null;
let calMonth = null;
let calDays = [];
let calSelected = null;

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

function caseBlob(o) {
  return [o.customer_name, o.unit_no, o.project_name, o.phone, o.cnic, o.type, o.trigger_label, o.reason, o.why]
    .filter(Boolean).join(' ').toLowerCase();
}

function filteredCases() {
  const q = ($('rec-search')?.value || '').trim().toLowerCase();
  const source = recTab === 'soon' ? recoverySoon : recoveryOverdue;
  return source.filter((o) => {
    if (recTab === 'overdue' && ageFilter && ageBucket(o.days_overdue || 0) !== ageFilter) return false;
    if (!q) return true;
    return caseBlob(o).includes(q);
  });
}

export async function loadRecovery() {
  const d = await api(`/api/recovery${projectFilterQuery()}`);
  recoveryOverdue = Array.isArray(d.overdue) ? d.overdue : [];
  recoverySoon = Array.isArray(d.due_soon) ? d.due_soon : [];
  if ($('r-recv')) $('r-recv').textContent = fmtShort(d.receivable);
  if ($('r-over')) $('r-over').textContent = fmtShort(d.overdue_amt);
  if ($('r-coll')) $('r-coll').textContent = fmtShort(d.collected_month);
  if ($('r-cases')) $('r-cases').textContent = recoveryOverdue.length;
  paintAgeing(d.ageing && d.ageing.d30 ? d.ageing : ageingFromRows());
  syncRecTabs();
  renderRecoveryTable();
  await loadCalendar();
}

function ensureCalMonth() {
  if (calYear && calMonth) return;
  const n = new Date();
  calYear = n.getFullYear();
  calMonth = n.getMonth() + 1;
}

async function loadCalendar() {
  if (!$('rec-calendar')) return;
  ensureCalMonth();
  const extra = projectFilterQuery();
  const url = `/api/recovery/calendar?year=${calYear}&month=${calMonth}${extra ? `&${extra.slice(1)}` : ''}`;
  try {
    const d = await api(url);
    calDays = d.days || [];
  } catch {
    calDays = [];
  }
  renderCalendar();
}

function renderCalendar() {
  const grid = $('rec-calendar');
  if (!grid) return;
  const label = $('cal-label');
  if (label) {
    label.textContent = new Date(calYear, calMonth - 1, 1).toLocaleString('en-GB', {
      month: 'long', year: 'numeric',
    });
  }
  const byDate = {};
  calDays.forEach((d) => { byDate[d.date] = d; });
  const first = new Date(calYear, calMonth - 1, 1);
  const startDow = first.getDay();
  const daysInMonth = new Date(calYear, calMonth, 0).getDate();
  const today = todayISO();
  const dow = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  let html = dow.map((n) => `<div class="cal-dow">${n}</div>`).join('');
  for (let i = 0; i < startDow; i += 1) html += '<div class="cal-cell empty"></div>';
  for (let day = 1; day <= daysInMonth; day += 1) {
    const iso = `${calYear}-${String(calMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const bucket = byDate[iso];
    const cls = [
      'cal-cell',
      bucket ? 'has-due' : '',
      iso === today ? 'today' : '',
      calSelected === iso ? 'today' : '',
    ].filter(Boolean).join(' ');
    html += `<button type="button" class="${cls}" data-cal-day="${iso}">
      <div class="cal-day">${day}</div>
      ${bucket ? `<div class="cal-meta">${bucket.count} · ${fmtShort(bucket.amount)}</div>` : ''}
    </button>`;
  }
  grid.innerHTML = html;
  grid.querySelectorAll('[data-cal-day]').forEach((btn) => {
    btn.addEventListener('click', () => showCalDay(btn.dataset.calDay));
  });
  if (calSelected) showCalDay(calSelected);
  else if ($('cal-day-list')) $('cal-day-list').hidden = true;
}

function showCalDay(iso) {
  calSelected = iso;
  const box = $('cal-day-list');
  if (!box) return;
  const bucket = calDays.find((d) => d.date === iso);
  if (!bucket || !bucket.items?.length) {
    box.hidden = true;
    box.innerHTML = '';
    return;
  }
  box.hidden = false;
  box.innerHTML = `
    <div style="font-weight:800;font-size:13px;margin-bottom:8px">Due ${esc(iso)}</div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Customer</th><th>Unit</th><th>Type</th><th>Due</th><th></th></tr></thead>
      <tbody>${bucket.items.map((i) => `
        <tr>
          <td class="td-b">${esc(i.customer_name)}</td>
          <td>${esc(i.unit_no)}</td>
          <td>${esc(i.type || '—')}</td>
          <td class="td-red">${fmt(i.amount)}</td>
          <td><button type="button" class="btn sm primary" data-cal-pay="${i.id}">Pay</button></td>
        </tr>`).join('')}
      </tbody>
    </table></div>`;
  box.querySelectorAll('[data-cal-pay]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const row = bucket.items.find((x) => x.id === parseInt(btn.dataset.calPay, 10));
      if (row) openPayForInstallment(row);
    });
  });
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

function findCase(id) {
  return recoveryOverdue.find((x) => x.id === id)
    || recoverySoon.find((x) => x.id === id)
    || payChoices.find((x) => x.id === id)
    || null;
}

function syncRecTabs() {
  document.querySelectorAll('[data-rec-tab]').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.recTab === recTab);
  });
  const hint = $('rec-tab-hint');
  if (hint) {
    hint.textContent = recTab === 'soon'
      ? `${recoverySoon.length} installment${recoverySoon.length === 1 ? '' : 's'} still upcoming this month`
      : `${recoveryOverdue.length} overdue installment${recoveryOverdue.length === 1 ? '' : 's'}`;
  }
  document.querySelectorAll('.age-card').forEach((el) => {
    el.disabled = recTab === 'soon';
    el.classList.toggle('is-dim', recTab === 'soon');
  });
}

function renderRecoveryTable() {
  const rows = filteredCases();
  const tbody = $('recovery-tbody');
  if (!tbody) return;
  const empty = recTab === 'soon'
    ? (recoverySoon.length ? 'No matching upcoming installments' : 'Nothing else due this month')
    : (recoveryOverdue.length ? 'No matching installments' : 'No overdue installments');
  tbody.innerHTML = rows.length
    ? rows.map((o) => {
        const days = o.days_overdue || 0;
        const bucket = recTab === 'overdue' ? ageBucket(days) : '';
        const when = o.when || (recTab === 'overdue'
          ? `${days}d overdue · ${o.due_date || ''}`
          : o.due_date || '—');
        return `
      <tr class="${bucket ? `rec-${bucket}` : ''}">
        <td>
          <div class="td-b">${esc(o.customer_name)}</div>
          <div class="td-sm">${esc(o.phone || '—')}</div>
        </td>
        <td>
          <div>${esc(o.unit_no)}</div>
          <div class="td-sm">${esc(o.project_name || '')}</div>
        </td>
        <td class="rec-why">
          <div>${esc(o.why || o.trigger_label || o.type || 'Installment')}</div>
          <div class="td-sm">${esc(o.what || '')}</div>
        </td>
        <td class="${recTab === 'overdue' ? 'td-red' : ''}">${fmt(o.amount)}</td>
        <td>${recTab === 'overdue'
          ? `<span class="badge ${overdueBadge(days)}">${esc(when)}</span>`
          : esc(when)}</td>
        <td style="white-space:nowrap">
          <button type="button" class="btn sm primary" data-rec-pay="${o.id}">Pay</button>
          ${recTab === 'overdue' ? `<button type="button" class="btn sm" data-rec-notice="${o.id}">Notice</button>` : ''}
          <button type="button" class="btn sm" data-rec-view="${o.customer_id}">View</button>
        </td>
      </tr>`;
      }).join('')
    : `<tr><td colspan="6" style="text-align:center;color:var(--g400);padding:20px">${empty}</td></tr>`;

  tbody.querySelectorAll('[data-rec-view]').forEach((btn) => {
    btn.addEventListener('click', () => openCustomerDetail(parseInt(btn.dataset.recView, 10)));
  });
  tbody.querySelectorAll('[data-rec-pay]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const row = findCase(parseInt(btn.dataset.recPay, 10));
      if (row) openPayModal(row);
    });
  });
  tbody.querySelectorAll('[data-rec-notice]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const row = findCase(parseInt(btn.dataset.recNotice, 10));
      if (!row) return;
      const { openGenerate } = await import('./documents.js');
      await openGenerate({ customerId: row.customer_id, bookingId: row.booking_id, kind: 'notice' });
    });
  });
}

function resetPayForm() {
  payContext = null;
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
    <div class="sum-row"><span class="sum-lbl">Why</span><span class="sum-val">${esc(row.why || row.trigger_label || row.type || 'Installment')}</span></div>
    <div class="sum-row"><span class="sum-lbl">When</span><span class="sum-val">${esc(row.when || row.due_date || '—')}</span></div>
    <div class="sum-row"><span class="sum-lbl">Remaining</span><span class="sum-val td-red">${fmt(row.amount)}</span></div>`;
}

export function openPayForInstallment(row) {
  resetPayForm();
  payContext = row;
  fillPayFromRow(row);
  openModal('pay-modal');
}

async function loadPayChoices() {
  const seen = new Map();
  recoveryOverdue.forEach((o) => seen.set(o.id, o));
  const now = new Date();
  for (let i = 0; i < 3; i++) {
    let y = now.getFullYear();
    let m = now.getMonth() + 1 + i;
    if (m > 12) { m -= 12; y += 1; }
    try {
      const cal = await api(`/api/recovery/calendar?year=${y}&month=${m}${projectFilterQuery()}`);
      for (const day of cal.days || []) {
        for (const item of day.items || []) {
          if (!seen.has(item.id)) seen.set(item.id, item);
        }
      }
    } catch { /* ignore */ }
  }
  return [...seen.values()];
}

async function openPayModal(row = null) {
  resetPayForm();
  openModal('pay-modal');
  if (row) {
    payContext = row;
    fillPayFromRow(row);
    return;
  }
  payChoices = await loadPayChoices();
  if (!payChoices.length) {
    closeModal('pay-modal');
    toast('No upcoming or overdue installments.', 'error');
    return;
  }
  $('pay-pick-wrap').hidden = false;
  $('pay-pick').innerHTML = '<option value="">Select…</option>' + payChoices.map((o) =>
    `<option value="${o.id}">${esc(o.customer_name)} · ${esc(o.unit_no)} · ${fmt(o.amount || o.amount_due || 0)}</option>`).join('');
}

function onPayPickChange() {
  const id = parseInt($('pay-pick')?.value, 10);
  const row = payChoices.find((x) => x.id === id) || recoveryOverdue.find((x) => x.id === id);
  if (row) {
    payContext = row;
    fillPayFromRow(row);
  }
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
  const row = findCase(instId) || (payContext && payContext.id === instId ? payContext : null);
  const due = row?.amount || row?.remaining_amount || 0;
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
  if (!await askConfirm(`Record payment of ${fmt(amount)} for ${who}?`, {
    title: 'Record payment',
    confirmLabel: 'Record payment',
  })) return;
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
    if (getCurrentScreen() === 'portal') reloadCurrentScreen();
  } catch {
    /* api() already toasts */
  }
}

export function initRecoveryEvents() {
  $('rec-search')?.addEventListener('input', renderRecoveryTable);
  document.querySelectorAll('[data-rec-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      recTab = btn.dataset.recTab || 'overdue';
      if (recTab === 'soon') ageFilter = null;
      syncRecTabs();
      paintAgeing(ageingFromRows());
      renderRecoveryTable();
    });
  });
  $('btn-rec-pay')?.addEventListener('click', () => { openPayModal(null); });
  $('pay-pick')?.addEventListener('change', onPayPickChange);
  $('btn-save-payment')?.addEventListener('click', submitPayment);
  $('cal-prev')?.addEventListener('click', () => {
    ensureCalMonth();
    calMonth -= 1;
    if (calMonth < 1) { calMonth = 12; calYear -= 1; }
    calSelected = null;
    loadCalendar();
  });
  $('cal-next')?.addEventListener('click', () => {
    ensureCalMonth();
    calMonth += 1;
    if (calMonth > 12) { calMonth = 1; calYear += 1; }
    calSelected = null;
    loadCalendar();
  });
  document.querySelectorAll('.age-card').forEach((el) => {
    el.addEventListener('click', () => {
      const key = el.dataset.age;
      ageFilter = ageFilter === key ? null : key;
      paintAgeing(ageingFromRows());
      renderRecoveryTable();
    });
  });
}
