import { $, loadingHtml } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort } from '../format.js';
import { closeModal, openModal } from '../modal.js';
import { projectFilterQuery } from '../project-filter.js';

export async function loadSite() {
  const logs = await api(`/api/site-logs${projectFilterQuery()}`);
  $('site-workers').textContent = logs.length
    ? (logs[0].workers_skilled || 0) + (logs[0].workers_unskilled || 0)
    : 0;

  $('site-logs-list').innerHTML = logs.length
    ? logs.map((l) => `
      <div class="site-log">
        <div style="display:flex;justify-content:space-between;margin-bottom:8px">
          <span style="font-weight:800;font-size:13px">${l.project_name || 'Project'} — ${(l.work_done || '').substring(0, 50)}</span>
          <span style="font-size:11px;color:var(--g400)">${l.log_date} &nbsp;|&nbsp; ${l.engineer || '—'}</span>
        </div>
        <div class="g3" style="font-size:11.5px">
          <div><span style="color:var(--g400);font-weight:700">LABOR: </span>${l.workers_skilled || 0} skilled + ${l.workers_unskilled || 0} unskilled</div>
          <div><span style="color:var(--g400);font-weight:700">MATERIAL: </span>${l.material_used || '—'}</div>
          <div><span style="color:var(--g400);font-weight:700">WORK: </span>${l.work_done || '—'}</div>
        </div>
      </div>`).join('')
    : '<div class="loading" style="padding:24px">No site logs yet — module coming soon</div>';
}

export function openSiteLogModal() {
  $('sl-date').value = new Date().toISOString().split('T')[0];
  openModal('site-modal');
}

export async function submitSiteLog() {
  const d = {
    project_id: $('sl-proj').value,
    log_date: $('sl-date').value,
    engineer: $('sl-eng').value,
    workers_skilled: parseInt($('sl-sk').value, 10) || 0,
    workers_unskilled: parseInt($('sl-usk').value, 10) || 0,
    material_used: $('sl-mat').value,
    work_done: $('sl-work').value,
  };
  if (!d.engineer || !d.work_done) {
    toast('Fill all fields', 'error');
    return;
  }
  await api('/api/site-logs', { method: 'POST', body: JSON.stringify(d) });
  closeModal('site-modal');
  toast('✅ Site log saved!');
  loadSite();
}

export async function loadAccounts() {
  const d = await api('/api/ledger');
  $('gl-rev').textContent = fmtShort(d.revenue);
  $('gl-exp').textContent = fmtShort(d.expenses);
  $('gl-profit').textContent = fmtShort(d.profit);
  $('gl-entries').innerHTML = d.entries.length
    ? d.entries.map((e) => `
      <div class="gl-row">
        <span>${e.entry_date}</span><span>${e.narration}</span>
        <span>${e.debit ? `<span class="dr">${fmt(e.debit)}</span>` : '—'}</span>
        <span>${e.credit ? `<span class="cr">${fmt(e.credit)}</span>` : '—'}</span>
        <span style="font-family:monospace;font-size:11px">${fmt(e.balance)}</span>
      </div>`).join('')
    : '<div class="loading" style="padding:24px">No ledger entries — module coming soon</div>';
}

export function openLedgerModal() {
  $('le-date').value = new Date().toISOString().split('T')[0];
  openModal('ledger-modal');
}

export async function submitLedger() {
  const nar = $('le-nar').value.trim();
  if (!nar) {
    toast('Narration required', 'error');
    return;
  }
  await api('/api/ledger', {
    method: 'POST',
    body: JSON.stringify({
      entry_date: $('le-date').value,
      narration: nar,
      debit: parseInt($('le-dr').value, 10) || 0,
      credit: parseInt($('le-cr').value, 10) || 0,
      account_type: $('le-type').value,
    }),
  });
  closeModal('ledger-modal');
  toast('✅ Journal entry posted!');
  loadAccounts();
}

export function initAccountsEvents() {
  $('btn-site-log')?.addEventListener('click', openSiteLogModal);
  $('btn-save-site-log')?.addEventListener('click', submitSiteLog);
  $('btn-ledger-entry')?.addEventListener('click', openLedgerModal);
  $('btn-save-ledger')?.addEventListener('click', submitLedger);
}
