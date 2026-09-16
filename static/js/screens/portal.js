import { $, esc } from '../dom.js';
import { api } from '../api.js';
import { fmt, instStatusBadge } from '../format.js';
import { openModal } from '../modal.js';
import { parseAttrList } from '../detail.js';
import { openPayForInstallment } from './recovery.js';

const STORE_KEY = 'havenPortalCustomerId';

let portalCustomers = [];
let portalData = null;
let activeBookingId = null;
let selectedCustomerId = null;

function floorLabel(n) {
  if (n == null || n === '') return '—';
  const v = Number(n);
  if (v === 0) return 'Ground';
  if (v === 1) return '1st';
  if (v === 2) return '2nd';
  if (v === 3) return '3rd';
  return `${v}th`;
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

function hidePortalMenu() {
  const menu = $('portal-cust-menu');
  if (menu) menu.hidden = true;
  $('portal-combo-cust')?.classList.remove('open');
}

function showPortalMenu() {
  const menu = $('portal-cust-menu');
  if (!menu) return;
  menu.hidden = false;
  $('portal-combo-cust')?.classList.add('open');
}

function paintPortalCustomers() {
  const menu = $('portal-cust-menu');
  if (!menu) return;
  const typed = ($('portal-cust-q')?.value || '').trim().toLowerCase();
  const selected = portalCustomers.find((c) => c.id === selectedCustomerId);
  const q = (selected && typed === (selected.name || '').toLowerCase()) ? '' : typed;
  const rows = portalCustomers.filter((c) => {
    if (!q) return true;
    return [c.name, c.cnic, c.phone, c.father_name, c.nok_name, c.nok_phone, c.nok_cnic]
      .filter(Boolean).join(' ').toLowerCase().includes(q);
  });
  if (!rows.length) {
    menu.innerHTML = '<div class="bk-opt-empty">No booked customer matches</div>';
    return;
  }
  menu.innerHTML = rows.map((c) => {
    const sub = [c.cnic, c.phone, c.booking_count ? `${c.booking_count} booking(s)` : '']
      .filter(Boolean).join(' · ');
    return `<button type="button" class="bk-opt${c.id === selectedCustomerId ? ' active' : ''}" data-portal-id="${c.id}">
      <span class="bk-av">${esc(initials(c.name))}</span>
      <span class="bk-opt-text">
        <span class="bk-opt-title">${esc(c.name)}</span>
        ${sub ? `<span class="bk-opt-sub">${esc(sub)}</span>` : ''}
      </span>
    </button>`;
  }).join('');
}

export async function loadPortal() {
  try {
    portalCustomers = await api('/api/portal');
  } catch {
    portalCustomers = [];
  }
  const saved = parseInt(sessionStorage.getItem(STORE_KEY) || '', 10);
  const pick = (selectedCustomerId && portalCustomers.some((c) => c.id === selectedCustomerId))
    ? selectedCustomerId
    : (saved && portalCustomers.some((c) => c.id === saved) ? saved : null);
  paintPortalCustomers();
  if (pick) {
    await pickPortalCustomer(pick, false);
  } else {
    selectedCustomerId = null;
    if ($('portal-cust-q')) $('portal-cust-q').value = '';
    showEmpty(portalCustomers.length ? 'Search and select a booked customer' : 'No booked customers yet');
  }
}

function showEmpty(msg) {
  portalData = null;
  if ($('portal-empty')) {
    $('portal-empty').hidden = false;
    $('portal-empty').textContent = msg;
  }
  if ($('portal-body')) $('portal-body').hidden = true;
  if ($('portal-booking')) $('portal-booking').hidden = true;
}

async function pickPortalCustomer(customerId, fromMenu = true) {
  const row = portalCustomers.find((c) => c.id === customerId);
  selectedCustomerId = customerId || null;
  if ($('portal-cust-q')) $('portal-cust-q').value = row?.name || '';
  hidePortalMenu();
  if (!customerId) {
    showEmpty('Search and select a booked customer');
    return;
  }
  await showCustomer(customerId);
  if (fromMenu) paintPortalCustomers();
}

async function showCustomer(customerId) {
  if (!customerId) {
    showEmpty('Search and select a booked customer');
    return;
  }
  try {
    portalData = await api(`/api/portal?customer_id=${customerId}`);
  } catch {
    showEmpty('Could not load portal');
    return;
  }
  sessionStorage.setItem(STORE_KEY, String(customerId));
  const bookings = portalData.bookings || [];
  if (!bookings.length) {
    showEmpty('This customer has no active booking');
    return;
  }
  const bkSel = $('portal-booking');
  if (bkSel) {
    bkSel.hidden = bookings.length < 2;
    bkSel.innerHTML = bookings.map((b) =>
      `<option value="${b.id}">${esc(b.unit_no)} · ${esc(b.project_name)}</option>`).join('');
    const keep = bookings.some((b) => b.id === activeBookingId) ? activeBookingId : bookings[0].id;
    bkSel.value = String(keep);
    activeBookingId = keep;
  } else {
    activeBookingId = bookings[0].id;
  }
  renderPortal();
}

function currentBooking() {
  return (portalData?.bookings || []).find((b) => b.id === activeBookingId)
    || (portalData?.bookings || [])[0];
}

function renderPortal() {
  const c = portalData?.customer;
  const b = currentBooking();
  if (!c || !b) {
    showEmpty('Search and select a booked customer');
    return;
  }
  $('portal-empty').hidden = true;
  $('portal-body').hidden = false;

  const s = b.summary || {};
  const u = b.unit || {};
  const meta = [c.cnic, c.phone, c.email].filter(Boolean).join(' · ');
  $('portal-hero').innerHTML = `
    <div style="font-size:9.5px;font-weight:800;letter-spacing:2px;opacity:.5;text-transform:uppercase;margin-bottom:7px">Haven Builders — Customer Portal</div>
    <div style="font-size:21px;font-weight:900;margin-bottom:3px">Welcome, ${esc(c.name)}</div>
    ${c.father_name ? `<div style="font-size:12px;opacity:.7;margin-bottom:4px">S/O ${esc(c.father_name)}</div>` : ''}
    <div style="font-size:12px;opacity:.65;margin-bottom:6px">${esc(b.unit_no)} · ${esc(b.project_name)}${b.project_location ? ` · ${esc(b.project_location)}` : ''}</div>
    ${meta ? `<div style="font-size:11.5px;opacity:.55;margin-bottom:16px">${esc(meta)}</div>` : '<div style="margin-bottom:16px"></div>'}
    <div style="display:flex;gap:22px;flex-wrap:wrap">
      <div><div style="font-size:19px;font-weight:900">${fmt(s.sale_price)}</div><div style="font-size:10px;opacity:.5;font-weight:700;text-transform:uppercase;letter-spacing:1px">Total Value</div></div>
      <div style="width:1px;background:rgba(255,255,255,.2)"></div>
      <div><div style="font-size:19px;font-weight:900">${fmt(s.total_paid)}</div><div style="font-size:10px;opacity:.5;font-weight:700;text-transform:uppercase;letter-spacing:1px">Paid to Date</div></div>
      <div style="width:1px;background:rgba(255,255,255,.2)"></div>
      <div><div style="font-size:19px;font-weight:900;color:#FDE68A">${fmt(s.outstanding)}</div><div style="font-size:10px;opacity:.5;font-weight:700;text-transform:uppercase;letter-spacing:1px">Outstanding</div></div>
    </div>`;

  const insts = b.installments || [];
  $('portal-sched').innerHTML = insts.length
    ? insts.map((i) => {
        const remaining = i.remaining_amount ?? Math.max((i.amount || 0) - (i.paid_amount || 0), 0);
        const canPay = !['paid', 'cancelled', 'scheduled'].includes(i.status) && remaining > 0;
        const due = i.status === 'scheduled'
          ? `Forecast ${esc(i.forecast_due_date || i.due_date || '—')}`
          : esc(i.due_date || '—');
        const type = i.trigger_kind === 'construction'
          ? `${esc(i.trigger_label || i.type || 'Milestone')} @ ${i.trigger_progress ?? '—'}%`
          : esc(i.type || '—');
        return `
      <tr>
        <td>${due}</td>
        <td>${type}</td>
        <td>${fmt(i.amount)}</td>
        <td class="td-green">${fmt(i.paid_amount || 0)}</td>
        <td class="${remaining > 0 && i.status !== 'scheduled' ? 'td-red' : 'td-green'}">${fmt(remaining)}</td>
        <td><span class="badge ${instStatusBadge(i.status)}">${esc(i.status)}</span></td>
        <td>${canPay ? `<button type="button" class="btn sm primary" data-portal-pay="${i.id}">Pay</button>` : ''}</td>
      </tr>`;
      }).join('')
    : '<tr><td colspan="7" style="text-align:center;color:var(--g400);padding:16px">No installment schedule</td></tr>';

  $('portal-sched').querySelectorAll('[data-portal-pay]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const inst = insts.find((x) => x.id === parseInt(btn.dataset.portalPay, 10));
      if (!inst) return;
      const remaining = inst.remaining_amount ?? Math.max((inst.amount || 0) - (inst.paid_amount || 0), 0);
      openPayForInstallment({
        id: inst.id,
        booking_id: b.id,
        customer_id: c.id,
        customer_name: c.name,
        unit_no: b.unit_no,
        project_name: b.project_name,
        due_date: inst.due_date,
        days_overdue: inst.days_overdue || 0,
        amount: remaining,
      });
    });
  });

  const size = u.size_sqft ? `${Number(u.size_sqft).toLocaleString('en-PK')} sq.ft` : (u.area_ghaz ? `${u.area_ghaz} ghaz` : '—');
  const tags = parseAttrList(u.unit_attributes);
  const tagHtml = tags.length
    ? tags.map((t) => `<span class="badge bg-blue" style="margin:2px">${esc(t)}</span>`).join(' ')
    : '—';
  $('portal-unit').innerHTML = `
    <div class="sum-row"><span class="sum-lbl">Booking</span><span class="sum-val">${esc(b.booking_no || '—')}</span></div>
    <div class="sum-row"><span class="sum-lbl">Unit</span><span class="sum-val">${esc(b.unit_no)}</span></div>
    <div class="sum-row"><span class="sum-lbl">Project</span><span class="sum-val">${esc(b.project_name)}</span></div>
    <div class="sum-row"><span class="sum-lbl">Type</span><span class="sum-val">${esc(u.unit_type || u.type || '—')}</span></div>
    <div class="sum-row"><span class="sum-lbl">Floor</span><span class="sum-val">${esc(floorLabel(u.floor_number ?? u.floor))}</span></div>
    <div class="sum-row"><span class="sum-lbl">Size</span><span class="sum-val">${esc(size)}</span></div>
    <div class="sum-row"><span class="sum-lbl">Tags</span><span class="sum-val">${tagHtml}</span></div>
    ${c.address ? `<div class="sum-row"><span class="sum-lbl">Address</span><span class="sum-val">${esc(c.address)}</span></div>` : ''}`;

  const pays = b.payments || [];
  $('portal-pays').innerHTML = pays.length
    ? pays.map((p, idx) => `
      <tr>
        <td>${esc(p.payment_date || '—')}</td>
        <td class="td-mono">${esc(p.receipt_no || '—')}</td>
        <td class="td-green">${fmt(p.amount)}</td>
        <td>${p.receipt_no ? `<button type="button" class="btn sm" data-rcpt="${idx}">View</button>` : ''}</td>
      </tr>`).join('')
    : '<tr><td colspan="4" style="text-align:center;color:var(--g400);padding:16px">No payments yet</td></tr>';

  $('portal-pays').querySelectorAll('[data-rcpt]').forEach((btn) => {
    btn.addEventListener('click', () => openReceipt(pays[parseInt(btn.dataset.rcpt, 10)], c, b));
  });
}

function openReceipt(p, customer, booking) {
  if (!p) return;
  $('receipt-body').innerHTML = `
    <div class="bk-dcard">
      <div class="bk-dname">${esc(p.receipt_no || 'Receipt')}</div>
      <div class="sum-row"><span class="sum-lbl">Customer</span><span class="sum-val">${esc(customer.name)}</span></div>
      <div class="sum-row"><span class="sum-lbl">Unit</span><span class="sum-val">${esc(booking.unit_no)} · ${esc(booking.project_name)}</span></div>
      <div class="sum-row"><span class="sum-lbl">Date</span><span class="sum-val">${esc(p.payment_date || '—')}</span></div>
      <div class="sum-row"><span class="sum-lbl">Amount</span><span class="sum-val">${fmt(p.amount)}</span></div>
      <div class="sum-row"><span class="sum-lbl">Method</span><span class="sum-val">${esc(p.payment_method || '—')}</span></div>
      <div class="sum-row"><span class="sum-lbl">Reference</span><span class="sum-val">${esc(p.reference_number || '—')}</span></div>
      ${p.inst_type ? `<div class="sum-row"><span class="sum-lbl">Against</span><span class="sum-val">${esc(p.inst_type)}</span></div>` : ''}
    </div>`;
  openModal('receipt-modal');
}

export function initPortalEvents() {
  const q = $('portal-cust-q');
  q?.addEventListener('focus', () => {
    paintPortalCustomers();
    showPortalMenu();
  });
  q?.addEventListener('input', () => {
    paintPortalCustomers();
    showPortalMenu();
  });
  $('portal-cust-menu')?.addEventListener('mousedown', (e) => {
    const btn = e.target.closest('[data-portal-id]');
    if (!btn) return;
    e.preventDefault();
    pickPortalCustomer(parseInt(btn.dataset.portalId, 10));
  });
  document.addEventListener('mousedown', (e) => {
    if (!e.target.closest('#portal-combo-cust')) hidePortalMenu();
  });
  $('portal-booking')?.addEventListener('change', () => {
    activeBookingId = parseInt($('portal-booking').value, 10);
    renderPortal();
  });
}
