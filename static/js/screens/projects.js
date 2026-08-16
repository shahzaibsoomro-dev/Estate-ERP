import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort } from '../format.js';
import { askConfirm } from '../dialog.js';
import { openModal, closeModal } from '../modal.js';
import { state } from '../state.js';
import { goScreen } from '../nav.js';
import { unitFormHtml, readUnitForm, openUnitFormModal, bindResidentialPreset } from '../unit-form.js';
import { projectDetailsHtml } from '../detail.js';
import { loadProjectFilterOptions } from '../project-filter.js';

let onboardStep = 1;
let unitRowSeq = 0;
let projectFormMode = 'create';
let editProjectId = null;

export async function refreshProjectSelects() {
  const projects = await api('/api/projects');
  loadProjectFilterOptions(projects);
  const opts = projects.map((p) =>
    `<option value="${p.id}">${esc(p.name)}</option>`).join('');
  if ($('sl-proj')) $('sl-proj').innerHTML = `<option value="">Select…</option>${opts}`;
  if ($('site-f-proj')) $('site-f-proj').innerHTML = `<option value="">All (top filter)</option>${opts}`;
  if ($('ni-proj')) $('ni-proj').innerHTML = `<option value="">Company (no project)</option>${opts}`;
}

export async function loadProjects() {
  const data = await api('/api/projects');
  loadProjectFilterOptions(data);

  if (!data.length) {
    $('projects-list').innerHTML = '<div class="loading" style="padding:24px">No projects yet — click + New Project to add one</div>';
    return;
  }

  $('projects-list').innerHTML = data.map((p) => `
    <div class="card"><div class="card-bd">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">
        <div>
          <div class="card-click-title" style="font-size:16px;font-weight:900" data-proj-detail="${p.id}" title="View project details">${esc(p.name)}</div>
          <div style="font-size:11.5px;color:var(--g400);margin-top:2px">📍 ${esc(p.location || '—')}${p.city ? ` · ${esc(p.city)}` : ''} &nbsp;|&nbsp; ${esc(p.start_date || '—')} → ${esc(p.end_date || '—')}</div>
        </div>
        <span class="badge ${p.status === 'Completed' ? 'bg-grey' : 'bg-green'}">${esc(p.status)}</span>
      </div>
      <div class="g4" style="margin-bottom:14px">
        <div class="sm"><div class="sm-v">${p.total_units}</div><div class="sm-l">Total</div></div>
        <div class="sm"><div class="sm-v" style="color:var(--success)">${p.sold}</div><div class="sm-l">Sold</div></div>
        <div class="sm"><div class="sm-v" style="color:var(--blue)">${p.available}</div><div class="sm-l">Available</div></div>
        <div class="sm"><div class="sm-v" style="color:var(--accent)">${p.hold}</div><div class="sm-l">Hold</div></div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:11.5px;margin-bottom:4px">
        <span style="font-weight:700;color:var(--g500)">Construction Progress</span>
        <span style="font-weight:900;color:${p.progress >= 80 ? 'var(--success)' : p.progress >= 50 ? 'var(--blue)' : 'var(--accent)'}">${p.progress}%</span>
      </div>
      <div class="prog"><div class="prog-fill ${p.progress === 100 ? 'g' : p.progress < 50 ? 'a' : ''}" style="width:${p.progress}%"></div></div>
      <div style="font-size:11.5px;color:var(--g500);margin-top:8px">Vendor spend ${fmtShort(p.po_total || 0)} · paid ${fmtShort(p.vendor_paid || 0)} · due ${fmtShort(p.vendor_outstanding || 0)}</div>
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
        <button type="button" class="btn sm" data-proj-detail="${p.id}">Details</button>
        <button type="button" class="btn sm" data-proj-edit="${p.id}">Edit</button>
        <button type="button" class="btn sm" data-proj-units="${p.id}">View Units</button>
        <button type="button" class="btn sm" data-screen="site">Site Logs</button>
        <button type="button" class="btn sm" data-screen="accounts">Financials</button>
        <button type="button" class="btn sm danger" data-delete-project="${p.id}">Delete</button>
      </div>
    </div></div>`).join('');

  $('projects-list').querySelectorAll('[data-proj-units]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const id = parseInt(btn.dataset.projUnits, 10);
      import('./units.js').then(({ setUnitsProjectId }) => {
        setUnitsProjectId(id);
        goScreen('units');
      });
    });
  });
  $('projects-list').querySelectorAll('[data-proj-detail]').forEach((el) => {
    el.addEventListener('click', () => openProjectDetail(parseInt(el.dataset.projDetail, 10)));
  });
  $('projects-list').querySelectorAll('[data-proj-edit]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      openProjectEditModal(parseInt(btn.dataset.projEdit, 10));
    });
  });
  $('projects-list').querySelectorAll('[data-screen]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      goScreen(btn.dataset.screen);
    });
  });
  $('projects-list').querySelectorAll('[data-delete-project]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      deleteProject(parseInt(btn.dataset.deleteProject, 10));
    });
  });
}

async function deleteProject(id) {
  let p = state.projects.find((x) => x.id === id);
  if (!p) {
    try {
      p = await api(`/api/projects/${id}`);
    } catch {
      return;
    }
  }

  const name = p.name || 'this project';
  const total = p.total_units || 0;
  const sold = p.sold || 0;
  const avail = (p.available || 0) + (p.hold || 0);

  let msg = `Delete project "${name}"?\n\nThis cannot be undone.`;
  if (total) {
    msg += `\n\nThis project has ${total} unit(s)`;
    if (sold) msg += ` (${sold} sold/booked`;
    if (avail) msg += sold ? `, ${avail} available/hold)` : ` (${avail} available/hold)`;
    else if (sold) msg += ')';
    msg += '.\nRemove all units from Unit Inventory before deleting the project.';
  }

  if (!await askConfirm(msg, { title: 'Delete project', confirmLabel: 'Delete', danger: true })) return;

  try {
    await api(`/api/projects/${id}`, { method: 'DELETE' });
    toast(`Project "${name}" deleted`);
    await refreshProjectSelects();
    await loadProjects();
  } catch {
    /* api() already toasts the server message */
  }
}

export async function openProjectDetail(projectId) {
  openModal('project-detail-modal');
  $('pd-title').textContent = 'Loading…';
  $('pd-body').innerHTML = '<div class="loading"><span class="spinner"></span>Loading project…</div>';

  try {
    const [p, units, budget] = await Promise.all([
      api(`/api/projects/${projectId}`),
      api(`/api/units?project_id=${projectId}`),
      api(`/api/budget/summary?project_id=${projectId}`).catch(() => []),
    ]);
    const budgetRows = (budget || []).length
      ? `<div class="detail-block"><div class="detail-block-lbl">Budget</div>
          <div class="tbl-wrap"><table><thead><tr><th>Category</th><th>Planned</th><th>Actual</th><th>Variance</th><th>Status</th></tr></thead>
          <tbody>${budget.map((b) => `
            <tr><td>${esc(b.category_name)}</td><td>${fmt(b.planned_amount)}</td>
            <td>${fmt(b.actual_spent)}</td><td>${fmt(b.variance)}</td>
            <td>${esc(b.status)}</td></tr>`).join('')}
          </tbody></table></div></div>`
      : '';
    $('pd-title').textContent = p.name;
    $('pd-body').innerHTML = `
      ${projectDetailsHtml(p, units)}
      ${budgetRows}
      <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap">
        <button type="button" class="btn sm" data-pd-edit="${p.id}">✏️ Edit Project</button>
        <button type="button" class="btn sm primary" data-pd-units="${p.id}">View All Units</button>
        <button type="button" class="btn sm danger" data-pd-delete="${p.id}">Delete Project</button>
      </div>`;

    $('pd-body').querySelector('[data-pd-units]')?.addEventListener('click', () => {
      closeModal('project-detail-modal');
      import('./units.js').then(({ setUnitsProjectId }) => {
        setUnitsProjectId(p.id);
        goScreen('units');
      });
    });
    $('pd-body').querySelector('[data-pd-edit]')?.addEventListener('click', () => {
      closeModal('project-detail-modal');
      openProjectEditModal(p.id);
    });
    $('pd-body').querySelector('[data-pd-delete]')?.addEventListener('click', () => {
      closeModal('project-detail-modal');
      deleteProject(p.id);
    });
    $('pd-body').querySelectorAll('[data-unit-open]').forEach((row) => {
      row.addEventListener('click', () => {
        const uid = parseInt(row.dataset.unitOpen, 10);
        closeModal('project-detail-modal');
        import('./units.js').then(({ openUnit }) => openUnit(uid));
      });
    });
  } catch (e) {
    $('pd-body').innerHTML = `<div class="error-box">Failed to load project: ${esc(e.message)}</div>`;
  }
}

function unitCardHtml(seq) {
  return `
    <div class="unit-onboard-card" data-unit-row="${seq}">
      <div class="unit-onboard-hd">
        <strong>Unit ${seq}</strong>
        <button type="button" class="del-btn" data-remove-unit title="Remove">🗑</button>
      </div>
      ${unitFormHtml()}
    </div>`;
}

function resetProjectForm() {
  ['np-name', 'np-location', 'np-area', 'np-city', 'np-notes', 'np-units', 'np-floors',
    'np-area-ghaz', 'np-cost', 'np-progress', 'np-tmpl-name'].forEach((id) => {
    if ($(id)) $(id).value = '';
  });
  if ($('np-status')) $('np-status').value = 'under_construction';
  if ($('np-tmpl-enable')) $('np-tmpl-enable').value = '0';
  const today = new Date().toISOString().split('T')[0];
  if ($('np-start')) $('np-start').value = today;
  if ($('np-end')) $('np-end').value = '';
  $('np-attributes')?.querySelectorAll('input[type=checkbox]').forEach((cb) => { cb.checked = false; });
  resetTemplateRules();
}

function resetTemplateRules() {
  const box = $('np-tmpl-rules');
  if (!box) return;
  box.innerHTML = '';
  EXAMPLE_TMPL_RULES.forEach((r) => addTemplateRuleRow(r));
  syncTemplateEnableUi();
}

const EXAMPLE_TMPL_RULES = [
  { label: 'Foundation', amount_pct: 20, milestone_progress: 10, due_days_after_trigger: 7 },
  { label: 'Structure 40%', amount_pct: 25, milestone_progress: 40, due_days_after_trigger: 7 },
  { label: 'Structure 70%', amount_pct: 25, milestone_progress: 70, due_days_after_trigger: 7 },
  { label: 'Finishing 90%', amount_pct: 20, milestone_progress: 90, due_days_after_trigger: 7 },
  { label: 'Possession', amount_pct: 10, milestone_progress: 100, due_days_after_trigger: 0 },
];

function addTemplateRuleRow(data = {}) {
  const box = $('np-tmpl-rules');
  if (!box) return;
  const row = document.createElement('div');
  row.className = 'form-row tmpl-rule';
  row.innerHTML = `
    <div class="fg"><label>Label</label><input data-tr="label" type="text" value="${esc(data.label || '')}"></div>
    <div class="fg"><label>% of financed</label><input data-tr="pct" type="number" min="0" max="100" step="0.01" value="${data.amount_pct ?? (data.amount_bps != null ? data.amount_bps / 100 : '')}"></div>
    <div class="fg"><label>Progress %</label><input data-tr="progress" type="number" min="0" max="100" value="${data.milestone_progress ?? data.trigger_progress ?? ''}"></div>
    <div class="fg"><label>Grace days</label><input data-tr="grace" type="number" min="0" value="${data.due_days_after_trigger ?? 0}"></div>
    <div class="fg"><label>Forecast date</label><input data-tr="forecast" type="date" value="${esc(data.forecast_due_date || '')}"></div>
    <div class="fg"><label>&nbsp;</label><button type="button" class="btn sm danger" data-tr-del>Remove</button></div>`;
  row.querySelector('[data-tr-del]')?.addEventListener('click', () => row.remove());
  box.appendChild(row);
}

function syncTemplateEnableUi() {
  const on = $('np-tmpl-enable')?.value === '1';
  if ($('np-tmpl-rules')) $('np-tmpl-rules').style.opacity = on ? '1' : '0.55';
  if ($('btn-add-tmpl-rule')) $('btn-add-tmpl-rule').hidden = !on;
  if ($('np-tmpl-name')) $('np-tmpl-name').disabled = !on;
}

function collectTemplatePayload() {
  if ($('np-tmpl-enable')?.value !== '1') return null;
  const rules = [];
  $('np-tmpl-rules')?.querySelectorAll('.tmpl-rule').forEach((row) => {
    const label = row.querySelector('[data-tr="label"]')?.value.trim();
    const pct = parseFloat(row.querySelector('[data-tr="pct"]')?.value);
    const progress = parseInt(row.querySelector('[data-tr="progress"]')?.value, 10);
    const grace = parseInt(row.querySelector('[data-tr="grace"]')?.value, 10) || 0;
    const forecast = row.querySelector('[data-tr="forecast"]')?.value || null;
    if (!label || !Number.isFinite(pct)) return;
    rules.push({
      label,
      amount_bps: Math.round(pct * 100),
      trigger_kind: 'construction',
      milestone_progress: Number.isFinite(progress) ? progress : null,
      due_days_after_trigger: grace,
      forecast_due_date: forecast,
    });
  });
  if (!rules.length) {
    toast('Add at least one template rule or disable the template', 'error');
    return false;
  }
  return {
    name: ($('np-tmpl-name')?.value || '').trim() || 'Construction installment plan',
    default_booking_bps: 1000,
    rules,
  };
}

async function saveProjectTemplate(projectId) {
  const tmpl = collectTemplatePayload();
  if (tmpl === false) return false;
  if (tmpl === null) {
    try {
      await api(`/api/projects/${projectId}/installment-template`, { method: 'DELETE' });
    } catch { /* ignore if none */ }
    return true;
  }
  await api(`/api/projects/${projectId}/installment-template`, {
    method: 'PUT',
    body: JSON.stringify(tmpl),
  });
  return true;
}

async function loadProjectTemplateIntoForm(projectId) {
  resetTemplateRules();
  if (!projectId) return;
  try {
    const tmpl = await api(`/api/projects/${projectId}/installment-template`);
    if (!tmpl?.rules?.length || tmpl.is_active === 0) {
      if ($('np-tmpl-enable')) $('np-tmpl-enable').value = '0';
      syncTemplateEnableUi();
      return;
    }
    if ($('np-tmpl-enable')) $('np-tmpl-enable').value = '1';
    if ($('np-tmpl-name')) $('np-tmpl-name').value = tmpl.name || '';
    const box = $('np-tmpl-rules');
    if (box) box.innerHTML = '';
    tmpl.rules.forEach((r) => addTemplateRuleRow(r));
    syncTemplateEnableUi();
  } catch {
    if ($('np-tmpl-enable')) $('np-tmpl-enable').value = '0';
    syncTemplateEnableUi();
  }
}

function fillProjectForm(p) {
  $('np-name').value = p.name || '';
  $('np-location').value = p.location || '';
  $('np-area').value = p.area || '';
  $('np-city').value = p.city || '';
  $('np-notes').value = p.description || '';
  $('np-start').value = p.start_date || '';
  $('np-end').value = p.expected_end_date || p.end_date || '';
  $('np-status').value = p.raw_status || 'under_construction';
  $('np-progress').value = p.current_progress ?? p.progress ?? '';
  $('np-floors').value = p.number_of_floors ?? '';
  $('np-units').value = p.number_of_units ?? '';
  $('np-area-ghaz').value = p.total_area_ghaz ?? '';
  $('np-cost').value = p.estimated_cost ?? '';
  const attrs = new Set(p.project_attributes || []);
  $('np-attributes')?.querySelectorAll('input[type=checkbox]').forEach((cb) => {
    cb.checked = attrs.has(cb.value);
  });
}

function setProjectFormMode(mode) {
  projectFormMode = mode;
  const isEdit = mode === 'edit';
  const title = $('proj-modal')?.querySelector('.modal-title span');
  if (title) title.textContent = isEdit ? 'Edit Project' : 'Project Onboarding';
  $('proj-modal')?.querySelector('.onboard-steps')?.toggleAttribute('hidden', isEdit);
  $('btn-onboard-next').hidden = isEdit || onboardStep !== 1;
  $('btn-onboard-back').hidden = isEdit || onboardStep === 1;
  $('btn-onboard-skip').hidden = isEdit || onboardStep !== 2;
  $('btn-onboard-finish').hidden = isEdit || onboardStep !== 2;
  $('btn-save-project').hidden = !isEdit;
  if (isEdit) {
    $('onboard-step-1').hidden = false;
    $('onboard-step-2').hidden = true;
  }
}

function resetUnitsList() {
  unitRowSeq = 0;
  $('np-units-list').innerHTML = '';
  addUnitRow();
}

function addUnitRow() {
  unitRowSeq += 1;
  const wrap = document.createElement('div');
  wrap.innerHTML = unitCardHtml(unitRowSeq);
  const card = wrap.firstElementChild;
  bindResidentialPreset(card);
  card.querySelector('[data-remove-unit]')?.addEventListener('click', () => {
    const rows = $('np-units-list').querySelectorAll('[data-unit-row]');
    if (rows.length <= 1) {
      toast('Keep at least one unit row, or use Skip for now', 'error');
      return;
    }
    card.remove();
    renumberUnitCards();
  });
  $('np-units-list').appendChild(card);
}

function renumberUnitCards() {
  $('np-units-list').querySelectorAll('[data-unit-row]').forEach((card, i) => {
    card.querySelector('.unit-onboard-hd strong').textContent = `Unit ${i + 1}`;
  });
}

function setOnboardStep(step) {
  onboardStep = step;
  if (projectFormMode === 'edit') return;
  $('onboard-step-1').hidden = step !== 1;
  $('onboard-step-2').hidden = step !== 2;
  document.querySelectorAll('[data-onboard-step]').forEach((el) => {
    const n = parseInt(el.dataset.onboardStep, 10);
    el.classList.toggle('active', n === step);
    el.classList.toggle('done', n < step);
  });
  $('btn-onboard-next').hidden = step !== 1;
  $('btn-onboard-back').hidden = step === 1;
  $('btn-onboard-skip').hidden = step !== 2;
  $('btn-onboard-finish').hidden = step !== 2;
}

export function openProjectModal() {
  editProjectId = null;
  resetProjectForm();
  resetUnitsList();
  setOnboardStep(1);
  setProjectFormMode('create');
  openModal('proj-modal');
}

export async function openProjectEditModal(projectId) {
  editProjectId = projectId;
  resetProjectForm();
  try {
    const p = await api(`/api/projects/${projectId}`);
    fillProjectForm(p);
    await loadProjectTemplateIntoForm(projectId);
    setProjectFormMode('edit');
    openModal('proj-modal');
  } catch {
    /* api toasts error */
  }
}

function readChecked(container, selector) {
  return [...container.querySelectorAll(selector)].map((el) => el.value);
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

function collectProjectPayload() {
  const name = $('np-name').value.trim();
  const location = $('np-location').value.trim();
  if (!name || !location) {
    toast('Project name and location are required', 'error');
    return null;
  }
  return {
    name,
    location,
    area: valOrNull($('np-area').value.trim()),
    city: valOrNull($('np-city').value.trim()),
    description: valOrNull($('np-notes').value.trim()),
    start_date: valOrNull($('np-start').value),
    expected_end_date: valOrNull($('np-end').value),
    status: $('np-status').value,
    current_progress: intOrNull($('np-progress').value) || 0,
    number_of_floors: intOrNull($('np-floors').value) || 0,
    number_of_units: intOrNull($('np-units').value) || 0,
    total_area_ghaz: floatOrNull($('np-area-ghaz').value),
    estimated_cost: intOrNull($('np-cost').value),
    project_attributes: readChecked($('np-attributes'), 'input:checked'),
  };
}

function readUnitRow(card) {
  return readUnitForm(card);
}

function collectUnitPayloads() {
  const units = [];
  $('np-units-list').querySelectorAll('[data-unit-row]').forEach((card) => {
    const row = readUnitRow(card);
    if (row) units.push(row);
  });
  return units;
}

async function saveProjectEdit() {
  const payload = collectProjectPayload();
  if (!payload || !editProjectId) return;
  if (collectTemplatePayload() === false) return;
  await api(`/api/projects/${editProjectId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
  if (!(await saveProjectTemplate(editProjectId))) return;
  toast(`Project "${payload.name}" updated`);
  closeModal('proj-modal');
  editProjectId = null;
  await refreshProjectSelects();
  await loadProjects();
}

async function createProjectWithUnits(units) {
  const payload = collectProjectPayload();
  if (!payload) return;
  if (collectTemplatePayload() === false) return;

  const created = await api('/api/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!(await saveProjectTemplate(created.id))) return;

  let createdCount = 0;
  for (const unit of units) {
    await api('/api/units', {
      method: 'POST',
      body: JSON.stringify({ ...unit, project_id: created.id }),
    });
    createdCount += 1;
  }

  closeModal('proj-modal');
  if (createdCount) {
    toast(`✅ Project "${created.name}" created with ${createdCount} unit(s)`);
  } else {
    toast(`✅ Project "${created.name}" created`);
  }
  await refreshProjectSelects();
  await loadProjects();
}

function goToUnitsStep() {
  const payload = collectProjectPayload();
  if (!payload) return;
  setOnboardStep(2);
  const planned = intOrNull($('np-units').value);
  const current = $('np-units-list').querySelectorAll('[data-unit-row]').length;
  if (planned && planned > current) {
    for (let i = current; i < Math.min(planned, 20); i += 1) addUnitRow();
    if (planned > 20) toast(`Showing first 20 unit rows — add more manually if needed`);
  }
}

export function initProjectEvents() {
  $('btn-new-project')?.addEventListener('click', openProjectModal);
  $('btn-onboard-next')?.addEventListener('click', goToUnitsStep);
  $('btn-onboard-back')?.addEventListener('click', () => setOnboardStep(1));
  $('btn-onboard-skip')?.addEventListener('click', () => createProjectWithUnits([]));
  $('btn-onboard-finish')?.addEventListener('click', () => createProjectWithUnits(collectUnitPayloads()));
  $('btn-save-project')?.addEventListener('click', saveProjectEdit);
  $('btn-add-unit-row')?.addEventListener('click', addUnitRow);
  $('btn-add-tmpl-rule')?.addEventListener('click', () => addTemplateRuleRow());
  $('np-tmpl-enable')?.addEventListener('change', syncTemplateEnableUi);
}
