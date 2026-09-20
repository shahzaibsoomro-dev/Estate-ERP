import { $, esc } from './dom.js';
import { api, toast } from './api.js';
import { openModal, closeModal } from './modal.js';
import { parseAttrList } from './detail.js';

export const UNIT_TYPES = [
  ['residential', 'Residential'],
  ['commercial', 'Commercial'],
];
export const RESIDENTIAL_TYPES = [
  '2 Bed Lounge', '2 Bed DD', '3 Bed DD', '4 Bed', 'Studio', 'Penthouse',
];
export const RESIDENTIAL_PRESETS = {
  '2 Bed Lounge': { bedrooms: 2, bathrooms: 2 },
  '2 Bed DD': { bedrooms: 2, bathrooms: 2 },
  '3 Bed DD': { bedrooms: 3, bathrooms: 3 },
  '4 Bed': { bedrooms: 4, bathrooms: 4 },
  Studio: { bedrooms: 0, bathrooms: 1 },
  Penthouse: { bedrooms: 4, bathrooms: 4 },
};
export const FURNISHING = ['Builder Condition', 'Semi Furnished', 'Fully Furnished'];
export const UNIT_ATTRS = [
  'Corner', 'Road Facing', 'Park Facing', 'West Open', 'East Open', 'North Open', 'South Open',
  'Penthouse', 'Near Lift', 'Near Staircase', 'Roof Access',
];

export function normalizeUnitType(raw) {
  const t = String(raw || 'residential').trim().toLowerCase();
  if (['shop', 'office', 'showroom', 'warehouse', 'commercial'].includes(t)) return 'commercial';
  return 'residential';
}

export function typeLabel(raw) {
  return normalizeUnitType(raw) === 'commercial' ? 'Commercial' : 'Residential';
}

function opts(values, selected) {
  return values.map((v) =>
    `<option value="${esc(v)}"${v === selected ? ' selected' : ''}>${esc(v)}</option>`).join('');
}

function valOrNull(v) {
  return v === '' || v == null ? null : v;
}

function intOrNull(v) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : null;
}

function floatOrNull(v) {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
}

function isDefaultBedBath(value) {
  return value === '' || value == null || value === '0';
}

/** Apply residential-type bedroom/bathroom suggestions without overwriting manual edits. */
export function applyResidentialPreset(root, typeValue, { force = false } = {}) {
  const preset = RESIDENTIAL_PRESETS[typeValue];
  if (!preset || !root) return;
  const bed = root.querySelector('[data-f="bedrooms"]');
  const bath = root.querySelector('[data-f="bathrooms"]');
  if (bed && (force || (!bed.dataset.manual && isDefaultBedBath(bed.value)))) {
    bed.value = String(preset.bedrooms);
    delete bed.dataset.manual;
  }
  if (bath && (force || (!bath.dataset.manual && isDefaultBedBath(bath.value)))) {
    bath.value = String(preset.bathrooms);
    delete bath.dataset.manual;
  }
}

function syncKindFields(root) {
  const kind = root.querySelector('[data-f="unit_type"]')?.value || 'residential';
  const residential = kind === 'residential';
  root.querySelectorAll('[data-res-only]').forEach((el) => { el.hidden = !residential; });
}

function tagPickerHtml(selected) {
  const sel = new Set(selected);
  const chips = UNIT_ATTRS.filter((a) => sel.has(a)).map((a) =>
    `<button type="button" class="tag-chip" data-tag="${esc(a)}">${esc(a)} <span aria-hidden="true">×</span></button>`).join('');
  const addable = UNIT_ATTRS.filter((a) => !sel.has(a));
  return `
    <div class="tag-picker" data-tag-picker>
      <div class="tag-chips" data-tag-chips>${chips || '<span class="tag-empty">No tags yet</span>'}</div>
      <select data-tag-add ${addable.length ? '' : 'disabled'}>
        <option value="">+ Add tag</option>
        ${addable.map((a) => `<option value="${esc(a)}">${esc(a)}</option>`).join('')}
      </select>
    </div>`;
}

function selectedTags(root) {
  return [...root.querySelectorAll('[data-tag-chips] [data-tag]')].map((el) => el.dataset.tag);
}

function renderTagPicker(root, selected) {
  const wrap = root.querySelector('[data-tag-picker]')?.parentElement;
  if (!wrap) return;
  wrap.innerHTML = `<label>Amenities / tags</label>${tagPickerHtml(selected)}`;
  bindTagPicker(root);
}

function bindTagPicker(root) {
  const picker = root.querySelector('[data-tag-picker]');
  if (!picker || picker.dataset.bound) return;
  picker.dataset.bound = '1';
  picker.querySelector('[data-tag-add]')?.addEventListener('change', (e) => {
    const v = e.target.value;
    if (!v) return;
    renderTagPicker(root, [...selectedTags(root), v]);
  });
  picker.querySelector('[data-tag-chips]')?.addEventListener('click', (e) => {
    const chip = e.target.closest('[data-tag]');
    if (!chip) return;
    renderTagPicker(root, selectedTags(root).filter((t) => t !== chip.dataset.tag));
  });
}

export function bindResidentialPreset(root) {
  if (!root || root.dataset.resPresetBound) return;
  root.dataset.resPresetBound = '1';
  const typeSel = root.querySelector('[data-f="residential_type"]');
  const kindSel = root.querySelector('[data-f="unit_type"]');
  const bed = root.querySelector('[data-f="bedrooms"]');
  const bath = root.querySelector('[data-f="bathrooms"]');
  bed?.addEventListener('input', () => { bed.dataset.manual = '1'; });
  bath?.addEventListener('input', () => { bath.dataset.manual = '1'; });
  typeSel?.addEventListener('change', () => applyResidentialPreset(root, typeSel.value));
  kindSel?.addEventListener('change', () => {
    syncKindFields(root);
    if (kindSel.value === 'residential' && typeSel?.value) applyResidentialPreset(root, typeSel.value);
  });
  syncKindFields(root);
  if (typeSel?.value) applyResidentialPreset(root, typeSel.value);
  bindTagPicker(root);
}

/** Build unit form HTML (uses data-f field names). */
export function unitFormHtml(data = {}) {
  const kind = normalizeUnitType(data.unit_type || data.type);
  const attrs = parseAttrList(data.unit_attributes);
  return `
    <div class="form-row">
      <div class="fg"><label>Unit Number *</label><input data-f="unit_no" type="text" value="${esc(data.unit_no || '')}" placeholder="e.g. A-101"></div>
      <div class="fg"><label>Block / Tower</label><input data-f="block_tower" type="text" value="${esc(data.block_tower || '')}"></div>
      <div class="fg"><label>Type</label>
        <select data-f="unit_type">
          ${UNIT_TYPES.map(([v, l]) => `<option value="${v}"${kind === v ? ' selected' : ''}>${l}</option>`).join('')}
        </select>
      </div>
      <div class="fg" data-res-only><label>Layout</label>
        <select data-f="residential_type"><option value="">—</option>${opts(RESIDENTIAL_TYPES, data.residential_type || '')}</select>
      </div>
      <div class="fg"><label>Floor Number</label><input data-f="floor_number" type="number" min="0" value="${data.floor_number ?? data.floor ?? 1}" placeholder="0 = ground"></div>
      <div class="fg"><label>Area (Ghaz)</label><input data-f="area_ghaz" type="number" min="0" step="0.01" value="${data.area_ghaz ?? ''}"></div>
      <div class="fg" data-res-only><label>Bedrooms</label><input data-f="bedrooms" type="number" min="0" value="${data.bedrooms ?? ''}"></div>
      <div class="fg" data-res-only><label>Bathrooms</label><input data-f="bathrooms" type="number" min="0" value="${data.bathrooms ?? ''}"></div>
      <div class="fg"><label>Base Sale Price (PKR)</label><input data-f="base_sale_price" type="number" min="0" value="${data.base_sale_price ?? data.price ?? ''}"></div>
      <div class="fg"><label>Booking Amount Required</label><input data-f="booking_amount_required" type="number" min="0" value="${data.booking_amount_required ?? ''}"></div>
      <div class="fg"><label>Furnishing Status</label>
        <select data-f="furnishing_status"><option value="">—</option>${opts(FURNISHING, data.furnishing_status || '')}</select>
      </div>
      <div class="fg"><label>Possession Date</label><input data-f="possession_date" type="date" value="${esc(data.possession_date || '')}"></div>
    </div>
    <div class="fg"><label>Description</label><textarea data-f="description">${esc(data.description || '')}</textarea></div>
    <div class="fg"><label>Amenities / tags</label>${tagPickerHtml(attrs)}</div>
    <div class="fg"><label>Additional Requirements</label><textarea data-f="additional_requirements">${esc(data.additional_requirements || '')}</textarea></div>`;
}

export function readUnitForm(root) {
  const field = (name) => root.querySelector(`[data-f="${name}"]`);
  const unitNo = field('unit_no')?.value.trim();
  if (!unitNo) return null;
  const kind = normalizeUnitType(field('unit_type')?.value);
  const residential = kind === 'residential';
  return {
    unit_no: unitNo,
    description: valOrNull(field('description')?.value.trim()),
    unit_type: kind,
    residential_type: residential ? valOrNull(field('residential_type')?.value) : null,
    floor_number: intOrNull(field('floor_number')?.value) ?? 0,
    area_ghaz: floatOrNull(field('area_ghaz')?.value),
    block_tower: valOrNull(field('block_tower')?.value.trim()),
    bedrooms: residential ? intOrNull(field('bedrooms')?.value) : null,
    bathrooms: residential ? intOrNull(field('bathrooms')?.value) : null,
    base_sale_price: intOrNull(field('base_sale_price')?.value),
    booking_amount_required: intOrNull(field('booking_amount_required')?.value),
    furnishing_status: valOrNull(field('furnishing_status')?.value),
    unit_attributes: selectedTags(root),
    additional_requirements: valOrNull(field('additional_requirements')?.value.trim()),
    possession_date: valOrNull(field('possession_date')?.value),
  };
}

let formContext = { mode: 'add', projectId: null, unitId: null, onSaved: null };

export function openUnitFormModal({ mode, projectId, unit = null, onSaved }) {
  formContext = { mode, projectId, unitId: unit?.id || null, onSaved };
  $('unit-form-title').textContent = mode === 'edit' ? `Edit Unit — ${unit?.unit_no || ''}` : 'Add Unit';
  $('uf-body').innerHTML = unitFormHtml(unit || {});
  bindResidentialPreset($('uf-body'));
  openModal('unit-form-modal');
}

async function saveUnitForm() {
  const payload = readUnitForm($('uf-body'));
  if (!payload) {
    toast('Unit number is required', 'error');
    return;
  }
  if (formContext.mode === 'add') {
    await api('/api/units', {
      method: 'POST',
      body: JSON.stringify({ ...payload, project_id: formContext.projectId, status: 'available' }),
    });
    toast(`Unit ${payload.unit_no} added`);
  } else {
    await api(`/api/units/${formContext.unitId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    toast(`Unit ${payload.unit_no} updated`);
  }
  closeModal('unit-form-modal');
  if (formContext.onSaved) await formContext.onSaved();
}

export function initUnitFormEvents() {
  $('btn-save-unit-form')?.addEventListener('click', saveUnitForm);
}
