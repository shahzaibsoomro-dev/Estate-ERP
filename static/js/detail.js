import { esc } from './dom.js';
import { fmt } from './format.js';

/** Normalize JSON array fields that may arrive as strings from the API. */
export function parseAttrList(raw) {
  if (Array.isArray(raw)) return raw;
  if (typeof raw === 'string') {
    const s = raw.trim();
    if (!s) return [];
    try {
      const parsed = JSON.parse(s);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
}

function row(label, value, html = false) {
  if (value == null || value === '' || value === '—') return '';
  return `<div class="sum-row"><span class="sum-lbl">${esc(label)}</span><span class="sum-val">${html ? value : esc(String(value))}</span></div>`;
}

function badgeList(items) {
  const list = parseAttrList(items);
  if (!list.length) return '';
  return list.map((a) => `<span class="badge bg-blue" style="margin:2px">${esc(a)}</span>`).join(' ');
}

export function statusBadgeClass(displayStatus) {
  const s = (displayStatus || '').toLowerCase();
  if (s === 'available') return 'bg-green';
  if (s === 'hold') return 'bg-yellow';
  if (s === 'booked' || s === 'sold') return 'bg-blue';
  if (s === 'delivered' || s === 'possession_delivered') return 'bg-grey';
  return 'bg-grey';
}

export function unitDetailsHtml(u, displayStatus) {
  const statusClass = statusBadgeClass(displayStatus);
  const attrs = parseAttrList(u.unit_attributes);
  const holdBlock = displayStatus === 'hold' && (u.hold_until || u.hold_notes)
    ? `<div class="detail-note" style="margin-top:10px;padding:10px 12px;background:var(--warnp);border-radius:8px;font-size:12px">
        <strong>Hold:</strong> ${esc(u.hold_until || '—')}${u.hold_notes ? ` · ${esc(u.hold_notes)}` : ''}
      </div>`
    : '';

  return `
    <div class="detail-section">
      <div class="detail-section-title">📦 Unit Details</div>
      <div class="g2">
        <div>
          ${row('Unit No', u.unit_no)}
          ${row('Project', u.project_name)}
          ${row('Block / Tower', u.block_tower)}
          ${row('Unit Type', u.type || u.unit_type)}
          ${row('Residential Type', u.residential_type)}
          ${row('Floor', u.floor != null ? `Floor ${u.floor}` : null)}
          ${row('Area (Ghaz)', u.area_ghaz != null ? u.area_ghaz : null)}
          ${row('Size', u.size_sqft ? `${u.size_sqft} sqft` : null)}
        </div>
        <div>
          ${row('Bedrooms', u.bedrooms)}
          ${row('Bathrooms', u.bathrooms)}
          ${row('Base Sale Price', u.price || u.base_sale_price ? fmt(u.price || u.base_sale_price) : null)}
          ${row('Booking Amount Required', u.booking_amount_required ? fmt(u.booking_amount_required) : null)}
          ${row('Final Sold Price', u.final_sold_price ? fmt(u.final_sold_price) : null)}
          ${row('Furnishing', u.furnishing_status)}
          ${row('Possession Date', u.possession_date)}
          ${row('Status', `<span class="badge ${statusClass}">${esc(displayStatus)}</span>`, true)}
        </div>
      </div>
      ${u.description ? `<div class="detail-block"><div class="detail-block-lbl">Description</div><div class="detail-block-txt">${esc(u.description)}</div></div>` : ''}
      ${attrs.length ? `<div class="detail-block"><div class="detail-block-lbl">Unit Attributes</div><div>${badgeList(attrs)}</div></div>` : ''}
      ${u.additional_requirements ? `<div class="detail-block"><div class="detail-block-lbl">Additional Requirements</div><div class="detail-block-txt">${esc(u.additional_requirements)}</div></div>` : ''}
      ${holdBlock}
    </div>`;
}

export function customerStatusBadgeClass(status) {
  if (status === 'Overdue') return 'bg-red';
  if (status === 'Cleared') return 'bg-green';
  if (status === 'On Track') return 'bg-blue';
  return 'bg-grey';
}

export function customerDetailsHtml(c) {
  const status = c.cust_status || 'New';
  const bookings = Array.isArray(c.bookings) ? c.bookings : [];
  const payments = Array.isArray(c.payments) ? c.payments : [];

  const bookingRows = bookings.length
    ? bookings.map((b) => `
        <tr>
          <td class="td-mono">${esc(b.booking_no || b.id)}</td>
          <td>${esc(b.unit_no || '—')}</td>
          <td>${esc(b.project_name || '—')}</td>
          <td>${esc(b.booking_date || '—')}</td>
          <td>${fmt(b.final_sale_price || b.sale_price || 0)}</td>
          <td>${fmt(b.booking_amount || 0)}</td>
          <td><span class="badge ${b.status === 'active' ? 'bg-green' : 'bg-grey'}">${esc(b.status || '—')}</span></td>
          <td>${b.status === 'active' ? `<button type="button" class="btn sm danger" data-cancel-booking="${b.id}">Cancel</button>` : '—'}</td>
        </tr>`).join('')
    : '<tr><td colspan="8" style="text-align:center;color:var(--g400)">No bookings</td></tr>';

  const payRows = payments.length
    ? payments.map((p) => `
        <tr>
          <td>${esc(p.payment_date || p.paid_date || '—')}</td>
          <td>${esc(p.unit_no || '—')}</td>
          <td class="td-green">${fmt(p.amount)}</td>
          <td>${esc(p.payment_method || p.method || '—')}</td>
          <td><span class="badge bg-green">${esc(p.receipt_no || '—')}</span></td>
        </tr>`).join('')
    : '<tr><td colspan="5" style="text-align:center;color:var(--g400)">No payments</td></tr>';

  return `
    <div class="detail-section">
      <div class="g2">
        <div>
          ${row('Father name', c.father_name)}
          ${row('CNIC', c.cnic)}
          ${row('Phone', c.phone || c.contact_number)}
          ${row('Emergency', c.emergency_contact_number)}
          ${row('Email', c.email)}
          ${row('Address', c.address || c.residential_address)}
        </div>
        <div>
          ${row('Status', `<span class="badge ${customerStatusBadgeClass(status)}">${esc(status)}</span>`, true)}
          ${row('Booked units', c.units)}
          ${row('Total value', c.total_value ? fmt(c.total_value) : 'PKR 0')}
          ${row('Paid', fmt(c.total_paid || 0))}
          ${row('Outstanding', fmt(c.outstanding || 0))}
          ${row('Last payment', c.last_payment)}
          ${row('Registered', c.created_at)}
        </div>
      </div>
      ${c.description ? `<div class="detail-block"><div class="detail-block-lbl">Notes</div><div class="detail-block-txt">${esc(c.description)}</div></div>` : ''}
    </div>
    <div class="detail-section">
      <div class="detail-section-title">Bookings</div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Booking</th><th>Unit</th><th>Project</th><th>Date</th><th>Sale Price</th><th>Down Payment</th><th>Status</th><th></th></tr></thead>
        <tbody>${bookingRows}</tbody>
      </table></div>
    </div>
    <div class="detail-section">
      <div class="detail-section-title">Payments</div>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Date</th><th>Unit</th><th>Amount</th><th>Method</th><th>Receipt</th></tr></thead>
        <tbody>${payRows}</tbody>
      </table></div>
    </div>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:8px">
      <button type="button" class="btn" data-cust-edit="${c.id}">Edit</button>
      <button type="button" class="btn danger" data-cust-delete="${c.id}">Delete</button>
    </div>`;
}

export function projectDetailsHtml(p, units = []) {
  const attrs = parseAttrList(p.project_attributes);
  const statusLabel = p.status || '—';
  const statusClass = statusLabel === 'Completed' ? 'bg-grey' : 'bg-green';

  const unitPreview = units.length
    ? `<div class="detail-block"><div class="detail-block-lbl">Units in Project (${units.length})</div>
        <div class="tbl-wrap"><table><thead><tr><th>Unit</th><th>Type</th><th>Floor</th><th>Price</th><th>Status</th></tr></thead>
        <tbody>${units.slice(0, 12).map((u) => `
          <tr class="detail-unit-row" data-unit-open="${u.id}" style="cursor:pointer" title="Open unit details">
            <td class="td-b">${esc(u.unit_no)}</td><td>${esc(u.type || u.unit_type)}</td>
          <td>${u.floor ?? '—'}</td><td>${u.price ? fmt(u.price) : '—'}</td>
          <td><span class="badge ${statusBadgeClass(u.raw_status || u.status)}">${esc(u.raw_status || u.status)}</span></td></tr>`).join('')}
        ${units.length > 12 ? `<tr><td colspan="5" style="text-align:center;color:var(--g400);font-size:11px">+ ${units.length - 12} more — use View Units</td></tr>` : ''}
        </tbody></table></div></div>`
    : '<div class="detail-note" style="padding:12px;background:var(--g50);border-radius:8px;font-size:12px;color:var(--g500)">No units added yet.</div>';

  return `
    <div class="detail-section">
      <div class="g2">
        <div>
          ${row('Location', p.location)}
          ${row('Area', p.area)}
          ${row('City', p.city)}
          ${row('Start Date', p.start_date)}
          ${row('Expected End', p.end_date || p.expected_end_date)}
          ${row('Status', `<span class="badge ${statusClass}">${esc(statusLabel)}</span>`, true)}
          ${row('Floors', p.number_of_floors)}
          ${row('Planned Units', p.number_of_units)}
        </div>
        <div>
          ${row('Total Area (Ghaz)', p.total_area_ghaz)}
          ${row('Estimated Cost', p.estimated_cost ? fmt(p.estimated_cost) : null)}
          ${row('Construction Progress', `${p.progress ?? p.current_progress ?? 0}%`)}
          ${row('Live Inventory', `${p.total_units} total · ${p.sold} sold · ${p.available} avail · ${p.hold} hold`)}
          ${row('PO total', p.po_total != null ? fmt(p.po_total) : null)}
          ${row('Vendor paid', p.vendor_paid != null ? fmt(p.vendor_paid) : null)}
          ${row('Vendor outstanding', p.vendor_outstanding != null ? fmt(p.vendor_outstanding) : null)}
        </div>
      </div>
      ${p.description ? `<div class="detail-block"><div class="detail-block-lbl">Description</div><div class="detail-block-txt">${esc(p.description)}</div></div>` : ''}
      ${attrs.length ? `<div class="detail-block"><div class="detail-block-lbl">Project Attributes</div><div>${badgeList(attrs)}</div></div>` : ''}
      <div class="prog" style="margin:12px 0 4px"><div class="prog-fill ${(p.progress ?? 0) === 100 ? 'g' : (p.progress ?? 0) < 50 ? 'a' : ''}" style="width:${p.progress ?? 0}%"></div></div>
    </div>
    ${unitPreview}`;
}
