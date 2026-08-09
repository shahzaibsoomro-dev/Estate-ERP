import { $, esc, loadingHtml } from '../dom.js';
import { api, toast } from '../api.js';
import { closeModal, openModal } from '../modal.js';
import { state } from '../state.js';
import { activeProjectIds, projectFilterQuery } from '../project-filter.js';

function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export async function loadSite() {
  const list = $('site-logs-list');
  if (list) list.innerHTML = loadingHtml('Loading logs…');
  let logs = [];
  try {
    logs = await api(`/api/site-logs${projectFilterQuery()}`);
  } catch {
    if (list) list.innerHTML = '<div class="loading" style="padding:24px">Could not load site logs</div>';
    return;
  }

  const ids = activeProjectIds();
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
  list.innerHTML = logs.length
    ? logs.map((l) => `
      <div class="site-log">
        <div style="display:flex;justify-content:space-between;gap:12px;margin-bottom:8px;align-items:flex-start">
          <span style="font-weight:800;font-size:13px">${esc(l.project_name || 'Project')} — ${esc((l.work_done || '').substring(0, 80))}</span>
          <span style="font-size:11px;color:var(--g400);white-space:nowrap">${esc(l.log_date)} &nbsp;|&nbsp; ${esc(l.engineer || '—')}</span>
        </div>
        <div class="g3" style="font-size:11.5px">
          <div><span style="color:var(--g400);font-weight:700">LABOR: </span>${l.workers_skilled || 0} skilled + ${l.workers_unskilled || 0} unskilled</div>
          <div><span style="color:var(--g400);font-weight:700">MATERIAL: </span>${esc(l.material_used || '—')}</div>
          <div><span style="color:var(--g400);font-weight:700">WORK: </span>${esc(l.work_done || '—')}</div>
        </div>
        <div style="display:flex;justify-content:flex-end;margin-top:10px">
          <button type="button" class="btn sm danger" data-del-log="${l.id}">Delete</button>
        </div>
      </div>`).join('')
    : '<div class="loading" style="padding:24px">No site logs yet</div>';

  list.querySelectorAll('[data-del-log]').forEach((btn) => {
    btn.addEventListener('click', () => deleteSiteLog(parseInt(btn.dataset.delLog, 10)));
  });
}

export function openSiteLogModal() {
  if ($('sl-date')) $('sl-date').value = todayISO();
  if ($('sl-eng')) $('sl-eng').value = '';
  if ($('sl-sk')) $('sl-sk').value = '';
  if ($('sl-usk')) $('sl-usk').value = '';
  if ($('sl-mat')) $('sl-mat').value = '';
  if ($('sl-work')) $('sl-work').value = '';
  openModal('site-modal');
}

export async function submitSiteLog() {
  const d = {
    project_id: parseInt($('sl-proj')?.value, 10),
    log_date: $('sl-date')?.value,
    engineer: ($('sl-eng')?.value || '').trim(),
    workers_skilled: parseInt($('sl-sk')?.value, 10) || 0,
    workers_unskilled: parseInt($('sl-usk')?.value, 10) || 0,
    material_used: ($('sl-mat')?.value || '').trim() || null,
    work_done: ($('sl-work')?.value || '').trim(),
  };
  if (!d.project_id || !d.log_date || !d.engineer || !d.work_done) {
    toast('Project, date, engineer and work done are required.', 'error');
    return;
  }
  try {
    await api('/api/site-logs', { method: 'POST', body: JSON.stringify(d) });
    closeModal('site-modal');
    toast('Site log saved');
    await loadSite();
  } catch { /* toasted */ }
}

async function deleteSiteLog(id) {
  if (!confirm('Delete this site log?')) return;
  try {
    await api(`/api/site-logs/${id}`, { method: 'DELETE' });
    toast('Site log deleted');
    await loadSite();
  } catch { /* toasted */ }
}

export function initSiteEvents() {
  $('btn-site-log')?.addEventListener('click', openSiteLogModal);
  $('btn-save-site-log')?.addEventListener('click', submitSiteLog);
}
