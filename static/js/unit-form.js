import { $, esc } from './dom.js';
import { api, toast } from './api.js';
import { openModal, closeModal } from './modal.js';
import { parseAttrList } from './detail.js';

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

export function bindResidentialPreset(root) {
  if (!root || root.dataset.resPresetBound) return;
  root.dataset.resPresetBound = '1';
  const typeSel = root.querySelector('[data-f="residential_type"]');
  const bed = root.querySelector('[data-f="bedrooms"]');
  const bath = root.querySelector('[data-f="bathrooms"]');
  bed?.addEventListener('input', () => { bed.dataset.manual = '1'; });
  bath?.addEventListener('input', () => { bath.dataset.manual = '1'; });
  typeSel?.addEventListener('change', () => applyResidentialPreset(root, typeSel.value));
  if (typeSel?.value) applyResidentialPreset(root, typeSel.value);
}

/** Build unit form HTML (uses data-f field names). */
export function unitFormHtml(data = {}) {
  const attrs = new Set(parseAttrList(data.unit_attributes));
  return `
    <div class="form-row">
      <div class="fg"><label>Unit Number *</label><input data-f="unit_no" type="text" value="${esc(data.unit_no || '')}" placeholder="e.g. A-101"></div>
      <div class="fg"><label>Block / Tower</label><input data-f="block_tower" type="text" value="${esc(data.block_tower || '')}"></div>
      <div class="fg"><label>Unit Type</label>
        <select data-f="unit_type">
          ${['Flat', 'House', 'Shop'].map((t) =>
            `<option${(data.unit_type || 'Flat') === t ? ' selected' : ''}>${t}</option>`).join('')}
        </select>
      </div>
      <div class="fg"><label>Residential Type</label>
        <select data-f="residential_type"><option value="">—</option>${opts(RESIDENTIAL_TYPES, data.residential_type || '')}</select>
      </div>
      <div class="fg"><label>Floor Number</label><input data-f="floor_number" type="number" min="0" value="${data.floor_number ?? 1}"></div>
      <div class="fg"><label>Area (Ghaz)</label><input data-f="area_ghaz" type="number" min="0" step="0.01" value="${data.area_ghaz ?? ''}"></div>
      <div class="fg"><label>Bedrooms</label><input data-f="bedrooms" type="number" min="0" value="${data.bedrooms ?? ''}"></div>
      <div class="fg"><label>Bathrooms</label><input data-f="bathrooms" type="number" min="0" value="${data.bathrooms ?? ''}"></div>
      <div class="fg"><label>Base Sale Price (PKR)</label><input data-f="base_sale_price" type="number" min="0" value="${data.base_sale_price ?? data.price ?? ''}"></div>
      <div class="fg"><label>Booking Amount Required</label><input data-f="booking_amount_required" type="number" min="0" value="${data.booking_amount_required ?? ''}"></div>
      <div class="fg"><label>Furnishing Status</label>
        <select data-f="furnishing_status"><option value="">—</option>${opts(FURNISHING, data.furnishing_status || '')}</select>
      </div>
      <div class="fg"><label>Possession Date</label><input data-f="possession_date" type="date" value="${esc(data.possession_date || '')}"></div>
    </div>
    <div class="fg"><label>Description</label><textarea data-f="description">${esc(data.description || '')}</textarea></div>
    <div class="fg"><label>Unit Attributes</label>
      <div class="chk-grid">${UNIT_ATTRS.map((a) =>
        `<label><input type="checkbox" data-unit-attr value="${esc(a)}"${attrs.has(a) ? ' checked' : ''}> ${esc(a)}</label>`).join('')}
      </div>
    </div>
    <div class="fg"><label>Additional Requirements</label><textarea data-f="additional_requirements">${esc(data.additional_requirements || '')}</textarea></div>`;
}

export function readUnitForm(root) {
  const field = (name) => root.querySelector(`[data-f="${name}"]`);
  const unitNo = field('unit_no')?.value.trim();
  if (!unitNo) return null;
  return {
    unit_no: unitNo,
    description: valOrNull(field('description')?.value.trim()),
    unit_type: field('unit_type')?.value || 'Flat',
    residential_type: valOrNull(field('residential_type')?.value),
    floor_number: intOrNull(field('floor_number')?.value) ?? 1,
    area_ghaz: floatOrNull(field('area_ghaz')?.value),
    block_tower: valOrNull(field('block_tower')?.value.trim()),
    bedrooms: intOrNull(field('bedrooms')?.value),
    bathrooms: intOrNull(field('bathrooms')?.value),
    base_sale_price: intOrNull(field('base_sale_price')?.value),
    booking_amount_required: intOrNull(field('booking_amount_required')?.value),
    furnishing_status: valOrNull(field('furnishing_status')?.value),
    unit_attributes: [...root.querySelectorAll('[data-unit-attr]:checked')].map((el) => el.value),
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
