import { $, esc, loadingHtml } from '../dom.js';
import { api, apiUpload, toast } from '../api.js';
import { fmt } from '../format.js';
import { closeModal, openModal } from '../modal.js';
import { state } from '../state.js';
import { activeProjectIds, projectFilterQuery } from '../project-filter.js';
import { refreshProjectSelects } from './projects.js';
import { askConfirm } from '../dialog.js';

function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function siteQuery() {
  const extra = {};
  const from = $('site-from')?.value;
  const to = $('site-to')?.value;
  if (from) extra.date_from = from;
  if (to) extra.date_to = to;
  const local = parseInt($('site-f-proj')?.value, 10);
  if (local) {
    extra.project_id = local;
    const p = new URLSearchParams(extra);
    return `?${p}`;
  }
  return projectFilterQuery(extra);
}

function matRowHtml(m = {}) {
  return `<div class="form-row sl-mat-row" style="align-items:end;margin-bottom:6px">
    <div class="fg"><label>Material</label><input class="sl-m-name" value="${esc(m.name || '')}" placeholder="Cement"></div>
    <div class="fg"><label>Qty</label><input class="sl-m-qty" type="number" min="0" step="any" value="${m.qty != null ? esc(String(m.qty)) : ''}"></div>
    <div class="fg"><label>Unit</label><input class="sl-m-unit" value="${esc(m.unit || '')}" placeholder="kg"></div>
    <button type="button" class="btn sm danger sl-m-del">✕</button>
  </div>`;
}

function bindMatRows() {
  $('sl-mat-rows')?.querySelectorAll('.sl-m-del').forEach((b) => {
    b.addEventListener('click', () => b.closest('.sl-mat-row')?.remove());
  });
}

function collectMaterials() {
  return [...($('sl-mat-rows')?.querySelectorAll('.sl-mat-row') || [])]
    .map((row) => ({
      name: row.querySelector('.sl-m-name')?.value.trim() || '',
      qty: row.querySelector('.sl-m-qty')?.value.trim() || null,
      unit: row.querySelector('.sl-m-unit')?.value.trim() || null,
    }))
    .filter((m) => m.name);
}

function renderExistingFiles(log) {
  const box = $('sl-existing-files');
  if (!box) return;
  const atts = log?.attachments || [];
  if (!atts.length) {
    box.innerHTML = '';
    return;
  }
  box.innerHTML = atts.map((a) => `
    <div style="display:flex;gap:8px;align-items:center;font-size:12px;margin-bottom:4px">
      <a href="/api/site-logs/${log.id}/attachments/${a.id}" target="_blank">${esc(a.filename)}</a>
      <span style="color:var(--g400)">${esc(a.kind || 'file')}</span>
      <button type="button" class="btn sm danger" data-del-att="${a.id}">Remove</button>
    </div>`).join('');
  box.querySelectorAll('[data-del-att]').forEach((b) => {
    b.addEventListener('click', async () => {
      if (!log?.id) return;
      try {
        const updated = await api(`/api/site-logs/${log.id}/attachments/${b.dataset.delAtt}`, { method: 'DELETE' });
        renderExistingFiles(updated);
        toast('Attachment removed');
      } catch { /* toasted */ }
    });
  });
}

export async function loadSite() {
  const list = $('site-logs-list');
  if (list) list.innerHTML = loadingHtml('Loading logs…');
  let logs = [];
  try {
    logs = await api(`/api/site-logs${siteQuery()}`);
  } catch {
    if (list) list.innerHTML = '<div class="loading" style="padding:24px">Could not load site logs</div>';
    return;
  }

  const local = parseInt($('site-f-proj')?.value, 10);
  const ids = local ? [local] : activeProjectIds();
  const visible = (state.projects || []).filter((p) => !ids.length || ids.includes(p.id));
  const avg = visible.length
    ? Math.round(visible.reduce((a, p) => a + (Number(p.current_progress ?? p.progress) || 0), 0) / visible.length)
    : 0;
  if ($('site-progress')) $('site-progress').textContent = visible.length ? `${avg}%` : '—';
  if ($('site-progress-bar')) $('site-progress-bar').style.width = `${avg}%`;

  const today = todayISO();
  const workers = logs
    .filter((l) => l.log_date === today)
    .reduce((a, l) => a + (l.workers_skilled || 0) + (l.workers_unskilled || 0), 0);
  if ($('site-workers')) $('site-workers').textContent = workers;
  if ($('site-log-count')) $('site-log-count').textContent = logs.length;

  if (!list) return;
  if (!logs.length) {
    list.innerHTML = '<div class="loading" style="padding:24px">No site logs yet</div>';
    return;
  }

  let lastDate = '';
  list.innerHTML = logs.map((l) => {
    const head = l.log_date !== lastDate
      ? `<div class="site-day-hd">${esc(l.log_date)}</div>` : '';
    lastDate = l.log_date;
    const hours = l.hours_worked ? `${l.hours_worked}h` : (l.time_from && l.time_to ? `${l.time_from}–${l.time_to}` : '');
    const atts = (l.attachments || []).length;
    return `${head}
      <div class="site-log">
        <div style="display:flex;justify-content:space-between;gap:12px;margin-bottom:8px;align-items:flex-start">
          <span style="font-weight:800;font-size:13px">${esc(l.project_name || 'Project')} — ${esc((l.work_done || '').substring(0, 80))}</span>
          <span style="font-size:11px;color:var(--g400);white-space:nowrap">${esc(l.engineer || '—')}${l.reporter ? ` · ${esc(l.reporter)}` : ''}</span>
        </div>
        <div class="g3" style="font-size:11.5px">
          <div><span style="color:var(--g400);font-weight:700">LABOR: </span>${l.workers_skilled || 0} skilled + ${l.workers_unskilled || 0} unskilled${hours ? ` · ${esc(hours)}` : ''}</div>
          <div><span style="color:var(--g400);font-weight:700">MATERIAL: </span>${esc(l.material_used || '—')}</div>
          <div><span style="color:var(--g400);font-weight:700">WORK: </span>${esc(l.work_done || '—')}</div>
        </div>
        ${(l.extra_expenses || atts || l.notes) ? `<div style="font-size:11.5px;margin-top:6px;color:var(--g500)">
          ${l.extra_expenses ? `Expenses ${fmt(l.extra_expenses)} · ` : ''}${atts ? `${atts} file${atts === 1 ? '' : 's'} · ` : ''}${esc(l.notes || '')}
        </div>` : ''}
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px">
          <button type="button" class="btn sm" data-edit-log="${l.id}">Edit</button>
          <button type="button" class="btn sm danger" data-del-log="${l.id}">Delete</button>
        </div>
      </div>`;
  }).join('');

  list.querySelectorAll('[data-del-log]').forEach((btn) => {
    btn.addEventListener('click', () => deleteSiteLog(parseInt(btn.dataset.delLog, 10)));
  });
  list.querySelectorAll('[data-edit-log]').forEach((btn) => {
    btn.addEventListener('click', () => openSiteLogModal(logs.find((x) => x.id === parseInt(btn.dataset.editLog, 10))));
  });
}

export function openSiteLogModal(log = null) {
  if ($('sl-id')) $('sl-id').value = log?.id ? String(log.id) : '';
  if ($('site-modal-title')) $('site-modal-title').textContent = log ? 'Edit Site Entry' : 'Daily Site Entry';
  if ($('sl-date')) $('sl-date').value = log?.log_date || todayISO();
  if ($('sl-eng')) $('sl-eng').value = log?.engineer || '';
  if ($('sl-reporter')) $('sl-reporter').value = log?.reporter || '';
  if ($('sl-from')) $('sl-from').value = log?.time_from || '';
  if ($('sl-to')) $('sl-to').value = log?.time_to || '';
  if ($('sl-hours')) $('sl-hours').value = log?.hours_worked != null ? String(log.hours_worked) : '';
  if ($('sl-sk')) $('sl-sk').value = log ? String(log.workers_skilled || 0) : '';
  if ($('sl-usk')) $('sl-usk').value = log ? String(log.workers_unskilled || 0) : '';
  if ($('sl-workforce')) $('sl-workforce').value = log?.workforce_notes || '';
  if ($('sl-mat')) $('sl-mat').value = (log?.materials || []).length ? '' : (log?.material_used || '');
  if ($('sl-work')) $('sl-work').value = log?.work_done || '';
  if ($('sl-exp')) $('sl-exp').value = log?.extra_expenses ? String(log.extra_expenses) : '';
  if ($('sl-exp-notes')) $('sl-exp-notes').value = log?.expense_notes || '';
  if ($('sl-notes')) $('sl-notes').value = log?.notes || '';
  if ($('sl-progress')) $('sl-progress').value = '';
  if ($('sl-files')) $('sl-files').value = '';
  if ($('sl-proj') && log?.project_id) $('sl-proj').value = String(log.project_id);
  const mats = log?.materials?.length ? log.materials : [{}];
  if ($('sl-mat-rows')) {
    $('sl-mat-rows').innerHTML = mats.map(matRowHtml).join('');
    bindMatRows();
  }
  renderExistingFiles(log);
  openModal('site-modal');
}

export async function submitSiteLog() {
  const id = parseInt($('sl-id')?.value, 10);
  const progressRaw = ($('sl-progress')?.value || '').trim();
  const materials = collectMaterials();
  const d = {
    project_id: parseInt($('sl-proj')?.value, 10),
    log_date: $('sl-date')?.value,
    engineer: ($('sl-eng')?.value || '').trim(),
    reporter: ($('sl-reporter')?.value || '').trim() || null,
    time_from: $('sl-from')?.value || null,
    time_to: $('sl-to')?.value || null,
    hours_worked: parseFloat($('sl-hours')?.value) || null,
    workers_skilled: parseInt($('sl-sk')?.value, 10) || 0,
    workers_unskilled: parseInt($('sl-usk')?.value, 10) || 0,
    workforce_notes: ($('sl-workforce')?.value || '').trim() || null,
    material_used: ($('sl-mat')?.value || '').trim() || null,
    materials,
    work_done: ($('sl-work')?.value || '').trim(),
    extra_expenses: parseInt($('sl-exp')?.value, 10) || 0,
    expense_notes: ($('sl-exp-notes')?.value || '').trim() || null,
    notes: ($('sl-notes')?.value || '').trim() || null,
  };
  if (progressRaw !== '') d.current_progress = parseInt(progressRaw, 10);
  if (!d.project_id || !d.log_date || !d.engineer || !d.work_done) {
    toast('Project, date, engineer and work done are required.', 'error');
    return;
  }
  try {
    const saved = id
      ? await api(`/api/site-logs/${id}`, { method: 'PUT', body: JSON.stringify(d) })
      : await api('/api/site-logs', { method: 'POST', body: JSON.stringify(d) });
    const files = $('sl-files')?.files;
    if (files && files.length && saved?.id) {
      const form = new FormData();
      [...files].forEach((f) => form.append('files', f));
      await apiUpload(`/api/site-logs/${saved.id}/attachments`, form);
    }
    closeModal('site-modal');
    toast(id ? 'Site log updated' : 'Site log saved');
    if (progressRaw !== '') {
      try { await refreshProjectSelects(); } catch { /* ok */ }
    }
    await loadSite();
  } catch { /* toasted */ }
}

async function deleteSiteLog(id) {
  if (!await askConfirm('Delete this site log?', { title: 'Delete site log', confirmLabel: 'Delete', danger: true })) return;
  try {
    await api(`/api/site-logs/${id}`, { method: 'DELETE' });
    toast('Site log deleted');
    await loadSite();
  } catch { /* toasted */ }
}

export function initSiteEvents() {
  $('btn-site-log')?.addEventListener('click', () => openSiteLogModal());
  $('btn-save-site-log')?.addEventListener('click', submitSiteLog);
  $('site-f-proj')?.addEventListener('change', loadSite);
  $('site-from')?.addEventListener('change', loadSite);
  $('site-to')?.addEventListener('change', loadSite);
  $('sl-add-mat')?.addEventListener('click', () => {
    $('sl-mat-rows')?.insertAdjacentHTML('beforeend', matRowHtml());
    bindMatRows();
  });
}
