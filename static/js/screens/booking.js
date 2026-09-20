import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt } from '../format.js';
import { state } from '../state.js';
import { parseAttrList } from '../detail.js';
import { askConfirm } from '../dialog.js';
import { customerOptionHtml, customerSearchBlob } from '../customer-pick.js';

let bookingUnits = [];
let customerItems = [];
let projectItems = [];
let unitItems = [];
let selectedCustomer = null;
let selectedProject = null;
let selectedUnit = null;
let dpLast = 'amount';
let planSource = 'custom';
let activeTemplateMeta = null;
let heldCustomerId = null;

function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function addMonths(iso, months) {
  const [y, m, day] = String(iso || todayISO()).split('-').map(Number);
  const d = new Date(y, (m || 1) - 1, day || 1);
  d.setMonth(d.getMonth() + months);
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

function filterItems(items, q) {
  const s = (q || '').trim().toLowerCase();
  if (!s) return items;
  return items.filter((it) => (it.search || it.label || '').toLowerCase().includes(s));
}

function showList(id) {
  hideAllLists();
  const menu = $(id);
  if (!menu) return;
  menu.hidden = false;
  menu.closest('.bk-combo')?.classList.add('open');
}

function hideList(id) {
  const menu = $(id);
  if (!menu) return;
  menu.hidden = true;
  menu.closest('.bk-combo')?.classList.remove('open');
  menu.querySelectorAll('.bk-opt.hl').forEach((el) => el.classList.remove('hl'));
}

function hideAllLists() {
  ['bk-customer', 'bk-project', 'bk-unit'].forEach(hideList);
}

function setUnitEnabled(on) {
  const q = $('bk-unit-q');
  const combo = $('bk-combo-unit');
  combo?.classList.toggle('is-disabled', !on);
  if (q) {
    q.disabled = !on;
    q.placeholder = on ? 'Search unit…' : 'Select project first';
    if (!on) q.value = '';
  }
  if (!on) hideList('bk-unit');
}

function unitStatus(u) {
  const st = (u?.raw_status || u?.status || '').toLowerCase();
  return st === 'hold' ? 'hold' : 'available';
}

function statusLabel(u) {
  return unitStatus(u) === 'hold' ? 'On Hold' : 'Available';
}

function fillMenu(menuId, items, emptyLabel, renderItem) {
  const menu = $(menuId);
  if (!menu) return;
  if (!items.length) {
    menu.innerHTML = `<div class="bk-opt-empty">${esc(emptyLabel)}</div>`;
    return;
  }
  menu.innerHTML = items.map(renderItem).join('');
}

function paintCustomers() {
  const q = $('bk-customer-q')?.value || '';
  const keepName = selectedCustomer?.name || '';
  const query = (selectedCustomer && q === keepName) ? '' : q;
  fillMenu(
    'bk-customer',
    filterItems(customerItems, query),
    'No match',
    (it) => customerOptionHtml(it.data || { id: it.id, name: it.label }, {
      selected: selectedCustomer?.id === it.id,
    }),
  );
}

function paintProjects() {
  const q = $('bk-project-q')?.value || '';
  const keepName = selectedProject?.name || '';
  const query = (selectedProject && q === keepName) ? '' : q;
  fillMenu(
    'bk-project',
    filterItems(projectItems, query),
    'No match',
    (it) => `<button type="button" class="bk-opt${selectedProject?.id === it.id ? ' active' : ''}" data-id="${it.id}">
      <span class="bk-av proj">${esc(initials(it.label))}</span>
      <span class="bk-opt-title">${esc(it.label)}</span>
    </button>`,
  );
}

function projectUnits() {
  const pid = selectedProject?.id;
  if (!pid) return [];
  return unitItems.filter((it) => it.data.project_id === pid);
}

function paintUnits() {
  const q = $('bk-unit-q')?.value || '';
  const keepLabel = selectedUnit?.unit_no || '';
  const query = (selectedUnit && q === keepLabel) ? '' : q;
  const base = projectUnits();
  fillMenu(
    'bk-unit',
    filterItems(base, query),
    selectedProject ? (base.length ? 'No match' : 'No units') : 'Select project first',
    (it) => {
      const st = unitStatus(it.data);
      return `<button type="button" class="bk-opt${selectedUnit?.id === it.id ? ' active' : ''}" data-id="${it.id}">
        <span class="bk-opt-title">${esc(it.data.unit_no)}</span>
        <span class="bk-status ${st === 'hold' ? 'hold' : 'avail'}">${st === 'hold' ? 'On Hold' : 'Available'}</span>
      </button>`;
    },
  );
}

export async function initBooking() {
  if ($('bk-date')) $('bk-date').value = todayISO();
  if ($('bk-plan-start') && !$('bk-plan-start').value) {
    $('bk-plan-start').value = addMonths(todayISO(), 1);
  }

  try {
    await loadBookingCustomers();
    paintCustomers();
    await loadBookingProjects();
    paintProjects();
    await loadBookingAgents();
    await loadBookingUnits();
    paintUnits();
  } catch (e) {
    console.error('Booking data failed to load', e);
    toast('Could not load booking lists.', 'error');
  }

  applyPendingUnit();
  setUnitEnabled(!!selectedProject);
  hideAllLists();
  if (selectedCustomer && $('bk-customer-q')) $('bk-customer-q').value = selectedCustomer.name;
  if (selectedProject && $('bk-project-q')) $('bk-project-q').value = selectedProject.name;
  if (selectedUnit && $('bk-unit-q')) $('bk-unit-q').value = selectedUnit.unit_no;
  updateSelectionDetails();
  syncDpPercent();
  updateBookingSummary();
}

async function loadBookingCustomers() {
  const rows = await api('/api/customers');
  state.allCustomers = Array.isArray(rows) ? rows : [];
  customerItems = state.allCustomers.map((c) => ({
    id: c.id,
    label: c.name,
    search: customerSearchBlob(c),
    data: c,
  }));
}

async function loadBookingProjects() {
  const projects = await api('/api/projects');
  state.projects = Array.isArray(projects) ? projects : [];
  projectItems = state.projects.map((p) => ({
    id: p.id,
    label: p.name,
    search: `${p.name} ${p.location || ''} ${p.city || ''}`,
    data: p,
  }));
}

async function loadBookingAgents() {
  state.agents = await api('/api/agents?active_only=true');
  if (!$('bk-agent')) return;
  $('bk-agent').innerHTML = '<option value="">None</option>' +
    (state.agents || []).map((a) =>
      `<option value="${a.id}">${esc(a.name)}${a.commission_label ? ` · ${esc(a.commission_label)}` : ''}</option>`).join('');
  paintCommissionPreview();
}

function selectedBookingAgent() {
  const id = parseInt($('bk-agent')?.value, 10);
  return (state.agents || []).find((a) => a.id === id) || null;
}

function previewCommissionAmount(mode, sale, base, rate, flat, share) {
  const surplus = Math.max((sale || 0) - (base || 0), 0);
  if (mode === 'flat') return Math.max(parseInt(flat, 10) || 0, 0);
  if (mode === 'over_base') {
    const pct = share == null || Number.isNaN(share) ? 100 : share;
    return Math.max(Math.round(surplus * pct / 100), 0);
  }
  const pct = rate == null || Number.isNaN(rate) ? 0 : rate;
  return Math.max(Math.round((sale || 0) * pct / 100), 0);
}

function applyAgentDealToOverride(ag) {
  if (!ag) return;
  if ($('bk-comm-mode')) $('bk-comm-mode').value = ag.commission_mode || 'percent';
  if ($('bk-comm-rate')) $('bk-comm-rate').value = String(ag.default_rate_pct ?? ag.rate ?? 2);
  if ($('bk-comm-flat')) $('bk-comm-flat').value = String(ag.default_flat_amount || 0);
  if ($('bk-comm-over')) $('bk-comm-over').value = String(ag.over_base_pct ?? 100);
}

function syncBkCommOverrideFields() {
  const on = !!$('bk-comm-override')?.checked;
  if ($('bk-comm-override-fields')) $('bk-comm-override-fields').hidden = !on;
  const mode = $('bk-comm-mode')?.value || 'percent';
  if ($('bk-comm-rate-fg')) $('bk-comm-rate-fg').hidden = mode !== 'percent';
  if ($('bk-comm-flat-fg')) $('bk-comm-flat-fg').hidden = mode !== 'flat';
  if ($('bk-comm-over-fg')) $('bk-comm-over-fg').hidden = mode !== 'over_base';
  paintCommissionPreview();
}

function paintCommissionPreview() {
  const box = $('bk-comm-preview');
  const wrap = $('bk-comm-override-wrap');
  const ag = selectedBookingAgent();
  if (!box) return;
  if (!ag) {
    box.hidden = true;
    if (wrap) { wrap.hidden = true; wrap.style.display = 'none'; }
    if ($('bk-comm-override-fields')) $('bk-comm-override-fields').hidden = true;
    return;
  }
  if (wrap) { wrap.hidden = false; wrap.style.display = 'flex'; }
  box.hidden = false;
  const override = !!$('bk-comm-override')?.checked;
  const mode = override ? ($('bk-comm-mode')?.value || 'percent') : (ag.commission_mode || 'percent');
  const sale = salePrice();
  const base = parseInt(selectedUnit?.base_sale_price, 10) || sale;
  const rate = override ? parseFloat($('bk-comm-rate')?.value) : parseFloat(ag.default_rate_pct ?? ag.rate ?? 0);
  const flat = override ? parseInt($('bk-comm-flat')?.value, 10) : parseInt(ag.default_flat_amount, 10);
  const share = override ? parseFloat($('bk-comm-over')?.value) : parseFloat(ag.over_base_pct ?? 100);
  const amount = previewCommissionAmount(mode, sale, base, rate, flat, share);
  const surplus = Math.max(sale - base, 0);
  let how = ag.commission_label || '';
  if (mode === 'percent') how = `${rate || 0}% of sale`;
  else if (mode === 'flat') how = `${fmt(flat || 0)} fixed`;
  else how = `${share == null || Number.isNaN(share) ? 100 : share}% of surplus over base (${fmt(base)})`;
  box.innerHTML = `
    <h4>Agent commission</h4>
    <div class="sum-row"><span class="sum-lbl">Deal</span><span class="sum-val">${esc(how)}</span></div>
    ${mode === 'over_base' ? `<div class="sum-row"><span class="sum-lbl">Surplus</span><span class="sum-val">${fmt(surplus)}</span></div>` : ''}
    <div class="sum-row"><span class="sum-lbl">This booking</span><span class="sum-val">${fmt(amount)}</span></div>`;
}

async function loadBookingUnits() {
  const all = await api('/api/units');
  bookingUnits = (Array.isArray(all) ? all : []).filter((u) => {
    const st = u.raw_status || u.status;
    return st === 'available' || st === 'hold';
  });
  unitItems = bookingUnits.map((u) => ({
    id: u.id,
    label: u.unit_no,
    search: `${u.unit_no} ${u.type || ''} ${u.unit_type || ''} ${u.block_tower || ''} ${u.floor || ''} ${u.residential_type || ''} ${parseAttrList(u.unit_attributes).join(' ')} ${u.facing || ''}`,
    data: u,
  }));
}

function applyPendingUnit() {
  const uid = state.pendingBookingUnitId;
  if (!uid) return;
  const unit = bookingUnits.find((u) => u.id === uid);
  state.pendingBookingUnitId = null;
  if (!unit) return;
  selectedProject = state.projects.find((p) => p.id === unit.project_id) || null;
  selectedUnit = unit;
  setUnitEnabled(!!selectedProject);
  paintProjects();
  paintUnits();
  fillPricingFromUnit(unit);
}

function selectCustomer(id) {
  if (heldCustomerId && id !== heldCustomerId) {
    toast('This unit is on hold — only the held customer can book it', 'error');
    return;
  }
  const item = customerItems.find((c) => c.id === id);
  selectedCustomer = item?.data || null;
  if ($('bk-customer-q')) $('bk-customer-q').value = selectedCustomer?.name || '';
  hideList('bk-customer');
  updateSelectionDetails();
  updateBookingSummary();
}

async function maybeLoadProjectTemplate() {
  if (!selectedProject?.id) return;
  try {
    const tmpl = await api(`/api/projects/${selectedProject.id}/installment-template`);
    const hasRules = Array.isArray(tmpl?.rules) && tmpl.rules.length > 0 && tmpl.is_active !== 0;
    if ($('bk-plan-source')) {
      if (hasRules) {
        $('bk-plan-source').value = 'template';
        planSource = 'template';
        activeTemplateMeta = tmpl;
        await loadTemplatePlan();
      } else {
        $('bk-plan-source').value = 'custom';
        planSource = 'custom';
        activeTemplateMeta = null;
        syncPlanSourceUi();
      }
    }
  } catch {
    planSource = 'custom';
    syncPlanSourceUi();
  }
}

function syncPlanSourceUi() {
  planSource = $('bk-plan-source')?.value || 'custom';
  const isTmpl = planSource === 'template';
  if ($('bk-custom-tools')) $('bk-custom-tools').hidden = isTmpl;
  if ($('btn-load-tmpl')) $('btn-load-tmpl').hidden = !isTmpl;
  if ($('btn-add-inst')) $('btn-add-inst').hidden = isTmpl;
  if ($('btn-add-inst-2')) $('btn-add-inst-2').hidden = isTmpl;
  const hint = $('bk-tmpl-hint');
  if (hint) {
    if (isTmpl && activeTemplateMeta) {
      hint.hidden = false;
      hint.textContent = `Using template “${activeTemplateMeta.name || 'Construction plan'}” · rev ${activeTemplateMeta.revision || 1}. Manual edits switch to Custom.`;
    } else if (isTmpl) {
      hint.hidden = false;
      hint.textContent = 'No active project template — save one on the project, or switch to Custom.';
    } else {
      hint.hidden = true;
      hint.textContent = '';
    }
  }
}

async function loadTemplatePlan() {
  if (!selectedProject?.id) {
    toast('Select a project first', 'error');
    return;
  }
  const price = salePrice();
  const dp = dpAmount();
  if (!price || dp >= price) {
    toast('Enter sale price and booking amount below sale price to preview template', 'error');
    return;
  }
  try {
    const preview = await api(`/api/projects/${selectedProject.id}/installment-template/preview`, {
      method: 'POST',
      body: JSON.stringify({ sale_price: price, booking_amount: dp, booking_date: $('bk-date')?.value || null }),
    });
    activeTemplateMeta = {
      id: preview.template_id,
      name: preview.template_name,
      revision: preview.template_revision,
    };
    planSource = 'template';
    if ($('bk-plan-source')) $('bk-plan-source').value = 'template';
    $('instRows').innerHTML = '';
    (preview.installments || []).forEach((inst) => {
      addInstRow({
        amount: inst.amount,
        due_date: inst.forecast_due_date || inst.due_date || '',
        type: inst.label || inst.type || 'Stage',
        notes: inst.trigger_kind === 'construction'
          ? `Milestone @ ${inst.trigger_progress}% · scheduled until progress`
          : (inst.notes || ''),
        trigger_kind: inst.trigger_kind,
        trigger_progress: inst.trigger_progress,
        forecast_due_date: inst.forecast_due_date,
        due_days_after_trigger: inst.due_days_after_trigger,
        template_rule_id: inst.template_rule_id,
        trigger_label: inst.trigger_label || inst.label,
      });
    });
    syncPlanSourceUi();
    toast(`Loaded ${preview.installments?.length || 0} template installments`);
  } catch { /* toasted */ }
}

function selectProject(id) {
  const item = projectItems.find((p) => p.id === id);
  selectedProject = item?.data || null;
  if ($('bk-project-q')) $('bk-project-q').value = selectedProject?.name || '';
  hideList('bk-project');
  selectedUnit = null;
  heldCustomerId = null;
  if ($('bk-unit-q')) $('bk-unit-q').value = '';
  setUnitEnabled(!!selectedProject);
  paintUnits();
  updateSelectionDetails();
  updateBookingSummary();
  maybeLoadProjectTemplate();
}

function selectUnit(id) {
  const item = unitItems.find((u) => u.id === id);
  selectedUnit = item?.data || null;
  if (selectedUnit) {
    if ($('bk-unit-q')) $('bk-unit-q').value = selectedUnit.unit_no;
    fillPricingFromUnit(selectedUnit);
    const st = selectedUnit.raw_status || selectedUnit.status;
    heldCustomerId = st === 'hold' ? (selectedUnit.hold_customer_id || null) : null;
    if (heldCustomerId) {
      selectCustomer(heldCustomerId);
      toast('Held unit — token will apply to this booking; customer locked to holder');
    }
    if (selectedProject?.id !== selectedUnit.project_id) {
      selectedProject = state.projects.find((p) => p.id === selectedUnit.project_id) || selectedProject;
      if ($('bk-project-q')) $('bk-project-q').value = selectedProject?.name || '';
      maybeLoadProjectTemplate();
    } else if (planSource === 'template') {
      loadTemplatePlan();
    }
  } else {
    heldCustomerId = null;
  }
  hideList('bk-unit');
  updateSelectionDetails();
  updateBookingSummary();
}

function salePrice() {
  return parseInt($('bk-price')?.value, 10) || 0;
}

function dpAmount() {
  const v = $('bk-dp')?.value;
  if (v === '' || v == null) return 0;
  return parseInt(v, 10) || 0;
}

function formatPct(n) {
  if (!Number.isFinite(n)) return '';
  const rounded = Math.round(n * 100) / 100;
  return String(rounded);
}

function syncDpPercent() {
  const price = salePrice();
  const amt = dpAmount();
  if (!$('bk-dp-pct')) return;
  $('bk-dp-pct').value = price > 0 ? formatPct((amt / price) * 100) : '';
}

function syncDpAmount() {
  const price = salePrice();
  const raw = $('bk-dp-pct')?.value;
  if (!$('bk-dp')) return;
  if (raw === '' || raw == null) {
    $('bk-dp').value = '';
    return;
  }
  const pct = parseFloat(raw);
  if (!price || !Number.isFinite(pct)) return;
  $('bk-dp').value = String(Math.round(price * pct / 100));
}

function fillPricingFromUnit(unit) {
  const price = unit.price || unit.base_sale_price || '';
  const dp = unit.booking_amount_required;
  if (price !== '' && $('bk-price')) $('bk-price').value = price;
  if ($('bk-dp')) {
    $('bk-dp').value = dp != null && dp !== '' ? dp : '';
  }
  dpLast = 'amount';
  syncDpPercent();
}

function dItem(label, value, html = false) {
  if (value == null || value === '' || value === '—') return '';
  return `<div class="bk-ditem"><label>${esc(label)}</label><span>${html ? value : esc(String(value))}</span></div>`;
}

function statusBadge(text) {
  if (!text) return '';
  const t = String(text).toLowerCase();
  let cls = 'bg-grey';
  if (t.includes('overdue')) cls = 'bg-red';
  else if (t.includes('track') || t.includes('cleared') || t.includes('active')) cls = 'bg-green';
  else if (t.includes('hold')) cls = 'bg-yellow';
  return `<span class="badge ${cls}">${esc(text)}</span>`;
}

function updateSelectionDetails() {
  const box = $('bk-details');
  if (!box) return;
  if (!selectedCustomer && !selectedProject && !selectedUnit) {
    box.hidden = true;
    box.innerHTML = '';
    return;
  }
  box.hidden = false;
  const cards = [];

  if (selectedCustomer) {
    const c = selectedCustomer;
    const father = c.father_name ? `S/O ${c.father_name}` : '';
    cards.push(`
      <div class="bk-dcard full">
        <h4>Customer</h4>
        <div class="bk-dhead">
          <div class="bk-av lg">${esc(initials(c.name))}</div>
          <div style="flex:1;min-width:0">
            <div class="bk-dname">${esc(c.name)}</div>
            ${father ? `<div class="bk-dsub">${esc(father)}</div>` : ''}
          </div>
          ${c.cust_status ? statusBadge(c.cust_status) : ''}
        </div>
        <div class="bk-dgrid">
          ${dItem('Phone', c.phone || c.contact_number)}
          ${dItem('Emergency', c.emergency_contact_number)}
          ${dItem('CNIC', c.cnic)}
          ${dItem('Email', c.email)}
          ${dItem('Address', c.address || c.residential_address)}
          ${dItem('Booked units', c.units)}
          ${dItem('Total value', c.total_value ? fmt(c.total_value) : null)}
          ${dItem('Paid', c.total_paid ? fmt(c.total_paid) : null)}
          ${dItem('Outstanding', c.outstanding ? fmt(c.outstanding) : null)}
          ${dItem('Last payment', c.last_payment)}
        </div>
      </div>`);
  }

  if (selectedProject) {
    const p = selectedProject;
    cards.push(`
      <div class="bk-dcard">
        <h4>Project</h4>
        <div class="bk-dhead">
          <div class="bk-av proj lg">${esc(initials(p.name))}</div>
          <div style="flex:1;min-width:0">
            <div class="bk-dname">${esc(p.name)}</div>
            <div class="bk-dsub">${esc([p.location, p.city].filter(Boolean).join(' · ') || '—')}</div>
          </div>
          ${p.status ? statusBadge(p.status) : ''}
        </div>
        <div class="bk-dgrid cols-2">
          ${dItem('Location', p.location)}
          ${dItem('City', p.city)}
          ${dItem('Available', p.available != null ? String(p.available) : null)}
          ${dItem('On hold', p.hold != null ? String(p.hold) : null)}
          ${dItem('Sold', p.sold != null ? String(p.sold) : null)}
          ${dItem('Total units', p.total_units != null ? String(p.total_units) : null)}
          ${p.project_type === 'housing_scheme' ? '' : dItem('Floors', p.number_of_floors || null)}
          ${dItem('Timeline', (p.start_date || p.end_date) ? `${p.start_date || '—'} → ${p.end_date || '—'}` : null)}
        </div>
      </div>`);
  }

  if (selectedUnit) {
    const u = selectedUnit;
    const st = unitStatus(u);
    const attrs = parseAttrList(u.unit_attributes);
    const attrHtml = attrs.length
      ? attrs.map((a) => `<span class="badge bg-blue" style="margin:2px 4px 0 0">${esc(a)}</span>`).join('')
      : null;
    cards.push(`
      <div class="bk-dcard">
        <h4>Unit</h4>
        <div class="bk-dhead">
          <div style="flex:1;min-width:0">
            <div class="bk-dname">${esc(u.unit_no)}</div>
            <div class="bk-dsub">${esc(u.project_name || selectedProject?.name || '')}</div>
          </div>
          <span class="bk-status ${st === 'hold' ? 'hold' : 'avail'}">${statusLabel(u)}</span>
        </div>
        <div class="bk-dgrid cols-2">
          ${dItem('Type', u.type_label || u.type || u.unit_type)}
          ${dItem('Layout', u.residential_type)}
          ${dItem('Floor', u.floor != null || u.floor_number != null ? String(u.floor ?? u.floor_number) : null)}
          ${dItem('Block / Tower', u.block_tower)}
          ${dItem('Area', u.area_ghaz != null ? `${u.area_ghaz} ghaz` : null)}
          ${dItem('Size', u.size_sqft ? `${u.size_sqft} sqft` : null)}
          ${dItem('Bedrooms', u.bedrooms)}
          ${dItem('Bathrooms', u.bathrooms)}
          ${dItem('Price', u.price || u.base_sale_price ? fmt(u.price || u.base_sale_price) : null)}
          ${dItem('Booking required', u.booking_amount_required ? fmt(u.booking_amount_required) : null)}
          ${dItem('Furnishing', u.furnishing_status)}
          ${dItem('Possession', u.possession_date)}
          ${dItem('Hold until', u.hold_until)}
          ${dItem('Features', attrHtml, true)}
        </div>
        ${u.description ? `<div class="bk-ditem" style="margin-top:10px"><label>Description</label><span>${esc(u.description)}</span></div>` : ''}
      </div>`);
  }

  box.innerHTML = cards.join('');
}

function instPlanTotal() {
  let total = 0;
  $('instRows')?.querySelectorAll('.inst-row').forEach((row) => {
    total += parseInt(row.querySelector('[data-inst="amt"]')?.value, 10) || 0;
  });
  return total;
}

function remainingAmount() {
  return Math.max(salePrice() - dpAmount(), 0);
}

function updatePlanBalance() {
  const el = $('bk-plan-balance');
  if (!el) return;
  const remaining = remainingAmount();
  const planned = instPlanTotal();
  const rows = $('instRows')?.querySelectorAll('.inst-row').length || 0;
  if (!rows) {
    el.hidden = true;
    el.textContent = '';
    el.className = 'bk-plan-balance';
    return;
  }
  el.hidden = false;
  const diff = remaining - planned;
  if (diff === 0) {
    el.className = 'bk-plan-balance ok';
    el.textContent = `Balanced · ${fmt(remaining)}`;
  } else if (diff > 0) {
    el.className = 'bk-plan-balance warn';
    el.textContent = `Short ${fmt(diff)}`;
  } else {
    el.className = 'bk-plan-balance warn';
    el.textContent = `Over ${fmt(-diff)}`;
  }
}

export function updateBookingSummary() {
  const box = $('booking-summary');
  const price = salePrice();
  const dp = dpAmount();
  const remaining = remainingAmount();
  const pct = price > 0 ? (dp / price) * 100 : 0;
  if ($('bk-remaining')) $('bk-remaining').value = fmt(remaining);
  updatePlanBalance();
  if (!box) return;
  const pctLabel = price > 0 ? ` · ${formatPct(pct)}%` : '';
  box.innerHTML = `
    <div class="sum-row"><span class="sum-lbl">Customer</span><span class="sum-val">${selectedCustomer ? esc(selectedCustomer.name) : '—'}</span></div>
    <div class="sum-row"><span class="sum-lbl">Project</span><span class="sum-val">${selectedProject ? esc(selectedProject.name) : '—'}</span></div>
    <div class="sum-row"><span class="sum-lbl">Unit</span><span class="sum-val">${selectedUnit ? esc(selectedUnit.unit_no) : '—'}</span></div>
    <div class="sum-row"><span class="sum-lbl">Sale Price</span><span class="sum-val" style="font-size:15px">${fmt(price)}</span></div>
    <div class="sum-row"><span class="sum-lbl">Down Payment</span><span class="sum-val" style="color:var(--success)">${fmt(dp)}${pctLabel}</span></div>
    <div class="sum-row"><span class="sum-lbl">Remaining</span><span class="sum-val" style="color:var(--danger)">${fmt(remaining)}</span></div>
    <div class="sum-row"><span class="sum-lbl">Installments</span><span class="sum-val">${instPlanTotal() ? fmt(instPlanTotal()) : '—'}</span></div>
    <div class="prog" style="margin-top:10px"><div class="prog-fill g" style="width:${Math.min(Math.round(pct), 100)}%"></div></div>`;
  paintCommissionPreview();
}

export function addInstRow(prefill = {}) {
  if (!$('instRows')) return;
  const typeOpts = ['Booking', 'Monthly', 'Quarterly', 'Stage', 'Possession'];
  if (prefill.type && !typeOpts.includes(prefill.type)) typeOpts.push(prefill.type);
  const r = document.createElement('div');
  r.className = 'inst-row';
  r.dataset.triggerKind = prefill.trigger_kind || 'time';
  if (prefill.trigger_progress != null) r.dataset.triggerProgress = String(prefill.trigger_progress);
  if (prefill.forecast_due_date) r.dataset.forecast = prefill.forecast_due_date;
  if (prefill.due_days_after_trigger != null) r.dataset.dueDays = String(prefill.due_days_after_trigger);
  if (prefill.template_rule_id != null) r.dataset.ruleId = String(prefill.template_rule_id);
  if (prefill.trigger_label) r.dataset.triggerLabel = prefill.trigger_label;
  r.innerHTML = `
    <input data-inst="amt" type="number" min="0" placeholder="Amount" value="${prefill.amount || ''}">
    <input data-inst="date" type="date" value="${prefill.due_date || prefill.forecast_due_date || ''}">
    <select data-inst="type">
      ${typeOpts.map((t) => `<option${(prefill.type || 'Monthly') === t ? ' selected' : ''}>${esc(t)}</option>`).join('')}
    </select>
    <input data-inst="notes" type="text" placeholder="Notes" value="${esc(prefill.notes || '')}">
    <button type="button" class="del-btn" title="Remove">🗑</button>`;
  const markCustom = () => {
    if (planSource === 'template') {
      planSource = 'custom';
      if ($('bk-plan-source')) $('bk-plan-source').value = 'custom';
      syncPlanSourceUi();
    }
  };
  r.querySelector('.del-btn').addEventListener('click', () => {
    r.remove();
    markCustom();
    updateBookingSummary();
  });
  r.querySelectorAll('input, select').forEach((el) => {
    el.addEventListener('input', () => { markCustom(); updateBookingSummary(); });
    el.addEventListener('change', () => { markCustom(); updateBookingSummary(); });
  });
  $('instRows').appendChild(r);
  updateBookingSummary();
}

function generatePlan() {
  const remaining = remainingAmount();
  const count = parseInt($('bk-plan-count').value, 10);
  const freq = $('bk-plan-freq').value;
  const start = $('bk-plan-start').value;
  if (remaining <= 0) {
    toast('Nothing remaining to split. Lower the down payment or raise the sale price.', 'error');
    return;
  }
  if (!count || count < 1) {
    toast('Enter installment count.', 'error');
    return;
  }
  if (!start) {
    toast('Pick a start date.', 'error');
    return;
  }
  const step = freq === 'Quarterly' ? 3 : 1;
  const base = Math.floor(remaining / count);
  const last = remaining - base * (count - 1);
  $('instRows').innerHTML = '';
  for (let i = 0; i < count; i += 1) {
    addInstRow({
      amount: i === count - 1 ? last : base,
      due_date: addMonths(start, i * step),
      type: freq,
      notes: `${freq} ${i + 1}/${count}`,
    });
  }
  toast(`Generated ${count} ${freq.toLowerCase()} installments`);
}

export async function resetBookingForm() {
  selectedCustomer = null;
  selectedProject = null;
  selectedUnit = null;
  dpLast = 'amount';
  planSource = 'custom';
  activeTemplateMeta = null;
  heldCustomerId = null;
  ['bk-price', 'bk-dp', 'bk-dp-pct', 'bk-customer-q', 'bk-project-q', 'bk-unit-q'].forEach((id) => {
    if ($(id)) $(id).value = '';
  });
  if ($('bk-plan-source')) $('bk-plan-source').value = 'custom';
  if ($('bk-agent')) $('bk-agent').value = '';
  if ($('bk-comm-override')) $('bk-comm-override').checked = false;
  if ($('bk-comm-override-fields')) $('bk-comm-override-fields').hidden = true;
  setUnitEnabled(false);
  hideAllLists();
  if ($('instRows')) $('instRows').innerHTML = '';
  syncPlanSourceUi();
  updateSelectionDetails();
  await initBooking();
}

function collectInstallments() {
  const rows = [];
  $('instRows')?.querySelectorAll('.inst-row').forEach((row) => {
    const amount = parseInt(row.querySelector('[data-inst="amt"]')?.value, 10);
    const due_date = row.querySelector('[data-inst="date"]')?.value;
    const type = row.querySelector('[data-inst="type"]')?.value || 'Monthly';
    const notes = row.querySelector('[data-inst="notes"]')?.value || '';
    if (!amount) return;
    const item = {
      amount,
      due_date: due_date || row.dataset.forecast || todayISO(),
      type,
      notes,
      trigger_kind: row.dataset.triggerKind || 'time',
      trigger_progress: row.dataset.triggerProgress ? parseInt(row.dataset.triggerProgress, 10) : null,
      forecast_due_date: row.dataset.forecast || due_date || null,
      due_days_after_trigger: row.dataset.dueDays ? parseInt(row.dataset.dueDays, 10) : 0,
      template_rule_id: row.dataset.ruleId ? parseInt(row.dataset.ruleId, 10) : null,
      trigger_label: row.dataset.triggerLabel || type,
      label: type,
    };
    rows.push(item);
  });
  return rows;
}

export async function submitBooking() {
  if (!selectedCustomer?.id) {
    toast('Select a customer.', 'error');
    return;
  }
  if (!selectedUnit?.id || !selectedProject?.id) {
    toast('Select a project and unit.', 'error');
    return;
  }
  const price = salePrice();
  const dp = dpAmount();
  if (!price) {
    toast('Enter sale price and down payment.', 'error');
    return;
  }
  if (dp < 0) {
    toast('Down payment cannot be negative.', 'error');
    return;
  }
  if (dp > price) {
    toast('Down payment cannot exceed sale price.', 'error');
    return;
  }
  const installments = collectInstallments();
  const remaining = price - dp;
  const planned = installments.reduce((s, i) => s + i.amount, 0);
  if (remaining > 0 && !installments.length) {
    toast('Add installments or generate a plan.', 'error');
    return;
  }
  if (remaining > 0 && planned !== remaining) {
    if (!await askConfirm(`Installments (${fmt(planned)}) do not match remaining (${fmt(remaining)}). Save anyway?`, {
      title: 'Plan does not match',
      confirmLabel: 'Save anyway',
    })) return;
  }

  const payload = {
    customer_id: selectedCustomer.id,
    unit_id: selectedUnit.id,
    project_id: selectedProject.id,
    booking_date: $('bk-date').value || todayISO(),
    sale_price: price,
    base_sale_price: selectedUnit.base_sale_price || price,
    down_payment: dp,
    booking_amount: dp,
    agent_id: parseInt($('bk-agent').value, 10) || null,
    payment_mode: 'Cheque',
    installments,
    plan_source: planSource,
    template_id: planSource === 'template' ? (activeTemplateMeta?.id || null) : null,
    template_revision: planSource === 'template' ? (activeTemplateMeta?.revision || null) : null,
    template_name: planSource === 'template' ? (activeTemplateMeta?.name || null) : null,
  };
  if (payload.agent_id && $('bk-comm-override')?.checked) {
    const mode = $('bk-comm-mode')?.value || 'percent';
    payload.commission_mode = mode;
    if (mode === 'percent') payload.commission_rate_pct = parseFloat($('bk-comm-rate')?.value) || 0;
    if (mode === 'flat') payload.commission_flat_amount = parseInt($('bk-comm-flat')?.value, 10) || 0;
    if (mode === 'over_base') payload.commission_over_base_pct = parseFloat($('bk-comm-over')?.value) || 100;
  }

  if (!await askConfirm(
    `Confirm booking ${selectedUnit.unit_no || ''} for ${selectedCustomer.name} at ${fmt(price)} (DP ${fmt(dp)})?`,
    { title: 'Confirm booking', confirmLabel: 'Confirm booking' },
  )) return;

  const r = await api('/api/bookings', { method: 'POST', body: JSON.stringify(payload) });
  toast(`Booking confirmed · ${r.booking_id}`);
  const custId = selectedCustomer.id;
  const bookingId = r.booking_id;
  await resetBookingForm();
  if (await askConfirm('Generate an allotment letter for this booking now?', {
    title: 'Issue document',
    confirmLabel: 'Generate letter',
    cancelLabel: 'Skip',
  })) {
    const { openGenerate } = await import('./documents.js');
    await openGenerate({ customerId: custId, bookingId, kind: 'letter' });
  }
}

function moveHighlight(menu, dir) {
  const opts = [...menu.querySelectorAll('.bk-opt')];
  if (!opts.length) return;
  const cur = opts.findIndex((o) => o.classList.contains('hl'));
  const next = cur < 0 ? (dir > 0 ? 0 : opts.length - 1) : (cur + dir + opts.length) % opts.length;
  opts.forEach((o) => o.classList.remove('hl'));
  opts[next].classList.add('hl');
  opts[next].scrollIntoView({ block: 'nearest' });
}

function bindCombo(inputId, listId, paint, onPick) {
  const input = $(inputId);
  const menu = $(listId);
  if (!input || !menu) return;

  input.addEventListener('focus', () => {
    if (input.disabled) return;
    paint();
    showList(listId);
  });
  input.addEventListener('input', () => {
    if (input.disabled) return;
    paint();
    showList(listId);
  });
  input.addEventListener('keydown', (e) => {
    if (input.disabled) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (menu.hidden) { paint(); showList(listId); }
      moveHighlight(menu, 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (menu.hidden) { paint(); showList(listId); }
      moveHighlight(menu, -1);
    } else if (e.key === 'Enter') {
      const pick = menu.querySelector('.bk-opt.hl') || menu.querySelector('.bk-opt');
      if (pick && !menu.hidden) {
        e.preventDefault();
        onPick(parseInt(pick.dataset.id, 10));
      }
    } else if (e.key === 'Escape') {
      hideList(listId);
    }
  });
}

export function initBookingEvents() {
  bindCombo('bk-customer-q', 'bk-customer', paintCustomers, selectCustomer);
  bindCombo('bk-project-q', 'bk-project', paintProjects, selectProject);
  bindCombo('bk-unit-q', 'bk-unit', paintUnits, selectUnit);

  $('s-booking')?.addEventListener('mousedown', (e) => {
    const opt = e.target.closest('.bk-opt');
    if (!opt) return;
    e.preventDefault();
    const id = parseInt(opt.dataset.id, 10);
    const menu = opt.closest('.bk-menu');
    if (menu?.id === 'bk-customer') selectCustomer(id);
    if (menu?.id === 'bk-project') selectProject(id);
    if (menu?.id === 'bk-unit') selectUnit(id);
  });

  document.addEventListener('mousedown', (e) => {
    if (!e.target.closest('.bk-combo')) hideAllLists();
  });

  $('bk-price')?.addEventListener('input', () => {
    if (dpLast === 'pct') syncDpAmount();
    else syncDpPercent();
    updateBookingSummary();
  });
  $('bk-dp')?.addEventListener('input', () => {
    dpLast = 'amount';
    syncDpPercent();
    updateBookingSummary();
  });
  $('bk-dp-pct')?.addEventListener('input', () => {
    dpLast = 'pct';
    syncDpAmount();
    updateBookingSummary();
  });
  $('btn-add-inst')?.addEventListener('click', () => addInstRow());
  $('btn-add-inst-2')?.addEventListener('click', () => addInstRow());
  $('btn-gen-plan')?.addEventListener('click', () => {
    planSource = 'custom';
    if ($('bk-plan-source')) $('bk-plan-source').value = 'custom';
    syncPlanSourceUi();
    generatePlan();
  });
  $('bk-plan-source')?.addEventListener('change', () => {
    syncPlanSourceUi();
    if (planSource === 'template') loadTemplatePlan();
  });
  $('btn-load-tmpl')?.addEventListener('click', loadTemplatePlan);
  $('bk-price')?.addEventListener('change', () => {
    if (planSource === 'template') loadTemplatePlan();
  });
  $('bk-dp')?.addEventListener('change', () => {
    if (planSource === 'template') loadTemplatePlan();
  });
  $('btn-reset-booking')?.addEventListener('click', resetBookingForm);
  $('btn-submit-booking')?.addEventListener('click', submitBooking);
  $('bk-agent')?.addEventListener('change', () => {
    applyAgentDealToOverride(selectedBookingAgent());
    if ($('bk-comm-override')) $('bk-comm-override').checked = false;
    syncBkCommOverrideFields();
  });
  $('bk-comm-override')?.addEventListener('change', () => {
    if ($('bk-comm-override').checked) applyAgentDealToOverride(selectedBookingAgent());
    syncBkCommOverrideFields();
  });
  $('bk-comm-mode')?.addEventListener('change', syncBkCommOverrideFields);
  ['bk-comm-rate', 'bk-comm-flat', 'bk-comm-over'].forEach((id) => {
    $(id)?.addEventListener('input', paintCommissionPreview);
  });
}
