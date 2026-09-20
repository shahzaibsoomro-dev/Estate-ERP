import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort } from '../format.js';
import { closeModal, openModal } from '../modal.js';
import { askConfirm } from '../dialog.js';
import { state } from '../state.js';
import { can, readOnly } from '../session.js';

let budCats = [];
let budSummary = [];
let budLines = [];

const budProjectId = () => parseInt($('bud-project')?.value, 10) || null;

export async function loadBudget() {
  const pid = budProjectId();
  const projects = state.projects?.length ? state.projects : await api('/api/projects');
  if ($('bud-project') && !$('bud-project').dataset.ready) {
    $('bud-project').innerHTML = '<option value="">All projects</option>' + projects.map((p) =>
      `<option value="${p.id}">${esc(p.name)}</option>`).join('');
    $('bud-project').dataset.ready = '1';
  }
  [budCats, budSummary, budLines] = await Promise.all([
    api('/api/budget/categories'),
    api(`/api/budget/summary${pid ? `?project_id=${pid}` : ''}`),
    api(`/api/budget/lines${pid ? `?project_id=${pid}` : ''}`),
  ]);
  paintTotals();
  await paintRollup(pid);
  paintSummaryTable();
  paintLinesTable();
  paintCategories();
}

function paintTotals() {
  const planned = budSummary.reduce((a, r) => a + (r.planned_amount || 0), 0);
  const spent = budSummary.reduce((a, r) => a + (r.actual_spent || 0), 0);
  $('bud-planned').textContent = fmtShort(planned);
  $('bud-spent').textContent = fmtShort(spent);
  $('bud-var').textContent = fmtShort(planned - spent);
  $('bud-var').style.color = planned - spent < 0 ? 'var(--danger)' : 'var(--navy)';
  $('bud-used').textContent = planned ? `${Math.round(spent / planned * 100)}%` : '—';
}

async function paintRollup(pid) {
  const card = $('bud-rollup-card');
  if (!pid) { card.hidden = true; return; }
  let rollup;
  try { rollup = await api(`/api/budget/rollup?project_id=${pid}`); } catch { card.hidden = true; return; }
  const part = (label, value, sub, cls = '') => `
    <div class="bud-part ${cls}"><div class="bud-part-l">${label}</div>
      <div class="bud-part-v">${fmtShort(value)}</div><div class="bud-part-s">${sub}</div></div>`;
  $('bud-rollup').innerHTML = [
    part('BOQ material', rollup.boq_amount, 'Estimated quantities × rates'),
    part('Labour', rollup.labour_amount, 'Crew × daily rates × task duration'),
    part('Manual lines', rollup.manual_amount, 'Land, approvals, overheads'),
    part('Planned total', rollup.planned_amount, `${fmtShort(rollup.actual_spent)} spent so far`, 'total'),
    rollup.estimated_cost
      ? part('Project estimate', rollup.estimated_cost,
        `${rollup.planned_amount > rollup.estimated_cost ? 'Plan is above' : 'Plan is within'} the estimate`)
      : '',
  ].join('');
  card.hidden = false;
}

function paintSummaryTable() {
  const tone = (s) => (s === 'Exceeded' ? 'bg-red' : s === 'Near Limit' ? 'bg-yellow' : 'bg-green');
  $('bud-sum-tbody').innerHTML = budSummary.length ? budSummary.map((r) => `
    <tr>
      <td>${esc(r.project_name)}</td><td class="td-b">${esc(r.category_name)}</td>
      <td>${fmtShort(r.manual_amount)}</td><td>${fmtShort(r.boq_amount)}</td><td>${fmtShort(r.labour_amount)}</td>
      <td class="td-b">${fmt(r.planned_amount)}</td><td>${fmt(r.actual_spent)}</td>
      <td class="${r.variance < 0 ? 'td-red' : 'td-green'}">${fmt(r.variance)}</td>
      <td>${r.pct_used}%</td>
      <td><span class="badge ${tone(r.status)}">${esc(r.status)}</span></td>
    </tr>`).join('')
    : '<tr><td colspan="10" style="text-align:center;color:var(--g400)">Nothing planned yet — add BOQ lines, a Structure of Work, or a manual line</td></tr>';
}

function paintLinesTable() {
  const editable = can('budget', 'edit') && !readOnly();
  $('bud-line-tbody').innerHTML = budLines.length ? budLines.map((l) => `
    <tr>
      <td>${esc(l.project_name)}</td><td class="td-b">${esc(l.category_name)}</td>
      <td class="td-sm">${esc(l.stage_name || 'Whole project')}</td>
      <td>${fmt(l.planned_amount)}</td><td class="td-sm">r${l.revision_no ?? 1}</td>
      <td class="td-sm">${esc(l.notes || '—')}</td>
      <td>
        ${editable ? `<button type="button" class="btn sm" data-bud-rev="${l.id}">Revise</button>` : ''}
        ${can('budget', 'delete') && !readOnly() ? `<button type="button" class="btn sm danger" data-bud-del="${l.id}">✕</button>` : ''}
      </td>
    </tr>`).join('')
    : '<tr><td colspan="7" style="text-align:center;color:var(--g400)">No manual lines</td></tr>';

  $('bud-line-tbody').querySelectorAll('[data-bud-rev]').forEach((b) => b.addEventListener('click', () =>
    openRevise(budLines.find((l) => String(l.id) === b.dataset.budRev))));
  $('bud-line-tbody').querySelectorAll('[data-bud-del]').forEach((b) => b.addEventListener('click', async () => {
    const line = budLines.find((l) => String(l.id) === b.dataset.budDel);
    if (!await askConfirm(`Remove the ${line.category_name} line of ${fmt(line.planned_amount)}?`,
      { title: 'Remove budget line', danger: true, confirmLabel: 'Remove' })) return;
    try { await api(`/api/budget/lines/${line.id}`, { method: 'DELETE' }); toast('Line removed'); await loadBudget(); }
    catch { /* toasted */ }
  }));
}

function paintCategories() {
  $('bud-cat-tbody').innerHTML = budCats.length ? budCats.map((c) => `
    <tr><td class="td-b">${esc(c.name)}</td><td>${c.sort_order ?? 0}</td>
    <td>${can('budget', 'delete') && !readOnly() ? `<button type="button" class="btn sm danger" data-bud-cat-del="${c.id}">Delete</button>` : ''}</td></tr>`).join('')
    : '<tr><td colspan="3" style="text-align:center;color:var(--g400)">No categories</td></tr>';
  $('bud-cat-tbody').querySelectorAll('[data-bud-cat-del]').forEach((b) => b.addEventListener('click', async () => {
    if (!await askConfirm('Delete this category?', { title: 'Delete category', danger: true, confirmLabel: 'Delete' })) return;
    try { await api(`/api/budget/categories/${b.dataset.budCatDel}`, { method: 'DELETE' }); toast('Deleted'); await loadBudget(); }
    catch { /* toasted */ }
  }));
}

/* ── forms ───────────────────────────────────────────────── */
async function openBudLineForm() {
  const projects = state.projects?.length ? state.projects : await api('/api/projects');
  if (!budCats.length) budCats = await api('/api/budget/categories');
  $('bl-project').innerHTML = projects.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
  if (budProjectId()) $('bl-project').value = budProjectId();
  $('bl-category').innerHTML = budCats.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
  $('bl-planned').value = '';
  $('bl-notes').value = '';
  await fillStageOptions();
  openModal('bud-line-modal');
}

async function fillStageOptions() {
  const pid = parseInt($('bl-project').value, 10) || null;
  const select = $('bl-stage');
  select.innerHTML = '<option value="">Whole project</option>';
  if (!pid) return;
  try {
    const overview = await api(`/api/planning/overview?project_id=${pid}`);
    select.innerHTML += overview.stages.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join('');
  } catch { /* planning not readable for this user */ }
}

function openRevise(line) {
  $('br-line-id').value = line.id;
  $('br-what').innerHTML = `<b>${esc(line.category_name)}</b> on ${esc(line.project_name)} — currently ${fmt(line.planned_amount)} (revision ${line.revision_no ?? 1})`;
  $('br-amount').value = line.planned_amount;
  $('br-notes').value = line.notes || '';
  openModal('bud-revise-modal');
}

export function initBudgetEvents() {
  $('bud-project')?.addEventListener('change', () => loadBudget());
  $('bl-project')?.addEventListener('change', () => fillStageOptions());

  $('btn-add-bud-cat')?.addEventListener('click', () => {
    $('bc-name').value = '';
    $('bc-sort').value = budCats.length + 1;
    openModal('bud-cat-modal');
  });
  $('btn-save-bud-cat')?.addEventListener('click', async () => {
    const name = $('bc-name').value.trim();
    if (!name) { toast('Category name is required', 'error'); return; }
    try {
      await api('/api/budget/categories', {
        method: 'POST',
        body: JSON.stringify({ name, sort_order: parseInt($('bc-sort').value, 10) || 0 }),
      });
      closeModal('bud-cat-modal'); toast('Category added'); await loadBudget();
    } catch { /* toasted */ }
  });

  $('btn-add-bud-line')?.addEventListener('click', () => openBudLineForm());
  $('btn-save-bud-line')?.addEventListener('click', async () => {
    const payload = {
      project_id: parseInt($('bl-project').value, 10),
      category_id: parseInt($('bl-category').value, 10),
      planned_amount: parseInt($('bl-planned').value, 10),
      stage_id: parseInt($('bl-stage').value, 10) || null,
      notes: $('bl-notes').value.trim() || null,
    };
    if (!payload.project_id || !payload.category_id || !payload.planned_amount) {
      toast('Project, category and amount required', 'error'); return;
    }
    try {
      await api('/api/budget/lines', { method: 'POST', body: JSON.stringify(payload) });
      closeModal('bud-line-modal'); toast('Budget line added'); await loadBudget();
    } catch { /* toasted */ }
  });

  $('btn-save-bud-revise')?.addEventListener('click', async () => {
    const amount = parseInt($('br-amount').value, 10);
    if (!amount || amount <= 0) { toast('Enter the new planned amount', 'error'); return; }
    try {
      await api(`/api/budget/lines/${$('br-line-id').value}/revise`, {
        method: 'POST',
        body: JSON.stringify({ planned_amount: amount, notes: $('br-notes').value.trim() || null }),
      });
      closeModal('bud-revise-modal'); toast('Budget revised'); await loadBudget();
    } catch { /* toasted */ }
  });
}
