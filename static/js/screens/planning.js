import { $, esc, loadingHtml } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort } from '../format.js';
import { closeModal, openModal } from '../modal.js';
import { askConfirm } from '../dialog.js';
import { state } from '../state.js';
import { activeProjectIds } from '../project-filter.js';
import { can, readOnly } from '../session.js';
import { renderGantt, resetGanttScroll } from './gantt.js';

let plan = null;           // last /api/planning/overview payload
let planTab = 'structure';

export function currentPlan() {
  return plan;
}

export function planProjectId() {
  return parseInt($('plan-project')?.value, 10) || null;
}

const pctOf = (bps) => Number(((bps || 0) / 100).toFixed(2));
const bpsOf = (pct) => Math.round((parseFloat(pct) || 0) * 100);
const dash = (v) => (v ? esc(v) : '—');

/** Fill a project <select> from the top-bar filter, keeping the current choice when possible. */
export function fillProjectSelect(el, projects) {
  if (!el) return null;
  const allowed = new Set(activeProjectIds());
  const list = (projects || state.projects || []).filter((p) => !allowed.size || allowed.has(p.id));
  const previous = el.value;
  el.innerHTML = list.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join('')
    || '<option value="">No project</option>';
  if (previous && list.some((p) => String(p.id) === previous)) el.value = previous;
  return parseInt(el.value, 10) || null;
}

export async function loadPlanning() {
  const projects = state.projects?.length ? state.projects : await api('/api/projects');
  const pid = fillProjectSelect($('plan-project'), projects);
  if (!pid) {
    $('plan-structure').innerHTML = '<div class="empty"><b>No project selected</b>Create a project first.</div>';
    return;
  }
  $('plan-structure').innerHTML = loadingHtml('Loading plan…');
  plan = await api(`/api/planning/overview?project_id=${pid}`);
  paintSummary();
  renderStructure();
  if (planTab === 'gantt') renderGantt(plan);
}

function paintSummary() {
  const manual = plan.progress_mode === 'manual';
  $('plan-progress').textContent = `${plan.current_progress}%`;
  $('plan-progress-bar').style.width = `${plan.current_progress}%`;
  $('plan-computed').textContent = `${plan.computed_progress}%`;
  $('plan-labour').textContent = fmtShort(plan.labour_total);
  $('plan-warnings').textContent = plan.warning_count || 0;
  $('plan-warnings').style.color = plan.warning_count ? 'var(--warn)' : 'var(--success)';

  const row = $('plan-mode-row');
  row.classList.toggle('manual', manual);
  $('plan-mode-manual').checked = manual;
  $('plan-mode-note').innerHTML = manual
    ? `Progress is set by hand at <b>${plan.current_progress}%</b>. The Structure of Work says ${plan.computed_progress}% — switch the override off to follow it again.`
    : 'Progress follows the weighted tasks below, and releases construction-linked installments as it climbs.';

  let note = '';
  if (plan.stages.length && !plan.stage_weight_ok) {
    note = `Stage weights add up to ${pctOf(plan.stage_weight_bps)}% instead of 100%.`;
  } else if (plan.task_weight_issues.length) {
    const names = plan.task_weight_issues.map((i) => i.stage_name).join(', ');
    note = `Task weights don’t add up to 100% in: ${names}.`;
  }
  $('plan-warnings').title = note || 'Schedule and weights look consistent';
}

/* ── Structure list ──────────────────────────────────────── */
function renderStructure() {
  const host = $('plan-structure');
  const editable = can('planning', 'edit') && !readOnly();
  if (!plan.stages.length) {
    host.innerHTML = `<div class="empty"><b>No stages yet</b>Break the project into stages — substructure, grey structure, finishes — then add the tasks inside each one.</div>`;
    return;
  }
  host.innerHTML = plan.stages.map((s, i) => stageCard(s, i, editable)).join('');
  wireStructure(host, editable);
}

function stageCard(stage, index, editable) {
  const weightBad = plan.stages.length && !plan.stage_weight_ok;
  const taskBad = plan.task_weight_issues.some((t) => t.stage_id === stage.id);
  const dates = stage.planned_start || stage.planned_end
    ? `${dash(stage.planned_start)} → ${dash(stage.planned_end)}` : 'No dates yet';
  return `
  <div class="stage-card" data-stage="${stage.id}">
    <div class="stage-hd">
      <div class="stage-no">${index + 1}</div>
      <div class="stage-grow">
        <div class="stage-name">${esc(stage.name)}</div>
        <div class="stage-meta">${dates} · ${stage.task_count} task${stage.task_count === 1 ? '' : 's'}
          · <span${weightBad ? ' style="color:var(--warn);font-weight:700"' : ''}>${stage.weight_pct}% of project</span>
          · cumulative ${stage.cumulative_pct}%${taskBad ? ' · <span style="color:var(--warn);font-weight:700">task weights ≠ 100%</span>' : ''}
        </div>
      </div>
      <div class="stage-prog">
        <div class="stage-prog-v"><span>${esc(stage.status_label)}</span><span>${stage.progress_pct}%</span></div>
        <div class="prog"><div class="prog-fill ${stage.progress_pct >= 100 ? 'g' : ''}" style="width:${stage.progress_pct}%"></div></div>
      </div>
      ${editable ? `<div class="stage-acts">
        <button type="button" class="btn sm" data-add-task="${stage.id}">+ Task</button>
        <button type="button" class="btn sm" data-even-tasks="${stage.id}">Even task weights</button>
        <button type="button" class="btn sm" data-edit-stage="${stage.id}">Edit</button>
        ${can('planning', 'delete') ? `<button type="button" class="btn sm danger" data-del-stage="${stage.id}">Delete</button>` : ''}
      </div>` : ''}
    </div>
    ${stage.tasks.length
      ? stage.tasks.map((t) => taskRow(t, editable)).join('')
      : '<div class="stage-empty">No tasks in this stage yet.</div>'}
  </div>`;
}

function taskRow(task, editable) {
  const when = task.planned_start || task.planned_end
    ? `${dash(task.planned_start)} → ${dash(task.planned_end)} · ${task.duration_days}d` : 'No dates';
  const crew = (task.workers_skilled || task.workers_unskilled)
    ? `${task.workers_skilled} skilled · ${task.workers_unskilled} unskilled · ${fmtShort(task.labour_cost)}`
    : 'No crew planned';
  return `
  <div class="task-row" data-task="${task.id}">
    <div>
      <div class="task-name">${esc(task.name)}</div>
      <div class="task-sub">${when}</div>
    </div>
    <div class="task-sub">${task.weight_pct}% of stage</div>
    <div class="task-prog-input">
      <input type="number" min="0" max="100" value="${task.progress_pct}" data-progress="${task.id}" ${editable ? '' : 'disabled'}>
      <span class="task-sub">%</span>
    </div>
    <div class="task-sub">${esc(crew)}</div>
    <div>${task.dependency_warning
      ? `<span class="task-warn">${esc(task.dependency_warning)}</span>`
      : `<span class="task-sub">${task.depends_on_name ? `after ${esc(task.depends_on_name)}` : esc(task.status_label)}</span>`}</div>
    <div class="stage-acts">
      ${editable ? `<button type="button" class="btn sm" data-edit-task="${task.id}">Edit</button>` : ''}
      ${editable && can('planning', 'delete') ? `<button type="button" class="btn sm danger" data-del-task="${task.id}">✕</button>` : ''}
    </div>
  </div>`;
}

function wireStructure(host, editable) {
  host.querySelectorAll('[data-add-task]').forEach((b) =>
    b.addEventListener('click', () => openTaskForm(null, parseInt(b.dataset.addTask, 10))));
  host.querySelectorAll('[data-edit-stage]').forEach((b) =>
    b.addEventListener('click', () => openStageForm(findStage(parseInt(b.dataset.editStage, 10)))));
  host.querySelectorAll('[data-edit-task]').forEach((b) =>
    b.addEventListener('click', () => openTaskForm(findTask(parseInt(b.dataset.editTask, 10)))));
  host.querySelectorAll('[data-even-tasks]').forEach((b) => b.addEventListener('click', async () => {
    try {
      await api(`/api/planning/stages/${b.dataset.evenTasks}/even-task-weights`, { method: 'POST' });
      toast('Task weights split evenly'); await loadPlanning();
    } catch { /* toasted */ }
  }));
  host.querySelectorAll('[data-del-stage]').forEach((b) => b.addEventListener('click', async () => {
    const stage = findStage(parseInt(b.dataset.delStage, 10));
    const ok = await askConfirm(
      `Delete “${stage.name}” and its ${stage.task_count} task(s)? BOQ lines pointing at it stay, but lose the link.`,
      { title: 'Delete stage', danger: true, confirmLabel: 'Delete' });
    if (!ok) return;
    try { await api(`/api/planning/stages/${stage.id}`, { method: 'DELETE' }); toast('Stage deleted'); await loadPlanning(); }
    catch { /* toasted */ }
  }));
  host.querySelectorAll('[data-del-task]').forEach((b) => b.addEventListener('click', async () => {
    const task = findTask(parseInt(b.dataset.delTask, 10));
    if (!await askConfirm(`Delete “${task.name}”?`, { title: 'Delete task', danger: true, confirmLabel: 'Delete' })) return;
    try { await api(`/api/planning/tasks/${task.id}`, { method: 'DELETE' }); toast('Task deleted'); await loadPlanning(); }
    catch { /* toasted */ }
  }));
  if (!editable) return;
  host.querySelectorAll('[data-progress]').forEach((input) => {
    input.addEventListener('change', async () => {
      const value = Math.max(0, Math.min(100, parseInt(input.value, 10) || 0));
      input.value = value;
      try {
        await api(`/api/planning/tasks/${input.dataset.progress}/progress`,
          { method: 'POST', body: JSON.stringify({ progress_pct: value }) });
        await loadPlanning();
      } catch { /* toasted */ }
    });
  });
}

function findStage(id) { return plan.stages.find((s) => s.id === id); }
function findTask(id) {
  for (const s of plan.stages) {
    const t = s.tasks.find((x) => x.id === id);
    if (t) return t;
  }
  return null;
}

/* ── Stage form ──────────────────────────────────────────── */
function openStageForm(stage = null) {
  $('stage-modal-title').textContent = stage ? 'Edit stage' : 'Add stage';
  $('st-id').value = stage?.id || '';
  $('st-name').value = stage?.name || '';
  $('st-weight').value = stage ? pctOf(stage.weight_bps) : suggestedStageWeight();
  $('st-status').value = stage?.status || 'not_started';
  $('st-start').value = stage?.planned_start || '';
  $('st-end').value = stage?.planned_end || '';
  $('st-notes').value = stage?.notes || '';
  openModal('stage-modal');
}

function suggestedStageWeight() {
  const used = plan ? plan.stage_weight_bps : 0;
  return pctOf(Math.max(10000 - used, 0));
}

async function submitStage() {
  const id = parseInt($('st-id').value, 10) || null;
  const payload = {
    project_id: planProjectId(),
    name: $('st-name').value.trim(),
    weight_bps: bpsOf($('st-weight').value),
    status: $('st-status').value,
    planned_start: $('st-start').value || null,
    planned_end: $('st-end').value || null,
    notes: $('st-notes').value.trim() || null,
  };
  if (!payload.name) { toast('Stage name is required', 'error'); return; }
  try {
    if (id) await api(`/api/planning/stages/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
    else await api('/api/planning/stages', { method: 'POST', body: JSON.stringify(payload) });
    closeModal('stage-modal');
    toast(id ? 'Stage updated' : 'Stage added');
    await loadPlanning();
  } catch { /* toasted */ }
}

/* ── Task form ───────────────────────────────────────────── */
function openTaskForm(task = null, stageId = null) {
  if (!plan?.stages.length) { toast('Add a stage first', 'error'); return; }
  $('task-modal-title').textContent = task ? 'Edit task' : 'Add task';
  $('tk-id').value = task?.id || '';
  $('tk-stage').innerHTML = plan.stages.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join('');
  $('tk-stage').value = task?.stage_id || stageId || plan.stages[0].id;
  $('tk-name').value = task?.name || '';
  $('tk-start').value = task?.planned_start || '';
  $('tk-end').value = task?.planned_end || '';
  $('tk-weight').value = task ? pctOf(task.weight_bps) : suggestedTaskWeight(parseInt($('tk-stage').value, 10));
  $('tk-progress').value = task?.progress_pct ?? 0;
  $('tk-lag').value = task?.lag_days ?? 0;
  $('tk-skilled').value = task?.workers_skilled ?? 0;
  $('tk-skilled-rate').value = task?.skilled_rate ?? 0;
  $('tk-unskilled').value = task?.workers_unskilled ?? 0;
  $('tk-unskilled-rate').value = task?.unskilled_rate ?? 0;
  $('tk-status').value = task?.status === 'on_hold' ? 'on_hold' : '';
  $('tk-notes').value = task?.notes || '';
  fillDependsOptions(task);
  paintLabourPreview();
  openModal('task-modal');
}

function suggestedTaskWeight(stageId) {
  const stage = findStage(stageId);
  if (!stage) return 100;
  const used = stage.tasks.reduce((a, t) => a + (t.weight_bps || 0), 0);
  return pctOf(Math.max(10000 - used, 0));
}

function fillDependsOptions(task) {
  const options = ['<option value="">Nothing — can start any time</option>'];
  plan.stages.forEach((s) => {
    s.tasks.filter((t) => !task || t.id !== task.id).forEach((t) => {
      options.push(`<option value="${t.id}">${esc(s.name)} · ${esc(t.name)}</option>`);
    });
  });
  $('tk-depends').innerHTML = options.join('');
  $('tk-depends').value = task?.depends_on_task_id || '';
}

function paintLabourPreview() {
  const days = dayCount($('tk-start').value, $('tk-end').value);
  const daily = (parseInt($('tk-skilled').value, 10) || 0) * (parseInt($('tk-skilled-rate').value, 10) || 0)
    + (parseInt($('tk-unskilled').value, 10) || 0) * (parseInt($('tk-unskilled-rate').value, 10) || 0);
  $('tk-labour-preview').innerHTML = daily
    ? `Labour cost <b>${fmt(days * daily)}</b> — ${fmt(daily)} a day over ${days} day${days === 1 ? '' : 's'}`
    : 'Labour cost <b>PKR 0</b> — add workers and daily rates to feed the budget';
}

function dayCount(start, end) {
  if (!start || !end) return 1;
  const a = Date.parse(start);
  const b = Date.parse(end);
  if (Number.isNaN(a) || Number.isNaN(b) || b < a) return 1;
  return Math.round((b - a) / 86400000) + 1;
}

async function submitTask() {
  const id = parseInt($('tk-id').value, 10) || null;
  const payload = {
    stage_id: parseInt($('tk-stage').value, 10),
    name: $('tk-name').value.trim(),
    planned_start: $('tk-start').value || null,
    planned_end: $('tk-end').value || null,
    weight_bps: bpsOf($('tk-weight').value),
    progress_pct: parseInt($('tk-progress').value, 10) || 0,
    depends_on_task_id: parseInt($('tk-depends').value, 10) || 0,
    lag_days: parseInt($('tk-lag').value, 10) || 0,
    workers_skilled: parseInt($('tk-skilled').value, 10) || 0,
    workers_unskilled: parseInt($('tk-unskilled').value, 10) || 0,
    skilled_rate: parseInt($('tk-skilled-rate').value, 10) || 0,
    unskilled_rate: parseInt($('tk-unskilled-rate').value, 10) || 0,
    status: $('tk-status').value || null,
    notes: $('tk-notes').value.trim() || null,
  };
  if (!payload.name) { toast('Task name is required', 'error'); return; }
  if (payload.planned_start && payload.planned_end && payload.planned_end < payload.planned_start) {
    toast('Finish date cannot be before the start date', 'error'); return;
  }
  try {
    if (id) await api(`/api/planning/tasks/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
    else await api('/api/planning/tasks', { method: 'POST', body: JSON.stringify(payload) });
    closeModal('task-modal');
    toast(id ? 'Task updated' : 'Task added');
    await loadPlanning();
  } catch { /* toasted */ }
}

/* ── Events ──────────────────────────────────────────────── */
function switchTab(tab) {
  planTab = tab;
  $('plan-tabs').querySelectorAll('[data-plan-tab]').forEach((b) =>
    b.classList.toggle('active', b.dataset.planTab === tab));
  $('plan-structure').hidden = tab !== 'structure';
  $('plan-gantt').hidden = tab !== 'gantt';
  if (tab === 'gantt' && plan) { renderGantt(plan); resetGanttScroll(); }
}

export function initPlanningEvents() {
  $('plan-project')?.addEventListener('change', () => loadPlanning());
  $('plan-tabs')?.querySelectorAll('[data-plan-tab]').forEach((b) =>
    b.addEventListener('click', () => switchTab(b.dataset.planTab)));
  $('btn-add-stage')?.addEventListener('click', () => openStageForm());
  $('btn-save-stage')?.addEventListener('click', submitStage);
  $('btn-save-task')?.addEventListener('click', submitTask);
  $('btn-plan-even')?.addEventListener('click', async () => {
    const pid = planProjectId();
    if (!pid) return;
    try {
      await api(`/api/planning/even-stage-weights?project_id=${pid}`, { method: 'POST' });
      toast('Stage weights split evenly'); await loadPlanning();
    } catch { /* toasted */ }
  });
  $('plan-mode-manual')?.addEventListener('change', async (e) => {
    const pid = planProjectId();
    if (!pid) return;
    try {
      await api('/api/planning/progress-mode', {
        method: 'POST',
        body: JSON.stringify({ project_id: pid, progress_mode: e.target.checked ? 'manual' : 'auto' }),
      });
      toast(e.target.checked ? 'Progress is now set by hand on the project page' : 'Progress follows the plan again');
      await loadPlanning();
    } catch { e.target.checked = !e.target.checked; }
  });
  $('tk-stage')?.addEventListener('change', () => {
    if (!$('tk-id').value) $('tk-weight').value = suggestedTaskWeight(parseInt($('tk-stage').value, 10));
  });
  ['tk-start', 'tk-end', 'tk-skilled', 'tk-skilled-rate', 'tk-unskilled', 'tk-unskilled-rate']
    .forEach((id) => $(id)?.addEventListener('input', paintLabourPreview));
}

/** The Gantt hands moved bars back here so every view refreshes together. */
export async function refreshPlan() {
  await loadPlanning();
}
