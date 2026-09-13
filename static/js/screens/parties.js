import { $, esc, loadingHtml } from '../dom.js';
import { api } from '../api.js';
import { fmt } from '../format.js';
import { openModal } from '../modal.js';

let allParties = [];

function typeLabel(t) {
  return ({
    customer: 'Customer', vendor: 'Vendor', agent: 'Agent',
    investor: 'Investor', partner: 'Partner', contractor: 'Contractor',
  })[t] || t;
}

export async function loadParties() {
  const type = $('party-type')?.value || '';
  const q = ($('party-search')?.value || '').trim();
  const params = new URLSearchParams();
  if (type) params.set('type', type);
  if (q) params.set('q', q);
  const qs = params.toString();
  allParties = await api(`/api/entities${qs ? `?${qs}` : ''}`);
  renderParties();
}

function renderParties() {
  const tbody = $('party-tbody');
  if (!tbody) return;
  tbody.innerHTML = allParties.length
    ? allParties.map((p) => `
      <tr>
        <td class="td-mono td-b">${esc(p.master_id)}</td>
        <td>${esc(typeLabel(p.entity_type))}</td>
        <td class="td-b">${esc(p.name)}</td>
        <td style="color:var(--g400);max-width:280px;white-space:normal">${esc(p.subtitle || '—')}</td>
        <td><span class="badge ${(p.status || '').toLowerCase() === 'inactive' || (p.status || '').toLowerCase() === 'withdrawn' ? 'bg-grey' : 'bg-green'}">${esc(p.status || 'active')}</span></td>
        <td><button type="button" class="btn sm primary" data-party-open="${esc(p.entity_type)}:${p.entity_id}">Open ledger</button></td>
      </tr>`).join('')
    : '<tr><td colspan="6" style="text-align:center;color:var(--g400);padding:20px">No parties found</td></tr>';

  tbody.querySelectorAll('[data-party-open]').forEach((b) => {
    b.addEventListener('click', () => {
      const [type, id] = b.dataset.partyOpen.split(':');
      openPartyDetail(type, parseInt(id, 10));
    });
  });
}

export async function openPartyDetail(type, id) {
  openModal('party-detail-modal');
  $('party-d-title').textContent = 'Loading…';
  $('party-d-body').innerHTML = loadingHtml('Loading party ledger…');
  let row;
  try {
    row = await api(`/api/entities/${type}/${id}`);
  } catch (e) {
    $('party-d-body').innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
    return;
  }
  $('party-d-title').textContent = `${row.master_id} · ${row.name}`;
  const profile = row.profile || {};
  const timeline = row.timeline || [];
  const tlRows = timeline.length
    ? timeline.map((t) => `
        <tr>
          <td>${esc(t.date || '—')}</td>
          <td>${esc(t.kind || '—')}</td>
          <td>${esc(t.label || '—')}</td>
          <td class="${t.direction === 'in' ? 'td-green' : t.direction === 'out' ? 'td-red' : ''}">${t.amount != null ? fmt(t.amount) : '—'}</td>
          <td class="td-mono">${esc(t.ref || '—')}</td>
        </tr>`).join('')
    : '<tr><td colspan="5" style="text-align:center;color:var(--g400)">No transactions yet</td></tr>';

  const extra = [];
  if (type === 'customer' && (row.holds || []).length) {
    extra.push(`<div class="detail-section-title">Holds</div>
      <div class="tbl-wrap" style="margin-bottom:14px"><table>
        <thead><tr><th>Unit</th><th>Project</th><th>Token</th><th>Status</th><th>Held</th></tr></thead>
        <tbody>${row.holds.map((h) => `
          <tr>
            <td>${esc(h.unit_no)}</td><td>${esc(h.project_name || '—')}</td>
            <td>${fmt(h.token_amount || 0)}</td><td>${esc(h.status)}</td><td>${esc(h.held_at || '—')}</td>
          </tr>`).join('')}</tbody></table></div>`);
  }
  if (type === 'vendor' && profile.ntn) {
    extra.push(`<div class="sum-row"><span class="sum-lbl">NTN</span><span class="sum-val">${esc(profile.ntn)}</span></div>`);
  }

  $('party-d-body').innerHTML = `
    <div class="g2" style="margin-bottom:14px">
      <div>
        <div class="sum-row"><span class="sum-lbl">Master ID</span><span class="sum-val td-mono">${esc(row.master_id)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Type</span><span class="sum-val">${esc(row.label || type)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Status</span><span class="sum-val">${esc(row.status || '—')}</span></div>
        ${extra.filter((x) => x.includes('sum-row')).join('') || ''}
      </div>
      <div>
        <div class="sum-row"><span class="sum-lbl">Internal id</span><span class="sum-val">${row.entity_id}</span></div>
        <div class="sum-row"><span class="sum-lbl">Contact</span><span class="sum-val">${esc(profile.contact || profile.contact_number || profile.mobile_number || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">CNIC / email</span><span class="sum-val">${esc(profile.cnic || profile.email || '—')}</span></div>
      </div>
    </div>
    ${extra.filter((x) => !x.includes('sum-row')).join('')}
    <div class="detail-section-title">Transaction ledger</div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Date</th><th>Kind</th><th>Label</th><th>Amount</th><th>Ref</th></tr></thead>
      <tbody>${tlRows}</tbody>
    </table></div>`;
}

let searchTimer = null;
export function initPartyEvents() {
  $('party-type')?.addEventListener('change', () => loadParties());
  $('party-search')?.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadParties(), 250);
  });
}
