import { esc } from './dom.js';
import { fmtShort } from './format.js';
import { customerStatusBadgeClass } from './detail.js';

export function customerInitials(name) {
  return String(name || '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase() || '?';
}

export function customerSearchBlob(c) {
  return [
    c.name, c.cnic, c.phone, c.contact_number, c.email,
    c.father_name, c.units, c.cust_status, c.nok_name, c.nok_phone, c.nok_cnic,
  ].filter(Boolean).join(' ').toLowerCase();
}

export function customerOptionLabel(c) {
  const bits = [c.cnic, c.units, c.cust_status].filter(Boolean);
  return bits.length ? `${c.name} — ${bits.join(' · ')}` : c.name;
}

export function customerOptionHtml(c, { selected = false, attr = 'data-id' } = {}) {
  const status = c.cust_status || 'New';
  const units = String(c.units || '').split(',').map((s) => s.trim()).filter(Boolean);
  const sub = [c.cnic, c.phone || c.contact_number].filter(Boolean).join(' · ');
  const unitLine = units.length
    ? units.slice(0, 2).join(', ') + (units.length > 2 ? ` +${units.length - 2}` : '')
    : 'No booked unit';
  const money = (c.outstanding || 0) > 0 ? fmtShort(c.outstanding) + ' due' : (c.cust_status === 'Cleared' ? 'Cleared' : '');
  return `<button type="button" class="bk-opt cust-opt${selected ? ' active' : ''}" ${attr}="${c.id}">
    <span class="bk-av">${esc(customerInitials(c.name))}</span>
    <span class="bk-opt-text">
      <span class="bk-opt-title">${esc(c.name)}
        <span class="badge ${customerStatusBadgeClass(status)}">${esc(status)}</span>
      </span>
      ${sub ? `<span class="bk-opt-sub">${esc(sub)}</span>` : ''}
      <span class="bk-opt-sub">${esc([unitLine, money].filter(Boolean).join(' · '))}</span>
    </span>
  </button>`;
}
