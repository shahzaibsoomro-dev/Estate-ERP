import { $, esc, loadingHtml } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, instStatusBadge } from '../format.js';
import { openModal, closeModal } from '../modal.js';
import { state } from '../state.js';
import { loadDashboard } from './dashboard.js';
import { openUnitFormModal, UNIT_ATTRS } from '../unit-form.js';
import { loadProjects } from './projects.js';
import { unitDetailsHtml, parseAttrList } from '../detail.js';
import { confirmCancelBooking, confirmPossession, openTransferModal, initTransferEvents } from '../booking-actions.js';
import { askConfirm } from '../dialog.js';

let unitsLoadSeq = 0;

function unitsApiQuery() {
  const id = state.unitsProjectId;
  return id ? `?project_id=${id}` : '';
}

function unitsScopeLabel() {
  if (!state.unitsProjectId) return 'All projects';
  const p = state.projects.find((x) => x.id === state.unitsProjectId);
  return p?.name || 'Selected project';
}

export function setUnitsProjectId(id) {
  state.unitsProjectId = id || null;
  const sel = $('u-proj');
  if (sel) sel.value = id ? String(id) : '';
}

export function syncUnitsProjectSelect() {
  const sel = $('u-proj');
  if (!sel) return;
  const prev = state.unitsProjectId;
  sel.innerHTML = `<option value="">All Projects</option>${state.projects.map((p) =>
    `<option value="${p.id}">${esc(p.name)}</option>`).join('')}`;
  if (prev && state.projects.some((p) => p.id === prev)) {
    sel.value = String(prev);
  } else if (prev) {
    state.unitsProjectId = null;
    sel.value = '';
  }
}

export async function loadUnits() {
  const seq = ++unitsLoadSeq;
  if (!state.projects.length) {
    try {
      state.projects = await api('/api/projects');
    } catch {
      /* dropdown stays empty until projects load */
    }
  }
  syncUnitsProjectSelect();
  $('unit-floors').innerHTML = loadingHtml('Loading units…');
  updateUnitsScopeLabel();

  try {
    const data = await api(`/api/units${unitsApiQuery()}`);
    if (seq !== unitsLoadSeq) return;
    state.allUnits = data;
    renderUnits(state.allUnits);
  } catch {
    if (seq !== unitsLoadSeq) return;
    $('unit-floors').innerHTML = '<div class="loading">Failed to load units</div>';
  }
}

function updateUnitsScopeLabel() {
  const el = $('units-scope');
  if (!el) return;
  el.textContent = unitsScopeLabel();
}

function unitSearchBlob(u) {
  const tags = parseAttrList(u.unit_attributes);
  return [
    u.unit_no, u.type, u.unit_type, u.block_tower, u.floor, u.floor_number,
    u.residential_type, u.furnishing_status, u.facing, u.description,
    u.project_name, u.additional_requirements, tags.join(' '),
  ].filter(Boolean).join(' ').toLowerCase();
}

function knownTags() {
  const set = new Set(UNIT_ATTRS);
  (state.allUnits || []).forEach((u) => {
    parseAttrList(u.unit_attributes).forEach((t) => { if (t) set.add(t); });
  });
  return [...set].sort((a, b) => a.localeCompare(b));
}

function applyLocalFilters(units) {
  const floorFilter = $('u-floor')?.value;
  const statusFilter = $('u-status')?.value;
  const q = ($('u-search')?.value || '').trim().toLowerCase();
  let filtered = units;
  if (floorFilter) filtered = filtered.filter((u) => String(u.floor) === floorFilter);
  if (statusFilter) filtered = filtered.filter((u) => u.status === statusFilter);
  if (q) {
    const exactTag = knownTags().find((t) => t.toLowerCase() === q);
    if (exactTag) {
      filtered = filtered.filter((u) => parseAttrList(u.unit_attributes)
        .some((t) => t.toLowerCase() === exactTag.toLowerCase()));
    } else {
      filtered = filtered.filter((u) => unitSearchBlob(u).includes(q));
    }
  }
  return filtered;
}

function hideUnitSearchMenu() {
  const menu = $('u-search-menu');
  if (menu) menu.hidden = true;
  $('u-tag-combo')?.classList.remove('open');
}

function showUnitSearchMenu() {
  const menu = $('u-search-menu');
  if (!menu) return;
  menu.hidden = false;
  $('u-tag-combo')?.classList.add('open');
}

function paintUnitSearchMenu() {
  const menu = $('u-search-menu');
  if (!menu) return;
  const q = ($('u-search')?.value || '').trim().toLowerCase();
  const tags = knownTags().filter((t) => !q || t.toLowerCase().includes(q));
  const units = (state.allUnits || []).filter((u) => {
    if (!q) return false;
    return String(u.unit_no || '').toLowerCase().includes(q);
  }).slice(0, 8);

  const parts = [];
  if (tags.length) {
    parts.push('<div class="bk-opt-empty" style="text-align:left;font-weight:800;padding:6px 10px 4px">Tags</div>');
    tags.forEach((t) => {
      parts.push(`<button type="button" class="bk-opt" data-u-tag="${esc(t)}">
        <span class="bk-opt-text"><span class="bk-opt-title">${esc(t)}</span>
        <span class="bk-opt-sub">Unit tag</span></span>
      </button>`);
    });
  }
  if (units.length) {
    parts.push('<div class="bk-opt-empty" style="text-align:left;font-weight:800;padding:8px 10px 4px">Units</div>');
    units.forEach((u) => {
      parts.push(`<button type="button" class="bk-opt" data-u-no="${esc(u.unit_no)}">
        <span class="bk-opt-text"><span class="bk-opt-title">${esc(u.unit_no)}</span>
        <span class="bk-opt-sub">${esc([u.project_name, u.type, u.status].filter(Boolean).join(' · '))}</span></span>
      </button>`);
    });
  }
  if (!parts.length) {
    menu.innerHTML = '<div class="bk-opt-empty">No matching tags or units</div>';
    return;
  }
  menu.innerHTML = parts.join('');
}

function applyUnitSearchPick(value) {
  if ($('u-search')) $('u-search').value = value || '';
  hideUnitSearchMenu();
  renderUnits(state.allUnits);
}

function groupByProject(units) {
  const groups = new Map();
  units.forEach((u) => {
    const key = u.project_id;
    if (!groups.has(key)) {
      groups.set(key, { id: key, name: u.project_name || `Project ${key}`, units: [] });
    }
    groups.get(key).units.push(u);
  });
  return [...groups.values()].sort((a, b) => a.name.localeCompare(b.name));
}

function floorCardsHtml(units) {
  const floors = {};
  units.forEach((u) => {
    (floors[u.floor] = floors[u.floor] || []).push(u);
  });

  return Object.entries(floors)
    .sort((a, b) => Number(a[0]) - Number(b[0]))
    .map(([fl, flUnits]) => `
      <div class="card">
        <div class="card-hd"><span class="card-title">Floor ${fl} — ${flUnits.length} Units</span></div>
        <div class="card-bd"><div class="unit-grid">
          ${flUnits.map((u) => unitTileHtml(u)).join('')}
        </div></div>
      </div>`).join('');
}

function unitTileHtml(u) {
  const tags = parseAttrList(u.unit_attributes);
  const tip = [u.unit_no, u.type, u.status, tags.join(', ')].filter(Boolean).join(' · ');
  return `
    <div class="utile ${u.status}" data-unit-id="${u.id}" title="${esc(tip)}">
      <div class="utile-no">${esc(u.unit_no)}</div>
      <div class="utile-type">${esc(u.type)}</div>
      <div style="font-size:9px;opacity:.6;margin-top:1px">${u.size_sqft || '—'} sqft</div>
      ${tags.length ? `<div style="font-size:8.5px;opacity:.75;margin-top:3px;font-weight:700">${esc(tags[0])}${tags.length > 1 ? ` +${tags.length - 1}` : ''}</div>` : ''}
    </div>`;
}

export function renderUnits(units) {
  const filtered = applyLocalFilters(units);

  if ($('u-avail-cnt')) $('u-avail-cnt').textContent = filtered.filter((u) => u.status === 'available').length;
  if ($('u-hold-cnt')) $('u-hold-cnt').textContent = filtered.filter((u) => u.status === 'hold').length;
  if ($('u-booked-cnt')) $('u-booked-cnt').textContent = filtered.filter((u) => u.status === 'booked').length;
  if ($('u-deliv-cnt')) $('u-deliv-cnt').textContent = filtered.filter((u) => u.status === 'delivered').length;

  if (!filtered.length) {
    $('unit-floors').innerHTML = `<div class="loading">No units match the filter for ${esc(unitsScopeLabel())}</div>`;
    return;
  }

  const projectGroups = groupByProject(filtered);
  const multiProject = !state.unitsProjectId && projectGroups.length > 1;

  if (multiProject) {
    $('unit-floors').innerHTML = projectGroups.map((pg) => `
      <div class="units-project-block">
        <div class="units-project-hd">${esc(pg.name)} <span style="font-weight:600;color:var(--g400)">· ${pg.units.length} units</span></div>
        ${floorCardsHtml(pg.units)}
      </div>`).join('');
  } else {
    $('unit-floors').innerHTML = floorCardsHtml(filtered);
  }
}

export async function openUnit(uid) {
  if (!uid || !Number.isFinite(uid)) return;

  openModal('unit-modal');
  $('um-title').textContent = 'Loading…';
  $('um-body').innerHTML = loadingHtml('Fetching unit details…');

  let d;
  try {
    d = await api(`/api/units/${uid}`);
  } catch (e) {
    $('um-body').innerHTML = `<div class="error-box">Failed to load unit: ${esc(e.message)}</div>`;
    return;
  }

  try {
    const u = d.unit;
    if (!u) throw new Error('Unit data missing from response');
    u.unit_attributes = parseAttrList(u.unit_attributes);

    const b = d.booking;
    const s = d.summary || { sale_price: 0, total_paid: 0, outstanding: 0, pct_paid: 0 };
    const displayStatus = u.raw_status || u.status;

    $('um-title').textContent = `${u.unit_no} — ${u.project_name || 'Unit'}`;

    const instRows = (d.installments || []).length
      ? d.installments.map((i) => {
          const canPay = b && ['pending', 'partial', 'overdue'].includes(i.status) && i.remaining_amount > 0;
          return `<tr>
            <td>${esc(i.due_date)}</td><td>${esc(i.type)}</td>
            <td>${fmt(i.amount)}${i.remaining_amount < i.amount ? `<div class="td-sm">Due: ${fmt(i.remaining_amount)}</div>` : ''}</td>
            <td>${esc(i.notes || '—')}</td>
            <td><span class="badge ${instStatusBadge(i.status)}">${esc(i.status)}</span></td>
            <td>${canPay ? `<button type="button" class="btn sm primary" data-pay='${JSON.stringify({ instId: i.id, bkId: b.id, custId: b.customer_id, amount: i.remaining_amount, uid })}'>Pay</button>` : '—'}</td>
          </tr>`;
        }).join('')
      : '<tr><td colspan="6" style="text-align:center;color:var(--g400)">No installments</td></tr>';

    const payRows = (d.payments || []).length
      ? d.payments.map((p) => `
        <tr><td>${esc(p.paid_date)}</td><td>${esc(p.inst_type || '—')}</td>
        <td class="td-green">${fmt(p.amount)}</td><td>${esc(p.method)}</td>
        <td><span class="badge bg-green">${esc(p.receipt_no || '—')}</span></td></tr>`).join('')
      : '<tr><td colspan="5" style="text-align:center;color:var(--g400)">No payments recorded yet</td></tr>';

    $('um-body').innerHTML = b ? soldUnitHtml(u, b, s, instRows, payRows, displayStatus)
      : availableUnitHtml(u, displayStatus);
    $('um-body').scrollTop = 0;

    $('um-body').querySelectorAll('[data-pay]').forEach((btn) => {
      btn.addEventListener('click', () => payInstallment(JSON.parse(btn.dataset.pay)));
    });

    $('um-body').querySelector('[data-book-unit]')?.addEventListener('click', () => {
      closeModal('unit-modal');
      state.pendingBookingUnitId = uid;
      import('../nav.js').then(({ goScreen }) => goScreen('booking'));
    });

    $('um-body').querySelector('[data-delete-unit]')?.addEventListener('click', () => {
      deleteUnit(uid, u.unit_no);
    });

    $('um-body').querySelector('[data-edit-unit]')?.addEventListener('click', () => {
      closeModal('unit-modal');
      openUnitFormModal({
        mode: 'edit',
        projectId: u.project_id,
        unit: { ...u, unit_attributes: parseAttrList(u.unit_attributes) },
        onSaved: async () => { await loadUnits(); loadProjects(); openUnit(uid); },
      });
    });

    $('um-body').querySelector('[data-cancel-bk]')?.addEventListener('click', async () => {
      if (await confirmCancelBooking(b.id)) {
        await loadUnits();
        loadProjects();
        loadDashboard();
        openUnit(uid);
      }
    });

    $('um-body').querySelector('[data-xfer-bk]')?.addEventListener('click', () => {
      openTransferModal({
        bookingId: b.id,
        unitId: uid,
        currentCustomerId: b.customer_id,
        currentName: b.customer_name,
        unitNo: u.unit_no,
      });
    });

    $('um-body').querySelector('[data-poss-unit]')?.addEventListener('click', async () => {
      if (await confirmPossession(uid, s.outstanding)) {
        await loadUnits();
        loadProjects();
        openUnit(uid);
      }
    });
  } catch (e) {
    console.error('openUnit render error', e);
    $('um-body').innerHTML = `<div class="error-box">Could not display unit: ${esc(e.message)}</div>`;
  }
}

async function deleteUnit(uid, unitNo) {
  if (!await askConfirm(`Delete unit ${unitNo}?\n\nOnly available units with no booking history can be deleted.`, {
    title: 'Delete unit', confirmLabel: 'Delete', danger: true,
  })) return;
  await api(`/api/units/${uid}`, { method: 'DELETE' });
  closeModal('unit-modal');
  toast(`Unit ${unitNo} deleted`);
  loadUnits();
  loadProjects();
}

function soldUnitHtml(u, b, s, instRows, payRows, displayStatus) {
  return `
    ${unitDetailsHtml(u, displayStatus)}
    <div class="g2" style="margin-bottom:14px;margin-top:14px">
      <div>
        <div style="font-size:13px;font-weight:800;margin-bottom:8px;color:var(--navy)">👤 Customer & Booking</div>
        <div class="sum-row"><span class="sum-lbl">Name</span><span class="sum-val">${esc(b.customer_name)}</span></div>
        <div class="sum-row"><span class="sum-lbl">CNIC</span><span class="sum-val" style="font-family:monospace;font-size:11px">${esc(b.cnic)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Phone</span><span class="sum-val">${esc(b.phone)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Booking No</span><span class="sum-val">${esc(b.booking_no || '—')}</span></div>
      </div>
      <div>
        <div style="font-size:13px;font-weight:800;margin-bottom:8px;color:var(--navy)">&nbsp;</div>
        <div class="sum-row"><span class="sum-lbl">Booked On</span><span class="sum-val">${esc(b.booking_date)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Agent</span><span class="sum-val">${esc(b.agent)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Payment Mode</span><span class="sum-val">${esc(b.payment_mode)}</span></div>
        <div class="sum-row"><span class="sum-lbl">Booking Amount</span><span class="sum-val">${fmt(b.booking_amount)}</span></div>
      </div>
    </div>
    <div class="g3" style="margin-bottom:14px">
      <div class="sm"><div class="sm-v" style="color:var(--navy)">${fmt(s.sale_price)}</div><div class="sm-l">Sale Price</div></div>
      <div class="sm"><div class="sm-v" style="color:var(--success)">${fmt(s.total_paid)}</div><div class="sm-l">Total Paid</div></div>
      <div class="sm"><div class="sm-v" style="color:${s.outstanding > 0 ? 'var(--danger)' : 'var(--success)'}">${fmt(s.outstanding)}</div><div class="sm-l">Outstanding</div></div>
    </div>
    <div class="prog" style="margin-bottom:4px"><div class="prog-fill g" style="width:${s.pct_paid}%"></div></div>
    <div style="font-size:10.5px;color:var(--g400);margin-bottom:14px">${s.pct_paid}% paid</div>
    <div style="font-size:13px;font-weight:800;margin-bottom:8px;color:var(--navy)">📅 Installment Schedule</div>
    <div class="tbl-wrap" style="margin-bottom:14px"><table><thead><tr><th>Due Date</th><th>Type</th><th>Amount</th><th>Notes</th><th>Status</th><th>Action</th></tr></thead><tbody>${instRows}</tbody></table></div>
    <div style="font-size:13px;font-weight:800;margin-bottom:8px;color:var(--navy)">💳 Payment History</div>
    <div class="tbl-wrap"><table><thead><tr><th>Paid Date</th><th>Type</th><th>Amount</th><th>Method</th><th>Receipt</th></tr></thead><tbody>${payRows}</tbody></table></div>
    <div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;margin-top:14px">
      <button type="button" class="btn danger" data-cancel-bk>Cancel booking</button>
      <button type="button" class="btn" data-xfer-bk>Transfer owner</button>
      ${String(displayStatus).includes('possession') || u.status === 'delivered' ? '' : '<button type="button" class="btn primary" data-poss-unit>Mark possession</button>'}
    </div>`;
}

function availableUnitHtml(u, displayStatus) {
  const isAvail = u.status === 'available' || displayStatus === 'available';
  const isHold = displayStatus === 'hold';
  const canManage = isAvail || isHold;
  return `
    ${unitDetailsHtml(u, displayStatus)}
    <div style="text-align:center;padding:16px 0 4px;color:var(--g400)">
      ${canManage ? `<div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap">
        ${isAvail ? '<button class="btn primary" data-book-unit>📋 Book This Unit</button>' : ''}
        <button class="btn" data-edit-unit>✏️ Edit</button>
        <button class="btn danger" data-delete-unit>🗑 Delete</button>
      </div>` : ''}
    </div>`;
}

async function payInstallment({ instId, bkId, custId, amount, uid }) {
  if (!await askConfirm(`Record payment of ${fmt(amount)}?`, {
    title: 'Record payment', confirmLabel: 'Record payment',
  })) return;
  const r = await api('/api/payments', {
    method: 'POST',
    body: JSON.stringify({
      installment_id: instId,
      booking_id: bkId,
      customer_id: custId,
      amount,
      method: 'Cash',
    }),
  });
  toast(`✅ Payment recorded! Receipt: ${r.receipt}`);
  openUnit(uid);
  loadDashboard();
}

export function initUnitsFilters() {
  $('unit-floors')?.addEventListener('click', (e) => {
    const tile = e.target.closest('[data-unit-id]');
    if (!tile) return;
    e.preventDefault();
    e.stopPropagation();
    const uid = parseInt(tile.getAttribute('data-unit-id'), 10);
    if (uid) openUnit(uid);
  });

  $('u-proj')?.addEventListener('change', () => {
    const v = $('u-proj').value;
    state.unitsProjectId = v ? parseInt(v, 10) : null;
    loadUnits();
  });
  $('u-floor')?.addEventListener('change', () => renderUnits(state.allUnits));
  $('u-status')?.addEventListener('change', () => renderUnits(state.allUnits));
  $('u-search')?.addEventListener('focus', () => {
    paintUnitSearchMenu();
    showUnitSearchMenu();
  });
  $('u-search')?.addEventListener('input', () => {
    paintUnitSearchMenu();
    showUnitSearchMenu();
    renderUnits(state.allUnits);
  });
  $('u-search-menu')?.addEventListener('mousedown', (e) => {
    const tagBtn = e.target.closest('[data-u-tag]');
    const noBtn = e.target.closest('[data-u-no]');
    if (tagBtn) {
      e.preventDefault();
      applyUnitSearchPick(tagBtn.dataset.uTag);
    } else if (noBtn) {
      e.preventDefault();
      applyUnitSearchPick(noBtn.dataset.uNo);
    }
  });
  document.addEventListener('mousedown', (e) => {
    if (!e.target.closest('#u-tag-combo')) hideUnitSearchMenu();
  });
  $('btn-bulk-units')?.addEventListener('click', () => {
    toast('Bulk CSV upload — coming soon');
  });
  $('btn-add-unit')?.addEventListener('click', () => {
    const projectId = state.unitsProjectId;
    if (!projectId) {
      toast('Select a project from the dropdown first', 'error');
      return;
    }
    openUnitFormModal({
      mode: 'add',
      projectId,
      onSaved: async () => { await loadUnits(); loadProjects(); },
    });
  });
  initTransferEvents(async (unitId) => {
    await loadUnits();
    loadProjects();
    if (unitId) openUnit(unitId);
  });
}
