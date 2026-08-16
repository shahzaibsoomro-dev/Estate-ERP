import { $, esc } from './dom.js';
import { api, toast } from './api.js';
import { fmt } from './format.js';
import { closeModal, openModal } from './modal.js';
import { askConfirm } from './dialog.js';

function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function initials(name) {
  return String(name || '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase() || '?';
}

let cancelResolver = null;
let possResolver = null;
let possOutstanding = 0;

export function confirmCancelBooking(bookingId) {
  return (async () => {
    let preview;
    try {
      preview = await api(`/api/bookings/${bookingId}/cancel-preview`);
    } catch {
      return false;
    }
    $('cancel-bk-id').value = String(bookingId);
    if ($('cancel-bk-reason')) $('cancel-bk-reason').value = '';
    $('cancel-bk-summary').innerHTML = `
      <div class="bk-dname">${esc(preview.booking_no || `Booking ${bookingId}`)}</div>
      <div class="sum-row"><span class="sum-lbl">Paid so far</span><span class="sum-val">${fmt(preview.total_paid)}</span></div>
      <div class="sum-row"><span class="sum-lbl">Forfeit (${preview.forfeit_pct}%)</span><span class="sum-val">${fmt(preview.forfeit_amount)}</span></div>
      <div class="sum-row"><span class="sum-lbl">Refund (not auto-posted)</span><span class="sum-val">${fmt(preview.refund_amount)}</span></div>
      <div style="font-size:11px;color:var(--g400);margin-top:8px">Unit becomes available. Unpaid installments are cancelled. Agent commission is reversed.</div>`;
    openModal('cancel-bk-modal');
    return await new Promise((resolve) => { cancelResolver = resolve; });
  })();
}

export function confirmPossession(unitId, outstanding) {
  possOutstanding = outstanding || 0;
  $('poss-unit-id').value = String(unitId);
  if ($('poss-date')) $('poss-date').value = todayISO();
  $('poss-summary').innerHTML = possOutstanding > 0
    ? `<div class="sum-row"><span class="sum-lbl">Outstanding</span><span class="sum-val td-red">${fmt(possOutstanding)}</span></div>
       <div style="font-size:11px;color:var(--g400);margin-top:8px">Possession can still be recorded while dues remain.</div>`
    : `<div style="font-size:12px;color:var(--g500)">Mark this unit as possession delivered.</div>`;
  openModal('poss-modal');
  return new Promise((resolve) => { possResolver = resolve; });
}

export function initCancelPossEvents() {
  $('btn-confirm-cancel-bk')?.addEventListener('click', async () => {
    const bookingId = parseInt($('cancel-bk-id').value, 10);
    if (!bookingId) return;
    if (!await askConfirm('Cancel this booking? This cannot be undone.', {
      title: 'Cancel booking', confirmLabel: 'Cancel booking', danger: true,
    })) return;
    try {
      await api(`/api/bookings/${bookingId}/cancel`, {
        method: 'POST',
        body: JSON.stringify({ reason: ($('cancel-bk-reason')?.value || '').trim() || null }),
      });
      closeModal('cancel-bk-modal');
      toast('Booking cancelled');
      if (cancelResolver) cancelResolver(true);
    } catch {
      if (cancelResolver) cancelResolver(false);
    }
    cancelResolver = null;
  });
  document.querySelector('[data-close-modal="cancel-bk-modal"]')?.addEventListener('click', () => {
    if (cancelResolver) cancelResolver(false);
    cancelResolver = null;
  });
  $('btn-confirm-poss')?.addEventListener('click', async () => {
    const unitId = parseInt($('poss-unit-id').value, 10);
    if (!unitId) return;
    if (possOutstanding > 0) {
      if (!await askConfirm(`Outstanding is still ${fmt(possOutstanding)}. Mark possession anyway?`, {
        title: 'Outstanding balance', confirmLabel: 'Mark possession',
      })) return;
    }
    try {
      await api(`/api/units/${unitId}/possession`, {
        method: 'POST',
        body: JSON.stringify({ possession_date: $('poss-date')?.value || todayISO() }),
      });
      closeModal('poss-modal');
      toast('Possession recorded');
      if (possResolver) possResolver(true);
    } catch {
      if (possResolver) possResolver(false);
    }
    possResolver = null;
  });
  document.querySelector('[data-close-modal="poss-modal"]')?.addEventListener('click', () => {
    if (possResolver) possResolver(false);
    possResolver = null;
  });
}

let xferCustomers = [];
let xferExcludeId = null;
let xferSelectedId = null;

function hideXferMenu() {
  const menu = $('xfer-menu');
  if (menu) menu.hidden = true;
  $('xfer-combo')?.classList.remove('open');
}

function showXferMenu() {
  const menu = $('xfer-menu');
  if (!menu) return;
  menu.hidden = false;
  $('xfer-combo')?.classList.add('open');
}

function paintXferMenu() {
  const menu = $('xfer-menu');
  if (!menu) return;
  const typed = ($('xfer-q')?.value || '').trim().toLowerCase();
  const selected = xferCustomers.find((c) => c.id === xferSelectedId);
  const q = (selected && typed === (selected.name || '').toLowerCase()) ? '' : typed;
  const rows = xferCustomers.filter((c) => {
    if (xferExcludeId && c.id === xferExcludeId) return false;
    if (!q) return true;
    return [c.name, c.cnic, c.phone, c.contact_number, c.father_name, c.nok_name, c.nok_phone, c.nok_cnic]
      .filter(Boolean).join(' ').toLowerCase().includes(q);
  });
  if (!rows.length) {
    menu.innerHTML = '<div class="bk-opt-empty">No match</div>';
    return;
  }
  menu.innerHTML = rows.map((c) => {
    const sub = [c.cnic, c.phone || c.contact_number].filter(Boolean).join(' · ');
    return `<button type="button" class="bk-opt${c.id === xferSelectedId ? ' active' : ''}" data-xfer-id="${c.id}">
      <span class="bk-av">${esc(initials(c.name))}</span>
      <span class="bk-opt-text">
        <span class="bk-opt-title">${esc(c.name)}</span>
        ${sub ? `<span class="bk-opt-sub">${esc(sub)}</span>` : ''}
      </span>
    </button>`;
  }).join('');
}

function pickXferCustomer(id) {
  const c = xferCustomers.find((x) => x.id === id);
  xferSelectedId = id || null;
  if ($('xfer-cust')) $('xfer-cust').value = id ? String(id) : '';
  if ($('xfer-q')) $('xfer-q').value = c?.name || '';
  hideXferMenu();
}

export async function openTransferModal({ bookingId, unitId, currentCustomerId, currentName, unitNo }) {
  $('xfer-bk-id').value = String(bookingId);
  $('xfer-unit-id').value = String(unitId || '');
  xferExcludeId = currentCustomerId || null;
  xferSelectedId = null;
  if ($('xfer-cust')) $('xfer-cust').value = '';
  $('xfer-notes').value = '';
  if ($('xfer-date')) $('xfer-date').value = todayISO();
  if ($('xfer-q')) $('xfer-q').value = '';
  $('xfer-summary').innerHTML = `
    <div class="bk-dname">${esc(unitNo || 'Unit')}</div>
    <div class="sum-row"><span class="sum-lbl">Current owner</span><span class="sum-val">${esc(currentName || '—')}</span></div>`;
  try {
    xferCustomers = await api('/api/customers');
  } catch {
    xferCustomers = [];
  }
  paintXferMenu();
  hideXferMenu();
  openModal('xfer-modal');
}

export function initTransferEvents(onDone) {
  $('xfer-q')?.addEventListener('focus', () => {
    paintXferMenu();
    showXferMenu();
  });
  $('xfer-q')?.addEventListener('input', () => {
    xferSelectedId = null;
    if ($('xfer-cust')) $('xfer-cust').value = '';
    paintXferMenu();
    showXferMenu();
  });
  $('xfer-menu')?.addEventListener('mousedown', (e) => {
    const btn = e.target.closest('[data-xfer-id]');
    if (!btn) return;
    e.preventDefault();
    pickXferCustomer(parseInt(btn.dataset.xferId, 10));
  });
  document.addEventListener('mousedown', (e) => {
    if (!e.target.closest('#xfer-combo')) hideXferMenu();
  });
  $('btn-save-xfer')?.addEventListener('click', async () => {
    const bookingId = parseInt($('xfer-bk-id').value, 10);
    const customerId = parseInt($('xfer-cust').value, 10);
    const unitId = parseInt($('xfer-unit-id').value, 10);
    if (!bookingId || !customerId) {
      toast('Select a registered customer.', 'error');
      return;
    }
    if (!await askConfirm('Transfer this booking to the selected customer?\n\nInstallments and payment history move to the new owner.', {
      title: 'Transfer ownership',
      confirmLabel: 'Transfer',
    })) {
      return;
    }
    try {
      await api(`/api/bookings/${bookingId}/transfer`, {
        method: 'POST',
        body: JSON.stringify({
          customer_id: customerId,
          notes: $('xfer-notes').value.trim() || null,
          transfer_date: $('xfer-date')?.value || todayISO(),
        }),
      });
      closeModal('xfer-modal');
      toast('Ownership transferred');
      if (onDone) await onDone(unitId || null);
    } catch { /* toasted */ }
  });
}
