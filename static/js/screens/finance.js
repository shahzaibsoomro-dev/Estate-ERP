import { $, esc } from '../dom.js';
import { api, toast } from '../api.js';
import { fmt, fmtShort } from '../format.js';
import { closeModal, openModal } from '../modal.js';
import { askConfirm } from '../dialog.js';
import { state } from '../state.js';
import { projectFilterQuery, filterLabelShort } from '../project-filter.js';

let lastBooks = null;

function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export async function loadAccounts() {
  const d = await api(`/api/ledger${projectFilterQuery()}`);
  lastBooks = d;
  if ($('gl-current')) $('gl-current').textContent = fmtShort(d.current ?? 0);
  if ($('gl-cash')) $('gl-cash').textContent = fmtShort(d.cash ?? 0);
  if ($('gl-bank')) $('gl-bank').textContent = fmtShort(d.bank ?? 0);
  if ($('gl-profit')) $('gl-profit').textContent = fmtShort(d.net ?? 0);
  if ($('gl-subtitle')) {
    const scope = filterLabelShort();
    $('gl-subtitle').textContent = d.filtered
      ? `Cash for ${scope}. Company-wide opening cash is hidden in this filter.`
      : 'Company-wide cash and every project — collections, vendors, agents, investors, partners';
  }
  const by = $('gl-by-project');
  if (by) {
    const rows = d.by_project || [];
    by.innerHTML = (!d.filtered && rows.length > 1)
      ? `<div class="card" style="padding:10px 14px"><div style="font-size:11px;font-weight:800;color:var(--g400);margin-bottom:8px">BY PROJECT</div>
         <div class="g3">${rows.map((p) => `
           <div class="sum-row"><span class="sum-lbl">${esc(p.project_name)}</span>
           <span class="sum-val">${fmtShort(p.net)}</span></div>`).join('')}</div></div>`
      : '';
  }
  const rows = d.entries || [];
  $('gl-entries').innerHTML = rows.length
    ? rows.map((e) => `
      <div class="gl-row">
        <span>${esc(e.entry_date || '—')}</span>
        <span>${esc(e.narration || '—')}</span>
        <span style="color:var(--g500)">${esc(e.project_name || '—')}</span>
        <span>${e.inflow ? `<span class="cr">${fmt(e.inflow)}</span>` : '—'}</span>
        <span>${e.outflow ? `<span class="dr">${fmt(e.outflow)}</span>` : '—'}</span>
        <span style="font-family:monospace;font-size:11px;display:flex;align-items:center;justify-content:space-between;gap:8px">
          ${fmt(e.balance)}
          ${e.id ? `<button type="button" class="btn sm danger" data-del-le="${e.id}">✕</button>` : ''}
        </span>
      </div>`).join('')
    : '<div class="loading" style="padding:24px">No cash movements in this view</div>';

  $('gl-entries').querySelectorAll('[data-del-le]').forEach((btn) => {
    btn.addEventListener('click', () => deleteLedgerEntry(parseInt(btn.dataset.delLe, 10)));
  });
}

async function deleteLedgerEntry(id) {
  if (!await askConfirm('Delete this manual entry?', { title: 'Delete entry', confirmLabel: 'Delete', danger: true })) return;
  try {
    await api(`/api/ledger/${id}`, { method: 'DELETE' });
    toast('Entry deleted');
    await loadAccounts();
  } catch { /* toasted */ }
}

export function openLedgerModal() {
  if ($('le-date')) $('le-date').value = todayISO();
  if ($('le-dir')) $('le-dir').value = 'out';
  if ($('le-amount')) $('le-amount').value = '';
  if ($('le-nar')) $('le-nar').value = '';
  if ($('le-type')) $('le-type').value = 'General';
  if ($('le-method')) $('le-method').value = 'Bank';
  const proj = $('le-project');
  if (proj) {
    proj.innerHTML = `<option value="">Company-wide</option>${(state.projects || []).map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join('')}`;
  }
  openModal('ledger-modal');
}

export async function submitLedger() {
  const nar = ($('le-nar')?.value || '').trim();
  const amount = parseInt($('le-amount')?.value, 10);
  if (!nar || !amount) {
    toast('Narration and amount are required.', 'error');
    return;
  }
  try {
    await api('/api/ledger', {
      method: 'POST',
      body: JSON.stringify({
        entry_date: $('le-date').value,
        narration: nar,
        amount,
        direction: $('le-dir')?.value || 'out',
        category: $('le-type')?.value || 'General',
        payment_method: $('le-method')?.value || 'Bank',
        project_id: $('le-project')?.value ? Number($('le-project').value) : null,
      }),
    });
    closeModal('ledger-modal');
    toast('Entry saved');
    await loadAccounts();
  } catch { /* toasted */ }
}

function openBalanceModal() {
  const d = lastBooks || {};
  $('bal-cash').value = String(d.cash ?? 0);
  $('bal-bank').value = String(d.bank ?? 0);
  $('bal-date').value = todayISO();
  $('bal-reason').value = '';
  $('bal-modal-title').textContent = d.has_opening ? 'Adjust current balance' : 'Set opening balance';
  $('bal-summary').innerHTML = `
    <div class="sum-row"><span class="sum-lbl">Books now · cash</span><span class="sum-val">${fmt(d.cash || 0)}</span></div>
    <div class="sum-row"><span class="sum-lbl">Books now · bank</span><span class="sum-val">${fmt(d.bank || 0)}</span></div>
    <div class="sum-row"><span class="sum-lbl">Current total</span><span class="sum-val">${fmt(d.current || 0)}</span></div>
    <div style="font-size:11px;color:var(--g400);margin-top:8px">${d.has_opening
      ? 'Saving posts the difference as an adjustment.'
      : 'No opening has been recorded yet. Saving writes the opening cash and bank.'}</div>`;
  openModal('balance-modal');
}

async function submitBalance() {
  const cash = parseInt($('bal-cash').value, 10);
  const bank = parseInt($('bal-bank').value, 10);
  if (!Number.isFinite(cash) || !Number.isFinite(bank) || cash < 0 || bank < 0) {
    toast('Enter cash and bank as 0 or more.', 'error');
    return;
  }
  try {
    await api('/api/ledger/balance', {
      method: 'PUT',
      body: JSON.stringify({
        cash,
        bank,
        as_of: $('bal-date').value || todayISO(),
        reason: ($('bal-reason').value || '').trim() || null,
      }),
    });
    closeModal('balance-modal');
    toast('Balance saved');
    await loadAccounts();
  } catch { /* toasted */ }
}

export function initAccountsEvents() {
  $('btn-ledger-entry')?.addEventListener('click', openLedgerModal);
  $('btn-save-ledger')?.addEventListener('click', submitLedger);
  $('btn-set-balance')?.addEventListener('click', openBalanceModal);
  $('btn-save-balance')?.addEventListener('click', submitBalance);
}
