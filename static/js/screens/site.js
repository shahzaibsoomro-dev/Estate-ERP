import { $, esc, loadingHtml } from '../dom.js';
import { api, toast } from '../api.js';
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
    return `${head}
      <div class="site-log">
        <div style="display:flex;justify-content:space-between;gap:12px;margin-bottom:8px;align-items:flex-start">
          <span style="font-weight:800;font-size:13px">${esc(l.project_name || 'Project')} — ${esc((l.work_done || '').substring(0, 80))}</span>
          <span style="font-size:11px;color:var(--g400);white-space:nowrap">${esc(l.engineer || '—')}</span>
        </div>
        <div class="g3" style="font-size:11.5px">
          <div><span style="color:var(--g400);font-weight:700">LABOR: </span>${l.workers_skilled || 0} skilled + ${l.workers_unskilled || 0} unskilled</div>
          <div><span style="color:var(--g400);font-weight:700">MATERIAL: </span>${esc(l.material_used || '—')}</div>
          <div><span style="color:var(--g400);font-weight:700">WORK: </span>${esc(l.work_done || '—')}</div>
        </div>
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
  if ($('sl-sk')) $('sl-sk').value = log ? String(log.workers_skilled || 0) : '';
  if ($('sl-usk')) $('sl-usk').value = log ? String(log.workers_unskilled || 0) : '';
  if ($('sl-mat')) $('sl-mat').value = log?.material_used || '';
  if ($('sl-work')) $('sl-work').value = log?.work_done || '';
  if ($('sl-progress')) $('sl-progress').value = '';
  if ($('sl-proj') && log?.project_id) $('sl-proj').value = String(log.project_id);
  openModal('site-modal');
}

export async function submitSiteLog() {
  const id = parseInt($('sl-id')?.value, 10);
  const progressRaw = ($('sl-progress')?.value || '').trim();
  const d = {
    project_id: parseInt($('sl-proj')?.value, 10),
    log_date: $('sl-date')?.value,
    engineer: ($('sl-eng')?.value || '').trim(),
    workers_skilled: parseInt($('sl-sk')?.value, 10) || 0,
    workers_unskilled: parseInt($('sl-usk')?.value, 10) || 0,
    material_used: ($('sl-mat')?.value || '').trim() || null,
    work_done: ($('sl-work')?.value || '').trim(),
  };
  if (progressRaw !== '') d.current_progress = parseInt(progressRaw, 10);
  if (!d.project_id || !d.log_date || !d.engineer || !d.work_done) {
    toast('Project, date, engineer and work done are required.', 'error');
    return;
  }
  try {
    if (id) {
      await api(`/api/site-logs/${id}`, { method: 'PUT', body: JSON.stringify(d) });
    } else {
      await api('/api/site-logs', { method: 'POST', body: JSON.stringify(d) });
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
}
