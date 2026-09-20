import { $, esc, loadingHtml } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort } from '../format.js';
import { closeModal, openModal } from '../modal.js';
import { askConfirm } from '../dialog.js';
import { state } from '../state.js';
import { can, readOnly } from '../session.js';
import { fillProjectSelect } from './planning.js';

let summary = null;
let stages = [];
let items = [];
let categories = [];

const boqProjectId = () => parseInt($('boq-project')?.value, 10) || null;
const num = (id) => parseFloat($(id).value) || 0;
const qty = (n) => (Number(n) % 1 === 0 ? String(Number(n)) : Number(n).toFixed(2));

export async function loadBoq() {
  const projects = state.projects?.length ? state.projects : await api('/api/projects');
  const pid = fillProjectSelect($('boq-project'), projects);
  if (!pid) {
    $('boq-tbody').innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--g400)">No project selected</td></tr>';
    return;
  }
  $('boq-tbody').innerHTML = `<tr><td colspan="10">${loadingHtml()}</td></tr>`;
  [summary, stages, items, categories] = await Promise.all([
    api(`/api/boq/summary?project_id=${pid}`),
    api(`/api/planning/overview?project_id=${pid}`).then((p) => p.stages).catch(() => []),
    api(`/api/inventory?project_id=${pid}`).catch(() => []),
    api('/api/budget/categories').catch(() => []),
  ]);
  $('boq-lines').textContent = summary.line_count;
  $('boq-estimated').textContent = fmtShort(summary.estimated_amount);
  $('boq-purchased').textContent = fmtShort(summary.purchased_amount);
  $('boq-over').textContent = summary.over_estimate;
  renderLines();
}

function renderLines() {
  const needle = ($('boq-search')?.value || '').trim().toLowerCase();
  const rows = summary.lines.filter((l) => !needle
    || `${l.name} ${l.stage_name || ''} ${l.task_name || ''} ${l.category_name || ''}`.toLowerCase().includes(needle));
  const editable = can('boq', 'edit') && !readOnly();
  const tone = (s) => (s === 'Over estimate' ? 'bg-red' : s === 'Near estimate' ? 'bg-yellow' : s === 'No estimate' ? 'bg-grey' : 'bg-green');
  $('boq-tbody').innerHTML = rows.length ? rows.map((l) => `
    <tr>
      <td class="td-b">${esc(l.name)}${l.item_name ? `<div class="td-sm">linked to ${esc(l.item_name)}</div>` : ''}</td>
      <td class="td-sm">${esc(l.stage_name || 'Whole project')}${l.task_name ? ` · ${esc(l.task_name)}` : ''}</td>
      <td>${qty(l.qty)} ${esc(l.unit || '')}</td>
      <td class="td-sm">${l.wastage_pct ? `+${l.wastage_pct}% → ${qty(l.estimated_qty)}` : '—'}</td>
      <td>${fmt(l.rate)}</td>
      <td class="td-b">${fmt(l.estimated_amount)}</td>
      <td>${qty(l.purchased_qty)} ${esc(l.unit || '')}<div class="td-sm">${fmtShort(l.purchased_amount)}${l.purchase_refs.length ? ` · ${esc(l.purchase_refs.slice(0, 2).join(', '))}${l.purchase_refs.length > 2 ? '…' : ''}` : ''}</div></td>
      <td>${qty(l.consumed_qty)} ${esc(l.unit || '')}<div class="td-sm">${usageNote(l)}</div></td>
      <td><span class="badge ${tone(l.status)}">${esc(l.status)}</span><div class="td-sm">${l.usage_pct}% used</div></td>
      <td>
        ${editable ? `<button type="button" class="btn sm" data-boq-edit="${l.id}">Edit</button>` : ''}
        ${editable && can('boq', 'delete') ? `<button type="button" class="btn sm danger" data-boq-del="${l.id}">✕</button>` : ''}
      </td>
    </tr>`).join('')
    : '<tr><td colspan="10" style="text-align:center;color:var(--g400)">No BOQ lines yet — add the materials this project needs</td></tr>';

  $('boq-tbody').querySelectorAll('[data-boq-edit]').forEach((b) => b.addEventListener('click', () =>
    openBoqForm(summary.lines.find((l) => String(l.id) === b.dataset.boqEdit))));
  $('boq-tbody').querySelectorAll('[data-boq-del]').forEach((b) => b.addEventListener('click', async () => {
    const line = summary.lines.find((l) => String(l.id) === b.dataset.boqDel);
    if (!await askConfirm(`Remove “${line.name}” from the BOQ?`,
      { title: 'Remove BOQ line', danger: true, confirmLabel: 'Remove' })) return;
    try { await api(`/api/boq/lines/${line.id}`, { method: 'DELETE' }); toast('Line removed'); await loadBoq(); }
    catch { /* toasted */ }
  }));
}

function usageNote(line) {
  if (!line.consumed_stock_qty && !line.consumed_site_qty) return 'nothing used yet';
  const parts = [];
  if (line.consumed_stock_qty) parts.push(`${qty(line.consumed_stock_qty)} issued from stock`);
  if (line.consumed_site_qty) parts.push(`${qty(line.consumed_site_qty)} on site logs`);
  return esc(parts.join(' · '));
}

/* ── form ────────────────────────────────────────────────── */
function openBoqForm(line = null) {
  $('boq-modal-title').textContent = line ? 'Edit BOQ line' : 'Add BOQ line';
  $('bq-id').value = line?.id || '';
  $('bq-item').innerHTML = '<option value="">Not linked — type a name below</option>'
    + items.map((i) => `<option value="${i.id}" data-unit="${esc(i.unit || '')}">${esc(i.name)}</option>`).join('');
  $('bq-item').value = line?.item_id || '';
  $('bq-stage').innerHTML = '<option value="">Whole project</option>'
    + stages.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join('');
  $('bq-stage').value = line?.stage_id || '';
  fillTaskOptions(line?.task_id);
  $('bq-category').innerHTML = '<option value="">Materials (default)</option>'
    + categories.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
  $('bq-category').value = line?.category_id || '';
  $('bq-name').value = line?.name || '';
  $('bq-unit').value = line?.unit || '';
  $('bq-qty').value = line?.qty ?? 0;
  $('bq-wastage').value = line?.wastage_pct ?? 0;
  $('bq-rate').value = line?.rate ?? 0;
  $('bq-notes').value = line?.notes || '';
  paintPreview();
  openModal('boq-modal');
}

function fillTaskOptions(selected) {
  const stageId = parseInt($('bq-stage').value, 10) || null;
  const pool = stageId ? stages.filter((s) => s.id === stageId) : stages;
  $('bq-task').innerHTML = '<option value="">Whole stage</option>'
    + pool.flatMap((s) => s.tasks.map((t) =>
      `<option value="${t.id}">${esc(s.name)} · ${esc(t.name)}</option>`)).join('');
  if (selected) $('bq-task').value = selected;
}

function paintPreview() {
  const q = num('bq-qty');
  const waste = num('bq-wastage');
  const rate = num('bq-rate');
  const estQty = q * (1 + waste / 100);
  $('bq-preview').innerHTML = `Estimated <b>${qty(estQty)} ${esc($('bq-unit').value || 'units')}</b>
    at ${fmt(rate)} each = <b>${fmt(Math.round(estQty * rate))}</b>`;
}

async function submitBoq() {
  const id = parseInt($('bq-id').value, 10) || null;
  const payload = {
    project_id: boqProjectId(),
    stage_id: parseInt($('bq-stage').value, 10) || 0,
    task_id: parseInt($('bq-task').value, 10) || 0,
    item_id: parseInt($('bq-item').value, 10) || 0,
    category_id: parseInt($('bq-category').value, 10) || 0,
    name: $('bq-name').value.trim(),
    unit: $('bq-unit').value.trim() || null,
    qty: num('bq-qty'),
    wastage_pct: num('bq-wastage'),
    rate: Math.round(num('bq-rate')),
    notes: $('bq-notes').value.trim() || null,
  };
  if (!payload.name && !payload.item_id) { toast('Pick a material item or type a name', 'error'); return; }
  if (payload.qty <= 0) { toast('Quantity must be greater than 0', 'error'); return; }
  try {
    if (id) await api(`/api/boq/lines/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
    else await api('/api/boq/lines', { method: 'POST', body: JSON.stringify(payload) });
    closeModal('boq-modal');
    toast(id ? 'BOQ line updated' : 'BOQ line added');
    await loadBoq();
  } catch { /* toasted */ }
}

export function initBoqEvents() {
  $('boq-project')?.addEventListener('change', () => loadBoq());
  $('boq-search')?.addEventListener('input', () => summary && renderLines());
  $('btn-add-boq')?.addEventListener('click', () => openBoqForm());
  $('btn-save-boq')?.addEventListener('click', submitBoq);
  $('bq-stage')?.addEventListener('change', () => fillTaskOptions());
  $('bq-item')?.addEventListener('change', () => {
    const opt = $('bq-item').selectedOptions[0];
    if (!opt?.value) return;
    if (!$('bq-name').value.trim()) $('bq-name').value = opt.textContent;
    if (!$('bq-unit').value.trim()) $('bq-unit').value = opt.dataset.unit || '';
    paintPreview();
  });
  ['bq-qty', 'bq-wastage', 'bq-rate', 'bq-unit'].forEach((id) => $(id)?.addEventListener('input', paintPreview));
}
