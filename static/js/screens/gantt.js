/** Hand-rolled Gantt for the Structure of Work: drag/resize bars, dependency arrows, today line, zoom. */
import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { fmtShort } from '../format.js';
import { can, readOnly } from '../session.js';

const DAY_MS = 86400000;
const ROW_H = 30;
const ZOOM = {
  week: { dayW: 26, step: 1 },
  month: { dayW: 9, step: 7 },
};

let zoom = 'week';
let lastPlan = null;
let range = null;   // { start, end } in day numbers
let tip = null;

const toDay = (iso) => {
  if (!iso) return null;
  const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
  if (!y || !m || !d) return null;
  return Math.round(Date.UTC(y, m - 1, d) / DAY_MS);
};
const fromDay = (n) => new Date(n * DAY_MS).toISOString().slice(0, 10);
const todayDay = () => toDay(new Date().toISOString().slice(0, 10));
const monthName = (n) => new Date(n * DAY_MS).toLocaleDateString('en-GB', { month: 'short', year: '2-digit', timeZone: 'UTC' });
const dayNum = (n) => new Date(n * DAY_MS).getUTCDate();
const isWeekend = (n) => [0, 6].includes(new Date(n * DAY_MS).getUTCDay());
const prettyDate = (iso) => (iso
  ? new Date(toDay(iso) * DAY_MS).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
  : '—');

/** Flatten stages and tasks into the rows the chart draws, in display order. */
function buildRows(plan) {
  const rows = [];
  plan.stages.forEach((stage) => {
    rows.push({ kind: 'stage', id: stage.id, name: stage.name, data: stage });
    stage.tasks.forEach((task) => rows.push({ kind: 'task', id: task.id, name: task.name, data: task }));
  });
  return rows;
}

function computeRange(rows) {
  const days = [];
  rows.forEach((r) => {
    [toDay(r.data.planned_start), toDay(r.data.planned_end)].forEach((d) => { if (d) days.push(d); });
  });
  const today = todayDay();
  if (!days.length) return { start: today - 7, end: today + 30 };
  const pad = zoom === 'week' ? 3 : 10;
  return { start: Math.min(...days) - pad, end: Math.max(...days) + pad };
}

export function renderGantt(plan) {
  lastPlan = plan;
  const host = $('gantt-root');
  if (!host) return;
  const rows = buildRows(plan);
  if (!rows.length) {
    host.innerHTML = '<div class="gantt-empty">Add stages and tasks to see the timeline.</div>';
    return;
  }
  range = computeRange(rows);
  const { dayW, step } = ZOOM[zoom];
  const totalDays = range.end - range.start + 1;
  const width = totalDays * dayW;
  const height = rows.length * ROW_H;

  host.innerHTML = `
    <div class="gantt-names">
      <div class="gantt-names-hd">Stage / task</div>
      ${rows.map((r) => `<div class="gantt-name is-${r.kind}" title="${esc(r.name)}">${esc(r.name)}</div>`).join('')}
    </div>
    <div class="gantt-scroll">
      <div class="gantt-head" style="width:${width}px">
        <div class="gantt-head-top">${headTop(width, dayW)}</div>
        <div class="gantt-head-bot">${headBottom(dayW, step)}</div>
      </div>
      <div class="gantt-body" id="gantt-body" style="width:${width}px;height:${height}px">
        <div class="gantt-grid">${gridCols(dayW, step)}</div>
        ${rows.map((r, i) => `<div class="gantt-row is-${r.kind}" style="top:${i * ROW_H}px"></div>`).join('')}
        <svg class="gantt-arrows" width="${width}" height="${height}">
          <defs><marker id="gantt-head" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
            <path d="M0 0L7 3.5L0 7z"/></marker></defs>
          <g id="gantt-arrow-paths"></g>
        </svg>
        ${rows.map((r, i) => bar(r, i, dayW)).join('')}
        ${todayLine(dayW)}
      </div>
    </div>`;

  drawArrows(rows, dayW);
  wireBars(rows, dayW);
}

function headTop(width, dayW) {
  const out = [];
  let cursor = range.start;
  while (cursor <= range.end) {
    const d = new Date(cursor * DAY_MS);
    const monthEnd = Math.round(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0) / DAY_MS);
    const stop = Math.min(monthEnd, range.end);
    const left = (cursor - range.start) * dayW;
    const w = (stop - cursor + 1) * dayW;
    out.push(`<div class="gantt-tick" style="left:${left}px;width:${w}px">${monthName(cursor)}</div>`);
    cursor = stop + 1;
  }
  return out.join('');
}

function headBottom(dayW, step) {
  const out = [];
  for (let d = range.start; d <= range.end; d += step) {
    const left = (d - range.start) * dayW;
    const label = step === 1 ? dayNum(d) : `${dayNum(d)} ${monthName(d).split(' ')[0]}`;
    const weekend = step === 1 && isWeekend(d) ? ' weekend' : '';
    out.push(`<div class="gantt-tick minor${weekend}" style="left:${left}px;width:${step * dayW}px">${label}</div>`);
  }
  return out.join('');
}

function gridCols(dayW, step) {
  const out = [];
  for (let d = range.start; d <= range.end; d += step) {
    const weekend = step === 1 && isWeekend(d) ? ' weekend' : '';
    out.push(`<div class="gantt-col${weekend}" style="left:${(d - range.start) * dayW}px;width:${step * dayW}px"></div>`);
  }
  return out.join('');
}

function todayLine(dayW) {
  const t = todayDay();
  if (t < range.start || t > range.end) return '';
  return `<div class="gantt-today" style="left:${(t - range.start) * dayW}px"></div>`;
}

function barGeometry(item, dayW) {
  const start = toDay(item.planned_start);
  const end = toDay(item.planned_end) || start;
  if (!start) return null;
  return {
    left: (start - range.start) * dayW,
    width: Math.max((end - start + 1) * dayW, dayW),
    start, end,
  };
}

function bar(row, index, dayW) {
  const geo = barGeometry(row.data, dayW);
  const top = index * ROW_H;
  if (!geo) {
    return row.kind === 'task'
      ? `<div class="gbar-nodate" style="position:absolute;top:${top + 7}px;left:6px;font-size:10px;color:var(--g300)">no dates</div>`
      : '';
  }
  if (row.kind === 'stage') {
    return `<div class="gbar stage" style="left:${geo.left}px;width:${geo.width}px;top:${top + 10}px"
              title="${esc(row.name)} · ${row.data.progress_pct}%"></div>`;
  }
  const t = row.data;
  const tone = t.dependency_warning ? ' warn' : t.status === 'done' ? ' done' : t.status === 'on_hold' ? ' hold' : '';
  const movable = can('planning', 'edit') && !readOnly();
  return `
  <div class="gbar${tone}" data-bar="${t.id}" style="left:${geo.left}px;width:${geo.width}px;top:${top + 6}px">
    <div class="gbar-fill" style="width:${t.progress_pct}%"></div>
    ${movable ? '<div class="gbar-h l"></div><div class="gbar-h r"></div>' : ''}
    <div class="gbar-txt">${esc(t.name)}${t.progress_pct ? ` · ${t.progress_pct}%` : ''}</div>
  </div>`;
}

/* ── dependency arrows ───────────────────────────────────── */
function drawArrows(rows, dayW) {
  const host = $('gantt-arrow-paths');
  if (!host) return;
  const index = new Map();
  rows.forEach((r, i) => { if (r.kind === 'task') index.set(r.id, i); });
  const paths = [];
  rows.forEach((row, i) => {
    if (row.kind !== 'task' || !row.data.depends_on_task_id) return;
    const fromIdx = index.get(row.data.depends_on_task_id);
    if (fromIdx === undefined) return;
    const from = barGeometry(rows[fromIdx].data, dayW);
    const to = barGeometry(row.data, dayW);
    if (!from || !to) return;
    const x1 = from.left + from.width;
    const y1 = fromIdx * ROW_H + 15;
    const x2 = to.left;
    const y2 = i * ROW_H + 15;
    const mid = x2 > x1 + 14 ? x1 + 10 : x1 + 10;
    const d = x2 > x1 + 14
      ? `M${x1} ${y1} H${mid} V${y2} H${x2}`
      : `M${x1} ${y1} H${mid} V${(y1 + y2) / 2} H${x2 - 12} V${y2} H${x2}`;
    paths.push(`<path class="${row.data.dependency_warning ? 'bad' : ''}" d="${d}" marker-end="url(#gantt-head)"/>`);
  });
  host.innerHTML = paths.join('');
}

/* ── drag & resize ───────────────────────────────────────── */
function wireBars(rows, dayW) {
  const byId = new Map(rows.filter((r) => r.kind === 'task').map((r) => [r.id, r.data]));
  $('gantt-body')?.querySelectorAll('[data-bar]').forEach((el) => {
    const task = byId.get(parseInt(el.dataset.bar, 10));
    el.addEventListener('pointerenter', (e) => showTip(e, task));
    el.addEventListener('pointerleave', hideTip);
    if (!can('planning', 'edit') || readOnly()) return;
    el.addEventListener('pointerdown', (e) => startDrag(e, el, task, dayW));
  });
}

function startDrag(e, el, task, dayW) {
  if (e.button !== 0) return;
  e.preventDefault();
  hideTip();
  const mode = e.target.classList.contains('l') ? 'start'
    : e.target.classList.contains('r') ? 'end' : 'move';
  const origin = { x: e.clientX, left: el.offsetLeft, width: el.offsetWidth };
  el.classList.add('dragging');
  try { el.setPointerCapture(e.pointerId); } catch { /* pointer already released */ }

  const onMove = (ev) => {
    const shift = Math.round((ev.clientX - origin.x) / dayW) * dayW;
    if (mode === 'move') {
      el.style.left = `${Math.max(origin.left + shift, 0)}px`;
    } else if (mode === 'end') {
      el.style.width = `${Math.max(origin.width + shift, dayW)}px`;
    } else {
      const left = Math.min(origin.left + shift, origin.left + origin.width - dayW);
      el.style.left = `${Math.max(left, 0)}px`;
      el.style.width = `${origin.width - (left - origin.left)}px`;
    }
  };

  const onUp = async () => {
    el.removeEventListener('pointermove', onMove);
    el.removeEventListener('pointerup', onUp);
    el.classList.remove('dragging');
    const start = range.start + Math.round(el.offsetLeft / dayW);
    const days = Math.max(Math.round(el.offsetWidth / dayW), 1);
    const body = mode === 'move'
      ? { planned_start: fromDay(start), keep_duration: true }
      : { planned_start: fromDay(start), planned_end: fromDay(start + days - 1) };
    if (body.planned_start === task.planned_start
        && (mode === 'move' || body.planned_end === task.planned_end)) return;
    try {
      await api(`/api/planning/tasks/${task.id}/move`, { method: 'POST', body: JSON.stringify(body) });
      toast(`“${task.name}” rescheduled`);
      const { refreshPlan } = await import('./planning.js');
      await refreshPlan();
    } catch {
      el.style.left = `${origin.left}px`;
      el.style.width = `${origin.width}px`;
    }
  };

  el.addEventListener('pointermove', onMove);
  el.addEventListener('pointerup', onUp);
}

/* ── tooltip ─────────────────────────────────────────────── */
function showTip(e, task) {
  if (!task) return;
  hideTip();
  tip = document.createElement('div');
  tip.className = 'gantt-tip';
  tip.innerHTML = `<b>${esc(task.name)}</b><br>${prettyDate(task.planned_start)} → ${prettyDate(task.planned_end)}
    · ${task.duration_days}d<br>${task.progress_pct}% done · ${fmtShort(task.labour_cost)} labour
    ${task.dependency_warning ? `<br><span style="color:#FBD38D">${esc(task.dependency_warning)}</span>` : ''}`;
  document.body.appendChild(tip);
  tip.style.left = `${Math.min(e.clientX + 12, window.innerWidth - 260)}px`;
  tip.style.top = `${e.clientY + 16}px`;
}

function hideTip() {
  tip?.remove();
  tip = null;
}

export function resetGanttScroll() {
  const host = $('gantt-root');
  if (!host || !range) return;
  const target = (Math.max(todayDay(), range.start) - range.start) * ZOOM[zoom].dayW - 160;
  host.scrollLeft = Math.max(target, 0);
}

export function initGanttEvents() {
  $('gantt-zoom')?.querySelectorAll('[data-zoom]').forEach((b) => b.addEventListener('click', () => {
    zoom = b.dataset.zoom;
    $('gantt-zoom').querySelectorAll('[data-zoom]').forEach((x) => x.classList.toggle('active', x === b));
    if (lastPlan) { renderGantt(lastPlan); resetGanttScroll(); }
  }));
  $('btn-gantt-today')?.addEventListener('click', resetGanttScroll);
}
