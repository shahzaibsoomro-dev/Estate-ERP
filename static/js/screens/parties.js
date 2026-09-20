import { $, esc, loadingHtml } from '../dom.js';
import { api } from '../api.js';
import { fmt } from '../format.js';
import { closeModal, openModal } from '../modal.js';
import { goScreen } from '../nav.js';

const TYPES = [
  { id: '', label: 'All' },
  { id: 'customer', label: 'Customers' },
  { id: 'vendor', label: 'Vendors' },
  { id: 'agent', label: 'Agents' },
  { id: 'investor', label: 'Investors' },
  { id: 'partner', label: 'Partners' },
  { id: 'contractor', label: 'Contractors' },
];

let allParties = [];
let activeType = '';

function typeLabel(t) {
  return ({
    customer: 'Customer', vendor: 'Vendor', agent: 'Agent',
    investor: 'Investor', partner: 'Partner', contractor: 'Contractor',
  })[t] || t;
}

function partySearchBlob(p) {
  return [
    p.master_id, p.name, p.subtitle, p.entity_type, p.cnic, p.contact, p.email, p.ntn, p.status,
  ].filter(Boolean).join(' ').toLowerCase();
}

export async function loadParties() {
  allParties = await api('/api/entities');
  renderPartyPills();
  renderParties();
}

function filteredParties() {
  const q = ($('party-search')?.value || '').trim().toLowerCase();
  return allParties.filter((p) => {
    if (activeType && p.entity_type !== activeType) return false;
    if (!q) return true;
    return partySearchBlob(p).includes(q);
  });
}

function renderPartyPills() {
  const host = $('party-pills');
  if (!host) return;
  const counts = { '': allParties.length };
  allParties.forEach((p) => { counts[p.entity_type] = (counts[p.entity_type] || 0) + 1; });
  host.innerHTML = TYPES.map((t) => `
    <button type="button" class="party-pill ${activeType === t.id ? 'on' : ''}" data-party-type="${t.id}">
      ${esc(t.label)} <b>${counts[t.id] || 0}</b>
    </button>`).join('');
  host.querySelectorAll('[data-party-type]').forEach((btn) => {
    btn.addEventListener('click', () => {
      activeType = btn.dataset.partyType || '';
      renderPartyPills();
      renderParties();
    });
  });
}

function renderParties() {
  const host = $('party-results');
  if (!host) return;
  const rows = filteredParties();
  if (!rows.length) {
    host.innerHTML = '<div class="party-empty">No parties match this search</div>';
    return;
  }
  host.innerHTML = rows.map((p) => {
    const st = (p.status || 'active').toLowerCase();
    const dim = st === 'inactive' || st === 'withdrawn';
    return `
      <article class="party-card">
        <div class="party-card-top">
          <span class="party-card-id">${esc(p.master_id)}</span>
          <span class="badge ${dim ? 'bg-grey' : 'bg-green'}">${esc(p.status || 'active')}</span>
        </div>
        <div class="party-card-name" title="${esc(p.name)}">${esc(p.name)}</div>
        <div style="font-size:12px;font-weight:600;color:var(--g400)">${esc(typeLabel(p.entity_type))}</div>
        <div class="party-card-sub">${esc(p.subtitle || p.contact || p.cnic || '—')}</div>
        <div class="party-card-actions">
          <button type="button" class="btn sm primary" data-party-open="${esc(p.entity_type)}:${p.entity_id}">Open ledger</button>
          <button type="button" class="btn sm" data-party-go="${esc(p.entity_type)}:${p.entity_id}">Go to record</button>
        </div>
      </article>`;
  }).join('');
  host.querySelectorAll('[data-party-open]').forEach((b) => {
    b.addEventListener('click', () => {
      const [type, id] = b.dataset.partyOpen.split(':');
      openPartyDetail(type, parseInt(id, 10));
    });
  });
  host.querySelectorAll('[data-party-go]').forEach((b) => {
    b.addEventListener('click', () => {
      const [type, id] = b.dataset.partyGo.split(':');
      goToPartyRecord(type, parseInt(id, 10));
    });
  });
}

async function goToPartyRecord(type, id) {
  closeModal('party-detail-modal');
  const screens = {
    customer: 'customers', vendor: 'vendors', agent: 'agents',
    investor: 'investors', partner: 'partners', contractor: 'contractors',
  };
  const screen = screens[type];
  if (screen) goScreen(screen);
  try {
    if (type === 'customer') {
      const m = await import('./customers.js');
      await m.openCustomerDetail(id);
    } else if (type === 'vendor') {
      const m = await import('./operations.js');
      await m.openVendorDetail(id);
    } else if (type === 'agent') {
      const m = await import('./agents.js');
      await m.openAgentDetail(id);
    } else if (type === 'investor') {
      const m = await import('./investors.js');
      await m.openInvestorDetail(id);
    } else if (type === 'partner') {
      const m = await import('./partners.js');
      await m.openPartnerDetail(id);
    } else if (type === 'contractor') {
      const m = await import('./ops-extra.js');
      await m.openCtrDetail(id);
    }
  } catch { /* native screen already open */ }
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

  $('party-d-body').innerHTML = `
    <div class="g2" style="margin-bottom:14px">
      <div>
        <div class="sum-row"><span class="sum-lbl">Master ID</span><span class="sum-val td-mono">${esc(row.master_id)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Type</span><span class="sum-val">${esc(row.label || type)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Status</span><span class="sum-val">${esc(row.status || '—')}</span></div>
        ${profile.ntn ? `<div class="sum-row"><span class="sum-lbl">NTN</span><span class="sum-val">${esc(profile.ntn)}</span></div>` : ''}
      </div>
      <div>
        <div class="sum-row"><span class="sum-lbl">Contact</span><span class="sum-val">${esc(profile.contact || profile.contact_number || profile.mobile_number || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">CNIC</span><span class="sum-val">${esc(profile.cnic || '—')}</span></div>
        <div class="sum-row"><span class="sum-lbl">Email</span><span class="sum-val">${esc(profile.email || '—')}</span></div>
      </div>
    </div>
    ${extra.join('')}
    <div class="detail-section-title">Transaction ledger</div>
    <div class="tbl-wrap" style="margin-bottom:14px"><table>
      <thead><tr><th>Date</th><th>Kind</th><th>Label</th><th>Amount</th><th>Ref</th></tr></thead>
      <tbody>${tlRows}</tbody>
    </table></div>
    <div style="display:flex;justify-content:flex-end">
      <button type="button" class="btn primary" data-party-go="${esc(type)}:${id}">Go to record</button>
    </div>`;
  $('party-d-body').querySelector('[data-party-go]')?.addEventListener('click', () => goToPartyRecord(type, id));
}

let searchTimer = null;
export function initPartyEvents() {
  $('party-search')?.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => renderParties(), 120);
  });
}
