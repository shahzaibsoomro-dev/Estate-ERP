import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt } from '../format.js';
import { state } from '../state.js';

let customerMode = 'existing';

export async function initBooking() {
  await Promise.all([loadAvailableUnits(), loadBookingCustomers(), loadBookingAgents()]);
  $('instRows').innerHTML = '';
  addInstRow();
  $('bk-date').value = new Date().toISOString().split('T')[0];
  setCustomerMode('existing');
  await loadBookingProjects();
}

async function loadBookingProjects() {
  const projects = state.projects.length ? state.projects : await api('/api/projects');
  state.projects = projects;
  const active = projects.filter((p) => p.status !== 'Completed');
  $('bk-project').innerHTML = active.map((p) =>
    `<option value="${p.id}">${esc(p.name)}</option>`).join('');
  await loadAvailableUnits();
}

async function loadBookingCustomers() {
  state.allCustomers = await api('/api/customers');
  const sel = $('bk-customer-select');
  if (!sel) return;
  sel.innerHTML = '<option value="">— Select customer —</option>' +
    state.allCustomers.map((c) =>
      `<option value="${c.id}">${esc(c.name)} · ${esc(c.cnic)}</option>`).join('');
}

async function loadBookingAgents() {
  state.agents = await api('/api/agents');
  $('bk-agent').innerHTML = '<option value="">None — Direct</option>' +
    state.agents.map((a) =>
      `<option value="${esc(a.name)}">${esc(a.name)} (${a.rate || a.default_rate_pct}%)</option>`).join('');
}

export function setCustomerMode(mode) {
  customerMode = mode;
  const existing = $('bk-existing-wrap');
  const newForm = $('bk-new-wrap');
  if (existing) existing.style.display = mode === 'existing' ? 'block' : 'none';
  if (newForm) newForm.style.display = mode === 'new' ? 'block' : 'none';
  document.querySelectorAll('[data-cust-mode]').forEach((btn) => {
    btn.classList.toggle('primary', btn.dataset.custMode === mode);
  });
}

export async function loadAvailableUnits() {
  const pid = $('bk-project').value;
  const units = await api(`/api/units?project_id=${pid}&status=available`);
  $('bk-unit').innerHTML = units.length
    ? units.map((u) => `<option value="${u.id}" data-price="${u.price || u.base_sale_price || 0}">${esc(u.unit_no)} · ${esc(u.type)} · ${u.size_sqft || '—'} sqft · ${fmt(u.price)}</option>`).join('')
    : '<option value="">No available units</option>';
  if (units.length && !$('bk-price').value) {
    const opt = $('bk-unit').options[$('bk-unit').selectedIndex];
    if (opt?.dataset.price) $('bk-price').value = opt.dataset.price;
  }
  updateBookingSummary();
}

export function updateBookingSummary() {
  const unit = $('bk-unit');
  const opt = unit.options[unit.selectedIndex];
  const price = parseInt($('bk-price').value, 10) || parseInt(opt?.dataset.price, 10) || 0;
  const dp = parseInt($('bk-dp').value, 10) || 0;
  if (!price) {
    $('booking-summary').textContent = 'Enter price to see summary';
    return;
  }
  const remaining = price - dp;
  const pct = price > 0 ? Math.round((dp / price) * 100) : 0;
  $('booking-summary').innerHTML = `
    <div class="sum-row"><span class="sum-lbl">Unit</span><span class="sum-val">${unit.value ? esc(unit.options[unit.selectedIndex].text.split('·')[0].trim()) : '—'}</span></div>
    <div class="sum-row"><span class="sum-lbl">Sale Price</span><span class="sum-val" style="font-size:15px">${fmt(price)}</span></div>
    <div class="sum-row"><span class="sum-lbl">Down Payment</span><span class="sum-val" style="color:var(--success)">${fmt(dp)}</span></div>
    <div class="sum-row"><span class="sum-lbl">Remaining</span><span class="sum-val" style="color:var(--danger)">${fmt(remaining)}</span></div>
    <div class="prog" style="margin-top:10px"><div class="prog-fill g" style="width:${pct}%"></div></div>
    <div style="font-size:10.5px;color:var(--g400);margin-top:3px">${pct}% paid upfront</div>`;
}

export function addInstRow() {
  const r = document.createElement('div');
  r.className = 'inst-row';
  r.innerHTML = `
    <input type="number" placeholder="Amount PKR">
    <input type="date">
    <select><option>Booking</option><option>Monthly</option><option>Quarterly</option><option>Stage</option><option>Possession</option></select>
    <input type="text" placeholder="Notes">
    <button type="button" class="del-btn" title="Remove">🗑</button>`;
  r.querySelector('.del-btn').addEventListener('click', () => r.remove());
  $('instRows').appendChild(r);
}

export function resetBookingForm() {
  $('bk-customer-select').value = '';
  ['bk-name', 'bk-cnic', 'bk-phone', 'bk-email', 'bk-address', 'bk-price', 'bk-dp'].forEach((id) => {
    if ($(id)) $(id).value = '';
  });
  initBooking();
}

export async function submitBooking() {
  const unitId = parseInt($('bk-unit').value, 10);
  const projId = parseInt($('bk-project').value, 10);
  const price = parseInt($('bk-price').value, 10);
  const dp = parseInt($('bk-dp').value, 10);

  if (!unitId || !price || !dp) {
    toast('Please fill unit, sale price, and down payment', 'error');
    return;
  }

  let customerId = null;
  const payload = {
    unit_id: unitId,
    project_id: projId,
    booking_date: $('bk-date').value,
    sale_price: price,
    down_payment: dp,
    booking_amount: dp,
    agent: $('bk-agent').value || 'None',
    payment_mode: 'Cheque',
    installments: [],
  };

  if (customerMode === 'existing') {
    customerId = parseInt($('bk-customer-select').value, 10);
    if (!customerId) {
      toast('Please select a customer', 'error');
      return;
    }
    payload.customer_id = customerId;
  } else {
    const name = $('bk-name').value.trim();
    const cnic = $('bk-cnic').value.trim();
    if (!name || !cnic) {
      toast('Name and CNIC required for new customer', 'error');
      return;
    }
    payload.customer = {
      name,
      cnic,
      phone: $('bk-phone').value,
      email: $('bk-email').value,
      address: $('bk-address').value,
    };
  }

  $('instRows').querySelectorAll('.inst-row').forEach((row) => {
    const inputs = row.querySelectorAll('input, select');
    const amount = parseInt(inputs[0].value, 10);
    const due_date = inputs[1].value;
    const type = inputs[2].value;
    const notes = inputs[3].value;
    if (amount && due_date) payload.installments.push({ amount, due_date, type, notes });
  });

  const r = await api('/api/bookings', { method: 'POST', body: JSON.stringify(payload) });
  toast(`🎉 Booking confirmed! ID: ${r.booking_id}`);
  resetBookingForm();
}

export function initBookingEvents() {
  $('bk-project')?.addEventListener('change', loadAvailableUnits);
  $('bk-unit')?.addEventListener('change', () => {
    const opt = $('bk-unit').options[$('bk-unit').selectedIndex];
    if (opt?.dataset.price && !$('bk-price').value) $('bk-price').value = opt.dataset.price;
    updateBookingSummary();
  });
  $('bk-price')?.addEventListener('input', updateBookingSummary);
  $('bk-dp')?.addEventListener('input', updateBookingSummary);
  document.querySelectorAll('[data-cust-mode]').forEach((btn) => {
    btn.addEventListener('click', () => setCustomerMode(btn.dataset.custMode));
  });
  document.querySelectorAll('#btn-add-inst, .btn-add-inst').forEach((btn) => {
    btn.addEventListener('click', addInstRow);
  });
  $('btn-reset-booking')?.addEventListener('click', resetBookingForm);
  $('btn-submit-booking')?.addEventListener('click', submitBooking);
}
